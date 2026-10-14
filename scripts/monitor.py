#!/usr/bin/env python3
"""
Pharos On-Chain Event & Log Monitor
===================================
A real-time, continuous event/log monitor for the Pharos blockchain.
Supports both the Pharos Hosted Chain MCP (Streamable HTTP) and direct JSON-RPC.

Adheres strictly to the Pharos Skill Engine specification and Pharos Agent Arena
Task 2 requirements:
  - Uses Chain MCP log queries filtered by contract address and event signature.
  - Runs continuously (polling block-by-block) and reports only new events with no duplicates.
  - Decodes each event into readable fields (from, to, amount, tx hash, block number).
  - Supports historical replay and bounded test execution.
  - Zero cost ($0), strictly read-only, zero dependencies beyond Python standard library.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable, Deque, Dict, Iterator, List, Optional, Set, Tuple

# Ensure local script directory is in python path to import inspector
CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from inspector import (
    DEFAULT_TIMEOUT,
    ETH_ADDRESS_REGEX,
    ETH_TX_HASH_REGEX,
    HOSTED_MCP_URL,
    USER_AGENT,
    InspectorError,
    NetworkError,
    PharosInspector,
    ValidationError,
    decode_abi_uint256,
)

# Standard EVM Event Topic 0 Hashes (Keccak-256)
STANDARD_EVENT_TOPICS: Dict[str, Dict[str, Any]] = {
    "Transfer": {
        "signature": "Transfer(address,address,uint256)",
        "topic0": "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
        "description": "ERC-20 / ERC-721 Token Transfer"
    },
    "Approval": {
        "signature": "Approval(address,address,uint256)",
        "topic0": "0x8c5be1e5ebec7d5bd14f71427d1e84f3dd0314c0f7b2291e5b200ac8c7c3b925",
        "description": "ERC-20 Token Approval"
    },
    "Deposit": {
        "signature": "Deposit(address,uint256)",
        "topic0": "0xe1fff362409666200f571d1b33db3744fc48f55ac529737f7aa9f740eac1ee3e",
        "description": "Wrapped Native Token Deposit"
    },
    "Withdrawal": {
        "signature": "Withdrawal(address,uint256)",
        "topic0": "0x7f68928815e1d297a71b269739ebf75c3d0abc18402fae8348b6bc1ec3ee5c3f",
        "description": "Wrapped Native Token Withdrawal"
    }
}

TOPIC_HASH_REGEX = re.compile(r"^0x[0-9a-fA-F]{64}$")
MAX_DEDUP_CACHE_SIZE = 50_000
MAX_MCP_BLOCK_WINDOW = 1000  # Upstream RPC and Chain MCP window limit


def extract_address_from_topic(topic_hex: str) -> str:
    """
    Extract a 20-byte EVM address from a 32-byte indexed topic word.
    Handles '0x' prefix and validates 40-character hexadecimal representation.
    """
    if not isinstance(topic_hex, str):
        raise ValidationError(f"Topic must be a string, got {type(topic_hex).__name__}")
    raw = topic_hex.lower()
    if raw.startswith("0x"):
        raw = raw[2:]
    if len(raw) != 64:
        raise ValidationError(f"Invalid 32-byte topic length: {len(raw)} characters (expected 64 hex chars).")
    # EVM indexed address occupies the last 20 bytes (40 hex characters)
    addr_hex = "0x" + raw[24:]
    if not ETH_ADDRESS_REGEX.match(addr_hex):
        raise ValidationError(f"Decoded topic does not match EVM address pattern: {addr_hex}")
    return addr_hex


def resolve_event_topic(event_input: str) -> Tuple[str, str]:
    """
    Resolve user event input into (event_name, topic0_hex).
    Accepts:
      - Short name: 'Transfer', 'Approval'
      - Exact signature: 'Transfer(address,address,uint256)'
      - Raw 32-byte hex hash: '0xddf252ad...'
    """
    name_clean = event_input.strip()
    # Check pre-known standard names
    for key, spec in STANDARD_EVENT_TOPICS.items():
        if name_clean.lower() == key.lower() or name_clean.lower() == spec["signature"].lower():
            return key, spec["topic0"].lower()

    # Check raw hex topic
    if TOPIC_HASH_REGEX.match(name_clean):
        # Reverse lookup if known
        for key, spec in STANDARD_EVENT_TOPICS.items():
            if spec["topic0"].lower() == name_clean.lower():
                return key, spec["topic0"].lower()
        return "CustomEvent", name_clean.lower()

    # If user passed custom signature like Foo(address,uint256), hash it with keccak or reject
    raise ValidationError(
        f"Unsupported event signature '{event_input}'. "
        f"Supported names: {list(STANDARD_EVENT_TOPICS.keys())} or raw 32-byte 0x-prefixed hash."
    )


class PharosEventMonitor:
    """
    Continuous event monitoring engine for Pharos contracts and events.
    Guarantees strict deduplication, safe paging windowing, and rich decoding.
    """

    def __init__(
        self,
        inspector: Optional[PharosInspector] = None,
        max_cache_size: int = MAX_DEDUP_CACHE_SIZE
    ):
        self.inspector = inspector or PharosInspector()
        self.max_cache_size = max_cache_size
        self._seen_event_keys: Set[Tuple[str, int]] = set()
        self._seen_fifo: Deque[Tuple[str, int]] = collections.deque()
        self.total_events_seen = 0
        self.total_events_reported = 0

    def reset_dedup_cache(self) -> None:
        """Clear the deduplication cache."""
        self._seen_event_keys.clear()
        self._seen_fifo.clear()
        self.total_events_seen = 0
        self.total_events_reported = 0

    def is_duplicate(self, tx_hash: str, log_index: int) -> bool:
        """Check if an event key (tx_hash, log_index) has already been processed."""
        key = (tx_hash.lower(), int(log_index))
        return key in self._seen_event_keys

    def record_event(self, tx_hash: str, log_index: int) -> None:
        """Record an event key into the bounded FIFO deduplication cache."""
        key = (tx_hash.lower(), int(log_index))
        if key in self._seen_event_keys:
            return
        if len(self._seen_fifo) >= self.max_cache_size:
            oldest = self._seen_fifo.popleft()
            self._seen_event_keys.discard(oldest)
        self._seen_fifo.append(key)
        self._seen_event_keys.add(key)
        self.total_events_reported += 1

    def decode_log(
        self,
        raw_log: Dict[str, Any],
        token_decimals: int = 18,
        token_symbol: str = "TOKEN",
        explorer_base_url: str = "https://www.pharosscan.xyz"
    ) -> Dict[str, Any]:
        """
        Decode a raw EVM log dictionary into clean, human-readable fields.
        Supports standard ERC-20 Transfer events with fallback for generic events.
        """
        contract_addr = raw_log.get("address", "").lower()
        block_raw = raw_log.get("blockNumber", "0")
        block_num = int(block_raw, 16) if isinstance(block_raw, str) and block_raw.startswith("0x") else int(block_raw)

        tx_hash = raw_log.get("transactionHash", "")
        log_idx_raw = raw_log.get("logIndex", "0")
        log_idx = int(log_idx_raw, 16) if isinstance(log_idx_raw, str) and log_idx_raw.startswith("0x") else int(log_idx_raw)

        topics: List[str] = raw_log.get("topics", [])
        data_hex: str = raw_log.get("data", "0x")

        topic0 = topics[0].lower() if topics else ""

        # Identify token metadata from registry if available
        matched_symbol = token_symbol
        matched_decimals = token_decimals
        for net_tokens in self.inspector.tokens.values():
            for t in net_tokens:
                if t["address"].lower() == contract_addr:
                    matched_symbol = t.get("symbol", token_symbol)
                    matched_decimals = t.get("decimals", token_decimals)
                    break

        decoded: Dict[str, Any] = {
            "blockNumber": block_num,
            "transactionHash": tx_hash,
            "logIndex": log_idx,
            "contractAddress": contract_addr,
            "topic0": topic0,
            "rawLog": raw_log,
            "explorerUrl": f"{explorer_base_url.rstrip('/')}/tx/{tx_hash}" if tx_hash else ""
        }

        # ERC-20 / ERC-721 Transfer(address indexed from, address indexed to, uint256 value)
        if topic0 == STANDARD_EVENT_TOPICS["Transfer"]["topic0"].lower():
            decoded["eventName"] = "Transfer"
            from_addr = extract_address_from_topic(topics[1]) if len(topics) > 1 else "Unknown"
            to_addr = extract_address_from_topic(topics[2]) if len(topics) > 2 else "Unknown"
            
            raw_amount = decode_abi_uint256(data_hex) if data_hex and data_hex != "0x" else 0
            formatted_amount = self.inspector.format_token_amount(raw_amount, matched_decimals)

            decoded["from"] = from_addr
            decoded["to"] = to_addr
            decoded["rawAmount"] = str(raw_amount)
            decoded["formattedAmount"] = formatted_amount
            decoded["symbol"] = matched_symbol
            decoded["decimals"] = matched_decimals
            decoded["summary"] = f"Transfer {formatted_amount} {matched_symbol} from {from_addr} to {to_addr}"

        # ERC-20 Approval(address indexed owner, address indexed spender, uint256 value)
        elif topic0 == STANDARD_EVENT_TOPICS["Approval"]["topic0"].lower():
            decoded["eventName"] = "Approval"
            owner = extract_address_from_topic(topics[1]) if len(topics) > 1 else "Unknown"
            spender = extract_address_from_topic(topics[2]) if len(topics) > 2 else "Unknown"
            raw_amount = decode_abi_uint256(data_hex) if data_hex and data_hex != "0x" else 0
            formatted_amount = self.inspector.format_token_amount(raw_amount, matched_decimals)

            decoded["owner"] = owner
            decoded["spender"] = spender
            decoded["rawAmount"] = str(raw_amount)
            decoded["formattedAmount"] = formatted_amount
            decoded["symbol"] = matched_symbol
            decoded["summary"] = f"Approval of {formatted_amount} {matched_symbol} by {owner} for {spender}"

        # Generic / Custom Event
        else:
            decoded["eventName"] = "CustomEvent"
            decoded["topics"] = topics
            decoded["data"] = data_hex
            decoded["summary"] = f"Event {topic0[:10]}... at contract {contract_addr}"

        return decoded

    def fetch_logs_window(
        self,
        from_block: int,
        to_block: int,
        contract_address: Optional[str] = None,
        topic0: Optional[str] = None,
        network: str = "mainnet",
        use_mcp: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Query logs for a single window of at most 1,000 blocks via Chain MCP or direct JSON-RPC.
        """
        if to_block < from_block:
            raise ValidationError(f"toBlock ({to_block}) cannot be less than fromBlock ({from_block})")
        
        span = to_block - from_block + 1
        if span > MAX_MCP_BLOCK_WINDOW:
            raise ValidationError(
                f"Window size {span} exceeds the maximum limit of {MAX_MCP_BLOCK_WINDOW} blocks."
            )

        if use_mcp:
            args: Dict[str, Any] = {
                "fromBlock": from_block,
                "toBlock": to_block
            }
            if contract_address:
                args["address"] = contract_address
            if topic0:
                args["topics"] = [topic0]

            mcp_res = self.inspector.query_hosted_mcp("get_logs", args)
            content = mcp_res.get("content", [{}])[0].get("text", "[]")
            try:
                logs_data = json.loads(content)
                if isinstance(logs_data, list):
                    return logs_data
                elif isinstance(logs_data, dict) and "error" in logs_data:
                    raise NetworkError(f"Chain MCP get_logs error: {logs_data['error']}")
                return []
            except json.JSONDecodeError as e:
                raise NetworkError(f"Failed to decode MCP get_logs response: {content[:200]}") from e
        else:
            # Direct JSON-RPC eth_getLogs
            filter_obj: Dict[str, Any] = {
                "fromBlock": hex(from_block),
                "toBlock": hex(to_block)
            }
            if contract_address:
                filter_obj["address"] = contract_address
            if topic0:
                filter_obj["topics"] = [topic0]

            logs_res = self.inspector.rpc_call("eth_getLogs", [filter_obj], network=network)
            return logs_res if isinstance(logs_res, list) else []

    def get_logs_paged(
        self,
        from_block: int,
        to_block: int,
        contract_address: Optional[str] = None,
        topic0: Optional[str] = None,
        network: str = "mainnet",
        use_mcp: bool = True,
        chunk_size: int = MAX_MCP_BLOCK_WINDOW
    ) -> Iterator[Dict[str, Any]]:
        """
        Iterate over arbitrary historical block ranges by chunking queries into compliant sub-windows.
        """
        chunk = min(chunk_size, MAX_MCP_BLOCK_WINDOW)
        curr = from_block
        while curr <= to_block:
            sub_to = min(curr + chunk - 1, to_block)
            logs = self.fetch_logs_window(
                from_block=curr,
                to_block=sub_to,
                contract_address=contract_address,
                topic0=topic0,
                network=network,
                use_mcp=use_mcp
            )
            for log in logs:
                yield log
            curr = sub_to + 1

    def monitor_stream(
        self,
        contract_address: Optional[str] = None,
        event_signature: str = "Transfer",
        start_block: Optional[int] = None,
        to_block: Optional[int] = None,
        poll_interval: float = 3.0,
        max_events: Optional[int] = None,
        network: str = "mainnet",
        use_mcp: bool = True,
        chunk_size: int = MAX_MCP_BLOCK_WINDOW,
        callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> Iterator[Dict[str, Any]]:
        """
        Run continuous or bounded monitoring.
        Yields decoded events, guaranteeing zero duplicates.
        """
        event_name, topic0 = resolve_event_topic(event_signature)
        valid_contract = self.inspector.validate_address(contract_address) if contract_address else None
        net_cfg = self.inspector.get_network_config(network)
        explorer_url = net_cfg.get("explorerUrl", "https://www.pharosscan.xyz")

        # Determine starting block
        if start_block is None:
            latest = self.inspector.get_block_number(network=network, use_mcp=use_mcp)
            curr_cursor = max(0, latest - 10)  # Scan recent 10 blocks by default
        else:
            curr_cursor = start_block

        reported_count = 0
        is_bounded = (to_block is not None)

        try:
            while True:
                # 1. Fetch current network block height
                latest_chain_block = self.inspector.get_block_number(network=network, use_mcp=use_mcp)

                # In bounded mode, stop if cursor exceeded target
                if is_bounded and to_block is not None and curr_cursor > to_block:
                    break

                target_to = min(curr_cursor + chunk_size - 1, latest_chain_block)
                if is_bounded and to_block is not None:
                    target_to = min(target_to, to_block)

                if curr_cursor <= target_to:
                    # Query log chunk
                    logs = self.fetch_logs_window(
                        from_block=curr_cursor,
                        to_block=target_to,
                        contract_address=valid_contract,
                        topic0=topic0,
                        network=network,
                        use_mcp=use_mcp
                    )

                    for raw_log in logs:
                        self.total_events_seen += 1
                        tx_hash = raw_log.get("transactionHash", "")
                        raw_idx = raw_log.get("logIndex", "0")
                        log_idx = int(raw_idx, 16) if isinstance(raw_idx, str) and raw_idx.startswith("0x") else int(raw_idx)

                        # Deduplication check
                        if self.is_duplicate(tx_hash, log_idx):
                            continue

                        # Mark as seen
                        self.record_event(tx_hash, log_idx)
                        decoded = self.decode_log(
                            raw_log=raw_log,
                            explorer_base_url=explorer_url
                        )

                        if callback:
                            callback(decoded)
                        yield decoded

                        reported_count += 1
                        if max_events and reported_count >= max_events:
                            return

                    curr_cursor = target_to + 1

                # If caught up to the tip in continuous mode, wait before polling next block
                if curr_cursor > latest_chain_block:
                    if is_bounded:
                        break
                    time.sleep(poll_interval)

        except KeyboardInterrupt:
            # Graceful termination handled by caller or CLI loop
            pass


def print_human_event(event: Dict[str, Any]) -> None:
    """Print an event in clean, highlighted human-readable format."""
    block = event.get("blockNumber")
    name = event.get("eventName", "Event")
    tx_hash = event.get("transactionHash", "")
    short_tx = f"{tx_hash[:10]}...{tx_hash[-8:]}" if len(tx_hash) > 20 else tx_hash

    if name == "Transfer":
        from_a = event.get("from", "")
        to_a = event.get("to", "")
        short_from = f"{from_a[:8]}...{from_a[-6:]}" if len(from_a) > 16 else from_a
        short_to = f"{to_a[:8]}...{to_a[-6:]}" if len(to_a) > 16 else to_a
        amount = event.get("formattedAmount", "0")
        symbol = event.get("symbol", "TOKEN")

        print(
            f" [Block #{block:,}] TRANSFER: {amount:>12} {symbol:<5} | "
            f"{short_from} -> {short_to} | Tx: {short_tx}"
        )
    else:
        print(
            f" [Block #{block:,}] {name}: Contract {event.get('contractAddress')} | "
            f"Tx: {short_tx} | {event.get('summary')}"
        )


def cli_main() -> None:
    parser = argparse.ArgumentParser(
        description="Pharos On-Chain Event & Log Monitor (Task 2 Compliance)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Monitor Pacific USDC Transfers via Pharos Chain MCP (Continuous live stream)
  python monitor.py --contract 0xc879c018db60520f4355c26ed1a6d572cdac1815

  # Historical replay: check last 50 blocks and stop after 5 events
  python monitor.py --contract 0xc879c018db60520f4355c26ed1a6d572cdac1815 --blocks 50 --max-events 5

  # Bounded block range with JSON output
  python monitor.py --from-block 20256400 --to-block 20256475 --json

  # Monitor Atlantic Testnet USDC using direct JSON-RPC fallback
  python monitor.py --network atlantic-testnet --rpc --contract 0xE0BE08c77f415F577A1B3A9aD7a1Df1479564ec8
        """
    )

    parser.add_argument(
        "--contract",
        dest="contract",
        default="0xc879c018db60520f4355c26ed1a6d572cdac1815",
        help="Target contract address to filter (default: Pacific USDC 0xc879c018db60520f4355c26ed1a6d572cdac1815)"
    )
    parser.add_argument(
        "--event",
        dest="event",
        default="Transfer",
        help="Event name or signature to watch (default: Transfer). Also supports raw 0x topic0."
    )
    parser.add_argument(
        "--network",
        dest="network",
        default="mainnet",
        choices=["mainnet", "atlantic-testnet"],
        help="Target Pharos network (default: mainnet)"
    )
    parser.add_argument(
        "--mcp",
        action="store_true",
        default=True,
        help="Query logs via Pharos Hosted Chain MCP (default: True)"
    )
    parser.add_argument(
        "--rpc",
        action="store_true",
        default=False,
        help="Force direct JSON-RPC instead of Chain MCP"
    )
    parser.add_argument(
        "--from-block",
        type=int,
        default=None,
        help="Starting block number for scanning (default: current block - 20)"
    )
    parser.add_argument(
        "--to-block",
        type=int,
        default=None,
        help="Ending block number for bounded scanning (if omitted, runs continuously)"
    )
    parser.add_argument(
        "--blocks",
        type=int,
        default=None,
        help="Scan the most recent N blocks from latest block height"
    )
    parser.add_argument(
        "--max-events",
        type=int,
        default=None,
        help="Stop monitor after processing N new events"
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=3.0,
        help="Polling delay in seconds between block checks (default: 3.0s)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as newline-delimited JSON objects"
    )

    args = parser.parse_args()

    # Determine query engine: use MCP unless --rpc explicitly specified
    use_mcp = not args.rpc

    inspector = PharosInspector()
    monitor = PharosEventMonitor(inspector=inspector)

    # Calculate starting block if --blocks passed
    start_b = args.from_block
    if args.blocks is not None:
        latest = inspector.get_block_number(network=args.network, use_mcp=use_mcp)
        start_b = max(0, latest - args.blocks)

    if not args.json:
        print("\n" + "=" * 70)
        print(" Pharos On-Chain Event & Log Monitor -- Task 2 Compliance")
        print("=" * 70)
        print(f" Target Network:     {args.network}")
        print(f" Query Engine:       {'Pharos Hosted Chain MCP' if use_mcp else 'Direct JSON-RPC'}")
        print(f" Contract Filter:    {args.contract}")
        print(f" Event Filter:       {args.event}")
        if start_b:
            print(f" Starting Block:     {start_b:,}")
        if args.to_block:
            print(f" Ending Block:       {args.to_block:,} (Bounded Replay)")
        else:
            print(" Polling Mode:       Continuous Block-by-Block (Press Ctrl+C to stop)")
        if args.max_events:
            print(f" Max Events Limit:   {args.max_events}")
        print("=" * 70 + "\n")

    event_count = 0
    try:
        for event in monitor.monitor_stream(
            contract_address=args.contract,
            event_signature=args.event,
            start_block=start_b,
            to_block=args.to_block,
            poll_interval=args.poll_interval,
            max_events=args.max_events,
            network=args.network,
            use_mcp=use_mcp
        ):
            event_count += 1
            if args.json:
                print(json.dumps(event))
            else:
                print_human_event(event)

        if not args.json:
            print(f"\n[Completed] Processed {event_count} events without duplicates.")

    except KeyboardInterrupt:
        if not args.json:
            print(f"\n[Terminated by user] Monitored {monitor.total_events_reported} total unique events.")
        sys.exit(0)
    except InspectorError as e:
        sys.stderr.write(f"\n[Monitor Error] {e}\n\n")
        sys.exit(1)
    except Exception as e:
        sys.stderr.write(f"\n[Unexpected Error] {e}\n\n")
        sys.exit(2)


if __name__ == "__main__":
    cli_main()

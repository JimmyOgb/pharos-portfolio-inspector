#!/usr/bin/env python3
"""
Pharos On-Chain Data & Portfolio Inspector
==========================================
A read-only, zero-cost CLI and agent utility for inspecting Pharos blockchain state.
Supports both direct JSON-RPC querying and Pharos Hosted Chain MCP (Streamable HTTP) integration.

Adheres strictly to the Pharos Skill Engine specification and Pharos Agent Arena Task 1 requirements.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Address format: 0x followed by exactly 40 hexadecimal characters
ETH_ADDRESS_REGEX = re.compile(r"^0x[0-9a-fA-F]{40}$")
# Transaction hash: 0x followed by exactly 64 hexadecimal characters
ETH_TX_HASH_REGEX = re.compile(r"^0x[0-9a-fA-F]{64}$")

DEFAULT_TIMEOUT = 12.0
USER_AGENT = "PharosPortfolioInspector/1.0 (+https://github.com/JimmyOgb)"
HOSTED_MCP_URL = "https://mcp.pharos.xyz/mcp"

# Standard ERC-20 4-byte function selectors
ERC20_NAME_SELECTOR = "0x06fdde03"
ERC20_SYMBOL_SELECTOR = "0x95d89b41"
ERC20_DECIMALS_SELECTOR = "0x313ce567"
ERC20_TOTAL_SUPPLY_SELECTOR = "0x18160ddd"
ERC20_BALANCE_OF_SELECTOR = "0x70a08231"
DEFAULT_HOLDER_BURN_ADDRESS = "0x000000000000000000000000000000000000dEaD"


class InspectorError(Exception):
    """Base exception for inspector errors."""
    pass


class ValidationError(InspectorError):
    """Raised when an address, transaction hash, or parameter fails validation."""
    pass


class NetworkError(InspectorError):
    """Raised when an RPC or MCP network call fails."""
    pass


def decode_abi_string(hex_data: str) -> str:
    """Decode an ABI-encoded string (supporting dynamic string and bytes32 formats)."""
    if not hex_data or hex_data == "0x":
        raise ValidationError("Cannot decode empty hex string as ABI string.")
    raw = hex_data[2:] if hex_data.startswith("0x") else hex_data
    # Dynamic string: [offset 32 bytes][length 32 bytes][data...]
    if len(raw) >= 128:
        try:
            offset = int(raw[:64], 16) * 2
            if offset + 64 <= len(raw):
                length = int(raw[offset:offset + 64], 16)
                data_hex = raw[offset + 64:offset + 64 + length * 2]
                return bytes.fromhex(data_hex).decode("utf-8", errors="replace")
        except Exception:
            pass
    # Fixed bytes32 string: [32 bytes UTF-8 data null-padded]
    if len(raw) == 64:
        try:
            b = bytes.fromhex(raw)
            return b.rstrip(b"\x00").decode("utf-8", errors="replace")
        except Exception:
            pass
    raise ValidationError(f"Malformed or unexpected ABI string return data: {hex_data[:66]}")


def decode_abi_uint256(hex_data: str) -> int:
    """Decode a 32-byte EVM word into an unsigned integer."""
    if not hex_data or hex_data == "0x":
        raise ValidationError("Cannot decode empty hex string as uint256.")
    raw = hex_data[2:] if hex_data.startswith("0x") else hex_data
    if len(raw) < 2:
        raise ValidationError(f"Insufficient hex data for uint256: {hex_data}")
    try:
        return int(raw, 16)
    except ValueError as e:
        raise ValidationError(f"Invalid hex integer format: {hex_data}") from e


def find_assets_dir() -> Path:
    """Locate assets directory relative to this script."""
    current = Path(__file__).resolve().parent
    candidates = [
        current.parent / "assets",
        current / "assets",
        Path.cwd() / "assets",
        Path.cwd() / "skills" / "pharos-portfolio-inspector" / "assets"
    ]
    for c in candidates:
        if c.is_dir() and (c / "networks.json").exists():
            return c
    # Fallback to current parent/assets
    return current.parent / "assets"


class PharosInspector:
    def __init__(self, assets_dir: Optional[Path] = None):
        self.assets_dir = assets_dir or find_assets_dir()
        self.networks = self._load_networks()
        self.tokens = self._load_tokens()
        self._mcp_session_id: Optional[str] = None
        self._mcp_cookie: Optional[str] = None

    def _load_networks(self) -> Dict[str, Any]:
        net_path = self.assets_dir / "networks.json"
        if not net_path.exists():
            raise FileNotFoundError(f"Networks config not found at: {net_path}")
        with open(net_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _load_tokens(self) -> Dict[str, Any]:
        token_path = self.assets_dir / "tokens.json"
        if not token_path.exists():
            return {}
        with open(token_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def get_network_config(self, network_name: str) -> Dict[str, Any]:
        """Retrieve network parameters for a given network name."""
        for net in self.networks.get("networks", []):
            if net["name"] == network_name:
                return net
        valid = [net["name"] for net in self.networks.get("networks", [])]
        raise ValidationError(f"Unknown network '{network_name}'. Supported networks: {valid}")

    @staticmethod
    def validate_address(address: str) -> str:
        """Validate an EVM address. Returns normalized checksummed/lowercased address or raises ValidationError."""
        if not isinstance(address, str):
            raise ValidationError(f"Address must be a string, got {type(address).__name__}")
        addr = address.strip()
        if not ETH_ADDRESS_REGEX.match(addr):
            raise ValidationError(f"Invalid EVM address '{addr}'. Must be 0x followed by 40 hex characters.")
        return addr

    @staticmethod
    def validate_tx_hash(tx_hash: str) -> str:
        """Validate a transaction hash."""
        if not isinstance(tx_hash, str):
            raise ValidationError(f"Transaction hash must be a string, got {type(tx_hash).__name__}")
        h = tx_hash.strip()
        if not ETH_TX_HASH_REGEX.match(h):
            raise ValidationError(f"Invalid transaction hash '{h}'. Must be 0x followed by 64 hex characters.")
        return h

    @staticmethod
    def format_token_amount(raw_wei: int, decimals: int) -> str:
        """Format an integer amount with decimals into a human-readable decimal string without loss of precision."""
        if decimals == 0:
            return str(raw_wei)
        sign = "-" if raw_wei < 0 else ""
        raw_str = str(abs(raw_wei)).zfill(decimals + 1)
        integer_part = raw_str[:-decimals]
        fractional_part = raw_str[-decimals:].rstrip("0")
        if not fractional_part:
            return f"{sign}{integer_part}"
        return f"{sign}{integer_part}.{fractional_part}"

    def rpc_call(self, method: str, params: list, network: str = "atlantic-testnet", custom_rpc: Optional[str] = None) -> Any:
        """Execute a standard JSON-RPC request to the target Pharos RPC endpoint."""
        rpc_url = custom_rpc or self.get_network_config(network)["rpcUrl"]
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            rpc_url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT
            },
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
            raise NetworkError(f"RPC HTTP Error {e.code} ({e.reason}) from {rpc_url}: {err_body}") from e
        except urllib.error.URLError as e:
            raise NetworkError(f"RPC Connection Error to {rpc_url}: {e.reason}") from e
        except Exception as e:
            raise NetworkError(f"Unexpected RPC transport error to {rpc_url}: {e}") from e

        try:
            res = json.loads(body)
        except json.JSONDecodeError as e:
            raise NetworkError(f"Malformed JSON response from RPC {rpc_url}: {body[:200]}") from e

        if "error" in res:
            err = res["error"]
            err_msg = err.get("message", "Unknown error") if isinstance(err, dict) else str(err)
            raise NetworkError(f"RPC Error [{method}]: {err_msg}")

        return res.get("result")

    # -------------------------------------------------------------------------
    # Core Read Capabilities
    # -------------------------------------------------------------------------

    def check_contract_code(self, address: str, network: str = "atlantic-testnet", use_mcp: bool = False) -> str:
        """Verify deployed bytecode exists at address using eth_getCode or MCP get_code."""
        valid_addr = self.validate_address(address)
        if use_mcp:
            mcp_res = self.query_hosted_mcp("get_code", {"address": valid_addr})
            text = mcp_res.get("content", [{}])[0].get("text", "{}")
            try:
                parsed = json.loads(text)
                code_hex = parsed.get("code", "0x")
            except Exception:
                code_hex = "0x"
        else:
            code_hex = self.rpc_call("eth_getCode", [valid_addr, "latest"], network=network)

        if not code_hex or code_hex in ("0x", "0x0") or len(code_hex) <= 2:
            raise ValidationError(
                f"Address {valid_addr} has no deployed bytecode on {network} (EOA or un-deployed contract)."
            )
        return code_hex

    def get_block_number(self, network: str = "atlantic-testnet", use_mcp: bool = False) -> int:
        """Fetch current block number via direct RPC or Chain MCP."""
        if use_mcp:
            mcp_res = self.query_hosted_mcp("get_block_number", {})
            text = mcp_res.get("content", [{}])[0].get("text", "{}")
            try:
                parsed = json.loads(text)
                return int(parsed.get("blockNumber", "0"))
            except Exception as e:
                raise NetworkError(f"Failed to parse blockNumber from MCP response: {text}") from e
        else:
            block_hex = self.rpc_call("eth_blockNumber", [], network=network)
            return int(block_hex, 16) if block_hex else 0

    def execute_eth_call(self, to_address: str, data: str, network: str = "atlantic-testnet", use_mcp: bool = False) -> str:
        """Execute a read-only EVM call via direct RPC or Chain MCP."""
        valid_to = self.validate_address(to_address)
        if use_mcp:
            mcp_res = self.query_hosted_mcp("eth_call", {
                "transaction": {
                    "to": valid_to,
                    "data": data
                }
            })
            text = mcp_res.get("content", [{}])[0].get("text", "{}")
            try:
                parsed = json.loads(text)
                res_hex = parsed.get("result", "")
            except Exception as e:
                raise NetworkError(f"Failed to parse eth_call result from MCP: {text}") from e
        else:
            tx_obj = {"to": valid_to, "data": data}
            res_hex = self.rpc_call("eth_call", [tx_obj, "latest"], network=network)

        if not res_hex or res_hex == "0x":
            raise NetworkError(f"EVM call to {valid_to} (data: {data[:10]}) reverted or returned empty data (0x).")
        return res_hex

    def get_chain_status(self, network: str = "atlantic-testnet") -> Dict[str, Any]:
        """Fetch chain block height, client version, and configured network parameters."""
        net_cfg = self.get_network_config(network)
        block_hex = self.rpc_call("eth_blockNumber", [], network=network)
        client_version = self.rpc_call("web3_clientVersion", [], network=network)
        chain_id_hex = self.rpc_call("eth_chainId", [], network=network)

        block_num = int(block_hex, 16) if block_hex else 0
        reported_chain_id = int(chain_id_hex, 16) if chain_id_hex else 0

        return {
            "network": network,
            "configuredChainId": net_cfg["chainId"],
            "reportedChainId": reported_chain_id,
            "chainIdMatch": reported_chain_id == net_cfg["chainId"],
            "blockNumber": block_num,
            "clientVersion": client_version,
            "rpcUrl": net_cfg["rpcUrl"],
            "nativeToken": net_cfg["nativeToken"],
            "explorerUrl": net_cfg["explorerUrl"]
        }

    def get_native_balance(self, address: str, network: str = "atlantic-testnet") -> Dict[str, Any]:
        """Fetch native token balance (PHRS on testnet, PROS on mainnet)."""
        valid_addr = self.validate_address(address)
        net_cfg = self.get_network_config(network)
        bal_hex = self.rpc_call("eth_getBalance", [valid_addr, "latest"], network=network)
        raw_wei = int(bal_hex, 16) if bal_hex else 0
        human_readable = self.format_token_amount(raw_wei, 18)

        return {
            "address": valid_addr,
            "network": network,
            "symbol": net_cfg["nativeToken"],
            "decimals": 18,
            "balanceWei": str(raw_wei),
            "formatted": human_readable
        }

    def get_token_balance(
        self,
        address: str,
        token_address: str,
        decimals: int = 18,
        symbol: str = "UNKNOWN",
        name: str = "Unknown Token",
        network: str = "atlantic-testnet"
    ) -> Dict[str, Any]:
        """Fetch ERC-20 token balance via eth_call balanceOf(address)."""
        valid_owner = self.validate_address(address)
        valid_token = self.validate_address(token_address)

        # Confirm bytecode exists before treating as a valid contract
        self.check_contract_code(valid_token, network=network)

        # balanceOf(address) selector: 0x70a08231
        # padded address (32 bytes = 64 hex chars without 0x)
        clean_addr = valid_owner[2:].lower().zfill(64)
        call_data = f"{ERC20_BALANCE_OF_SELECTOR}{clean_addr}"

        res_hex = self.execute_eth_call(valid_token, call_data, network=network)
        if len(res_hex) < 66:
            raise NetworkError(f"Invalid return data length for balanceOf from {valid_token}: {res_hex}")

        raw_balance = decode_abi_uint256(res_hex)

        return {
            "owner": valid_owner,
            "tokenAddress": valid_token,
            "symbol": symbol,
            "name": name,
            "decimals": decimals,
            "raw": str(raw_balance),
            "formatted": self.format_token_amount(raw_balance, decimals)
        }

    def get_contract_state(
        self,
        contract_address: str,
        holder_address: Optional[str] = None,
        network: str = "atlantic-testnet",
        use_mcp: bool = False
    ) -> Dict[str, Any]:
        """Read at least 3 distinct state values from one deployed smart contract (Task 1 compliance)."""
        valid_contract = self.validate_address(contract_address)

        # Step 1: Verify contract bytecode
        code_hex = self.check_contract_code(valid_contract, network=network, use_mcp=use_mcp)
        code_size_bytes = (len(code_hex) - 2) // 2

        # Step 2: Read current block height
        block_num = self.get_block_number(network=network, use_mcp=use_mcp)

        # Step 3: State 1 - name()
        name_hex = self.execute_eth_call(valid_contract, ERC20_NAME_SELECTOR, network=network, use_mcp=use_mcp)
        token_name = decode_abi_string(name_hex)

        # Step 4: State 2 - symbol()
        symbol_hex = self.execute_eth_call(valid_contract, ERC20_SYMBOL_SELECTOR, network=network, use_mcp=use_mcp)
        token_symbol = decode_abi_string(symbol_hex)

        # Step 5: State 3 - decimals()
        try:
            decimals_hex = self.execute_eth_call(valid_contract, ERC20_DECIMALS_SELECTOR, network=network, use_mcp=use_mcp)
            decimals = decode_abi_uint256(decimals_hex)
        except Exception:
            decimals = 18

        # Step 6: State 4 - totalSupply()
        total_supply_hex = self.execute_eth_call(valid_contract, ERC20_TOTAL_SUPPLY_SELECTOR, network=network, use_mcp=use_mcp)
        raw_total_supply = decode_abi_uint256(total_supply_hex)
        formatted_total_supply = self.format_token_amount(raw_total_supply, decimals)

        # Step 7: State 5 - balanceOf(holder)
        if holder_address:
            valid_holder = self.validate_address(holder_address)
            holder_label = f"Custom Holder ({valid_holder})"
        else:
            valid_holder = DEFAULT_HOLDER_BURN_ADDRESS
            holder_label = f"Default Harmless Burn Fixture ({valid_holder})"

        clean_holder = valid_holder[2:].lower().zfill(64)
        bal_data = f"{ERC20_BALANCE_OF_SELECTOR}{clean_holder}"
        bal_hex = self.execute_eth_call(valid_contract, bal_data, network=network, use_mcp=use_mcp)
        raw_holder_balance = decode_abi_uint256(bal_hex)
        formatted_holder_balance = self.format_token_amount(raw_holder_balance, decimals)

        return {
            "contractAddress": valid_contract,
            "network": network,
            "queryEngine": "Hosted Chain MCP (https://mcp.pharos.xyz/mcp)" if use_mcp else f"Direct JSON-RPC ({self.get_network_config(network)['rpcUrl']})",
            "blockNumber": block_num,
            "hasBytecode": True,
            "bytecodeSizeBytes": code_size_bytes,
            "stateValues": {
                "name": token_name,
                "symbol": token_symbol,
                "decimals": decimals,
                "totalSupply": {
                    "raw": str(raw_total_supply),
                    "formatted": f"{formatted_total_supply} {token_symbol}"
                },
                "balanceOf": {
                    "holderAddress": valid_holder,
                    "holderLabel": holder_label,
                    "raw": str(raw_holder_balance),
                    "formatted": f"{formatted_holder_balance} {token_symbol}",
                    "addressDependencyExplanation": (
                        f"This value reflects the balance held by the selected address ({valid_holder}), "
                        "not an internal balance of the token contract itself."
                    )
                }
            }
        }

    def get_portfolio(self, address: str, network: str = "atlantic-testnet") -> Dict[str, Any]:
        """Fetch wallet portfolio overview: native balance and all registered ERC-20 tokens."""
        valid_addr = self.validate_address(address)
        native = self.get_native_balance(valid_addr, network=network)

        token_list = self.tokens.get(network, [])
        token_results = []
        for t in token_list:
            try:
                t_bal = self.get_token_balance(
                    address=valid_addr,
                    token_address=t["address"],
                    decimals=t.get("decimals", 18),
                    symbol=t.get("symbol", "UNKNOWN"),
                    name=t.get("name", ""),
                    network=network
                )
                token_results.append(t_bal)
            except Exception as e:
                token_results.append({
                    "tokenAddress": t.get("address"),
                    "symbol": t.get("symbol", "ERR"),
                    "name": t.get("name", "Error"),
                    "error": str(e)
                })

        return {
            "address": valid_addr,
            "network": network,
            "nativeBalance": native,
            "tokens": token_results,
            "totalTokensQueried": len(token_results)
        }

    def get_transaction_status(self, tx_hash: str, network: str = "atlantic-testnet") -> Dict[str, Any]:
        """Fetch confirmation status and receipt details for a transaction hash."""
        valid_hash = self.validate_tx_hash(tx_hash)
        net_cfg = self.get_network_config(network)
        receipt = self.rpc_call("eth_getTransactionReceipt", [valid_hash], network=network)

        if not receipt:
            return {
                "transactionHash": valid_hash,
                "network": network,
                "status": "NOT_FOUND_OR_PENDING",
                "isConfirmed": False,
                "details": None,
                "explorerUrl": f"{net_cfg['explorerUrl']}tx/{valid_hash}"
            }

        status_code = receipt.get("status")
        is_success = status_code == "0x1"
        block_num = int(receipt.get("blockNumber", "0x0"), 16)
        gas_used = int(receipt.get("gasUsed", "0x0"), 16)

        return {
            "transactionHash": valid_hash,
            "network": network,
            "status": "SUCCESS" if is_success else "REVERTED",
            "isConfirmed": True,
            "blockNumber": block_num,
            "gasUsed": gas_used,
            "from": receipt.get("from"),
            "to": receipt.get("to"),
            "contractAddress": receipt.get("contractAddress"),
            "logsCount": len(receipt.get("logs", [])),
            "explorerUrl": f"{net_cfg['explorerUrl']}tx/{valid_hash}"
        }

    # -------------------------------------------------------------------------
    # Hosted MCP Integration
    # -------------------------------------------------------------------------

    def query_hosted_mcp(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Query tools via the hosted Streamable HTTP MCP server (https://mcp.pharos.xyz/mcp)."""
        # Step 1: Initialize session if not already active
        if not self._mcp_session_id:
            init_payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "pharos-inspector-client", "version": "1.0.0"}
                }
            }
            init_req = urllib.request.Request(
                HOSTED_MCP_URL,
                data=json.dumps(init_payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream",
                    "User-Agent": USER_AGENT
                },
                method="POST"
            )
            try:
                with urllib.request.urlopen(init_req, timeout=DEFAULT_TIMEOUT) as resp:
                    session_id = resp.headers.get("mcp-session-id")
                    cookie = resp.headers.get("Set-Cookie")
                    self._mcp_session_id = session_id
                    self._mcp_cookie = cookie.split(";")[0] if cookie else None
            except Exception as e:
                raise NetworkError(f"Failed to initialize session with Hosted MCP ({HOSTED_MCP_URL}): {e}") from e

        common_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "User-Agent": USER_AGENT,
            "mcp-session-id": self._mcp_session_id or ""
        }
        if self._mcp_cookie:
            common_headers["Cookie"] = self._mcp_cookie

        # Step 2: Call tool
        call_payload = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }
        call_req = urllib.request.Request(
            HOSTED_MCP_URL,
            data=json.dumps(call_payload).encode("utf-8"),
            headers=common_headers,
            method="POST"
        )
        try:
            with urllib.request.urlopen(call_req, timeout=DEFAULT_TIMEOUT) as resp:
                body_text = resp.read().decode("utf-8")
        except Exception as e:
            raise NetworkError(f"Hosted MCP tool call '{tool_name}' failed: {e}") from e

        # Parse SSE
        parsed = None
        for line in body_text.splitlines():
            if line.startswith("data: "):
                parsed = json.loads(line[6:])
                break

        if not parsed:
            raise NetworkError(f"Failed to parse SSE payload from Hosted MCP response: {body_text[:200]}")

        if "error" in parsed:
            raise NetworkError(f"Hosted MCP error: {parsed['error']}")

        return parsed.get("result", {})


def cli_main() -> None:
    # Common flags accepted both before and after subcommands
    common_parser = argparse.ArgumentParser(add_help=False)
    common_parser.add_argument(
        "--network",
        default="atlantic-testnet",
        choices=["atlantic-testnet", "mainnet"],
        help="Target Pharos network (default: atlantic-testnet)"
    )
    common_parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON format"
    )

    parser = argparse.ArgumentParser(
        description="Pharos On-Chain Data & Portfolio Inspector (Read-Only, Zero-Cost)",
        parents=[common_parser]
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand: status
    subparsers.add_parser("status", parents=[common_parser], help="Check Pharos node block height and client status")

    # Subcommand: balance
    bal_parser = subparsers.add_parser("balance", parents=[common_parser], help="Query native PHRS/PROS balance of an address")
    bal_parser.add_argument("address", help="Target EVM address (0x...)")

    # Subcommand: token
    tok_parser = subparsers.add_parser("token", parents=[common_parser], help="Query specific ERC-20 token balance")
    tok_parser.add_argument("address", help="Wallet owner address (0x...)")
    tok_parser.add_argument("token_address", help="ERC-20 contract address (0x...)")
    tok_parser.add_argument("--decimals", type=int, default=18, help="Token decimals (default: 18)")
    tok_parser.add_argument("--symbol", default="TOKEN", help="Token symbol")

    # Subcommand: contract (Task 1 compliance)
    c_parser = subparsers.add_parser("contract", parents=[common_parser], help="Read multi-state values from a deployed smart contract (Task 1 compliance)")
    c_parser.add_argument("contract_address", help="Target contract EVM address (0x...)")
    c_parser.add_argument("--holder", default=None, help="Optional holder address for balanceOf check (defaults to 0x...dEaD)")
    c_parser.add_argument("--mcp", action="store_true", default=False, help="Query via Pharos Hosted Chain MCP")
    c_parser.add_argument("--rpc", action="store_true", default=False, help="Force direct JSON-RPC query instead of Chain MCP")

    # Subcommand: portfolio
    port_parser = subparsers.add_parser("portfolio", parents=[common_parser], help="Query native + all registered token balances")
    port_parser.add_argument("address", help="Target wallet address (0x...)")

    # Subcommand: tx
    tx_parser = subparsers.add_parser("tx", parents=[common_parser], help="Query confirmation status of a transaction hash")
    tx_parser.add_argument("tx_hash", help="Transaction hash (0x...)")

    # Subcommand: mcp
    mcp_parser = subparsers.add_parser("mcp", parents=[common_parser], help="Query live data via Pharos Hosted MCP endpoint")
    mcp_parser.add_argument("tool", help="MCP tool name (e.g. get_chain_info, get_block_number, get_balance)")
    mcp_parser.add_argument("--args", default="{}", help="JSON string of arguments for the tool")

    args = parser.parse_args()

    try:
        inspector = PharosInspector()
        result = {}

        if args.command == "status":
            result = inspector.get_chain_status(network=args.network)
        elif args.command == "balance":
            result = inspector.get_native_balance(args.address, network=args.network)
        elif args.command == "token":
            result = inspector.get_token_balance(
                address=args.address,
                token_address=args.token_address,
                decimals=args.decimals,
                symbol=args.symbol,
                network=args.network
            )
        elif args.command == "contract":
            target_network = args.network
            # If --mcp is requested on default testnet, automatically route to mainnet where hosted MCP is connected
            if args.mcp and target_network == "atlantic-testnet":
                target_network = "mainnet"
            # Primary engine for Task 1: use MCP if --mcp flag passed or if querying mainnet unless --rpc is explicitly forced
            use_mcp = args.mcp or (target_network == "mainnet" and not getattr(args, "rpc", False))
            result = inspector.get_contract_state(
                contract_address=args.contract_address,
                holder_address=args.holder,
                network=target_network,
                use_mcp=use_mcp
            )
        elif args.command == "portfolio":
            result = inspector.get_portfolio(args.address, network=args.network)
        elif args.command == "tx":
            result = inspector.get_transaction_status(args.tx_hash, network=args.network)
        elif args.command == "mcp":
            call_args = json.loads(args.args)
            result = inspector.query_hosted_mcp(args.tool, call_args)

        if args.json:
            print(json.dumps(result, indent=2))
        else:
            # Human readable display
            print("\n=== Pharos On-Chain Data Inspector ===")
            if args.command == "status":
                print(f"Network:        {result['network']}")
                print(f"Block Number:   {result['blockNumber']:,}")
                print(f"Chain ID:       {result['reportedChainId']} (Expected: {result['configuredChainId']})")
                print(f"Client:         {result['clientVersion']}")
                print(f"RPC Endpoint:   {result['rpcUrl']}")
                print(f"Explorer:       {result['explorerUrl']}")
            elif args.command == "balance":
                print(f"Address:        {result['address']}")
                print(f"Network:        {result['network']}")
                print(f"Native Balance: {result['formatted']} {result['symbol']}")
                print(f"Raw (Wei):      {result['balanceWei']}")
            elif args.command == "token":
                print(f"Owner:          {result['owner']}")
                print(f"Token:          {result['symbol']} ({result['tokenAddress']})")
                print(f"Balance:        {result['formatted']} {result['symbol']}")
            elif args.command == "contract":
                s = result['stateValues']
                print(f"Contract:       {result['contractAddress']}")
                print(f"Network:        {result['network']}")
                print(f"Query Engine:   {result['queryEngine']}")
                print(f"Read at Block:  {result['blockNumber']:,}")
                print(f"Bytecode Size:  {result['bytecodeSizeBytes']:,} bytes")
                print(f"\n--- Contract State Values (Decoded & Formatted) ---")
                print(f"1. Token Name:    {s['name']}")
                print(f"2. Token Symbol:  {s['symbol']}")
                print(f"3. Decimals:      {s['decimals']}")
                print(f"4. Total Supply:  {s['totalSupply']['formatted']} (Raw: {s['totalSupply']['raw']})")
                print(f"5. Holder Balance: {s['balanceOf']['formatted']} (Raw: {s['balanceOf']['raw']})")
                print(f"   Target Holder: {s['balanceOf']['holderLabel']}")
                print(f"   Note:          {s['balanceOf']['addressDependencyExplanation']}")
            elif args.command == "portfolio":
                print(f"Address:        {result['address']}")
                print(f"Network:        {result['network']}")
                nat = result['nativeBalance']
                print(f"\n--- Native Asset ---")
                print(f"{nat['symbol']}: {nat['formatted']}")
                print(f"\n--- Registered ERC-20 Tokens ({result['totalTokensQueried']} monitored) ---")
                for tok in result['tokens']:
                    if "error" in tok:
                        print(f"- {tok['symbol']} ({tok['tokenAddress']}): Query Error - {tok['error']}")
                    else:
                        print(f"- {tok['symbol']:<6} ({tok['name']}): {tok['formatted']}")
            elif args.command == "tx":
                print(f"Tx Hash:        {result['transactionHash']}")
                print(f"Status:         {result['status']}")
                print(f"Confirmed:      {result['isConfirmed']}")
                if result['isConfirmed']:
                    print(f"Block:          {result['blockNumber']}")
                    print(f"Gas Used:       {result['gasUsed']:,}")
                    print(f"From:           {result['from']}")
                    print(f"To:             {result['to']}")
                print(f"Explorer Link:  {result['explorerUrl']}")
            elif args.command == "mcp":
                print(f"Tool:           {args.tool}")
                print(json.dumps(result, indent=2))
            print("======================================\n")

    except InspectorError as e:
        sys.stderr.write(f"\n[Inspector Error] {e}\n\n")
        sys.exit(1)
    except Exception as e:
        sys.stderr.write(f"\n[Unexpected Error] {e}\n\n")
        sys.exit(2)


if __name__ == "__main__":
    cli_main()

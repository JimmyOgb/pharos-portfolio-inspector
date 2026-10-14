#!/usr/bin/env python3
"""
Test Suite for Pharos On-Chain Event & Log Monitor (Task 2)
==========================================================
Includes:
  1. Offline Deterministic Unit Tests (Mocked MCP & RPC)
  2. Strict EVM Topic Address Extraction & Signature Resolution Tests
  3. Deduplication & Window Pagination Tests
  4. Live Network Integration Tests (Gated via PHAROS_LIVE_TESTS=1)
"""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

# Ensure scripts directory is on sys.path
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
import sys
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from monitor import (
    MAX_MCP_BLOCK_WINDOW,
    STANDARD_EVENT_TOPICS,
    PharosEventMonitor,
    extract_address_from_topic,
    resolve_event_topic,
)
from inspector import PharosInspector, ValidationError, NetworkError


class TestMonitorUnitMocked(unittest.TestCase):
    """Offline deterministic unit tests for event monitor utilities and engine."""

    def setUp(self) -> None:
        self.mock_inspector = MagicMock(spec=PharosInspector)
        self.mock_inspector.tokens = {
            "mainnet": [
                {
                    "symbol": "USDC",
                    "decimals": 6,
                    "address": "0xc879c018db60520f4355c26ed1a6d572cdac1815"
                }
            ]
        }
        self.mock_inspector.validate_address.side_effect = lambda a: a.strip().lower()
        self.mock_inspector.format_token_amount = PharosInspector.format_token_amount
        self.mock_inspector.get_network_config.return_value = {
            "name": "mainnet",
            "explorerUrl": "https://www.pharosscan.xyz"
        }
        self.monitor = PharosEventMonitor(inspector=self.mock_inspector, max_cache_size=100)

    # -------------------------------------------------------------------------
    # 1. Topic Address Extraction Tests
    # -------------------------------------------------------------------------

    def test_extract_address_from_valid_topic(self) -> None:
        topic = "0x000000000000000000000000912c9ade24d44d8922f0866d8dcb079f1363f647"
        expected = "0x912c9ade24d44d8922f0866d8dcb079f1363f647"
        self.assertEqual(extract_address_from_topic(topic), expected)

    def test_extract_address_without_0x_prefix(self) -> None:
        raw_topic = "0000000000000000000000001f3546a29eec2102c8d52e21a45114124014c85c"
        expected = "0x1f3546a29eec2102c8d52e21a45114124014c85c"
        self.assertEqual(extract_address_from_topic(raw_topic), expected)

    def test_extract_address_invalid_length_raises(self) -> None:
        with self.assertRaises(ValidationError):
            extract_address_from_topic("0x1234")
        with self.assertRaises(ValidationError):
            extract_address_from_topic("0x" + "0" * 66)

    def test_extract_address_non_hex_raises(self) -> None:
        with self.assertRaises(ValidationError):
            extract_address_from_topic("0x" + "z" * 64)

    # -------------------------------------------------------------------------
    # 2. Event Signature Resolution Tests
    # -------------------------------------------------------------------------

    def test_resolve_standard_event_names(self) -> None:
        name, topic = resolve_event_topic("Transfer")
        self.assertEqual(name, "Transfer")
        self.assertEqual(topic, STANDARD_EVENT_TOPICS["Transfer"]["topic0"].lower())

        name, topic = resolve_event_topic("transfer")
        self.assertEqual(name, "Transfer")

        name, topic = resolve_event_topic("Approval")
        self.assertEqual(name, "Approval")
        self.assertEqual(topic, STANDARD_EVENT_TOPICS["Approval"]["topic0"].lower())

    def test_resolve_full_event_signature(self) -> None:
        name, topic = resolve_event_topic("Transfer(address,address,uint256)")
        self.assertEqual(name, "Transfer")
        self.assertEqual(topic, STANDARD_EVENT_TOPICS["Transfer"]["topic0"].lower())

    def test_resolve_raw_topic0_hex(self) -> None:
        raw_topic = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
        name, topic = resolve_event_topic(raw_topic)
        self.assertEqual(name, "Transfer")
        self.assertEqual(topic, raw_topic)

        custom_topic = "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
        name, topic = resolve_event_topic(custom_topic)
        self.assertEqual(name, "CustomEvent")
        self.assertEqual(topic, custom_topic)

    def test_resolve_invalid_event_signature_raises(self) -> None:
        with self.assertRaises(ValidationError):
            resolve_event_topic("InvalidEventNonSense")

    # -------------------------------------------------------------------------
    # 3. Log Decoding Tests
    # -------------------------------------------------------------------------

    def test_decode_standard_transfer_log(self) -> None:
        raw_log = {
            "address": "0xc879c018db60520f4355c26ed1a6d572cdac1815",
            "blockNumber": "0x13516a5",
            "transactionHash": "0xbc48b05ba38577188b7f38ee72081d08c48c513c85b182443908db3945709a60",
            "logIndex": "0x1",
            "topics": [
                STANDARD_EVENT_TOPICS["Transfer"]["topic0"],
                "0x000000000000000000000000912c9ade24d44d8922f0866d8dcb079f1363f647",
                "0x0000000000000000000000001f3546a29eec2102c8d52e21a45114124014c85c"
            ],
            "data": "0x00000000000000000000000000000000000000000000000000000000037d5330"  # 58544944
        }

        decoded = self.monitor.decode_log(raw_log)
        self.assertEqual(decoded["eventName"], "Transfer")
        self.assertEqual(decoded["blockNumber"], 20256421)
        self.assertEqual(decoded["logIndex"], 1)
        self.assertEqual(decoded["from"], "0x912c9ade24d44d8922f0866d8dcb079f1363f647")
        self.assertEqual(decoded["to"], "0x1f3546a29eec2102c8d52e21a45114124014c85c")
        self.assertEqual(decoded["rawAmount"], "58544944")
        self.assertEqual(decoded["formattedAmount"], "58.544944")
        self.assertEqual(decoded["symbol"], "USDC")
        self.assertEqual(decoded["decimals"], 6)
        self.assertIn("https://www.pharosscan.xyz/tx/0xbc48b05b", decoded["explorerUrl"])

    def test_decode_custom_unknown_event(self) -> None:
        custom_topic = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        raw_log = {
            "address": "0x1111111111111111111111111111111111111111",
            "blockNumber": 100,
            "transactionHash": "0x2222222222222222222222222222222222222222222222222222222222222222",
            "logIndex": 0,
            "topics": [custom_topic],
            "data": "0x1234"
        }
        decoded = self.monitor.decode_log(raw_log)
        self.assertEqual(decoded["eventName"], "CustomEvent")
        self.assertEqual(decoded["topic0"], custom_topic)
        self.assertEqual(decoded["blockNumber"], 100)

    # -------------------------------------------------------------------------
    # 4. Deduplication Tests
    # -------------------------------------------------------------------------

    def test_deduplication_exact_match(self) -> None:
        tx = "0x430f6728555f50f405a0a0351965a0550cae597da9dcf2612ea6725e18dc43d6"
        log_idx = 0

        self.assertFalse(self.monitor.is_duplicate(tx, log_idx))
        self.monitor.record_event(tx, log_idx)
        self.assertTrue(self.monitor.is_duplicate(tx, log_idx))

        # Distinct log index on same tx is NOT duplicate
        self.assertFalse(self.monitor.is_duplicate(tx, 1))

    def test_deduplication_cache_eviction(self) -> None:
        mini_monitor = PharosEventMonitor(inspector=self.mock_inspector, max_cache_size=3)
        mini_monitor.record_event("0xtx1", 0)
        mini_monitor.record_event("0xtx2", 0)
        mini_monitor.record_event("0xtx3", 0)

        self.assertTrue(mini_monitor.is_duplicate("0xtx1", 0))

        # Adding 4th event must evict the 1st
        mini_monitor.record_event("0xtx4", 0)
        self.assertFalse(mini_monitor.is_duplicate("0xtx1", 0))
        self.assertTrue(mini_monitor.is_duplicate("0xtx2", 0))
        self.assertTrue(mini_monitor.is_duplicate("0xtx4", 0))

    def test_deduplication_reset(self) -> None:
        self.monitor.record_event("0xtx1", 0)
        self.assertTrue(self.monitor.is_duplicate("0xtx1", 0))
        self.monitor.reset_dedup_cache()
        self.assertFalse(self.monitor.is_duplicate("0xtx1", 0))
        self.assertEqual(self.monitor.total_events_reported, 0)

    # -------------------------------------------------------------------------
    # 5. Window Validation & Paging Tests
    # -------------------------------------------------------------------------

    def test_fetch_window_invalid_order_raises(self) -> None:
        with self.assertRaises(ValidationError):
            self.monitor.fetch_logs_window(from_block=100, to_block=50)

    def test_fetch_window_exceeds_1000_blocks_raises(self) -> None:
        with self.assertRaises(ValidationError):
            self.monitor.fetch_logs_window(from_block=100, to_block=1101)  # 1002 blocks

    def test_get_logs_paged_splits_chunks(self) -> None:
        call_windows: List[Tuple[int, int]] = []

        def mock_fetch(from_block: int = 0, to_block: int = 0, *args: Any, **kwargs: Any) -> List[Dict[str, Any]]:
            call_windows.append((from_block, to_block))
            return [{"mock": True, "window": (from_block, to_block)}]

        with patch.object(self.monitor, "fetch_logs_window", side_effect=mock_fetch):
            # Range 0 to 2500 -> 3 chunks: [0, 999], [1000, 1999], [2000, 2500]
            results = list(self.monitor.get_logs_paged(from_block=0, to_block=2500, chunk_size=1000))

        self.assertEqual(len(results), 3)
        self.assertEqual(call_windows, [
            (0, 999),
            (1000, 1999),
            (2000, 2500)
        ])

    # -------------------------------------------------------------------------
    # 6. Stream Monitoring with Deduplication Across Overlaps
    # -------------------------------------------------------------------------

    def test_monitor_stream_deduplicates_overlapping_responses(self) -> None:
        # Simulate two polling cycles returning overlapping logs
        log_a = {
            "address": "0xc879c018db60520f4355c26ed1a6d572cdac1815",
            "blockNumber": 100,
            "transactionHash": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "logIndex": 0,
            "topics": [STANDARD_EVENT_TOPICS["Transfer"]["topic0"]],
            "data": "0x01"
        }
        log_b = {
            "address": "0xc879c018db60520f4355c26ed1a6d572cdac1815",
            "blockNumber": 101,
            "transactionHash": "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            "logIndex": 0,
            "topics": [STANDARD_EVENT_TOPICS["Transfer"]["topic0"]],
            "data": "0x02"
        }

        # Mock block height: 101
        self.mock_inspector.get_block_number.return_value = 101
        
        # Poll 1 returns [log_a, log_b]
        # Poll 2 returns [log_b] (overlap)
        with patch.object(self.monitor, "fetch_logs_window", return_value=[log_a, log_b, log_b]):
            events = list(self.monitor.monitor_stream(
                contract_address="0xc879c018db60520f4355c26ed1a6d572cdac1815",
                start_block=100,
                to_block=101,
                use_mcp=False
            ))

        # Expected: exactly 2 unique events despite 3 items returned with duplicate
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["transactionHash"], log_a["transactionHash"])
        self.assertEqual(events[1]["transactionHash"], log_b["transactionHash"])

    def test_monitor_stream_stops_at_max_events(self) -> None:
        sample_logs = [
            {"address": "0x11", "blockNumber": 100, "transactionHash": f"0x{i:064x}", "logIndex": 0, "topics": [STANDARD_EVENT_TOPICS["Transfer"]["topic0"]], "data": "0x01"}
            for i in range(10)
        ]

        self.mock_inspector.get_block_number.return_value = 100
        with patch.object(self.monitor, "fetch_logs_window", return_value=sample_logs):
            events = list(self.monitor.monitor_stream(
                start_block=100,
                to_block=100,
                max_events=3,
                use_mcp=False
            ))

        self.assertEqual(len(events), 3)


class TestMonitorLiveNetwork(unittest.TestCase):
    """
    Live integration test against Pharos Chain MCP and Mainnet logs.
    Only executed when PHAROS_LIVE_TESTS=1 is explicitly set.
    """

    def setUp(self) -> None:
        if os.environ.get("PHAROS_LIVE_TESTS") != "1":
            self.skipTest("Live network integration tests disabled. Set PHAROS_LIVE_TESTS=1 to run.")

    def test_live_mcp_event_log_catch(self) -> None:
        """Verify catching and decoding real live on-chain Transfer events via Hosted Chain MCP."""
        inspector = PharosInspector()
        monitor = PharosEventMonitor(inspector=inspector)

        # Pacific USDC contract known to have continuous transfers
        usdc_pacific = "0xc879c018db60520f4355c26ed1a6d572cdac1815"
        latest_block = inspector.get_block_number(network="mainnet", use_mcp=True)
        self.assertGreater(latest_block, 20_000_000)

        # Scan recent 60 blocks for at least 1 real transfer event
        start_b = latest_block - 60
        events = list(monitor.monitor_stream(
            contract_address=usdc_pacific,
            event_signature="Transfer",
            start_block=start_b,
            to_block=latest_block,
            max_events=3,
            network="mainnet",
            use_mcp=True
        ))

        self.assertGreaterEqual(len(events), 1, "Should catch at least one live Transfer event in the block window")
        evt = events[0]
        self.assertEqual(evt["eventName"], "Transfer")
        self.assertTrue(evt["from"].startswith("0x"))
        self.assertTrue(evt["to"].startswith("0x"))
        self.assertTrue(evt["transactionHash"].startswith("0x"))
        self.assertGreater(evt["blockNumber"], 0)
        self.assertIn("https://www.pharosscan.xyz/tx/", evt["explorerUrl"])


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""
Automated Test Suite for Pharos Portfolio Inspector
===================================================
Covers:
  - Mocked deterministic unit tests (offline, zero-cost, harmless fixtures)
  - ABI decoding, precision formatting, input regex validation
  - Misleading zero balance fixes: bytecode detection, reverts, malformed returns, legitimate zeros
  - Task 1 multi-state contract inspection (name, symbol, decimals, totalSupply, balanceOf, blockNumber)
  - RPC failure modes: timeouts, malformed JSON, server error payloads
  - Live network tests against Atlantic Testnet & Hosted MCP (gated by PHAROS_LIVE_TESTS=1 or --live)
"""

import json
import os
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add parent scripts directory to path
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
sys.path.insert(0, str(SCRIPTS_DIR))

from inspector import (  # noqa: E402
    NetworkError,
    PharosInspector,
    ValidationError,
    decode_abi_string,
    decode_abi_uint256,
)


class TestInspectorUnitMocked(unittest.TestCase):
    """Offline unit tests using fixtures and mocks. Zero network calls."""

    def setUp(self):
        self.inspector = PharosInspector(assets_dir=ASSETS_DIR)

    # -------------------------------------------------------------------------
    # 1. Address Validation Tests
    # -------------------------------------------------------------------------

    def test_valid_address(self):
        valid = "0x000000000000000000000000000000000000dEaD"
        self.assertEqual(self.inspector.validate_address(valid), valid)

    def test_address_missing_0x(self):
        with self.assertRaises(ValidationError):
            self.inspector.validate_address("000000000000000000000000000000000000dEaD")

    def test_address_invalid_length(self):
        with self.assertRaises(ValidationError):
            self.inspector.validate_address("0x12345")

    def test_address_invalid_hex(self):
        with self.assertRaises(ValidationError):
            self.inspector.validate_address("0xGGGG000000000000000000000000000000000000")

    # -------------------------------------------------------------------------
    # 2. Transaction Hash Validation Tests
    # -------------------------------------------------------------------------

    def test_valid_tx_hash(self):
        valid_h = "0x" + "a" * 64
        self.assertEqual(self.inspector.validate_tx_hash(valid_h), valid_h)

    def test_invalid_tx_hash(self):
        with self.assertRaises(ValidationError):
            self.inspector.validate_tx_hash("0x" + "a" * 63)

    # -------------------------------------------------------------------------
    # 3. Precision Token Formatting Tests
    # -------------------------------------------------------------------------

    def test_format_token_amount_18_decimals(self):
        raw_wei = 1500000000000000000
        formatted = self.inspector.format_token_amount(raw_wei, 18)
        self.assertEqual(formatted, "1.5")

    def test_format_token_amount_6_decimals(self):
        raw_usdc = 10250000
        formatted = self.inspector.format_token_amount(raw_usdc, 6)
        self.assertEqual(formatted, "10.25")

    def test_format_token_amount_zero(self):
        self.assertEqual(self.inspector.format_token_amount(0, 18), "0")

    # -------------------------------------------------------------------------
    # 4. Network and Assets Configuration Tests
    # -------------------------------------------------------------------------

    def test_networks_config_loaded(self):
        self.assertIn("networks", self.inspector.networks)
        atlantic = self.inspector.get_network_config("atlantic-testnet")
        self.assertEqual(atlantic["chainId"], 688689)
        self.assertEqual(atlantic["nativeToken"], "PHRS")

    def test_unsupported_network_raises_validation_error(self):
        with self.assertRaises(ValidationError):
            self.inspector.get_network_config("non-existent-network")

    def test_tokens_config_loaded(self):
        self.assertIn("atlantic-testnet", self.inspector.tokens)
        tokens = self.inspector.tokens["atlantic-testnet"]
        symbols = [t["symbol"] for t in tokens]
        self.assertIn("USDC", symbols)
        self.assertIn("WPHRS", symbols)

    # -------------------------------------------------------------------------
    # 5. ABI Decoding Tests
    # -------------------------------------------------------------------------

    def test_decode_abi_string_dynamic(self):
        # ABI dynamic string for "USD Coin" (8 bytes, length word = 8)
        # offset (0x20 = 32), length (0x08 = 8), data ("USD Coin" + zeroes)
        hex_data = (
            "0x"
            + "0000000000000000000000000000000000000000000000000000000000000020"
            + "0000000000000000000000000000000000000000000000000000000000000008"
            + "55534420436f696e000000000000000000000000000000000000000000000000"
        )
        self.assertEqual(decode_abi_string(hex_data), "USD Coin")

    def test_decode_abi_string_bytes32(self):
        # 32 bytes string right-padded with null bytes: "USDC"
        hex_data = "0x55534443" + "00" * 28
        self.assertEqual(decode_abi_string(hex_data), "USDC")

    def test_decode_abi_string_empty_raises(self):
        with self.assertRaises(ValidationError):
            decode_abi_string("0x")

    def test_decode_abi_uint256(self):
        # 100 in 32-byte hex
        hex_data = "0x" + "0" * 62 + "64"
        self.assertEqual(decode_abi_uint256(hex_data), 100)

    def test_decode_abi_uint256_empty_raises(self):
        with self.assertRaises(ValidationError):
            decode_abi_uint256("0x")

    # -------------------------------------------------------------------------
    # 6. Misleading Zero Balance & Bytecode Verification Tests
    # -------------------------------------------------------------------------

    @patch.object(PharosInspector, "rpc_call")
    def test_check_contract_code_missing_bytecode_raises(self, mock_rpc):
        # Returns 0x for an EOA address with no code
        mock_rpc.return_value = "0x"
        with self.assertRaises(ValidationError) as ctx:
            self.inspector.check_contract_code("0x000000000000000000000000000000000000dEaD")
        self.assertIn("no deployed bytecode", str(ctx.exception))

    @patch.object(PharosInspector, "rpc_call")
    def test_get_token_balance_missing_bytecode_raises(self, mock_rpc):
        mock_rpc.return_value = "0x"
        with self.assertRaises(ValidationError) as ctx:
            self.inspector.get_token_balance(
                address="0x000000000000000000000000000000000000dEaD",
                token_address="0x000000000000000000000000000000000000dEaD"
            )
        self.assertIn("no deployed bytecode", str(ctx.exception))

    @patch.object(PharosInspector, "rpc_call")
    def test_get_token_balance_empty_return_revert_raises(self, mock_rpc):
        # eth_getCode returns valid bytecode, but eth_call returns 0x (revert/empty)
        def rpc_side_effect(method, params, network="atlantic-testnet"):
            if method == "eth_getCode":
                return "0x60806040"
            if method == "eth_call":
                return "0x"
            return None
        mock_rpc.side_effect = rpc_side_effect

        with self.assertRaises(NetworkError) as ctx:
            self.inspector.get_token_balance(
                address="0x000000000000000000000000000000000000dEaD",
                token_address="0xE0BE08c77f415F577A1B3A9aD7a1Df1479564ec8"
            )
        self.assertIn("reverted or returned empty data", str(ctx.exception))

    @patch.object(PharosInspector, "rpc_call")
    def test_get_token_balance_malformed_short_return_raises(self, mock_rpc):
        def rpc_side_effect(method, params, network="atlantic-testnet"):
            if method == "eth_getCode":
                return "0x60806040"
            if method == "eth_call":
                return "0x12"  # less than 66 chars
            return None
        mock_rpc.side_effect = rpc_side_effect

        with self.assertRaises(NetworkError) as ctx:
            self.inspector.get_token_balance(
                address="0x000000000000000000000000000000000000dEaD",
                token_address="0xE0BE08c77f415F577A1B3A9aD7a1Df1479564ec8"
            )
        self.assertIn("Invalid return data length", str(ctx.exception))

    @patch.object(PharosInspector, "rpc_call")
    def test_get_token_balance_legitimate_zero_preserved(self, mock_rpc):
        # 32 bytes of zeros confirms legitimate 0 balance
        def rpc_side_effect(method, params, network="atlantic-testnet"):
            if method == "eth_getCode":
                return "0x60806040"
            if method == "eth_call":
                return "0x" + "0" * 64
            return None
        mock_rpc.side_effect = rpc_side_effect

        res = self.inspector.get_token_balance(
            address="0x000000000000000000000000000000000000dEaD",
            token_address="0xE0BE08c77f415F577A1B3A9aD7a1Df1479564ec8",
            decimals=6,
            symbol="USDC"
        )
        self.assertEqual(res["raw"], "0")
        self.assertEqual(res["formatted"], "0")

    # -------------------------------------------------------------------------
    # 7. Task 1 Contract Multi-State Inspection Tests
    # -------------------------------------------------------------------------

    @patch.object(PharosInspector, "rpc_call")
    def test_get_contract_state_success_mocked(self, mock_rpc):
        name_hex = (
            "0x"
            + "0000000000000000000000000000000000000000000000000000000000000020"
            + "0000000000000000000000000000000000000000000000000000000000000008"
            + "55534420436f696e000000000000000000000000000000000000000000000000"
        )
        symbol_hex = (
            "0x"
            + "0000000000000000000000000000000000000000000000000000000000000020"
            + "0000000000000000000000000000000000000000000000000000000000000004"
            + "5553444300000000000000000000000000000000000000000000000000000000"
        )
        decimals_hex = "0x" + "0" * 63 + "6"
        supply_hex = "0x00000000000000000000000000000000000000000000000000000002540be400"  # 10,000,000,000 (10k USDC)
        bal_hex = "0x000000000000000000000000000000000000000000000000000000000459e440"     # 73,000,000 (73 USDC)

        def rpc_side_effect(method, params, network="atlantic-testnet"):
            if method == "eth_getCode":
                return "0x608060405234"
            if method == "eth_blockNumber":
                return "0x1de981c"  # block 31,365,148
            if method == "eth_call":
                data = params[0].get("data", "")
                if data == "0x06fdde03":
                    return name_hex
                if data == "0x95d89b41":
                    return symbol_hex
                if data == "0x313ce567":
                    return decimals_hex
                if data == "0x18160ddd":
                    return supply_hex
                if data.startswith("0x70a08231"):
                    return bal_hex
            return None

        mock_rpc.side_effect = rpc_side_effect

        contract_addr = "0xE0BE08c77f415F577A1B3A9aD7a1Df1479564ec8"
        res = self.inspector.get_contract_state(contract_addr)

        self.assertEqual(res["contractAddress"], contract_addr)
        self.assertEqual(res["blockNumber"], 31365148)
        self.assertTrue(res["hasBytecode"])
        self.assertGreater(res["bytecodeSizeBytes"], 0)

        s = res["stateValues"]
        self.assertEqual(s["name"], "USD Coin")
        self.assertEqual(s["symbol"], "USDC")
        self.assertEqual(s["decimals"], 6)
        self.assertEqual(s["totalSupply"]["formatted"], "10000 USDC")
        self.assertEqual(s["balanceOf"]["formatted"], "73 USDC")
        self.assertIn("addressDependencyExplanation", s["balanceOf"])

    @patch.object(PharosInspector, "query_hosted_mcp")
    def test_get_contract_state_mcp_mocked(self, mock_mcp):
        def mcp_side_effect(tool_name, args):
            if tool_name == "get_code":
                return {"content": [{"type": "text", "text": json.dumps({"code": "0x60806040"})}]}
            if tool_name == "get_block_number":
                return {"content": [{"type": "text", "text": json.dumps({"blockNumber": "20213600"})}]}
            if tool_name == "eth_call":
                data = args["transaction"]["data"]
                if data == "0x06fdde03":
                    return {"content": [{"type": "text", "text": json.dumps({"result": "0x" + "0"*62 + "20" + "0"*63 + "4" + "5750524f" + "0"*56})}]}
                if data == "0x95d89b41":
                    return {"content": [{"type": "text", "text": json.dumps({"result": "0x" + "0"*62 + "20" + "0"*63 + "5" + "5750524f53" + "0"*54})}]}
                if data == "0x313ce567":
                    return {"content": [{"type": "text", "text": json.dumps({"result": "0x" + "0"*62 + "12"})}]}  # 18
                if data == "0x18160ddd":
                    return {"content": [{"type": "text", "text": json.dumps({"result": "0x" + "0"*60 + "1000"})}]}
                if data.startswith("0x70a08231"):
                    return {"content": [{"type": "text", "text": json.dumps({"result": "0x" + "0"*64})}]}
            return {}

        mock_mcp.side_effect = mcp_side_effect

        res = self.inspector.get_contract_state(
            "0x52c48d4213107b20bc583832b0d951fb9ca8f0b0",
            network="mainnet",
            use_mcp=True
        )
        self.assertEqual(res["blockNumber"], 20213600)
        self.assertIn("Hosted Chain MCP", res["queryEngine"])
        s = res["stateValues"]
        self.assertEqual(s["decimals"], 18)
        self.assertEqual(s["balanceOf"]["raw"], "0")

    # -------------------------------------------------------------------------
    # 8. RPC Transport & Failure Modes Tests
    # -------------------------------------------------------------------------

    @patch.object(PharosInspector, "rpc_call")
    def test_mocked_native_balance(self, mock_rpc):
        mock_rpc.return_value = "0x1bc16d674ec80000"  # 2 ETH in hex
        res = self.inspector.get_native_balance("0x000000000000000000000000000000000000dEaD", network="atlantic-testnet")
        self.assertEqual(res["balanceWei"], "2000000000000000000")
        self.assertEqual(res["formatted"], "2")
        self.assertEqual(res["symbol"], "PHRS")

    @patch.object(PharosInspector, "rpc_call")
    def test_mocked_rpc_error_handling(self, mock_rpc):
        mock_rpc.side_effect = NetworkError("RPC Rate limit exceeded")
        with self.assertRaises(NetworkError):
            self.inspector.get_chain_status(network="atlantic-testnet")

    @patch("urllib.request.urlopen")
    def test_rpc_call_malformed_json_raises(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"<html>502 Bad Gateway</html>"
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        with self.assertRaises(NetworkError) as ctx:
            self.inspector.rpc_call("eth_blockNumber", [])
        self.assertIn("Malformed JSON response", str(ctx.exception))

    @patch("urllib.request.urlopen")
    def test_rpc_call_timeout_raises(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.URLError("timed out")

        with self.assertRaises(NetworkError) as ctx:
            self.inspector.rpc_call("eth_blockNumber", [])
        self.assertIn("RPC Connection Error", str(ctx.exception))

    @patch("urllib.request.urlopen")
    def test_rpc_call_server_error_payload_raises(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "error": {"code": -32000, "message": "execution reverted"}
        }).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        with self.assertRaises(NetworkError) as ctx:
            self.inspector.rpc_call("eth_call", [{}, "latest"])
        self.assertIn("execution reverted", str(ctx.exception))


# -----------------------------------------------------------------------------
# Live Network Tests (Gated by PHAROS_LIVE_TESTS=1 or --live flag)
# -----------------------------------------------------------------------------

class TestInspectorLiveNetwork(unittest.TestCase):
    """Live network read-only integration tests against Atlantic Testnet & Hosted MCP."""

    @classmethod
    def setUpClass(cls):
        if os.environ.get("PHAROS_LIVE_TESTS") != "1":
            raise unittest.SkipTest("Live network integration tests disabled by default. Set PHAROS_LIVE_TESTS=1 or pass --live to run.")
        cls.inspector = PharosInspector(assets_dir=ASSETS_DIR)

    def test_live_atlantic_status(self):
        """Verify connection to live Atlantic Testnet RPC (Chain ID 688689)."""
        try:
            status = self.inspector.get_chain_status(network="atlantic-testnet")
            self.assertEqual(status["configuredChainId"], 688689)
            self.assertEqual(status["reportedChainId"], 688689)
            self.assertTrue(status["chainIdMatch"])
            self.assertGreater(status["blockNumber"], 0)
            print(f"\n[LIVE] Atlantic Block Height: {status['blockNumber']:,} (Chain ID: {status['reportedChainId']})")
        except NetworkError as e:
            self.skipTest(f"Live Atlantic RPC unavailable: {e}")

    def test_live_atlantic_native_balance(self):
        """Query harmless burn address 0x000...dEaD on live Atlantic Testnet."""
        try:
            burn_addr = "0x000000000000000000000000000000000000dEaD"
            res = self.inspector.get_native_balance(burn_addr, network="atlantic-testnet")
            self.assertEqual(res["address"], burn_addr)
            self.assertEqual(res["symbol"], "PHRS")
            print(f"[LIVE] Burn Address Balance: {res['formatted']} {res['symbol']}")
        except NetworkError as e:
            self.skipTest(f"Live Atlantic RPC unavailable: {e}")

    def test_live_hosted_mcp(self):
        """Query get_chain_info via live Hosted Pharos MCP endpoint."""
        try:
            res = self.inspector.query_hosted_mcp("get_chain_info", {})
            self.assertIn("content", res)
            text = res["content"][0]["text"]
            self.assertTrue(len(text) > 0)
            print(f"[LIVE] Hosted MCP get_chain_info result:\n{text}")
        except NetworkError as e:
            self.skipTest(f"Hosted MCP endpoint unavailable: {e}")

    def test_live_atlantic_contract_usdc(self):
        """Task 1 live inspection on Atlantic USDC (0xE0BE08c77f415F577A1B3A9aD7a1Df1479564ec8)."""
        try:
            usdc_addr = "0xE0BE08c77f415F577A1B3A9aD7a1Df1479564ec8"
            res = self.inspector.get_contract_state(usdc_addr, network="atlantic-testnet")
            self.assertEqual(res["contractAddress"], usdc_addr)
            self.assertGreater(res["blockNumber"], 0)
            s = res["stateValues"]
            self.assertEqual(s["name"], "USD Coin")
            self.assertEqual(s["symbol"], "USDC")
            self.assertEqual(s["decimals"], 6)
            print(f"\n[LIVE TASK 1 SHOWCASE] Read at Block {res['blockNumber']:,}:")
            print(f"Name: {s['name']} | Symbol: {s['symbol']} | Decimals: {s['decimals']}")
            print(f"Total Supply: {s['totalSupply']['formatted']}")
            print(f"Burn Address Balance: {s['balanceOf']['formatted']}")
        except NetworkError as e:
            self.skipTest(f"Live Atlantic RPC unavailable: {e}")

    def test_live_mcp_contract_read(self):
        """Task 1 live inspection via Pharos Hosted Chain MCP (https://mcp.pharos.xyz/mcp)."""
        try:
            pacific_usdc = "0xc879c018db60520f4355c26ed1a6d572cdac1815"
            res = self.inspector.get_contract_state(pacific_usdc, network="mainnet", use_mcp=True)
            self.assertEqual(res["contractAddress"], pacific_usdc)
            self.assertIn("Hosted Chain MCP", res["queryEngine"])
            self.assertGreater(res["blockNumber"], 0)
            s = res["stateValues"]
            self.assertEqual(s["name"], "USDC")
            self.assertEqual(s["symbol"], "USDC")
            self.assertEqual(s["decimals"], 6)
            self.assertTrue(len(s["totalSupply"]["formatted"]) > 0)
            self.assertTrue(len(s["balanceOf"]["formatted"]) > 0)
            print(f"\n[LIVE TASK 1 MCP SHOWCASE] Read via Chain MCP at Block {res['blockNumber']:,}:")
            print(f"Name: {s['name']} | Symbol: {s['symbol']} | Decimals: {s['decimals']}")
            print(f"Total Supply: {s['totalSupply']['formatted']}")
            print(f"Burn Address Balance: {s['balanceOf']['formatted']}")
        except NetworkError as e:
            self.skipTest(f"Hosted MCP endpoint unavailable: {e}")


if __name__ == "__main__":
    if "--live" in sys.argv:
        sys.argv.remove("--live")
        os.environ["PHAROS_LIVE_TESTS"] = "1"

    unittest.main(verbosity=2)

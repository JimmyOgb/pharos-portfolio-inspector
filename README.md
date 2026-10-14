# Pharos On-Chain Data & Portfolio Inspector Skill

A production-ready, read-only AI agent skill for querying live on-chain balances, smart contract states, ERC-20 token holdings, transaction receipts, and block heights on the Pharos blockchain (Atlantic Testnet and Pacific Mainnet).

Built for **Pharos Season of AI — Agent Arena (Task 1: `read-contract-state`)**.

---

## Arena Task 1 Showcase: Read Contract State

This tool directly satisfies all four official evaluation criteria for **Arena Task 1: Read Contract State**:

| Official Requirement | Implementation Status | How it is Fulfilled |
|---|---|---|
| **01. Reads at least 3 values from 1 contract** | `FULFILLED` | Reads **5 distinct values** from one contract: `name()`, `symbol()`, `decimals()`, `totalSupply()`, and `balanceOf(address)`. |
| **02. Shows contract address and block number** | `FULFILLED` | Explicitly prints the contract address and the exact block height at which the state was fetched. |
| **03. Formats raw values for humans** | `FULFILLED` | Applies token decimals (e.g. 6 decimals for USDC), formats token amounts with symbols, labels addresses, and explains holder-dependent balances. |
| **04. Short README with contract, steps, output** | `FULFILLED` | Fully documented below with verified contract source, run steps, and actual terminal output. |

### Chosen Contract Showcase
- **Asset**: USD Coin (`USDC`) on Pharos Atlantic Testnet
- **Contract Address**: `0xE0BE08c77f415F577A1B3A9aD7a1Df1479564ec8`
- **Source Verification**: Verified in official [Pharos Skill Engine repository](https://github.com/PharosNetwork/pharos-skill-engine/blob/main/assets/tokens.json) and confirmed on-chain on Atlantic Testnet (`eth_getCode` returns 6,005 bytes of deployed EVM bytecode).
- **Network**: Atlantic Testnet (Chain ID `688689`, RPC `https://atlantic.dplabs-internal.com`)

### Reproduction Command
```bash
python scripts/inspector.py contract 0xE0BE08c77f415F577A1B3A9aD7a1Df1479564ec8
```

### Actual Sample Terminal Output
```text
=== Pharos On-Chain Data Inspector ===
Contract:       0xE0BE08c77f415F577A1B3A9aD7a1Df1479564ec8
Network:        atlantic-testnet
Query Engine:   Direct JSON-RPC (https://atlantic.dplabs-internal.com)
Read at Block:  31,405,579
Bytecode Size:  6,005 bytes

--- Contract State Values (Decoded & Formatted) ---
1. Token Name:    USD Coin
2. Token Symbol:  USDC
3. Decimals:      6
4. Total Supply:  1000000000000000000000 USDC (Raw: 1000000000000000000000000000)
5. Holder Balance: 73 USDC (Raw: 73000000)
   Target Holder: Default Harmless Burn Fixture (0x000000000000000000000000000000000000dEaD)
   Note:          This value reflects the balance held by the selected address (0x000000000000000000000000000000000000dEaD), not an internal balance of the token contract itself.
======================================
```

### Machine-Readable JSON Mode (for AI Agents)
```bash
python scripts/inspector.py --json contract 0xE0BE08c77f415F577A1B3A9aD7a1Df1479564ec8
```
Output:
```json
{
  "contractAddress": "0xE0BE08c77f415F577A1B3A9aD7a1Df1479564ec8",
  "network": "atlantic-testnet",
  "queryEngine": "Direct JSON-RPC (https://atlantic.dplabs-internal.com)",
  "blockNumber": 31405607,
  "hasBytecode": true,
  "bytecodeSizeBytes": 6005,
  "stateValues": {
    "name": "USD Coin",
    "symbol": "USDC",
    "decimals": 6,
    "totalSupply": {
      "raw": "1000000000000000000000000000",
      "formatted": "1000000000000000000000 USDC"
    },
    "balanceOf": {
      "holderAddress": "0x000000000000000000000000000000000000dEaD",
      "holderLabel": "Default Harmless Burn Fixture (0x000000000000000000000000000000000000dEaD)",
      "raw": "73000000",
      "formatted": "73 USDC",
      "addressDependencyExplanation": "This value reflects the balance held by the selected address (0x000000000000000000000000000000000000dEaD), not an internal balance of the token contract itself."
    }
  }
}
```

---

## Features
- **Task 1 Multi-State Inspection**: Reads contract name, symbol, decimals, total supply, and holder balance with block number and address labelling.
- **Bytecode & Error Integrity**: Verifies deployed bytecode using `eth_getCode`. Distinguishes un-deployed addresses, empty reverts (`0x`), and malformed responses from legitimate zero balances.
- **Dual Query Engine**: Direct EVM JSON-RPC support + Hosted Pharos Chain MCP client (`https://mcp.pharos.xyz/mcp`).
- **Zero Cost & Zero Risk**: Purely read-only; requires no wallet funding, no private keys, and no gas.
- **Strict Validation**: Hardened regex validation for all EVM addresses (`^0x[0-9a-fA-F]{40}$`) and transaction hashes (`^0x[0-9a-fA-F]{64}$`).
- **Multi-Asset Scans**: Inspects native PHRS/PROS plus registered testnet tokens (USDC, USDT, WBTC, WETH, WPHRS).

---

## Package Structure
```
skills/pharos-portfolio-inspector/
├── SKILL.md                 # Agent entry point & Capability Index
├── README.md                # Human & reviewer documentation
├── assets/
│   ├── networks.json        # Official Pharos network configs (Atlantic & Mainnet)
│   └── tokens.json          # Known official ERC-20 tokens registry
├── references/
│   └── query.md             # Detailed command templates & parsing rules
├── scripts/
│   └── inspector.py         # Standalone CLI / Agent tool
└── tests/
    └── test_inspector.py    # Automated test suite (Mocked unit + Live integration)
```

---

## Additional Capabilities

### 1. Check Node & Network Status
```bash
python scripts/inspector.py status
```

### 2. Check Native Balance
```bash
python scripts/inspector.py balance 0x000000000000000000000000000000000000dEaD
```

### 3. Check Complete Wallet Portfolio
```bash
python scripts/inspector.py portfolio 0x000000000000000000000000000000000000dEaD
```

### 4. Query Hosted Pharos MCP Directly
```bash
python scripts/inspector.py mcp get_chain_info
```

---

## Running the Automated Test Suite

### Offline Mocked Unit Tests (Instantaneous, Zero Network Calls)
```bash
python -m unittest tests/test_inspector.py -v
```
*Executes 29 deterministic unit tests covering ABI decoding, precision math, input validation, RPC timeout handling, and misleading zero-balance regressions in under 0.1 seconds.*

### Live Integration Tests (Against Live Atlantic Testnet & Hosted MCP)
```bash
python tests/test_inspector.py --live
```
*Executes all 33 tests including live block height, native balance query, hosted MCP handshake, and Atlantic USDC contract read.*

---

## Limitations
1. **Read-Only Scope**: This skill does not sign or broadcast state-changing transactions. It only queries view/pure EVM methods.
2. **Standard ERC-20 Interface**: Contract multi-state inspection relies on standard ERC-20 view methods (`name`, `symbol`, `decimals`, `totalSupply`, `balanceOf`). Non-standard or custom contracts that omit these selectors will return error descriptions.
3. **Bytecode Required**: Target addresses must be deployed smart contracts. EOAs or un-deployed contract addresses are cleanly caught and rejected with an explicit error.

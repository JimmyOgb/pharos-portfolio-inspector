# Pharos On-Chain Data & Portfolio Inspector Skill

A production-ready, read-only AI agent skill for querying live on-chain balances, smart contract states, ERC-20 token holdings, transaction receipts, and block heights on the Pharos blockchain (Atlantic Testnet and Pacific Mainnet).

Built for **Pharos Season of AI — Agent Arena (Task 1: `read-contract-state`)**.

---

## Arena Task 1 Showcase: Read Contract State via Pharos Chain MCP

This tool directly satisfies all four official evaluation criteria for **Arena Task 1: Read Contract State**:

| Official Requirement | Implementation Status | How it is Fulfilled |
|---|---|---|
| **01. Reads at least 3 values from 1 contract via Chain MCP** | `FULFILLED` | Reads **5 distinct values** from one contract through Pharos Chain MCP (`eth_call`): `name()`, `symbol()`, `decimals()`, `totalSupply()`, and `balanceOf(address)`. |
| **02. Shows contract address and block number** | `FULFILLED` | Explicitly queries and displays the contract address and the exact block height via Chain MCP `get_block_number`. |
| **03. Formats raw values for humans** | `FULFILLED` | Applies token decimals (e.g. 6 decimals for USDC), formats amounts with symbols, labels addresses, and explains holder-dependent balances. |
| **04. Short README with contract, steps, output** | `FULFILLED` | Fully documented below with verified contract source, run steps, and actual terminal output. |

### Primary Showcase: Pharos Chain MCP
- **Contract Asset**: USD Coin (`USDC`) on Pharos Pacific
- **Contract Address**: `0xc879c018db60520f4355c26ed1a6d572cdac1815`
- **Source Verification**: Registered in official [Pharos Skill Engine token registry](https://github.com/PharosNetwork/pharos-skill-engine/blob/main/assets/tokens.json) and verified on-chain via Pharos Chain MCP `get_code` (1,798 bytes of deployed EVM runtime bytecode).
- **Query Engine**: **Pharos Hosted Chain MCP** (`https://mcp.pharos.xyz/mcp`, Streamable HTTP)
- **Chain ID**: `1672` (Pharos Pacific)

#### Reproduction Command (Chain MCP)
```bash
python scripts/inspector.py contract 0xc879c018db60520f4355c26ed1a6d572cdac1815 --mcp
```

#### Actual Sample Terminal Output (Chain MCP)
```text
=== Pharos On-Chain Data Inspector ===
Contract:       0xc879c018db60520f4355c26ed1a6d572cdac1815
Network:        mainnet
Query Engine:   Hosted Chain MCP (https://mcp.pharos.xyz/mcp)
Read at Block:  20,220,938
Bytecode Size:  1,798 bytes

--- Contract State Values (Decoded & Formatted) ---
1. Token Name:    USDC
2. Token Symbol:  USDC
3. Decimals:      6
4. Total Supply:  22795206.851289 USDC (Raw: 22795206851289)
5. Holder Balance: 0.000904 USDC (Raw: 904)
   Target Holder: Default Harmless Burn Fixture (0x000000000000000000000000000000000000dEaD)
   Note:          This value reflects the balance held by the selected address (0x000000000000000000000000000000000000dEaD), not an internal balance of the token contract itself.
======================================
```

#### Machine-Readable JSON Mode (Chain MCP)
```bash
python scripts/inspector.py --json contract 0xc879c018db60520f4355c26ed1a6d572cdac1815 --mcp
```
Output:
```json
{
  "contractAddress": "0xc879c018db60520f4355c26ed1a6d572cdac1815",
  "network": "mainnet",
  "queryEngine": "Hosted Chain MCP (https://mcp.pharos.xyz/mcp)",
  "blockNumber": 20220938,
  "hasBytecode": true,
  "bytecodeSizeBytes": 1798,
  "stateValues": {
    "name": "USDC",
    "symbol": "USDC",
    "decimals": 6,
    "totalSupply": {
      "raw": "22795206851289",
      "formatted": "22795206.851289 USDC"
    },
    "balanceOf": {
      "holderAddress": "0x000000000000000000000000000000000000dEaD",
      "holderLabel": "Default Harmless Burn Fixture (0x000000000000000000000000000000000000dEaD)",
      "raw": "904",
      "formatted": "0.000904 USDC",
      "addressDependencyExplanation": "This value reflects the balance held by the selected address (0x000000000000000000000000000000000000dEaD), not an internal balance of the token contract itself."
    }
  }
}
```

---

### Secondary Showcase: Atlantic Testnet Direct JSON-RPC (Fallback)
- **Asset**: USD Coin (`USDC`) on Pharos Atlantic Testnet
- **Contract Address**: `0xE0BE08c77f415F577A1B3A9aD7a1Df1479564ec8`
- **Network**: Atlantic Testnet (Chain ID `688689`, RPC `https://atlantic.dplabs-internal.com`)
- **Command**:
  ```bash
  python scripts/inspector.py contract 0xE0BE08c77f415F577A1B3A9aD7a1Df1479564ec8
  ```

---

## Arena Task 2 Showcase: Continuous Event/Log Monitor via Pharos Chain MCP

This skill directly satisfies all four official evaluation criteria for **Arena Task 2: Event/Log Monitor**:

| Official Requirement | Implementation Status | How it is Fulfilled |
|---|---|---|
| **01. Uses Chain MCP log queries filtered by contract and signature** | `FULFILLED` | Queries the hosted Chain MCP server (`get_logs` tool) filtering by both contract address (`0xc879c018db60520f4355c26ed1a6d572cdac1815`) and 32-byte event signature topic (`0xddf252ad...` for `Transfer`). |
| **02. Runs continuously and reports only new events with no duplicates** | `FULFILLED` | Features a continuous block-by-block polling loop with a bounded FIFO deduplication cache tracking `(transactionHash, logIndex)` tuples across polling boundaries. |
| **03. Decodes each event into readable fields** | `FULFILLED` | Decodes 32-byte indexed EVM topics into 20-byte checksummed addresses (`from`, `to`), parses raw integer values from hex data, applies token decimal scaling (e.g. 6 decimals for USDC), labels symbols, and extracts block number and tx hash. |
| **04. Demonstrated catching at least one live or test event** | `FULFILLED` | Successfully caught and decoded multiple live ERC-20 `Transfer` events on Pharos Pacific Mainnet via Chain MCP, verified with block height, transaction hashes, and explorer proof links. |

### Live On-Chain Event Proofs (Pharos Pacific Mainnet)
- **Target Contract**: USD Coin (`USDC`) on Pharos Pacific (`0xc879c018db60520f4355c26ed1a6d572cdac1815`)
- **Event Signature**: `Transfer(address,address,uint256)` (`0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef`)
- **Query Engine**: **Pharos Hosted Chain MCP** (`https://mcp.pharos.xyz/mcp`)
- **Live Proof 1**:
  - **Block**: `20,256,421`
  - **Tx Hash**: `0xbc48b05ba38577188b7f38ee72081d08c48c513c85b182443908db3945709a60`
  - **Explorer Proof**: [https://www.pharosscan.xyz/tx/0xbc48b05ba38577188b7f38ee72081d08c48c513c85b182443908db3945709a60](https://www.pharosscan.xyz/tx/0xbc48b05ba38577188b7f38ee72081d08c48c513c85b182443908db3945709a60)
  - **From**: `0x912c9ade24d44d8922f0866d8dcb079f1363f647`
  - **To**: `0x1f3546a29eec2102c8d52e21a45114124014c85c`
  - **Decoded Amount**: `58.544944 USDC` (Raw base units: `58544944`)
- **Live Proof 2**:
  - **Block**: `20,256,425`
  - **Tx Hash**: `0x430f6728555f50f405a0a0351965a0550cae597da9dcf2612ea6725e18dc43d6`
  - **Explorer Proof**: [https://www.pharosscan.xyz/tx/0x430f6728555f50f405a0a0351965a0550cae597da9dcf2612ea6725e18dc43d6](https://www.pharosscan.xyz/tx/0x430f6728555f50f405a0a0351965a0550cae597da9dcf2612ea6725e18dc43d6)
  - **From**: `0x912c9ade24d44d8922f0866d8dcb079f1363f647`
  - **To**: `0x1f3546a29eec2102c8d52e21a45114124014c85c`
  - **Decoded Amount**: `58.533766 USDC` (Raw base units: `58533766`)

#### Continuous Monitoring Command (Chain MCP)
```bash
python scripts/monitor.py --contract 0xc879c018db60520f4355c26ed1a6d572cdac1815
```

#### Historical Replay & Bounded Demo Command
```bash
python scripts/monitor.py --from-block 20256420 --to-block 20256430 --max-events 3
```
Output:
```text
======================================================================
 Pharos On-Chain Event & Log Monitor -- Task 2 Compliance
======================================================================
 Target Network:     mainnet
 Query Engine:       Pharos Hosted Chain MCP
 Contract Filter:    0xc879c018db60520f4355c26ed1a6d572cdac1815
 Event Filter:       Transfer
 Starting Block:     20,256,420
 Ending Block:       20,256,430 (Bounded Replay)
 Max Events Limit:   3
======================================================================

 [Block #20,256,421] TRANSFER:    58.544944 USDC  | 0x912c9a...63f647 -> 0x1f3546...14c85c | Tx: 0xbc48b05b...45709a60
 [Block #20,256,425] TRANSFER:    58.533766 USDC  | 0x912c9a...63f647 -> 0x1f3546...14c85c | Tx: 0x430f6728...18dc43d6
 [Block #20,256,428] TRANSFER:    77.642255 USDC  | 0x936564...68b470 -> 0x912c9a...63f647 | Tx: 0xb64762ad...b7f15492

[Completed] Processed 3 events without duplicates.
```

#### Machine-Readable JSON Streaming Output Mode
```bash
python scripts/monitor.py --from-block 20256420 --to-block 20256425 --max-events 1 --json
```
Output:
```json
{
  "blockNumber": 20256421,
  "transactionHash": "0xbc48b05ba38577188b7f38ee72081d08c48c513c85b182443908db3945709a60",
  "logIndex": 0,
  "contractAddress": "0xc879c018db60520f4355c26ed1a6d572cdac1815",
  "topic0": "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
  "eventName": "Transfer",
  "from": "0x912c9ade24d44d8922f0866d8dcb079f1363f647",
  "to": "0x1f3546a29eec2102c8d52e21a45114124014c85c",
  "rawAmount": "58544944",
  "formattedAmount": "58.544944",
  "symbol": "USDC",
  "decimals": 6,
  "summary": "Transfer 58.544944 USDC from 0x912c9ade24d44d8922f0866d8dcb079f1363f647 to 0x1f3546a29eec2102c8d52e21a45114124014c85c",
  "explorerUrl": "https://www.pharosscan.xyz/tx/0xbc48b05ba38577188b7f38ee72081d08c48c513c85b182443908db3945709a60"
}
```

---

## Features
- **Task 1 Multi-State Inspection**: Reads contract name, symbol, decimals, total supply, and holder balance with block number and address labelling.
- **Task 2 Continuous Event Monitoring**: Real-time event log querying via Chain MCP with deduplication, sliding window chunking, and rich field decoding.
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
│   ├── inspector.py         # Multi-state & portfolio CLI tool (Task 1)
│   └── monitor.py           # Continuous event log monitor CLI tool (Task 2)
└── tests/
    ├── test_inspector.py    # Test suite for inspector (Task 1)
    └── test_monitor.py      # Test suite for event monitor (Task 2)
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
python -m unittest discover tests -v
```
*Executes 48 deterministic unit tests (29 for Task 1, 19 for Task 2) covering ABI decoding, precision math, topic address extraction, event signature resolution, deduplication FIFO eviction, log filtering, and window chunking in ~0.15 seconds.*

To run only Task 2 monitor tests:
```bash
python -m unittest tests/test_monitor.py -v
```

### Live Integration Tests (Against Live Pacific Mainnet, Atlantic Testnet & Hosted MCP)
```bash
# On Linux / macOS / Bash:
PHAROS_LIVE_TESTS=1 python -m unittest discover tests -v

# On Windows PowerShell:
$env:PHAROS_LIVE_TESTS="1"; python -m unittest discover tests -v
```
*Executes all 53 tests including live block height, native balance query, hosted Chain MCP handshake, Atlantic USDC contract read, and live Pacific USDC event log monitoring.*

---

## Limitations
1. **Read-Only Scope**: This skill does not sign or broadcast state-changing transactions. It only queries view/pure EVM methods and historical/streaming event logs.
2. **Chain MCP Block Window Limit**: In accordance with the upstream Pharos RPC and hosted Chain MCP constraints, individual `get_logs` queries are limited to $\le 1,000$ blocks. The monitor automatically pages larger historical spans in chunks of $\le 1,000$ blocks.
3. **Standard ERC-20 Interface**: Contract multi-state inspection and event decoding natively decode standard ERC-20 view methods (`name`, `symbol`, `decimals`, `totalSupply`, `balanceOf`) and events (`Transfer`, `Approval`). Arbitrary custom events are safely preserved and reported with raw topic hashes and data fields.
4. **Bytecode Required**: Target addresses for state calls must be deployed smart contracts. EOAs or un-deployed contract addresses are cleanly caught and rejected with an explicit error.


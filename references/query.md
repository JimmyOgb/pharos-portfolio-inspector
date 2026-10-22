# Portfolio & On-Chain Query Operation Instructions

This file contains detailed instructions for all read-only query operations on the Pharos chain, covering network status checks, native token balance queries, ERC-20 token holdings, complete portfolio overviews, transaction status verification, and hosted MCP tool queries.

> **Network Configuration**: The `<rpc>` parameter in all commands is read from the corresponding network's `rpcUrl` field in `assets/networks.json`. Defaults to `atlantic-testnet` (`https://atlantic.dplabs-internal.com`, Chain ID `688689`).
>
> **Native Token Symbol**: Read the native token symbol from the current network's `nativeToken` field in `assets/networks.json` (`PHRS` for Atlantic testnet, `PROS` for mainnet).
>
> **Zero Cost Guarantee**: All operations in this reference are 100% read-only (`eth_call`, `eth_getBalance`, `eth_blockNumber`, `eth_getTransactionReceipt`). No private keys, gas, wallet connections, or broadcast transactions are ever used.

---

## 1. Network Status & Node Synchronization

### Overview
Retrieves the latest block height, client version, and network configuration to verify node availability before executing agent workflows.

### Command Template
```bash
python scripts/inspector.py --network <network> status
```

### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `--network` | string | No | Target network: `atlantic-testnet` (default) or `mainnet` |
| `--json` | flag | No | Outputs raw JSON response for automated agent consumption |

### Output Parsing
| Field | Description |
|-------|-------------|
| `network` | The network queried (`atlantic-testnet` or `mainnet`) |
| `blockNumber` | Current synchronized block height on Pharos |
| `reportedChainId` | Chain ID returned directly by JSON-RPC |
| `chainIdMatch` | Boolean indicating whether reported chain ID matches canonical `assets/networks.json` |
| `clientVersion` | Full node software identifier |

### Error Handling
| Error Signature | Cause | Suggested Action |
|---|---|---|
| `RPC Connection Error` | RPC endpoint unreachable | Verify internet connectivity or test with fallback RPC |
| `Unknown network` | Typo in network parameter | Specify `--network atlantic-testnet` or `--network mainnet` |

> **Agent Guidelines**:
> 1. Check network status before executing time-sensitive or block-dependent operations.
> 2. Verify that `chainIdMatch` is `true`.

---

## 2. Address Balance Query

### Overview
Queries the native token balance (`PHRS` on Atlantic testnet, `PROS` on mainnet) of any EVM address.

### Command Template
```bash
python scripts/inspector.py --network <network> balance <address>
```

### Parameters
| Parameter | Type | Required | Description |
|---|---|---|---|
| `<address>` | string | Yes | Target 42-character EVM address (`0x` + 40 hex) |
| `--network` | string | No | Target network (defaults to `atlantic-testnet`) |

### Output Parsing
| Field | Description |
|---|---|
| `address` | Verified EVM address |
| `symbol` | Native token symbol (`PHRS` or `PROS`) |
| `formatted` | Human-readable balance formatted to 18 decimal places |
| `balanceWei` | Exact integer balance in wei (as string to prevent precision loss) |

### Error Handling
| Error Signature | Cause | Suggested Action |
|---|---|---|
| `Invalid EVM address` | Address missing `0x` prefix or has invalid length | Ensure address matches `^0x[0-9a-fA-F]{40}$` |
| `RPC Error [-32602]` | Invalid parameter passed to `eth_getBalance` | Re-check address casing and formatting |

> **Agent Guidelines**:
> 1. Always display the balance with its native token symbol (`PHRS` or `PROS`).
> 2. Convert amounts accurately using the 18 decimal rule.

---

## 3. ERC-20 Token Balance Query

### Overview
Executes an `eth_call` to the standard ERC-20 `balanceOf(address)` method for a specific contract.

### Command Template
```bash
python scripts/inspector.py --network <network> token <address> <token_address> --decimals <decimals> --symbol <symbol>
```

### Parameters
| Parameter | Type | Required | Description |
|---|---|---|---|
| `<address>` | string | Yes | Wallet owner address |
| `<token_address>` | string | Yes | ERC-20 token contract address |
| `--decimals` | int | No | Token decimals (default: 18, or 6 for USDC/USDT) |
| `--symbol` | string | No | Display symbol (e.g. `USDC`) |

### Output Parsing
| Field | Description |
|---|---|
| `tokenAddress` | Contract address queried |
| `formatted` | Decimal-adjusted token balance |
| `raw` | Raw token integer balance |

---

## 4. Wallet Portfolio Overview

### Overview
Scans the native balance and all registered official tokens in `assets/tokens.json` to produce a comprehensive asset overview.

### Command Template
```bash
python scripts/inspector.py --network <network> portfolio <address>
```

### Registered Assets Monitored (Atlantic Testnet)
* Native `PHRS`
* `USDC` (`0xE0BE08c77f415F577A1B3A9aD7a1Df1479564ec8`, 6 decimals)
* `USDT` (`0xE7E84B8B4f39C507499c40B4ac199B050e2882d5`, 6 decimals)
* `WBTC` (`0x0c64F03EEa5c30946D5c55B4b532D08ad74638a4`, 18 decimals)
* `WETH` (`0x7d211F77525ea39A0592794f793cC1036eEaccD5`, 18 decimals)
* `WPHRS` (`0x838800b758277CC111B2d48Ab01e5E164f8E9471`, 18 decimals)

> **Agent Guidelines**:
> 1. Present a clear tabular breakdown of all non-zero token balances.
> 2. If a token call returns `0x` or reverts, clearly flag it without failing the overall query.

---

## 5. Transaction Confirmation Query

### Overview
Verifies whether a transaction has been confirmed on the Pharos blockchain and decodes its execution status (`SUCCESS` or `REVERTED`).

### Command Template
```bash
python scripts/inspector.py --network <network> tx <tx_hash>
```

### Parameters
| Parameter | Type | Required | Description |
|---|---|---|---|
| `<tx_hash>` | string | Yes | 66-character transaction hash (`0x` + 64 hex) |

### Output Parsing
| Field | Description |
|---|---|
| `isConfirmed` | `true` if receipt exists, `false` if pending or not found |
| `status` | `SUCCESS` (status `0x1`) or `REVERTED` (status `0x0`) |
| `blockNumber` | Block index containing the transaction |
| `gasUsed` | Total gas consumed |
| `explorerUrl` | Direct clickable block explorer link |

---

## 6. Hosted MCP Tool Query

### Overview
Directly accesses Pharos tools through the official hosted MCP server (`https://mcp.pharos.xyz/mcp`) using Streamable HTTP.

### Command Template
```bash
python scripts/inspector.py mcp <tool_name> --args '<json_args>'
```

### Example
```bash
python scripts/inspector.py mcp get_chain_info
python scripts/inspector.py mcp get_balance --args '{"address":"0x000000000000000000000000000000000000dEaD"}'
```

---

## 7. Smart Contract Multi-State Inspection (Arena Task 1 Compliance)

### Overview
Reads multiple state values from a single deployed contract via direct EVM JSON-RPC or Chain MCP, validates deployed bytecode, displays the block number, formats decimals for non-developers, and explains address-dependent values.

### Command Template
```bash
python scripts/inspector.py contract <contract_address> [--holder <address>] [--mcp] [--network <network>] [--json]
```

### Parameters
| Parameter | Type | Required | Description |
|---|---|---|---|
| `<contract_address>` | string | Yes | Deployed smart contract address (`0x` + 40 hex) |
| `--holder` | string | No | Target address for `balanceOf(address)` (defaults to burn fixture `0x...dEaD`) |
| `--mcp` | flag | No | Query via Pharos Hosted Chain MCP (`https://mcp.pharos.xyz/mcp`) |
| `--network` | string | No | `atlantic-testnet` (default) or `mainnet` |
| `--json` | flag | No | Output raw structured JSON for agent parsing |

### Examples
```bash
# Primary Task 1 Showcase via Pharos Hosted Chain MCP (Pharos Pacific USDC)
python scripts/inspector.py contract 0xc879c018db60520f4355c26ed1a6d572cdac1815 --mcp

# Optional Direct JSON-RPC Query on Atlantic Testnet
python scripts/inspector.py contract 0xE0BE08c77f415F577A1B3A9aD7a1Df1479564ec8
```

---

## 8. Developer Docs MCP Integration (Arena Task 3 Compliance)

### Overview
Wraps the official Pharos Developer Docs Model Context Protocol (MCP) server (`https://docs.pharos.xyz/~gitbook/mcp`) using Streamable HTTP / SSE JSON-RPC 2.0 (MCP Protocol version `2024-11-05`). Provides direct, autonomous access to official Pharos documentation search, page retrieval, and synthesized answers with citations without external dependencies or API keys ($0 cost).

### MCP Server Connection Details
* **Hosted Docs MCP URL**: `https://docs.pharos.xyz/~gitbook/mcp`
* **Transport**: Streamable HTTP / Server-Sent Events (`text/event-stream`, `application/json`)
* **Protocol Version**: `2024-11-05`
* **Server Name**: `docs.pharos.xyz/~gitbook/mcp` (`docs.pharos.xyz MCP Server` v0.27.2)
* **Authentication**: None required (public read-only)

#### Cursor / Claude Desktop Configuration
```json
{
  "mcpServers": {
    "pharos-docs": {
      "type": "http",
      "url": "https://docs.pharos.xyz/~gitbook/mcp"
    }
  }
}
```

#### Command Template
```bash
# Ask a technical question (uses Docs MCP askQuestion tool)
python scripts/docs_query.py "<question>" [--goal "<user_goal>"] [--json] [--timeout <seconds>]

# Semantic documentation search (uses Docs MCP searchDocumentation tool)
python scripts/docs_query.py --search "<search_term>"

# Fetch full page markdown (uses Docs MCP getPage tool)
python scripts/docs_query.py --page "<full_page_url>"

# Discover available Docs MCP tools
python scripts/docs_query.py --list-tools
```

### Parameters
| Parameter | Type | Required | Description |
|---|---|---|---|
| `<question>` | string | No | Technical question submitted to Docs MCP `askQuestion` tool |
| `--search` | string | No | Search query submitted to Docs MCP `searchDocumentation` tool |
| `--page` | string | No | Full URL submitted to Docs MCP `getPage` tool |
| `--list-tools` | flag | No | Discovers and prints all registered MCP tools |
| `--goal` | string | No | Developer goal context passed to MCP tool (default: agent development) |
| `--json` | flag | No | Outputs raw structured JSON for agent consumption |
| `--endpoint` | string | No | Custom Docs MCP endpoint (defaults to `https://docs.pharos.xyz/~gitbook/mcp`) |
| `--timeout` | int | No | Request timeout in seconds (default: 35) |

### Discovered Docs MCP Tools
| Tool Name | Purpose | Key Arguments |
|---|---|---|
| `askQuestion` | Synthesized answer with source page citations | `question` (string, required), `goal` (string, optional) |
| `searchDocumentation` | Search documentation returning titles, links, snippets | `query` (string, required) |
| `getPage` | Fetch full markdown content of a documentation page | `url` (string, required) |
| `sendFeedback` | Report documentation issues to the documentation team | `content` (string, required), `pageUrl` (string, required) |

### Examples
```bash
# Ask Docs MCP about Pacific Mainnet parameters
python scripts/docs_query.py "What is the RPC URL and Chain ID for Pacific Mainnet?"

# Search documentation for Atlantic RPC configuration
python scripts/docs_query.py --search "Atlantic RPC"

# Discover all tools exposed by the Docs MCP server
python scripts/docs_query.py --list-tools --json
```

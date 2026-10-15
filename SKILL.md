---
name: pharos-portfolio-inspector
description: >
  On-chain data and portfolio inspection skill for the Pharos blockchain (Atlantic Testnet and Pacific Mainnet).
  Use this skill whenever the user asks to check native PHRS or PROS balances, inspect ERC-20 token holdings (USDC, USDT, WBTC, WETH, WPHRS), verify transaction hashes, monitor block numbers, check node synchronization, or query tools via the hosted Pharos MCP server.
  This skill is 100% read-only, consumes $0, and requires zero wallet funding, zero gas, and zero private keys.
version: 0.1.0
---

# Pharos On-Chain Data & Portfolio Inspector

A packaged developer skill for AI agents interacting with the Pharos blockchain. Enables autonomous, read-only inspection of balances, tokens, blocks, and transaction statuses without exposing private keys or spending funds.

## Capability Index

| User Need | Capability | Detailed Instructions |
|---|---|---|
| Read deployed contract state via Chain MCP (Task 1) | `python scripts/inspector.py contract <contract_address> --mcp` | → `references/query.md#7-smart-contract-multi-state-inspection` |
| Monitor on-chain events via Chain MCP (Task 2) | `python scripts/monitor.py --contract <address> --event <name>` | → `README.md#arena-task-2-showcase-continuous-eventlog-monitor-via-chain-mcp` |
| View wallet portfolio / all asset holdings | `python scripts/inspector.py portfolio <address>` | → `references/query.md#4-wallet-portfolio-overview` |
| Query native balance (PHRS / PROS) | `python scripts/inspector.py balance <address>` | → `references/query.md#2-address-balance-query` |
| Query ERC-20 token balance | `python scripts/inspector.py token <address> <token>` | → `references/query.md#3-erc-20-token-balance-query` |
| Check transaction confirmation & execution status | `python scripts/inspector.py tx <tx_hash>` | → `references/query.md#5-transaction-confirmation-query` |
| Check Pharos block height & node status | `python scripts/inspector.py status` | → `references/query.md#1-network-status--node-synchronization` |
| Query official Docs via Developer Docs MCP (Task 3) | `python scripts/docs_query.py "<question>"` | → `references/query.md#8-developer-docs-agentic-query-task-3-compliance` |
| Query via Hosted Pharos MCP server | `python scripts/inspector.py mcp <tool_name>` | → `references/query.md#6-hosted-mcp-tool-query` |

---

## Network Configuration

Network parameters are stored in `assets/networks.json`:
- **Default Network**: Atlantic Testnet (`atlantic-testnet`)
  - **RPC**: `https://atlantic.dplabs-internal.com`
  - **Chain ID**: `688689` (`0xa8231`)
  - **Native Token**: `PHRS`
  - **Explorer**: `https://atlantic.pharosscan.xyz/`
- **Production Network**: Pacific Mainnet (`mainnet`)
  - **RPC**: `https://rpc.pharos.xyz`
  - **Chain ID**: `1672` (`0x688`)
  - **Native Token**: `PROS`
  - **Explorer**: `https://www.pharosscan.xyz/`
- **Hosted MCP Endpoint**: `https://mcp.pharos.xyz/mcp` (Streamable HTTP, read-only)

---

## Zero-Cost & Security Guarantee

1. **Strictly Read-Only**: This skill only invokes read methods (`eth_getBalance`, `eth_call`, `eth_blockNumber`, `eth_getTransactionReceipt`).
2. **No Private Key Access**: Under no circumstances does this skill require, ask for, or read private keys.
3. **No Wallet Connection Required**: Works directly via public JSON-RPC and hosted MCP endpoints.
4. **Input Validation**: All addresses and transaction hashes are validated before execution against EVM regex patterns (`0x[0-9a-fA-F]{40}` and `0x[0-9a-fA-F]{64}`).

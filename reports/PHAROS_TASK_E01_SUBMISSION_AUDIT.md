# Pharos Season of AI — TASK-E01 Official Submission Audit

**Audit Date**: October 14, 2026  
**Status**: Completed Investigation  
**Primary Discovery Portal**: [Pharos Agent Arena (Vercel)](https://pharos-agent-arena.vercel.app/)  
**Official Portal**: [ai.pharos.xyz](https://ai.pharos.xyz/)  
**Developer Profile**: [JimmyOgb](https://github.com/JimmyOgb)  

---

## 1. Executive Summary & Status Matrix

Our investigation of the live official infrastructure has identified the **live Pharos Agent Arena submission portal** at `https://pharos-agent-arena.vercel.app/`. 

This resolves the previously unknown submission mechanism: **the 28 tasks are live, accessible, and accept submissions individually via GitHub authentication on the portal.**

| Dimension | Finding | Status Label | Authoritative Citation |
|---|---|---|---|
| **Submission Portal Location** | Dedicated Web Application at `https://pharos-agent-arena.vercel.app/` | `VERIFIED` | [Agent Arena Portal](https://pharos-agent-arena.vercel.app/) |
| **Authentication Method** | GitHub OAuth ("Sign in with GitHub") | `VERIFIED` | [Arena Sign-In Form](https://pharos-agent-arena.vercel.app/) |
| **Task Granularity** | 28 distinct task pages, each with individual submission forms | `VERIFIED` | [Arena Task Board](https://pharos-agent-arena.vercel.app/#tasks) |
| **Points Schedule** | Easy: 50 pts, Medium: 100 pts, Hard: 200 pts | `VERIFIED` | [Arena Scoring Rules](https://pharos-agent-arena.vercel.app/) |
| **Video Walkthrough Bonus** | Exactly +50 bonus points for sharing a demo walkthrough on social media | `VERIFIED` | [Task 1 Detail Page](https://pharos-agent-arena.vercel.app/tasks/read-contract-state) |
| **Repository Requirement** | Public GitHub repository link required if code was written | `VERIFIED` | [Task Detail Requirements](https://pharos-agent-arena.vercel.app/tasks/read-contract-state) |
| **Repository Naming Rule** | No forced naming convention; descriptive naming expected | `VERIFIED` | [Task Submission Modal](https://pharos-agent-arena.vercel.app/tasks/read-contract-state) |
| **Anvita Flow Dependency** | Optional; NOT a mandatory gatekeeper for SkillEngine/MCP submissions | `VERIFIED` | [Arena Task Specs](https://pharos-agent-arena.vercel.app/) |
| **Eligibility of TASK-E01** | Qualifies directly as **Task 1: Read Contract State** (Easy / 50 pts) with minor adjustments | `INFERRED` | [Task 1 Spec](https://pharos-agent-arena.vercel.app/tasks/read-contract-state) |

---

## 2. Official Submission Protocol

### A. Submission Platform
* **Live Arena URL**: `https://pharos-agent-arena.vercel.app/`
* **Sign-in Requirement**: Builders authenticate using their personal GitHub account via OAuth (`$ACTION_ID_404d6f1f5f4eed089afabcad39331a4508a6a2c744`).
* **Submissions per Task**: Each of the 28 tasks hosts its own submission drawer (`/tasks/<task-slug>`).

### B. Required Submission Deliverables (Evidence)
For any code build, the submission form requires three specific artifacts:
1. **Proof Link**: An accessible URL reviewers can inspect (e.g. an `ai.pharos.xyz` session share link, an Atlantic Testnet transaction hash on `atlantic.pharosscan.xyz`, or a deployed demo URL).
2. **Repository Link**: A public GitHub repository URL containing the source code, `SKILL.md`, and `README.md`.
3. **Walkthrough Video Link (Optional for +50 Bonus Points)**: A public video link (YouTube, X/Twitter, or Loom) walking through the build, setup, and live execution.

### C. Review & Scoring Workflow
* **Automated vs. Manual**:
  - Sign-in and submission tracking are automated via the Vercel Arena database.
  - Task evaluation is performed by **human reviewers** who score submissions directly against the published 4-point requirement checklist for that task.
  - Reviewers assign base points (50, 100, or 200), verify the video link for the +50 bonus, and can award partial points if checklist items are missing.

---

## 3. The 28 Official Tasks Breakdown

The 28 tasks are categorized across 10 tracks:

### Easy Tier (50 Base Points + 50 Video Bonus = 100 Points Max)
1. `read-contract-state`: Read a smart contract's state via Chain MCP (Chain MCP)
2. `event-log-monitor`: Build a small monitor that watches for a specific on-chain event/log via Chain MCP (Chain MCP)
3. `docs-mcp-onboarding`: Self-onboard into `ai.pharos.xyz` using only Developer Docs MCP (Developer Docs MCP)
4. `doc-search-cli`: Build a small wrapper/tool on top of Developer Docs MCP (Developer Docs MCP)
5. `on-chain-alert-bot`: Watches for a price threshold, large transfer, or contract call and notifies (Trading / Monitoring)
6. `dapp-support-agent`: Explains why a transaction failed, on request (Support / Reporting)

### Medium Tier (100 Base Points + 50 Video Bonus = 150 Points Max)
7. `threshold-guardian`: Evaluates multiple on-chain conditions before deciding whether to fire an action (SkillEngine)
8. `dry-run-executor`: Simulates a transaction's outcome/cost before submitting for real (SkillEngine)
9. `batch-executor`: Bundles several independent actions into one optimized execution (SkillEngine)
10. `policy-gatekeeper`: Checks requested action against spend limits/allowlists/time windows (SkillEngine)
11. `skill-chain-mcp-flow`: Compose a SkillEngine skill with a Chain MCP call into one working agent flow (Composition)
12. `docs-chain-mcp-agent`: Explains a contract function via Docs MCP, then calls it via Chain MCP (Composition)
13. `liquidation-watchdog`: Monitors a lending position and alerts before liquidation risk (DeFi / Portfolio)
14. `natural-language-payment-agent`: Turns "send 100 USDC to X" into prepared transaction (Payments)
15. `recurring-payment-agent`: Handles repeating on-chain payment (Payments)
16. `invoice-to-payment-agent`: Reads invoice and prepares matching payment (Payments)
17. `whale-watching-agent`: Tracks addresses and reports significant moves (Trading / Monitoring)
18. `gas-fee-optimizer`: Monitors gas price and times submission for lowest cost (Trading / Monitoring)
19. `wallet-risk-checker`: Flags wallet/contract suspicious history before transacting (Compliance / Security)
20. `audit-log-agent`: Generates plain-language activity report for a wallet (Compliance / Security)
21. `weekly-digest-agent`: Periodic summary of wallet or protocol activity (Support / Reporting)

### Hard Tier (200 Base Points + 50 Video Bonus = 250 Points Max)
22. `saga-executor`: Multi-step dependent workflow (approve → swap → deposit) with rollback/retry (SkillEngine)
23. `arbitrage-scanner`: Checks price/rate across two sources, nets fees, executes if profitable (SkillEngine)
24. `trend-watcher`: Persists state across runs, acting once multi-observation trend met (SkillEngine)
25. `portfolio-assistant`: Answers natural-language questions about wallet positions, balances, yields across protocols (DeFi / Portfolio)
26. `yield-optimizer`: Compares yields across vaults and recommends/executes rebalance (DeFi / Portfolio)
27. `doc-grounded-builder-agent`: Answers "how do I do X" via Docs MCP, then executes via Chain MCP/SkillEngine (Cross-tool / Advanced)
28. `multi-protocol-aggregator`: Harbor-style agent extended across multiple protocols/vaults (Cross-tool / Advanced)

---

## 4. Task Alignment Audit: Where Does Our Local Skill Fit?

Our local package [`skills/pharos-portfolio-inspector`](skills/pharos-portfolio-inspector) was initiated as an "On-Chain Data & Portfolio Inspector" (`TASK-E01`).

Comparing our deliverable to the official task board:

### A. Primary Match: Task 1 — `read-contract-state` (Easy / 50 pts)
* **Official URL**: `https://pharos-agent-arena.vercel.app/tasks/read-contract-state`
* **Task Goal**: *"A small agent or script that reads live state from a deployed Pharos contract through Chain MCP and presents it in plain language. Pick any public contract (a token, vault, or registry) and turn its raw storage and view calls into something a non-developer can read."*
* **Official Acceptance Checklist**:
  1. `Req 01`: Reads at least 3 different values from one contract via Chain MCP (e.g. name, totalSupply, owner, a balance).
  2. `Req 02`: Shows the contract address and the block number the data was read at.
  3. `Req 03`: Formats raw values for humans: token decimals applied, addresses labelled.
  4. `Req 04`: Includes a short README: which contract you chose, how to run it, sample output.

#### Gap Assessment against Task 1
* `Req 01` Status: `PARTIALLY MET`. Our tool reads `balanceOf(address)` across registered tokens and invokes MCP tools (`get_chain_info`, `get_block_number`), but does not currently query `name()` and `totalSupply()` together on a single featured contract.
* `Req 02` Status: `PARTIALLY MET`. Our tool outputs contract addresses and has a `status` command returning block height, but `get_token_balance()` does not embed the current block number in its response.
* `Req 03` Status: `VERIFIED MET`. Token decimals (6 for USDC, 18 for others) are formatted into clean human-readable strings.
* `Req 04` Status: `PARTIALLY MET`. Our `README.md` documents general CLI usage, but does not highlight a specific chosen public contract as a case study.

### B. Secondary Match: Task 14 — `portfolio-assistant` (Hard / 200 pts)
* Our package name contains "portfolio inspector", but Task 14 requires reading positions across multiple DeFi protocols/vaults and answering natural language conversational questions. Our current package is a foundational CLI inspector, not a full multi-protocol conversational agent.

---

## 5. Submission Readiness & Safety Verdict

* **Registration**: Open at `https://forms.gle/ySBomVEAcwRQSCFe7` and `https://pharos-agent-arena.vercel.app/`.
* **External Actions Allowed by Agent**: **NONE**. The agent will not authenticate with GitHub, create remote repositories, or submit form data without explicit user direction.
* **Cost Incurred**: **$0.00**.

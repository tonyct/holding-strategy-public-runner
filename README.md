# E36 Public Research Runner

This export is intentionally **not** the private holding-strategy repository.

## Privacy boundary

The symbols in `config/research_universe.json` are a **research coverage universe only**. They do not identify actual holdings, position sizes, account balances, cost basis, trades, or recommendations.

This public runner may collect only public market/company information and produce public-safe research bundles.

It must never contain or consume:

- actual holdings or tracking-only account semantics
- quantities, cost basis, cash, NAV, fills, or broker data
- HOLD / ADD / REDUCE / EXIT portfolio decisions
- MAIN or private SHADOW runtime state
- Google Drive identifiers or user screenshot-derived facts
- personal cookies such as XUEQIU_COOKIE
- credentials that can write to the private repository

## Repository creation rule

Create a **new public repository with fresh Git history**. Do not fork or change visibility of the private repository.

## Data flow

Public sources -> public acquisition/parsing -> PUBLIC_RESEARCH_BUNDLE -> private repository verifies provenance/integrity -> private Shadow/MAIN performs user-specific research and portfolio decisions.

The private repository remains the only authority for account-aware conclusions.

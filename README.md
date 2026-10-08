# E36 Public Research Runner

This export is intentionally **not** the private holding-strategy repository.

## Privacy boundary

The symbols in `config/research_universe.json` are a **research coverage universe only**. They do not identify actual holdings, position sizes, account balances, cost basis, trades, or recommendations.

This public runner may collect public market/company information, perform deterministic public-only normalization and arithmetic, and publish public-safe research bundles. It must not perform valuation approval, recommendations, portfolio logic, or trading logic.

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

Public sources -> public acquisition/parsing -> public evidence index + deterministic metrics + run snapshot -> PUBLIC_RESEARCH_BUNDLE -> private state layer verifies exact run/commit/hash lineage -> private Shadow/MAIN performs user-specific research and portfolio decisions.

The private repository remains the only authority for account-aware conclusions.


## Runtime boundary

`runtime/latest` is generated only by this public repository from public-safe inputs. The public runner never reads the private repository. The private side may copy or reference public artifacts by exact run ID, commit SHA, and SHA-256, but private state is never sent back into the public workflow.\n
## Strict pull-only handoff

The Public runner publishes only to its own repository and public GitHub Actions artifacts.
It never holds a token with Private repository write access, never contacts the Private
Git API, and never dispatches a Private workflow. Historic public-to-private sink
code is retired; it must not be restored via configuration or secrets.

SHADOW runs from the Private trust boundary and pulls the exact Public
run/attempt/source-commit artifacts. SHADOW independently verifies SHA-256,
consumes only verified source bytes and decides whether they qualify for
Private research. The optional **Public Actions: read** credential, if needed,
exists only inside Private, with no Private write permission granted to Public.
Existing Private production research and trading approvals remain unchanged.

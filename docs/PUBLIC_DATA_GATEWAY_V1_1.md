# PUBLIC Data Access Gateway — V1.1 integration contract

This is a **PUBLIC-only execution service**, not a private SHADOW agent, valuation service or trading engine. It intentionally does not accept private research questions, holdings, target prices, thesis, or portfolio data.

## Capability discovery

Dispatch `.github/workflows/public_data_gateway.yml` with `request_json` containing:

```json
{"schema":"PUBLIC_DATA_GATEWAY_REQUEST/v1","request_id":"discover_20261010","operation":"DISCOVER"}
```

The run artifact contains `PUBLIC_GATEWAY_RECEIPT.json` with supported categories. An advertised capability is **not** proof of successful provider execution.

## Public-only data request

```json
{"schema":"PUBLIC_DATA_GATEWAY_REQUEST/v1","request_id":"public_001286_20261010","operation":"EXECUTE","symbol":"001286.SZ","data_type":"historical_quotes","start_date":"2026-09-01","end_date":"2026-09-30","source":"AUTO"}
```

Currently implemented: BaoStock A-share daily historical quotes only. No unsupported financial-report, official-filing or HK data is claimed.

## Delivery and PRIVATE pull

PUBLIC uploads a run-scoped, attempt-scoped artifact `public-gateway-<run_id>-<attempt>` with `PUBLIC_GATEWAY_RECEIPT.json` and, on successful nonempty fetch, `RAW_RESPONSE.json`. No PRIVATE credentials are needed in PUBLIC. SHADOW must fetch an exact immutable run/attempt/commit, verify raw response SHA-256 and reject mismatched identifiers, missing files, missing coverage, unverified data semantics or stale results. PRIVATE separately records the research question, model use, evidence links, API experience and upgrade proposal. PUBLIC must never be given that private state.

Status `DELIVERED` means raw API bytes were obtained, **not** independently verified economics or official issuer evidence. `GAP` means nothing was obtained; no fabricated fallback.

## Not yet implemented or accepted

- PRIVATE SHADOW dispatcher / run-poller / verified consumer.
- Persistent private API experience registry and capability promotion controls.
- Financials, announcements, filing original document adapters.
- Live provider run and end-to-end private verification.
- Multi-source failover and request lifecycle `CONSUMED`.

Do not mark V1.1 as production-ready until actual network run, PRIVATE pull and consumer verification, privacy tests, failure recovery and promotion review all pass.

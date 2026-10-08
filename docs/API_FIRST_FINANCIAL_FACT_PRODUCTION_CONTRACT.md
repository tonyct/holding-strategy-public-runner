# API-first Financial Fact Readiness
Status: PARTIALLY IMPLEMENTED; NOT VALUATION APPROVED.

1. Public A/H APIs are the primary source for normalized market and financial candidates, not the final authority for financial facts.
2. Provider field maps must explicitly specify source endpoint, source value, unit, currency, reporting start/end, statement scope, update timestamp, and corporate action adjustment.
3. Missing or conflicting material financial facts require source-bound official filing review; AI extraction is a review task, not automatic approval. Preserve report SHA256, page, exact excerpt, model version and prompt version.
4. Dynamic market metrics use session-date freshness. Accounting metrics are report/disclosure-event keyed. Formulas recompute on dependency hash changes only.
5. Historical TTM requires FY and comparable YTD or four quarters with same unit, scope, period and restatement basis. Capital structure requires issued shares, treasury shares, diluted securities, net debt and non-controlling interest.
6. Public output is immutable candidate packets and gap reports. Private public-input pointer must be atomically published with compare-and-swap; authoritative production HEAD is never touched by Public.
7. SHADOW must independently verify critical original statement values; MAIN only consumes authorized assumptions and facts.

## Remaining deployment prerequisites
- Real issuer/provider A/H API mapping and real-doc 11-stock comparison.
- Approved AI extraction executor with quotas, evidence requirements and conflict gates.
- End-to-end Public-to-Private credential, atomic sink and SHADOW consumption tests.
- No model result may change frozen valuation, positions, OOS, or trade authorization.

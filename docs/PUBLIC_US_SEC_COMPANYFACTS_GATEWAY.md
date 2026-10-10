# Public US SEC XBRL gateway — operator setup and verified limits

The `sec_companyfacts` category accepts a bounded public `AAPL.US`-style
symbol and `AUTO` / `sec_edgar` source. Data is retrieved from the official SEC
companyfacts API using an exact company-ticker-to-CIK mapping, with filing-date
cutoff and a source-response hash. Companyfacts rows remain economic
assertions **UNREVIEWED**: accounting period (FY/quarter/YTD), unit, entity and
filing original must be independently interpreted before E36/MAIN.

## Required SEC contact identification

For requests to actually reach SEC, configure GitHub repository Actions secret
`PUBLIC_SEC_USER_AGENT` with your organization's project/app name and a real
monitored contact email, as required by the SEC fair-access guidance. Do not
write an invented email in code, workflow files or public research requests.
The value is used only in the gateway execution step and is never included in
PUBLIC receipts or model-visible outputs.

Without that configured contact identification, requests **fail closed** as
`GAP`, never claim successful facts. Live GitHub run
[38060459987](https://github.com/tonyct/holding-strategy-public-runner/actions/runs/38060459987)
returned `GAP / 0 rows` on October 10, 2026, because this setting was empty.
The workflow job itself completed successfully, which is not evidence of a
successful data fetch.

## Safe request

```json
{"schema":"PUBLIC_DATA_GATEWAY_REQUEST/v1","operation":"EXECUTE",
 "request_id":"public_sec_aapl_example_20261010","symbol":"AAPL.US",
 "data_type":"sec_companyfacts","source":"AUTO",
 "start_date":"2025-10-09","end_date":"2026-10-09"}
```

The date range is the allowed source **filing-date** window, not necessarily
the XBRL measurement period. Each observed metric retains its own
`filed_at`, `report_period_end`, `accession`, `fiscal_period`,
`statement_start` and original SEC response digest. Later amendments must
not be used in historical simulations before their filing dates.

Any nonempty result is `PARTIAL` until an independent issuer-original and
accounting-semantic review. Do not treat this API, model hypotheses or matching
numbers from two relay vendors as fair-value proof.

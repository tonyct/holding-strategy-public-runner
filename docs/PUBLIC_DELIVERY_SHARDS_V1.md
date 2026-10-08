# Public delivery shards v1 — no change to economic approval or production HEAD

## Manifest audit (Public run 37765014355/1)

The original Public manifest lists 468 logical paths, 368 PDF entries and
517,324,638 declared logical bytes. Exactly 231 SHA-256 groups have two
identical copies; 184 PDF originals are duplicated inside
\`evidence/raw/sha256\`. There are only 237 unique SHA-256 payloads:
184 distinct PDFs (118 rolling A filings, 44 rolling HK filings, 22 pinned
historical TTM reports) and 53 distinct JSON/log payloads.

The duplicate raw-CAS copies are redundant **for transport**; they are not
unnecessary provenance identities. Preserve every logical manifest row.
Historical reports and current windows serve different source periods, and
must not be indiscriminately dropped or deduced from a title.

## Additive, reversible rollout

\`ops.public_delivery_shards\` validates the **original manifest's every
SHA-256 and byte length**, source run/attempt/commit, Public research-only
universe, and privacy before packaging one canonical copy per content SHA.
It publishes one small \`metadata\` artifact and eight independently
downloadable \`pdf-00..pdf-07\` artifacts, with an index mapping every
original manifest path to exactly one canonical payload and shard.

GitHub Actions downloads artifacts as ZIPs; sharding removes the one
432-MB download requirement rather than claiming the GitHub API provides
a raw per-file download endpoint. Source PDFs can also be reused from
Private's exact-SHA cache after verification.

The old \`public-research-{run}-{attempt}\` artifact is kept during the
compatibility period. SHADOW must opt into the new transport only after
the Private-side readback, manifest restoration, prior lead-queue, PDF
recovery, 13-step execution, and semantic gates have been independently
demonstrated. Do not report this change as a research-generation commit.

## Controls

- Public output never includes account data, Private commit/cycle IDs, or
  valuation and trading logic.
- Public research universe and all original manifest records are untouched.
- \`metadata/PUBLIC_DELIVERY_INDEX.json\` is a transport-only receipt;
  verify exact run, attempt, source commit, manifest bytes, universe SHA,
  full manifest mapping and each canonical file SHA before materialization.
- Never infer report semantics from a SHA or treat collection PASS as
  L2/L3 validation.
- Never replace a mismatched cache file; use exact-SHA verified reuse or
  fail only the affected scope.
- Do not remove the legacy artifact until the consumer is updated,
  tested and accepted through Coverage / Semantic / Audit gates.

# Real-data Admission

AOAE does not treat a downloadable file as research-ready data. A source must first have explicit provenance, time semantics, quality limits, research scope, redistribution policy, and a reproducible snapshot digest.

## First admitted snapshot

`ADM-0001-us-treasury-yield-curve` covers the U.S. Department of the Treasury's 2024 Daily Treasury Par Yield Curve Rates. Treasury provides an official unauthenticated XML feed and documents annual query parameters. The published curve is derived from indicative bid-side quotations obtained at or near 3:30 PM Eastern, not actual transactions. AOAE therefore treats an observation as research-available only on the next U.S. business day.

Official references:

- [Daily Treasury Rates](https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?page=1&type=daily_treasury_yield_curve)
- [Treasury Daily Interest Rate XML Feed](https://home.treasury.gov/treasury-daily-interest-rate-xml-feed)
- [USAGov guidance on federal-government copyright](https://www.usa.gov/government-copyright)

Public access does not automatically settle every reuse right. The raw snapshot is consequently restricted to internal research, excluded from Git, and not authorized for redistribution. Treasury attribution remains required. This is a conservative operating policy, not a legal opinion.

## Reproduce locally

Download the snapshot into the ignored raw-data directory:

```powershell
New-Item -ItemType Directory -Force -Path .\data\raw\treasury | Out-Null
curl.exe --fail --location `
  --output .\data\raw\treasury\daily_treasury_yield_curve_2024.xml `
  "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?data=daily_treasury_yield_curve&field_tdr_date_value=2024"
```

Run the admission and independent audit:

```powershell
.\.venv\python.exe -m aoae data-audit `
  --spec .\research\data_admissions\0001-us-treasury-yield-curve\spec.json `
  --repo-root . `
  --output .\research\data_admissions\0001-us-treasury-yield-curve\result.json

.\.venv\python.exe .\scripts\audit_treasury_snapshot.py
```

The admitted local snapshot has 250 unique trading-day rows and 13 required maturities with no missing values. Its SHA-256 is recorded in the result. If Treasury revises historical data, a fresh download may differ; do not silently replace the admitted record. Create a new snapshot record and explain the revision.

## Current authorization boundary

Allowed: format parsing, provenance checks, descriptive quality analysis, and creation of a canonical derived table.

Not allowed: strategy search, backtest trials, raw redistribution, live trading, or capital allocation.

## First prospective event-market snapshot

`ADM-0003-polymarket-public-active-events` admitted a read-only snapshot from Polymarket's documented public Gamma `events/keyset` endpoint after the contract was committed at `fe52311`. It contains 100 open events and 1,221 market records. The response body is excluded from Git; the committed result binds it by SHA-256, byte count, UTC capture time, server `Date`, schema checks, and unique identifiers.

The earlier `ADM-0002` attempt remains recorded as `FAIL`: its body was preserved, but a CLI defect prevented the HTTP `Date` from reaching the result, and some constituent markets lacked a CLOB-token field. It was quarantined rather than silently replaced. The retry admits event metadata fields guaranteed by the observed public schema; availability of token identifiers must be a separate, preregistered eligibility rule before any price collection.

This admission does not establish predictive edge. It authorizes only prospective observation. No model was fitted, no strategy was tried, and no authentication, wallet, order, or capital was used.

## Canonical curve table

`DER-0001-treasury-curve-canonical` converts the admitted XML into a deterministic private CSV with 250 rows and 19 columns. It preserves 13 quoted par yields and adds only exact descriptive identities:

- 10-year minus 2-year spread, in basis points
- 10-year minus 3-month spread, in basis points
- 30-year minus 10-year spread, in basis points
- one-observation changes for the 2-year and 10-year yields

The table contains no signal, position, return, PnL, or Sharpe field. In 2024, the 10-year minus 2-year spread was negative on 166 of 250 observations, while the 10-year minus 3-month spread was negative on 238 observations. These are descriptions, not forecasts. Treasury explicitly notes that CMT values are theoretical constant-maturity par yields rather than yields of a particular security, and cautions that forecasting future rates is risky. See the [Treasury methodology](https://home.treasury.gov/policy-issues/financing-the-government/interest-rate-statistics/treasury-yield-curve-methodology) and [interest-rate FAQ](https://home.treasury.gov/policy-issues/financing-the-government/interest-rate-statistics/interest-rates-frequently-asked-questions).

The derived CSV remains in `data/processed/` and is excluded from Git. Its content hash, schema, invariants, and descriptive evidence are retained under `research/derived_datasets/`.

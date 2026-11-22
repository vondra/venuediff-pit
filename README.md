# venuediff-pit

Point-in-time, bitemporal **Apache Parquet (ZSTD)** dataset of trading rules, margin ladders, collateral haircuts, funding regimes, and prediction-market settlement rules across 8 venues:

- **Perpetuals & Futures (6):** Binance USD-M, Bybit Linear/Inverse, OKX Swap/Futures, Deribit Futures/Perpetuals, Hyperliquid (native + HIP-3 DEXes), Lighter.
- **Prediction Markets (2):** Kalshi (CFTC-regulated series & markets), Polymarket (Gamma markets, CLOB Liquidity Rewards, Polygon UMA OOV2 / ManagedOOV2 disputes).

All Parquet files are published as immutable **GitHub Release** assets referenced by SHA-256 and exact row counts in [`manifests/latest.json`](manifests/latest.json). Git history holds only lightweight text documentation, SQL views, schemas, and manifests (`< 1 MiB` permanently).

---

## Why This Dataset Exists

Exchange microstructure backtests and risk engines silently break when current rules are projected backward:

- **Funding intervals drift:** As of `2026-11-22`, **57.7%** of active Binance USD-M perpetuals (`469 / 813`), **46.3%** of Bybit (`416 / 899`), and **39.6%** of OKX (`216 / 546`) are no longer on 8-hour funding (`28800s`).
- **Margin ladders are not interchangeable:** OKX brackets are denominated in **contracts** (`exposure_unit = 'contracts'`), Binance/Bybit/multi-tier Hyperliquid in **USD notional** (`'usd_notional'`), and Lighter / flat Hyperliquid in **unbounded** flat fractions (`'unbounded'`).
- **Tickers recycle across corporate actions & delistings:** On Lighter, pre-split `SNDK_DELISTED` (`lighter:perp:139`) and post-split `SNDK` (`lighter:perp:11649`) are distinct `subject_id` incarnations.
- **Survivorship bias:** Live exchange endpoints erase purged contracts. Enumerating Binance's public S3 `fundingRate/` archive independently of `exchangeInfo` recovers 71 purged USDT-M perpetuals back to `2020-01-01`; `history.deribit.com` recovers 2,746 expired Deribit futures/perpetuals back to `2016-07-13`.
- **Collector outages & API caps must be machine-readable:** Every missed polling slot and API retention limit is recorded in [`coverage.parquet`](schema/v1/SCHEMA.md#6-coverageparquet) so downstream queries can explicitly flag blind intervals instead of assuming continuous observation.

---

## v1.0 Dataset Layout (6 Core Tables + 1 Optional Rewards Table)

Snapshot `v1.0.0-2026-11-22` (total **15.78 MiB** ZSTD across 7 Parquet files):

| Table | Rows | Cols | Size (ZSTD) | Observed Span | Summary |
|---|---:|---:|---:|---|---|
| `instruments.parquet` | 6,311 | 36 | 133.9 KiB | `2016-07-13` .. `2026-11-22` | Bitemporal SCD Type 2 specs across 6 perp/futures venues (`3,494` live PIT + `2,746` Deribit expired `terminal_snapshot` + `71` Binance S3 purged `observed_activity_bound`). |
| `margin_tiers.parquet` | 2,984 | 12 | 323.7 KiB | `2026-11-22` | Atomic versioned margin ladders (`82,971` typed tier structs) with explicit `exposure_unit` (`usd_notional` / `contracts` / `unbounded`). |
| `collateral_rules.parquet` | 570 | 14 | 72.1 KiB | `2026-11-22` | Atomic versioned collateral haircuts, LTV ratios, liquidation thresholds, and tiered discount bands. |
| `prediction_rules.parquet` | 307,559 | 36 | 10.0 MiB | `2021-06-30` .. `2026-11-22` | Kalshi series (`16,775`), active markets (`1,344`), and historical markets (`287,797`, `terminal_snapshot`); Polymarket Gamma markets (`1,643`) with ordered 256-bit ERC-1155 `clob_token_id` outcomes and true `feeSchedule`. |
| `events.parquet` | 38,078 | 25 | 4.73 MiB | `2020-10-31` .. `2026-11-22` | Unified bitemporal rule-change log: clean 2-min live PIT diffs (`653` rows, zero rewards noise) + 8-venue verified historical events (`37,425` rows). |
| `coverage.parquet` | 132 | 12 | 7.7 KiB | `2026-11-22` | Per-venue, per-endpoint live SLA (`ok` / `missed_slot` / `truncated`) and historical backfill truncation bounds. |
| `prediction_rewards.parquet` | 7,908 | 12 | 547.4 KiB | `2026-11-22` | Optional append-only Polymarket CLOB Liquidity Rewards stream (`1` row per pool/asset/sample), completely separated from `events.parquet`. |

Full column-level contract and invariants: [`schema/v1/SCHEMA.md`](schema/v1/SCHEMA.md).

---

## Quickstart (DuckDB + PyArrow)

```bash
pip install duckdb pyarrow
python3 examples/quickstart.py --manifest manifests/latest.json
```

`examples/quickstart.py` downloads all 7 Parquet files from the immutable release referenced in `manifests/latest.json`, verifies every SHA-256 digest before reading, and runs 7 sanity queries.

### Direct DuckDB Examples

#### 1. Zero Look-Ahead Point-in-Time As-Of State

Filter `known_from_utc <= decision_ts` **before** `valid_from_utc <= venue_ts`, exclude `terminal_snapshot` unless opting in, and left-join `coverage.parquet` blind gaps. Ready-to-run query: [`sql/v1/as_of_state.sql`](sql/v1/as_of_state.sql).

```sql
SET VARIABLE decision_ts = TIMESTAMPTZ '2026-11-22T14:00:00Z';
SET VARIABLE venue_ts    = TIMESTAMPTZ '2026-11-22T14:00:00Z';

-- Run sql/v1/as_of_state.sql against local files or GitHub Release URLs
```

#### 2. Flatten Typed Margin Ladders Without Mixing Units

Ready-to-run view: [`sql/v1/margin_tiers_flat.sql`](sql/v1/margin_tiers_flat.sql).

```sql
SELECT venue, exposure_unit,
       COUNT(*) AS ladders,
       CAST(SUM(len(tiers)) AS BIGINT) AS total_tiers
FROM read_parquet('margin_tiers.parquet')
GROUP BY 1, 2
ORDER BY 1, 2;
```

Observed output on `v1.0.0-2026-11-22`:

```text
binance       usd_notional      956 ladders  ( 7,585 tiers)
bybit         usd_notional      939 ladders  (27,372 tiers)
hyperliquid   unbounded         254 ladders  (   254 tiers)
hyperliquid   usd_notional       43 ladders  (    79 tiers)
lighter       unbounded         246 ladders  (   246 tiers)
okx           contracts         546 ladders  (47,435 tiers)
```

#### 3. Join Polymarket Orderbook Fills via Exact 256-bit ERC-1155 `clob_token_id`

```sql
SELECT p.condition_id, p.gamma_market_id,
       o.outcome.outcome_index, o.outcome.label, o.outcome.clob_token_id,
       p.fee_type, p.fee_rate, p.fee_exponent
FROM read_parquet('prediction_rules.parquet') p,
     UNNEST(p.outcomes) AS o(outcome)
WHERE p.venue = 'polymarket'
LIMIT 5;
```

#### 4. Polymarket Time-Weighted Daily Liquidity Rewards

Ready-to-run view: [`sql/v1/rewards_twap.sql`](sql/v1/rewards_twap.sql) (caps individual sample spans at `3,600s` so collector outages never extrapolate stale reward budgets).

---

## Explicit Data Caveats & Known Truncation Bounds

All truncation limits below are also machine-readable in `coverage.parquet`:

1. **Bitemporal `claim_kind` semantics:**
   - `terminal_snapshot` rows (2,746 expired Deribit contracts, 287,797 Kalshi `/historical/markets` contracts, 138 Binance `SETTLING` records) represent final contract metadata returned at archive query time, **not** guaranteed mid-life parameters. Filter `claim_kind IN ('live_observation', 'effective_event')` for strict zero-look-ahead backtests.
   - `regulatory_filing_index` rows (Kalshi S3: 658 CFTC Rule 40.6 notices + 5,249 Rule 40.2 product certifications) index official PDF URLs, S3 `LastModified` (stored in `observed_at_utc`), ETag, and filename dates; `LastModified` is not conflated with legal effective date and PDFs are not bulk-parsed.
   - `announcement_notice` rows (Binance 879, Bybit 781, OKX 202) carry notice publication timestamps in `announced_at_utc` and link to raw official notices; HTML rule tables inside notices are not parsed into numeric diffs in v1.0.
2. **Hyperliquid HIP-3 explorer 300-tx cap:** `rpc.hyperliquid.xyz/explorer` caps `userDetails` at 300 transactions per address. Across 51 HIP-3 deployer/sub-deployer endpoints queried, 30 hit this cap (`outcome = 'truncated'` in `coverage.parquet`), meaning older historical prefixes before the 300-tx window are incomplete for those high-activity addresses. Going forward, the live collector polls the explorer continuously so new `perpDeploy` governance actions are captured before rolling off. Price `setOracle` updates and reverted transactions are excluded.
3. **OKX funding-rate history retention:** OKX's public REST `/api/v5/public/funding-rate-history` retains ~95 days (`92` observed switches; `outcome = 'truncated'`).
4. **Polymarket UMA dispute linking:** All `24,768` UMA transitions (deduplicated across Polygon OOV2 and ManagedOOV2 since July 2022) are linked to markets **strictly deterministically** (`29` `resolved` to current live Gamma markets; `24,739` explicitly `unresolved`). Fuzzy title matching is never used.
5. **Live collector blind gaps:** Live Point-in-Time collection runs every 2 minutes (heavy layer every 30 minutes). Any gap exceeding the cadence threshold is emitted as `outcome = 'missed_slot'` in `coverage.parquet` (including one 826-second stall on `2026-11-22 12:02:02Z .. 12:15:48Z` prior to state storage tuning).
6. **Windowed live prediction scans:** Kalshi active market polling scans up to 12,000 non-MVE markets while covering 100% of series; Polymarket Gamma polling scans top-volume + recently updated markets while covering 100% of active CLOB Liquidity Rewards pools.

---

## Repository Structure

```text
.
├── README.md
├── LICENSE                       # CC0-1.0 (dataset & schemas) / MIT (SQL & examples)
├── CHANGELOG.md
├── manifests/
│   └── latest.json               # Pinned release tag, URLs, row counts, SHA-256 digests
├── schema/
│   └── v1/
│       └── SCHEMA.md             # Frozen v1.0 table & column specification
├── sql/
│   └── v1/
│       ├── as_of_state.sql       # Zero-look-ahead bitemporal as-of state + blind-gap join
│       ├── margin_tiers_flat.sql # UNNEST margin ladders preserving exposure_unit
│       └── rewards_twap.sql      # Time-weighted daily Polymarket liquidity rewards
└── examples/
    └── quickstart.py             # SHA-256 verified DuckDB + PyArrow quickstart
```

## Release Cadence

Immutable daily snapshots are published to GitHub Releases (`data-YYYY-MM-DD`, with `v1.0.0-2026-11-22` as the initial frozen v1.0 baseline) and indexed in `manifests/latest.json`.

## License

See [`LICENSE`](LICENSE): dataset tables and schemas are dedicated under **CC0-1.0**; SQL views and example scripts are licensed under **MIT**.

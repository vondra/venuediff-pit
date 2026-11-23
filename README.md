# venuediff-pit (VenueDiff Open PIT v1.0)

Point-in-time, bitemporal **Apache Parquet (ZSTD)** dataset of trading rules, margin ladders, collateral haircuts, on-chain governance actions, and optimistic oracle dispute lifecycles across **3 permissionless on-chain sources**:

- **Hyperliquid L1 (`hyperliquid`):** Complete **Core + HIP-3 builder DEX** coverage (`perpDexs`, `allPerpMetas`, `spotMeta` collateral token resolution, `marginTables`, `growthMode`, `deployerFeeScale`, `onlyIsolated`) plus decoded on-chain `perpDeploy` governance transactions via `rpc.hyperliquid.xyz/explorer`.
- **Lighter L2 (`lighter`):** Complete perpetual and spot market specifications (`orderBookDetails`), margin collateral LTV/haircut rules (`assetDetails`), immutable `market_id` split incarnations, `force_reduce_only` restrictions, static USD open-interest caps, and historical trading activity windows (`observed_activity_bound`) for delisted markets from nonzero-volume `/api/v1/candles`.
- **Polygon UMA (`polygon_uma`):** Pure on-chain Polygon **Optimistic Oracle V2** (`polygon-optimistic-oracle-v2`) and **ManagedOOV2** (`polygon-managed-optimistic-oracle-v2`) dispute lifecycles (`uma_requested` → `uma_proposed` → `uma_disputed` → `uma_settled`) read directly from Polygon smart contracts via public Goldsky subgraphs since July 2022.

All Parquet files are published as immutable **GitHub Release** assets referenced by SHA-256 and exact row counts in [`manifests/latest.json`](manifests/latest.json) and `SHA256SUMS.txt`. Git history stores only lightweight text documentation, SQL views, schemas, and manifests (`< 1 MiB` permanently).

---

## Why This Dataset Exists

On-chain microstructure backtests, liquidation simulators, and risk engines silently break when current protocol parameters are projected backward:

- **HIP-3 builder DEX parameters mutate on-chain:** Hyperliquid's permissionless HIP-3 deployer markets (`xyz`, `para`, `io`, `mkts`) dynamically toggle `growthMode` (−90% fee mode, active on `162 / 175` live HIP-3 markets), adjust `deployerFeeScale`, update `marginTables`, set open-interest caps, and change funding clamps via on-chain `perpDeploy` governance transactions. Most perpetual reference aggregators omit HIP-3 entirely.
- **Margin ladders use incompatible exposure units:** Multi-tier Hyperliquid `marginTables` are denominated in **USD notional** (`exposure_unit = 'usd_notional'`), whereas flat Hyperliquid leverage and Lighter flat IMR/MMR/closeout fractions are **unbounded** (`exposure_unit = 'unbounded'`). Keeping `exposure_unit` explicit prevents silent unit-mixing bugs.
- **Tickers recycle across splits and delistings:** On Lighter L2, pre-split `SNDK_DELISTED` (`lighter:perp:139`) and post-split `SNDK` (`lighter:perp:11649`) are distinct immutable `subject_id` incarnations. Historical trading bounds for 30 delisted Lighter markets are recovered from nonzero-volume daily candles (stripping post-delisting zero-volume filler candles).
- **Optimistic oracle disputes unfold over days:** Polygon UMA OOV2 and ManagedOOV2 subgraph rows overwrite state in place. VenueDiff splits each of `6,259` disputed requests into strictly chronological point-in-time transitions so settlement outcomes never leak backward into request-time or dispute-time backtests.
- **Collector outages & explorer caps are machine-readable:** Every missed polling slot and explorer truncation bound (such as Hyperliquid's 300-tx/address explorer window) is recorded in [`coverage.parquet`](schema/v1/SCHEMA.md#5-coverageparquet).

---

## Why These Sources (Legal & Data Provenance)

Centralized exchange and proprietary prediction-market APIs commonly impose contractual Terms of Service prohibiting redistribution, repackaging, or commercial use of market data and instrument specifications. **VenueDiff Open PIT v1.0** deliberately restricts ingestion exclusively to permissionless blockchain state and public on-chain/L2 endpoints whose published terms permit public and commercial redistribution.

Every `.parquet` file embeds verifiable Arrow schema metadata:

```text
venuediff_license        = CC-BY-4.0
venuediff_schema_version = v1.0
venuediff_sources        = hyperliquid,lighter,polygon_uma
```

### Roadmap
- Additional permissionless on-chain perpetual protocols after primary Terms verification.
- Public regulatory product/rule filings (e.g., CFTC Rule 40.2 / 40.6 filings directly from public government portals once programmatically accessible without anti-bot gates).

---

## v1.0 Dataset Layout (5 Normalized Tables)

Release `v1.0.0-2026-11-23` (total **3.57 MiB** ZSTD across 5 Parquet files):

| Table | Rows | Cols | Size (ZSTD) | Observed Span | Summary |
|---|---:|---:|---:|---|---|
| `instruments.parquet` | 858 | 36 | 29.4 KiB | `2025-02-15` .. `2026-11-23` | Bitemporal SCD Type 2 specs for Hyperliquid L1 Core + HIP-3 (`570` live PIT) and Lighter L2 Perps/Spot (`258` live PIT + `30` delisted `/candles` `observed_activity_bound`). |
| `margin_tiers.parquet` | 543 | 12 | 13.8 KiB | `2026-11-23` | Atomic versioned margin ladders (`579` typed tier structs) with explicit `exposure_unit` (`usd_notional` / `unbounded`). |
| `collateral_rules.parquet` | 13 | 14 | 6.4 KiB | `2026-11-23` | Atomic versioned margin collateral LTV ratios, haircuts, liquidation thresholds, and global supply caps (Lighter L2 `assetDetails`). |
| `events.parquet` | 28,643 | 25 | 3.51 MiB | `2022-07-12` .. `2026-11-23` | Unified bitemporal on-chain event log: `24,967` Polygon UMA OOV2/ManagedOOV2 dispute transitions (`6,259` disputes), `3,646` Hyperliquid HIP-3 `perpDeploy` governance transitions, `30` Lighter delisted `/candles` bounds, plus live 2-min PIT diffs. |
| `coverage.parquet` | 79 | 12 | 6.4 KiB | `2026-11-23` | Per-source, per-endpoint live SLA (`ok` / `missed_slot` / `error`) and historical backfill truncation bounds. |

Full column-level contract and invariants: [`schema/v1/SCHEMA.md`](schema/v1/SCHEMA.md).

---

## Quickstart (DuckDB + PyArrow)

```bash
pip install duckdb pyarrow
python3 examples/quickstart.py --manifest manifests/latest.json
```

`examples/quickstart.py` downloads all 5 Parquet files from the immutable release referenced in `manifests/latest.json`, verifies every SHA-256 digest and embedded `CC-BY-4.0` Arrow metadata header before reading, and runs 6 sanity queries.

### Direct DuckDB Examples

#### 1. Zero Look-Ahead Point-in-Time As-Of State

Filter `known_from_utc <= decision_ts` **before** `valid_from_utc <= venue_ts`, exclude `observed_activity_bound` unless opting in, and left-join `coverage.parquet` blind gaps. Ready-to-run query: [`sql/v1/as_of_state.sql`](sql/v1/as_of_state.sql).

```sql
SET VARIABLE decision_ts = TIMESTAMPTZ '2026-11-24T00:00:00Z';
SET VARIABLE venue_ts    = TIMESTAMPTZ '2026-11-24T00:00:00Z';
```

#### 2. Flatten Typed Margin Ladders Without Mixing Exposure Units

Ready-to-run view: [`sql/v1/margin_tiers_flat.sql`](sql/v1/margin_tiers_flat.sql).

```sql
SELECT venue, exposure_unit,
       COUNT(*) AS ladders,
       CAST(SUM(len(tiers)) AS BIGINT) AS total_tiers
FROM read_parquet('margin_tiers.parquet')
GROUP BY 1, 2
ORDER BY 1, 2;
```

Observed output on `v1.0.0-2026-11-23`:

```text
hyperliquid   unbounded         254 ladders  (  254 tiers)
hyperliquid   usd_notional       43 ladders  (   79 tiers)
lighter       unbounded         246 ladders  (  246 tiers)
```

#### 3. Inspect Lighter L2 Margin Collateral Haircuts & LTVs

Ready-to-run view: [`sql/v1/collateral_haircuts_flat.sql`](sql/v1/collateral_haircuts_flat.sql).

#### 4. Analyze Polygon UMA OOV2 / ManagedOOV2 Dispute-to-Settlement Lifecycles

Ready-to-run view: [`sql/v1/uma_disputes_timeline.sql`](sql/v1/uma_disputes_timeline.sql).

---

## Explicit Data Caveats & Known Truncation Bounds

All truncation limits below are also machine-readable in `coverage.parquet`:

1. **Bitemporal `claim_kind` semantics:**
   - `observed_activity_bound` rows (`30` Lighter delisted markets recovered via `/api/v1/candles` where daily volume `v > 0`) bound the first and last observed active trading day — **not** exact listing/delisting seconds or mid-life fee changes. Filter `claim_kind IN ('live_observation', 'effective_event')` for strict zero-look-ahead backtests.
   - `7` inactive Lighter markets returned zero traded candles (pre-launch or never traded) and are transparently noted in `coverage.parquet` without fabricated dates.
2. **Hyperliquid HIP-3 explorer 300-tx cap:** `rpc.hyperliquid.xyz/explorer` caps `userDetails` at 300 transactions per address. Addresses hitting this cap carry `outcome = 'truncated'` in `coverage.parquet`, meaning older historical prefixes before the 300-tx window are incomplete for high-activity deployers. Going forward, the live collector polls the explorer continuously every 30 minutes so new `perpDeploy` governance actions are captured before rolling off. Price `setOracle` ticks and reverted transactions are excluded.
3. **Polygon UMA protocol-level scope:** All `6,259` disputed Polygon UMA requests (`24,967` chronological lifecycle transitions across OOV2 and ManagedOOV2 since `2022-07-12`) are read directly from Polygon smart contracts via Goldsky subgraphs. Raw `ancillaryData` is hashed (`ancillary_sha256`) rather than copying arbitrary third-party free-text prose into titles.
4. **Live collector cadence & blind gaps:** Live Point-in-Time collection runs every 2 minutes (heavy explorer/subgraph watchers every 30 minutes). Any gap exceeding the cadence threshold is emitted per source as `outcome = 'missed_slot'` in `coverage.parquet`.

---

## Repository Structure

```text
.
├── README.md
├── LICENSE                            # CC-BY-4.0 (dataset *.parquet) / MIT (code, schemas, SQL, manifests)
├── CHANGELOG.md
├── manifests/
│   └── latest.json                    # Pinned release tag, URLs, license, row counts, SHA-256 digests
├── schema/
│   └── v1/
│       └── SCHEMA.md                  # Frozen v1.0 5-table specification
├── sql/
│   └── v1/
│       ├── as_of_state.sql            # Zero-look-ahead bitemporal as-of state + blind-gap join
│       ├── margin_tiers_flat.sql      # UNNEST margin ladders preserving exposure_unit
│       ├── collateral_haircuts_flat.sql # UNNEST Lighter L2 collateral LTV & haircuts
│       └── uma_disputes_timeline.sql  # Polygon UMA OOV2/ManagedOOV2 dispute-to-settlement lifecycle view
└── examples/
    └── quickstart.py                  # SHA-256 & Arrow metadata verified DuckDB + PyArrow quickstart
```

## Release Cadence

Immutable daily snapshots are published to GitHub Releases (`data-YYYY-MM-DD`, with `v1.0.0-2026-11-23` as the initial frozen On-Chain Open PIT v1.0 release) and indexed in `manifests/latest.json` alongside `SHA256SUMS.txt`.

## License

See [`LICENSE`](LICENSE):
- **Dataset files (`*.parquet` GitHub Release assets):** **CC-BY-4.0** (Creative Commons Attribution 4.0 International — free for public and commercial use with attribution).
- **Schemas, SQL views, manifests, documentation, and example scripts (`schema/`, `sql/`, `examples/`, `manifests/`, `*.md`, `*.py`, `*.sql`):** **MIT License**.

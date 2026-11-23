# VenueDiff Open PIT v1.0 — Schema Specification

All datasets are published as **ZSTD-compressed Apache Parquet** files attached to immutable **GitHub Releases** (referenced by SHA-256 and exact row counts in [`manifests/latest.json`](../../manifests/latest.json) and `SHA256SUMS.txt`). Git history stores only lightweight text assets (`schema/`, `sql/`, `examples/`, `manifests/`).

- **Dataset License (`*.parquet`):** Creative Commons Attribution 4.0 International (**CC-BY-4.0**)
- **Code, Schema, SQL & Examples License:** **MIT License**
- **Embedded Arrow Schema Metadata** (present in every `.parquet` file):
  - `venuediff_license = "CC-BY-4.0"`
  - `venuediff_schema_version = "v1.0"`
  - `venuediff_sources = "hyperliquid,lighter,polygon_uma"`

---

## Core Invariants

1. **Strict On-Chain & Permissionless Provenance:** Every row across all 5 tables satisfies `venue IN ('hyperliquid', 'lighter', 'polygon_uma')`. No centralized exchange or proprietary API feeds with redistribution restrictions are ingested.
2. **Immutable `subject_id` Incarnations:** Identifiers are venue-scoped and never reuse an old ID after a stock split or ticker recycle (e.g., Lighter pre-split `SNDK_DELISTED` is `lighter:perp:139`; post-split `SNDK` is `lighter:perp:11649`).
3. **Bitemporal Clocks (Zero Look-Ahead):**
   - `valid_from_utc` / `valid_to_utc`: half-open interval `[from, to)` of protocol validity.
   - `known_from_utc` / `known_to_utc`: when VenueDiff durably recorded this revision. Always filter `known_from_utc <= decision_ts` **before** resolving `valid_from_utc <= venue_ts`.
   - `announced_at_utc`, `scheduled_for_utc`, `effective_at_utc`, `observed_at_utc`, `change_after_utc`, `change_by_utc`: kept strictly separate on `events.parquet` — on-chain execution timestamps are never conflated with observation or scheduling times.
4. **Explicit `claim_kind`:**
   - `live_observation`: direct Point-in-Time observation from the live 2-min / 30-min collector.
   - `effective_event`: on-chain verified effective transition (Hyperliquid HIP-3 `perpDeploy` governance tx, Polygon UMA OOV2 / ManagedOOV2 lifecycle transition).
   - `scheduled_change`: scheduled future change (supports `operation='retract'` if cancelled).
   - `observed_activity_bound`: lower/upper bound on observed historical trading activity derived from nonzero-volume daily candles (`lighter` delisted markets via `/api/v1/candles`). **Never** conflated with exact listing/delisting second.
5. **Exact Decimal Representation:** Prices, ticks, lots, margins, haircuts, bonds, and fees are stored as canonical non-scientific decimal strings (never `FLOAT64`) to eliminate IEEE-754 drift. All timestamps are UTC `TIMESTAMP(MICROS, tz=UTC)`.

---

## Tables (5 Normalized Parquet Tables)

### 1. `instruments.parquet`
Bitemporal SCD Type 2 specifications across **Hyperliquid L1** (Core + all HIP-3 builder DEXes with resolved `spotMeta` collateral tokens, `growthMode`, `deployerFeeScale`, `onlyIsolated`) and **Lighter L2** (perpetuals + spot with immutable `market_id` split incarnations, `force_reduce_only`, static USD OI caps, fees, plus `observed_activity_bound` windows from `/api/v1/candles` for delisted markets).

Columns (36): `subject_id`, `venue`, `symbol`, `canonical_base`, `asset_class` (`crypto` | `equity` | `commodity` | `fx` | `index`), `contract_type`, `payoff_model` (`linear` | `inverse` | `quanto`), `contract_size`, `contract_size_unit`, `quote_ccy`, `settle_ccy`, `margin_ccy`, `status_canonical` (`ACTIVE` | `REDUCE_ONLY` | `HALTED` | `DELISTED` | `PENDING`), `status_raw`, `tick_size`, `lot_size`, `min_qty`, `min_notional`, `funding_interval_sec`, `funding_cap`, `funding_floor`, `max_leverage`, `maker_fee`, `taker_fee`, `growth_mode`, `deployer_fee_scale`, `only_isolated`, `force_reduce_only`, `open_interest_limit_usd`, `delivery_at_utc`, `valid_from_utc`, `valid_to_utc`, `known_from_utc`, `known_to_utc`, `claim_kind`, `evidence_ref`.

### 2. `margin_tiers.parquet`
Atomic versioned margin/leverage ladders across Hyperliquid L1 and Lighter L2. Replacing a multi-tier ladder replaces the entire `tiers` list atomically.
- `exposure_unit`: `usd_notional` (multi-tier Hyperliquid `marginTables`) | `unbounded` (Lighter flat margin fractions & flat Hyperliquid leverage).
- `tiers`: `LIST<STRUCT<ordinal: int32, lower_bound: string, upper_bound: string, max_leverage: string, imr: string, mmr: string, closeout_mr: string, maint_deduction: string, deduction_unit: string>>`.
- All margin rates (`imr`, `mmr`, `closeout_mr`) are normalized fractions in `[0, 1]` (e.g., Lighter `200` bps → `"0.02"`). Undisclosed parameters remain `NULL`.
- Flattened view: [`sql/v1/margin_tiers_flat.sql`](../../sql/v1/margin_tiers_flat.sql).

### 3. `collateral_rules.parquet`
Atomic versioned margin collateral haircuts, LTV ratios, liquidation thresholds, liquidation penalties, and global supply caps from **Lighter L2** (`/api/v1/assetDetails`).
- `bands`: `LIST<STRUCT<ordinal: int32, min_amt: string, max_amt: string, collateral_ratio: string, haircut: string, liq_penalty_rate: string>>`.
- Flattened view: [`sql/v1/collateral_haircuts_flat.sql`](../../sql/v1/collateral_haircuts_flat.sql).

### 4. `events.parquet`
Unified bitemporal on-chain rule-change & oracle dispute event log merging:
- Live 2-minute Point-in-Time diffs (`source_stream='live_pit'`, `hyperliquid` & `lighter`),
- On-chain **Hyperliquid HIP-3** `perpDeploy` governance transactions (`setGrowthModes`, `setDeployerFees`, `setFeeScale`, `setMarginTableIds`, `insertMarginTable`, `setMarginModes`, `haltTrading`, `setOpenInterestCaps`, `registerAsset`/`registerAsset2`, `disableDex`, `setFundingMultipliers`/`setFundingInterestRates`/`setFundingClamps`, `setPerpAnnotation`) — excluding reverted txs and price `setOracle` ticks, deduplicating no-op funding parameter setters,
- **Lighter L2** delisted market `/candles` observed trading activity bounds (`claim_kind='observed_activity_bound'`),
- Pure on-chain **Polygon UMA OOV2 & ManagedOOV2** disputed request lifecycles (`uma_requested`, `uma_proposed`, `uma_disputed`, `uma_settled`) read directly from Polygon smart contracts via Goldsky subgraphs, exposing each phase strictly at its on-chain timestamp (`link_status='resolved'`, `ancillary_sha256` stored without third-party free-text prose).

Columns (25): `event_id`, `revision`, `operation` (`assert` | `retract`), `source_stream`, `claim_kind`, `venue`, `subject_id`, `symbol`, `scope`, `event_type`, `field`, `old_value_json`, `new_value_json`, `announced_at_utc`, `scheduled_for_utc`, `effective_at_utc`, `observed_at_utc`, `change_after_utc`, `change_by_utc`, `known_from_utc`, `link_status`, `title`, `evidence_url`, `evidence_sha256`, `evidence_json`.

### 5. `coverage.parquet`
Per-source, per-endpoint reliability, missed-slot blind gaps, and historical backfill truncation bounds.
- Columns (12): `coverage_id`, `run_at_utc`, `stream` (`live_pit` | `historical_backfill`), `venue`, `endpoint`, `cadence_sec`, `outcome` (`ok` | `partial` | `error` | `missed_slot` | `truncated`), `pagination_complete`, `rows_observed`, `blind_gap_start_utc`, `blind_gap_end_utc`, `truncation_note`.
- Explicitly records Hyperliquid's 300-tx explorer cap per deployer/sub-deployer address (`outcome='truncated'`), Lighter `/candles` scan counts, Polygon UMA Goldsky indexed block heights, and any live collector missed slots (`outcome='missed_slot'`).

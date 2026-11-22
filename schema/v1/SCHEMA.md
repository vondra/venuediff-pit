# VenueDiff v1.0 Schema Specification

All datasets are published as **ZSTD-compressed Apache Parquet** files attached to immutable **GitHub Releases** (referenced by SHA-256 and exact row counts in [`manifests/latest.json`](../../manifests/latest.json)). Git history stores only lightweight text assets (`schema/`, `sql/`, `examples/`, `manifests/`).

## Core Invariants

1. **Immutable `subject_id` incarnations:** Identifiers are venue-scoped and never reuse an old ID after a stock split or ticker recycle (e.g., Lighter pre-split `SNDK_DELISTED` is `lighter:perp:139`; post-split `SNDK` is `lighter:perp:11649`).
2. **Bitemporal clocks (zero look-ahead):**
   - `valid_from_utc` / `valid_to_utc`: half-open interval `[from, to)` of venue validity.
   - `known_from_utc` / `known_to_utc`: when VenueDiff durably recorded this revision. Always filter `known_from_utc <= decision_ts` *before* resolving `valid_from_utc <= venue_ts`.
   - `announced_at_utc`, `scheduled_for_utc`, `effective_at_utc`, `observed_at_utc`, `change_after_utc`, `change_by_utc`: kept strictly separate on `events.parquet` — notice publication timestamps are never mixed with mathematical execution timestamps.
3. **Explicit `claim_kind`:**
   - `live_observation`: direct Point-in-Time observation from the live 2-min / 30-min collector.
   - `effective_event`: mathematically or on-chain verified effective transition (funding payout cadence step, Kalshi `fee_changes`, Hyperliquid `perpDeploy` tx, Polymarket UMA transition).
   - `scheduled_change`: announced future change (retains `operation='retract'` if cancelled).
   - `terminal_snapshot`: final parameters returned by a historical/expired endpoint (Deribit `history.deribit.com`, Kalshi `/historical/markets`, Binance `SETTLING` metadata). **Never** apply a terminal snapshot as an exact mid-life fee without explicitly opting in.
   - `observed_activity_bound`: lower/upper bound on observed archive activity (Binance S3 purged symbols recovered independently of `exchangeInfo`).
   - `regulatory_filing_index`: S3 regulatory filing metadata index (Kalshi CFTC Rule 40.6 notices & Rule 40.2 product certifications; S3 `LastModified` is stored in `observed_at_utc`, never conflated with legal effective date).
   - `announcement_notice`: official CEX trading-rule or delisting announcement notice (`announced_at_utc` = notice publication time).
4. **Exact decimal representation:** Prices, ticks, lots, margins, deductions, and fees are stored as canonical non-scientific decimal strings (never `FLOAT64`) to eliminate IEEE-754 boundary drift. All timestamps are UTC `TIMESTAMP(MICROS, tz=UTC)`.

---

## Tables (6 Core + 1 Optional Rewards)

### 1. `instruments.parquet`
Bitemporal SCD Type 2 specifications across 6 perpetual/futures venues (`binance`, `bybit`, `okx`, `deribit`, `hyperliquid`, `lighter`), combining live Point-in-Time state, Deribit expired contracts since 2016 (`claim_kind='terminal_snapshot'`), and Binance S3 purged symbols since 2020 (`claim_kind='observed_activity_bound'`).

Key columns: `subject_id`, `venue`, `symbol`, `canonical_base`, `asset_class` (`crypto` | `equity` | `commodity` | `fx` | `index`), `contract_type`, `payoff_model` (`linear` | `inverse` | `quanto`), `contract_size`, `contract_size_unit`, `quote_ccy`, `settle_ccy`, `margin_ccy`, `status_canonical` (`ACTIVE` | `REDUCE_ONLY` | `HALTED` | `DELISTED` | `PENDING`), `status_raw`, `tick_size`, `lot_size`, `min_qty`, `min_notional`, `funding_interval_sec`, `funding_cap`, `funding_floor`, `max_leverage`, `maker_fee`, `taker_fee`, `growth_mode`, `deployer_fee_scale`, `only_isolated`, `force_reduce_only`, `open_interest_limit_usd`, `delivery_at_utc`, `valid_from_utc`, `valid_to_utc`, `known_from_utc`, `known_to_utc`, `claim_kind`, `evidence_ref`.

### 2. `margin_tiers.parquet`
Atomic versioned margin/leverage ladders across venues. Replacing a 10-tier ladder with an 8-tier ladder replaces the entire `tiers` list atomically.
- `exposure_unit`: `usd_notional` (Binance, Bybit, multi-tier Hyperliquid) | `contracts` (OKX) | `base_qty` | `unbounded` (Lighter flat margin fractions & flat Hyperliquid leverage).
- `tiers`: `LIST<STRUCT<ordinal: int32, lower_bound: string, upper_bound: string, max_leverage: string, imr: string, mmr: string, closeout_mr: string, maint_deduction: string, deduction_unit: string>>`.
- All margin rates (`imr`, `mmr`, `closeout_mr`) are normalized fractions in `[0, 1]` (e.g., Lighter `200` bps → `"0.02"`). Undisclosed parameters remain `NULL`.
- Flattened view: [`sql/v1/margin_tiers_flat.sql`](../../sql/v1/margin_tiers_flat.sql).

### 3. `collateral_rules.parquet`
Atomic versioned margin collateral haircuts, LTV ratios, and tiered discount bands (`binance`, `bybit`, `okx`, `lighter`).
- `bands`: `LIST<STRUCT<ordinal: int32, min_amt: string, max_amt: string, collateral_ratio: string, haircut: string, liq_penalty_rate: string>>`.
- Plus `margin_mode`, `liquidation_threshold`, `borrowable`, `collateral_restrict`, and bitemporal clocks.

### 4. `prediction_rules.parquet`
Clean domain table for **Kalshi** (`record_scope='series'` for all series fee regimes + `record_scope='market'` for active & backfilled `/historical/markets`) and **Polymarket** (`record_scope='market'` for Gamma markets).
- **Polymarket identity:** distinct namespaces `gamma_market_id`, `condition_id`, `question_id`, and ordered `outcomes: LIST<STRUCT<outcome_index: int32, label: string, clob_token_id: string>>` storing exact 256-bit ERC-1155 token IDs as strings for direct orderbook/fill joins.
- **Polymarket fees:** true Gamma `feeSchedule` (`fees_enabled`, `fee_type`, `fee_rate`, `fee_exponent`, `fee_rebate_rate`, `taker_only`), avoiding the CLOB `/fee-rate` `1000` bps ceiling placeholder.
- **Kalshi hierarchy:** `series_ticker` → `event_ticker` → `market_ticker`, `fee_type`, `fee_multiplier`, `price_level_structure`, `price_ranges: LIST<STRUCT<start, end, step>>`, `rules_sha256`, `close_time_utc`, `settlement_ts_utc`, `result`.

### 5. `events.parquet`
Unified bitemporal rule-change event log merging clean live Point-in-Time diffs (`source_stream='live_pit'`, zero Polymarket rewards noise, zero duplicate UMA emissions) and the 8-venue historical archive (`source_stream='historical_backfill'`).
- Columns: `event_id`, `revision`, `operation` (`assert` | `retract`), `source_stream`, `claim_kind`, `venue`, `subject_id`, `symbol`, `scope`, `event_type`, `field`, `old_value_json`, `new_value_json`, `announced_at_utc`, `scheduled_for_utc`, `effective_at_utc`, `observed_at_utc`, `change_after_utc`, `change_by_utc`, `known_from_utc`, `link_status` (`resolved` | `unresolved` | `venue_wide` | `series_level`), `title`, `evidence_url`, `evidence_sha256`, `evidence_json`.
- **Polymarket UMA disputes:** deduplicated on native `(polygon, oracle, request_id)` across OOV2 & ManagedOOV2 and split into strictly chronological transitions (`uma_requested`, `uma_proposed`, `uma_disputed`, `uma_settled`). Market linking is strictly deterministic (explicit `market_id` in ancillary data or exact adapter hash); unlinked disputes carry `link_status='unresolved'` (never fuzzy title matched).
- **Hyperliquid HIP-3 governance:** decoded from on-chain `perpDeploy` transactions (excluding reverted txs and price `setOracle` ticks; deduplicating repeated no-op funding parameter setters).

### 6. `coverage.parquet`
Per-venue, per-endpoint reliability, missed-slot blind gaps, and historical backfill truncation bounds.
- Columns: `coverage_id`, `run_at_utc`, `stream` (`live_pit` | `historical_backfill`), `venue`, `endpoint`, `cadence_sec`, `outcome` (`ok` | `partial` | `error` | `missed_slot` | `truncated`), `pagination_complete`, `rows_observed`, `blind_gap_start_utc`, `blind_gap_end_utc`, `truncation_note`.
- Explicitly records collector blind gaps (including the 2026-11-22 13-minute stall prior to NVMe state migration), Hyperliquid's 300-tx explorer cap per address, OKX's ~95-day funding REST retention cap, and windowed prediction-market scans.

### 7. `prediction_rewards.parquet` *(Optional)*
Dedicated append-only Polymarket CLOB Liquidity Rewards observations completely decoupled from `events.parquet` (1 row per `(condition_id, reward_asset, sampled_at_utc)`).
- Columns: `condition_id`, `subject_id`, `venue`, `reward_asset`, `sampled_at_utc`, `daily_rate`, `min_size`, `max_spread`, `active`, `accepting_orders`, `known_from_utc`, `evidence_ref`.
- Time-weighted daily rate view: [`sql/v1/rewards_twap.sql`](../../sql/v1/rewards_twap.sql).

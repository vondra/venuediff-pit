# Changelog

## v1.0.0 — 2026-11-22

First frozen **v1.0** schema release replacing the v0.2.0 draft monolithic snapshot layout.

### Schema & Correctness
- **6 + 1 normalized Parquet architecture:** `instruments`, `margin_tiers`, `collateral_rules`, `prediction_rules`, `events`, `coverage`, plus dedicated `prediction_rewards`.
- **Zero look-ahead bitemporal model:** explicit `valid_from_utc`, `valid_to_utc`, `known_from_utc`, `known_to_utc`, `announced_at_utc`, `scheduled_for_utc`, `effective_at_utc`, `observed_at_utc`, `change_after_utc`, `change_by_utc`, and `claim_kind` (`live_observation`, `effective_event`, `scheduled_change`, `terminal_snapshot`, `observed_activity_bound`, `regulatory_filing_index`, `announcement_notice`).
- **Executable identity:** immutable `subject_id` incarnations (e.g. Lighter `lighter:perp:139` vs `lighter:perp:11649` across splits), Polymarket ordered `outcomes` with exact 256-bit ERC-1155 `clob_token_id` strings, Hyperliquid HIP-3 `spotMeta` token resolution (`USDC`, `USDT0`, `USDH`), and authoritative `asset_class` classification (`crypto`/`equity`/`commodity`/`fx`/`index`).
- **Contract economics & unified schedules:** explicit `payoff_model` (`linear`/`inverse`/`quanto`), `contract_size` + `contract_size_unit`, separated `quote_ccy`/`settle_ccy`/`margin_ccy`, unified `margin_tiers` with `exposure_unit` (`usd_notional`/`contracts`/`unbounded`), and canonical `status_canonical`.
- **Noise elimination & SLA transparency:** moved Polymarket Liquidity Rewards out of `events.parquet` into `prediction_rewards.parquet` (removing ~95% live diff noise), eliminated duplicate scalar `uma_resolution_status` emissions, and added `coverage.parquet` exposing missed slots and API truncation limits.

### Deeper Historical Backfill (All 8 Venues, 2016–2026)
- **Binance:** enumerated all USDT-M symbols directly from S3 `fundingRate/` independently of live `exchangeInfo`, recovering purged delisted perpetuals (survivorship-bias repair since 2020).
- **Deribit:** added all expired futures & perpetuals since July 2016 from `history.deribit.com` (`claim_kind='terminal_snapshot'`).
- **Hyperliquid HIP-3:** decoded on-chain `perpDeploy` governance transactions across all deployers and sub-deployers (excluding reverted txs and price `setOracle` ticks; deduplicating repeated funding parameter no-ops; flagging 300-tx explorer caps in `coverage.parquet`) plus continuous live explorer polling.
- **Kalshi:** added official historical `series/fee_changes`, flagship `/historical/markets` since 2021 (`terminal_snapshot`), and full S3 regulatory filing metadata index (`regulatory/notices/` and `regulatory/product-certifications/`).
- **Polymarket:** added deduplicated Polygon UMA OOV2 + ManagedOOV2 dispute transitions since July 2022 via Goldsky subgraphs with strictly deterministic linking (`link_status='unresolved'` when unlinked).

### Distribution
- Git repository contains only lightweight text artifacts (`schema/`, `sql/`, `examples/`, `manifests/latest.json`); immutable ZSTD Parquet files are published as GitHub Release assets with SHA-256 digests.

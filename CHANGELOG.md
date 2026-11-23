# Changelog

## v1.0.0 — 2026-11-23 (VenueDiff Open PIT — On-Chain & Permissionless Edition)

First public **v1.0** release of **VenueDiff Open PIT**, engineered strictly for clean public & commercial redistribution (**CC-BY-4.0** for Parquet datasets, **MIT** for schemas, SQL views, manifests, and example code).

### Clean On-Chain Scope (3 Permissionless Sources)
- **Hyperliquid L1 (`hyperliquid`):** Complete Core + HIP-3 builder DEX coverage (`perpDexs`, `allPerpMetas`, `spotMeta` collateral token resolution, `marginTables`, `growthMode`, `deployerFeeScale`, `onlyIsolated`) plus decoded on-chain `perpDeploy` governance history via `rpc.hyperliquid.xyz/explorer` (excluding reverted transactions and price `setOracle` ticks; deduplicating repeated no-op funding parameter setters; explicitly flagging 300-tx explorer caps in `coverage.parquet`).
- **Lighter L2 (`lighter`):** Complete perpetual and spot market catalog (`orderBookDetails`), margin collateral LTV/haircut schedules (`assetDetails`), immutable `market_id` split incarnations (e.g. pre-split `lighter:perp:139` vs post-split `lighter:perp:11649`), static USD open-interest caps, `force_reduce_only` flags, and historical trading activity windows (`claim_kind='observed_activity_bound'`) for delisted markets recovered from nonzero-volume `/api/v1/candles`.
- **Polygon UMA (`polygon_uma`):** Pure on-chain Polygon Optimistic Oracle V2 (`polygon-optimistic-oracle-v2`) and ManagedOOV2 (`polygon-managed-optimistic-oracle-v2`) dispute lifecycles read directly from Polygon smart contracts via public Goldsky subgraphs since 2022, deduplicated on `(oracle, request_id)` and split into strictly chronological point-in-time transitions (`uma_requested`, `uma_proposed`, `uma_disputed`, `uma_settled`).

### Schema, Licensing & Engineering Guarantees
- **5 normalized ZSTD Parquet tables:** `instruments.parquet`, `margin_tiers.parquet`, `collateral_rules.parquet`, `events.parquet`, and `coverage.parquet`.
- **Embedded Arrow schema metadata:** Every Parquet file embeds `venuediff_license=CC-BY-4.0`, `venuediff_schema_version=v1.0`, and `venuediff_sources=hyperliquid,lighter,polygon_uma`.
- **Unified dual license:** Resolved license consistency across `LICENSE`, `README.md`, `SCHEMA.md`, `manifests/latest.json`, and Parquet file metadata (`CC-BY-4.0` data / `MIT` code & schemas).
- **Zero look-ahead bitemporal model:** Separate `valid_from_utc`/`valid_to_utc`, `known_from_utc`/`known_to_utc`, `effective_at_utc`, `observed_at_utc`, and explicit `claim_kind`, with ready-to-run DuckDB SQL views under `sql/v1/`.
- **Immutable Release distribution:** Parquet files, `manifest.json`, and `SHA256SUMS.txt` are published as GitHub Release assets; Git tracks only lightweight text files (`< 1 MiB`).

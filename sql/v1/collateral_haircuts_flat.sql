-- VenueDiff Open PIT v1.0 — Flattened Collateral Haircuts & LTV View (Lighter L2)
--
-- Flattens `collateral_rules.parquet` into 1 row per collateral band with LTV,
-- haircut (`1 - collateral_ratio`), liquidation threshold, and liquidation penalty.

SELECT
    c.subject_id,
    c.venue,
    c.asset,
    c.margin_mode,
    b.band.ordinal          AS band_ordinal,
    b.band.min_amt          AS min_amt,
    b.band.max_amt          AS max_amt,
    b.band.collateral_ratio AS loan_to_value,
    b.band.haircut          AS haircut,
    b.band.liq_penalty_rate AS liq_penalty_rate,
    c.liquidation_threshold,
    c.valid_from_utc,
    c.valid_to_utc,
    c.known_from_utc,
    c.claim_kind
FROM read_parquet('collateral_rules.parquet') c,
     UNNEST(c.bands) AS b(band)
ORDER BY c.venue, c.asset, b.band.ordinal;

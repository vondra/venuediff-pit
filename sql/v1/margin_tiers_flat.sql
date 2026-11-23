-- VenueDiff Open PIT v1.0 — Flattened Margin Tiers View (`UNNEST` over atomic `LIST<STRUCT>`)
--
-- Flattens `margin_tiers.parquet` into 1 row per tier bracket while preserving
-- `exposure_unit` (`usd_notional` for multi-tier Hyperliquid marginTables vs
-- `unbounded` for Lighter flat margin fractions and flat Hyperliquid leverage).

SELECT
    m.subject_id,
    m.venue,
    m.symbol,
    m.margin_mode,
    m.exposure_unit,
    t.tier.ordinal          AS tier_ordinal,
    t.tier.lower_bound      AS lower_bound,
    t.tier.upper_bound      AS upper_bound,
    t.tier.max_leverage     AS max_leverage,
    t.tier.imr              AS imr,
    t.tier.mmr              AS mmr,
    t.tier.closeout_mr      AS closeout_mr,
    t.tier.maint_deduction  AS maint_deduction,
    t.tier.deduction_unit   AS deduction_unit,
    m.valid_from_utc,
    m.valid_to_utc,
    m.known_from_utc,
    m.claim_kind
FROM read_parquet('margin_tiers.parquet') m,
     UNNEST(m.tiers) AS t(tier)
ORDER BY m.venue, m.symbol, m.valid_from_utc, t.tier.ordinal;

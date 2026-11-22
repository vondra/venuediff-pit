-- VenueDiff v1.0 — Time-Weighted Daily Liquidity Rewards View (Polymarket)
--
-- Computes observed time-weighted average `daily_rate` per (UTC day, condition_id, reward_asset)
-- from `prediction_rewards.parquet`, capping individual sample spans at 3,600 seconds (2x the
-- 30-minute heavy sampling cadence) so collector outages do not extrapolate stale budgets.

WITH ordered AS (
    SELECT
        DATE_TRUNC('day', sampled_at_utc) AS reward_day_utc,
        condition_id,
        subject_id,
        reward_asset,
        sampled_at_utc,
        CAST(daily_rate AS DOUBLE) AS daily_rate_num,
        min_size,
        max_spread,
        active,
        accepting_orders,
        LEAD(sampled_at_utc) OVER (
            PARTITION BY DATE_TRUNC('day', sampled_at_utc), condition_id, reward_asset
            ORDER BY sampled_at_utc
        ) AS next_sampled_at_utc
    FROM read_parquet('prediction_rewards.parquet')
    WHERE daily_rate IS NOT NULL
),
weighted AS (
    SELECT
        reward_day_utc,
        condition_id,
        subject_id,
        reward_asset,
        daily_rate_num,
        min_size,
        max_spread,
        LEAST(
            COALESCE(EPOCH(next_sampled_at_utc - sampled_at_utc), 1800.0),
            3600.0
        ) AS span_sec
    FROM ordered
)
SELECT
    reward_day_utc,
    condition_id,
    subject_id,
    reward_asset,
    COUNT(*) AS sample_count,
    ROUND(SUM(span_sec), 0) AS covered_seconds,
    ROUND(SUM(daily_rate_num * span_sec) / NULLIF(SUM(span_sec), 0), 4) AS twap_daily_rate,
    MIN(daily_rate_num) AS min_daily_rate,
    MAX(daily_rate_num) AS max_daily_rate
FROM weighted
GROUP BY reward_day_utc, condition_id, subject_id, reward_asset
ORDER BY reward_day_utc DESC, twap_daily_rate DESC;

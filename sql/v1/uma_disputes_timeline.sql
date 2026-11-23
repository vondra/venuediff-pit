-- VenueDiff Open PIT v1.0 — Polygon UMA OOV2 / ManagedOOV2 Dispute Lifecycle Summary
--
-- Pivots chronological point-in-time `polygon_uma` transitions from `events.parquet`
-- into 1 row per on-chain disputed request, computing exact dispute-to-settlement duration.

SELECT
    subject_id,
    MIN(CASE WHEN field = 'uma_requested' THEN effective_at_utc END) AS requested_at_utc,
    MIN(CASE WHEN field = 'uma_proposed'  THEN effective_at_utc END) AS proposed_at_utc,
    MIN(CASE WHEN field = 'uma_disputed'  THEN effective_at_utc END) AS disputed_at_utc,
    MIN(CASE WHEN field = 'uma_settled'   THEN effective_at_utc END) AS settled_at_utc,
    ROUND(
        EPOCH(
            MIN(CASE WHEN field = 'uma_settled'  THEN effective_at_utc END)
            - MIN(CASE WHEN field = 'uma_disputed' THEN effective_at_utc END)
        ) / 3600.0,
        2
    ) AS dispute_to_settle_hours,
    COUNT(*) AS lifecycle_transitions
FROM read_parquet('events.parquet')
WHERE venue = 'polygon_uma'
  AND event_type = 'uma_resolution_changed'
GROUP BY subject_id
ORDER BY disputed_at_utc DESC NULLS LAST;

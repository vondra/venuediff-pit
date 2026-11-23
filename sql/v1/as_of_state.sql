-- VenueDiff Open PIT v1.0 — Bitemporal Point-in-Time As-Of State Query (Zero Look-Ahead)
--
-- Usage in DuckDB (2.x):
--   SET VARIABLE decision_ts = TIMESTAMPTZ '2026-11-23T23:59:59Z';
--   SET VARIABLE venue_ts    = TIMESTAMPTZ '2026-11-23T23:59:59Z';
--   -- Replace file paths with local files or immutable GitHub Release URLs from manifests/latest.json.
--
-- Semantics:
--   1. Filters by knowledge cutoff (`known_from_utc <= decision_ts`) BEFORE resolving protocol validity
--      (`valid_from_utc <= venue_ts < valid_to_utc`) so late corrections never leak into past decisions.
--   2. Excludes `claim_kind = 'observed_activity_bound'` and `'terminal_snapshot'` from exact-effective
--      state by default unless the caller explicitly opts in.
--   3. Left-joins `coverage.parquet` missed-slot/error blind gaps so callers see explicitly whether the
--      collector was blind at `venue_ts`.

WITH visible_instruments AS (
    SELECT
        i.*,
        ROW_NUMBER() OVER (
            PARTITION BY i.subject_id
            ORDER BY i.known_from_utc DESC, i.valid_from_utc DESC
        ) AS rn
    FROM read_parquet('instruments.parquet') i
    WHERE i.known_from_utc <= getvariable('decision_ts')
      AND (i.known_to_utc IS NULL OR getvariable('decision_ts') < i.known_to_utc)
      AND i.valid_from_utc <= getvariable('venue_ts')
      AND (i.valid_to_utc IS NULL OR getvariable('venue_ts') < i.valid_to_utc)
      AND i.claim_kind IN ('live_observation', 'effective_event')
),
active_blind_gaps AS (
    SELECT
        venue,
        endpoint,
        outcome,
        blind_gap_start_utc,
        blind_gap_end_utc,
        truncation_note
    FROM read_parquet('coverage.parquet')
    WHERE outcome IN ('missed_slot', 'error')
      AND blind_gap_start_utc IS NOT NULL
      AND blind_gap_end_utc IS NOT NULL
      AND blind_gap_start_utc <= getvariable('venue_ts')
      AND getvariable('venue_ts') <= blind_gap_end_utc
)
SELECT
    v.subject_id,
    v.venue,
    v.symbol,
    v.canonical_base,
    v.asset_class,
    v.contract_type,
    v.payoff_model,
    v.contract_size,
    v.contract_size_unit,
    v.quote_ccy,
    v.settle_ccy,
    v.margin_ccy,
    v.status_canonical,
    v.tick_size,
    v.lot_size,
    v.min_qty,
    v.min_notional,
    v.funding_interval_sec,
    v.max_leverage,
    v.growth_mode,
    v.deployer_fee_scale,
    v.only_isolated,
    v.force_reduce_only,
    v.open_interest_limit_usd,
    v.claim_kind,
    v.valid_from_utc,
    v.known_from_utc,
    CASE WHEN g.outcome IS NOT NULL THEN TRUE ELSE FALSE END AS in_collector_blind_gap,
    g.truncation_note AS blind_gap_note
FROM visible_instruments v
LEFT JOIN active_blind_gaps g
  ON g.venue = v.venue
WHERE v.rn = 1
ORDER BY v.venue, v.symbol;

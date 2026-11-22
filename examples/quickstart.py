#!/usr/bin/env python3
"""Quickstart example for venuediff-pit v1.0 (DuckDB + PyArrow).

Reads either a local directory containing the 7 v1.0 Parquet files OR downloads
immutable release assets directly from `manifests/latest.json`.

Usage:
    pip install duckdb pyarrow
    python3 examples/quickstart.py --data-dir ./parquet_v1
    python3 examples/quickstart.py --manifest manifests/latest.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import urllib.request
from pathlib import Path

import duckdb  # type: ignore
import pyarrow.parquet as pq  # type: ignore

TABLES = (
    "instruments",
    "margin_tiers",
    "collateral_rules",
    "prediction_rules",
    "events",
    "coverage",
    "prediction_rewards",
)


def download_from_manifest(manifest_path: Path, dest_dir: Path) -> Path:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    dest_dir.mkdir(parents=True, exist_ok=True)
    for tname, info in manifest["tables"].items():
        url = info["download_url"]
        expected_sha = info["sha256"]
        target = dest_dir / f"{tname}.parquet"
        req = urllib.request.Request(url, headers={"User-Agent": "venuediff-pit-quickstart/1.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
        got_sha = hashlib.sha256(raw).hexdigest()
        if got_sha != expected_sha:
            raise RuntimeError(f"SHA-256 mismatch for {tname}: expected {expected_sha}, got {got_sha}")
        target.write_bytes(raw)
    return dest_dir


def run_queries(data_dir: Path) -> None:
    con = duckdb.connect()

    print("=== 1. VenueDiff v1.0 Table Overview ===")
    for tname in TABLES:
        p = data_dir / f"{tname}.parquet"
        tbl = pq.read_table(str(p))
        print(f"  {tname:20s}  {tbl.num_rows:8,d} rows  {len(tbl.column_names):2d} cols  ({p.stat().st_size / 1024:7.1f} KiB)")

    print("\n=== 2. Active CEX Perpetuals Off 8-Hour Funding (instruments.parquet) ===")
    rows = con.execute(
        f"""
        SELECT venue,
               COUNT(*) AS active_perps,
               SUM(CASE WHEN funding_interval_sec != 28800 THEN 1 ELSE 0 END) AS non_8h,
               ROUND(100.0 * SUM(CASE WHEN funding_interval_sec != 28800 THEN 1 ELSE 0 END) / COUNT(*), 1) AS non_8h_pct
        FROM read_parquet('{data_dir / "instruments.parquet"}')
        WHERE venue IN ('binance', 'bybit', 'okx')
          AND claim_kind = 'live_observation'
          AND status_canonical = 'ACTIVE'
          AND funding_interval_sec IS NOT NULL
        GROUP BY venue
        ORDER BY non_8h_pct DESC
        """
    ).fetchall()
    for v, tot, n8, pct in rows:
        print(f"  {v:10s}  {n8:4d} / {tot:4d}  ({pct:4.1f}% non-8h)")

    print("\n=== 3. Historical Universe Coverage by claim_kind (instruments.parquet) ===")
    for r in con.execute(
        f"""
        SELECT venue, claim_kind, COUNT(*) AS rows,
               strftime(MIN(valid_from_utc), '%Y-%m-%d') AS earliest,
               strftime(MAX(COALESCE(valid_to_utc, valid_from_utc)), '%Y-%m-%d') AS latest
        FROM read_parquet('{data_dir / "instruments.parquet"}')
        GROUP BY 1, 2
        ORDER BY 1, 2
        """
    ).fetchall():
        print(f"  {r[0]:12s}  {r[1]:24s}  {r[2]:5,d} rows  ({r[3]} .. {r[4]})")

    print("\n=== 4. Unified Bitemporal Events by Venue & claim_kind (events.parquet) ===")
    for r in con.execute(
        f"""
        SELECT venue, claim_kind, COUNT(*) AS rows
        FROM read_parquet('{data_dir / "events.parquet"}')
        GROUP BY 1, 2
        ORDER BY rows DESC
        LIMIT 12
        """
    ).fetchall():
        print(f"  {r[0]:12s}  {r[1]:24s}  {r[2]:6,d}")

    print("\n=== 5. Margin Ladders by Venue & Exposure Unit (margin_tiers.parquet) ===")
    for r in con.execute(
        f"""
        SELECT venue, exposure_unit, COUNT(*) AS ladders,
               CAST(SUM(len(tiers)) AS BIGINT) AS total_tiers
        FROM read_parquet('{data_dir / "margin_tiers.parquet"}')
        GROUP BY 1, 2
        ORDER BY 1, 2
        """
    ).fetchall():
        print(f"  {r[0]:12s}  {r[1]:14s}  {r[2]:5,d} ladders  ({r[3]:6,d} tiers)")

    print("\n=== 6. Prediction Markets & ERC-1155 Outcomes (prediction_rules.parquet) ===")
    for r in con.execute(
        f"""
        SELECT venue, record_scope, claim_kind, COUNT(*) AS rows
        FROM read_parquet('{data_dir / "prediction_rules.parquet"}')
        GROUP BY 1, 2, 3
        ORDER BY 1, 2, 3
        """
    ).fetchall():
        print(f"  {r[0]:12s}  {r[1]:8s}  {r[2]:20s}  {r[3]:6,d}")

    print("\n=== 7. Collector SLA & Backfill Truncation Summary (coverage.parquet) ===")
    for r in con.execute(
        f"""
        SELECT stream, outcome, COUNT(*) AS rows
        FROM read_parquet('{data_dir / "coverage.parquet"}')
        GROUP BY 1, 2
        ORDER BY 1, 2
        """
    ).fetchall():
        print(f"  {r[0]:20s}  {r[1]:12s}  {r[2]:5,d}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Run verified DuckDB/PyArrow queries on venuediff-pit v1.0.")
    ap.add_argument("--data-dir", type=Path, default=None, help="Local directory with the 7 v1.0 Parquet files.")
    ap.add_argument("--manifest", type=Path, default=Path("manifests/latest.json"), help="Manifest JSON for downloading release assets.")
    args = ap.parse_args()

    if args.data_dir is not None:
        run_queries(args.data_dir)
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        d = download_from_manifest(args.manifest, Path(tmp))
        run_queries(d)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

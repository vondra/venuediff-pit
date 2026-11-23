#!/usr/bin/env python3
"""Quickstart example for venuediff-pit v1.0 (VenueDiff Open PIT — DuckDB + PyArrow).

Reads either a local directory containing the 5 v1.0 On-Chain Parquet files OR downloads
immutable release assets directly from `manifests/latest.json`, verifying SHA-256 digests
and embedded Arrow CC-BY-4.0 metadata before executing queries.

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
    "events",
    "coverage",
)
ALLOWED_SOURCES = {"hyperliquid", "lighter", "polygon_uma"}


def download_from_manifest(manifest_path: Path, dest_dir: Path) -> Path:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    dest_dir.mkdir(parents=True, exist_ok=True)
    for tname in TABLES:
        info = manifest["tables"][tname]
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

    print("=== 1. VenueDiff Open PIT v1.0 Table Overview & License Verification ===")
    for tname in TABLES:
        p = data_dir / f"{tname}.parquet"
        pf = pq.ParquetFile(str(p))
        meta = pf.schema_arrow.metadata or {}
        lic = (meta.get(b"venuediff_license") or b"").decode()
        srcs = (meta.get(b"venuediff_sources") or b"").decode()
        if lic != "CC-BY-4.0":
            raise RuntimeError(f"Unexpected Arrow license metadata on {tname}: {lic!r}")
        tbl = pf.read()
        if "venue" in tbl.column_names:
            distinct_v = {str(x) for x in tbl.column("venue").to_pylist() if x is not None}
            if not distinct_v.issubset(ALLOWED_SOURCES):
                raise RuntimeError(f"Disallowed venues in {tname}: {distinct_v - ALLOWED_SOURCES}")
        print(
            f"  {tname:18s}  {tbl.num_rows:7,d} rows  {len(tbl.column_names):2d} cols  "
            f"({p.stat().st_size / 1024:7.1f} KiB)  [{lic}; {srcs}]"
        )

    print("\n=== 2. Hyperliquid L1 Core vs HIP-3 Builder DEXes (instruments.parquet) ===")
    for r in con.execute(
        f"""
        SELECT
            CASE WHEN contract_type = 'PERP_CORE' THEN 'Core' ELSE contract_type END AS segment,
            COUNT(*) AS markets,
            SUM(CASE WHEN growth_mode = 'enabled' THEN 1 ELSE 0 END) AS growth_mode_on,
            SUM(CASE WHEN only_isolated THEN 1 ELSE 0 END) AS only_isolated
        FROM read_parquet('{data_dir / "instruments.parquet"}')
        WHERE venue = 'hyperliquid' AND claim_kind = 'live_observation' AND status_canonical = 'ACTIVE'
        GROUP BY 1
        ORDER BY markets DESC
        """
    ).fetchall():
        print(f"  {r[0]:20s}  {r[1]:4d} active  (growthMode={r[2]:3d}, isolated={r[3]:3d})")

    print("\n=== 3. Instruments Universe & Delisted /candles Bounds (instruments.parquet) ===")
    for r in con.execute(
        f"""
        SELECT venue, claim_kind, asset_class, COUNT(*) AS rows,
               strftime(MIN(valid_from_utc), '%Y-%m-%d') AS earliest,
               strftime(MAX(COALESCE(valid_to_utc, valid_from_utc)), '%Y-%m-%d') AS latest
        FROM read_parquet('{data_dir / "instruments.parquet"}')
        GROUP BY 1, 2, 3
        ORDER BY 1, 2, 4 DESC
        """
    ).fetchall():
        print(f"  {r[0]:12s}  {r[1]:24s}  {r[2]:10s}  {r[3]:4d} rows  ({r[4]} .. {r[5]})")

    print("\n=== 4. Margin Ladders by Source & Exposure Unit (margin_tiers.parquet) ===")
    for r in con.execute(
        f"""
        SELECT venue, exposure_unit, COUNT(*) AS ladders,
               CAST(SUM(len(tiers)) AS BIGINT) AS total_tiers
        FROM read_parquet('{data_dir / "margin_tiers.parquet"}')
        GROUP BY 1, 2
        ORDER BY 1, 2
        """
    ).fetchall():
        print(f"  {r[0]:12s}  {r[1]:14s}  {r[2]:4d} ladders  ({r[3]:5,d} tiers)")

    print("\n=== 5. On-Chain Events: HIP-3 Governance, Lighter /candles & Polygon UMA (events.parquet) ===")
    for r in con.execute(
        f"""
        SELECT venue, claim_kind, event_type, COUNT(*) AS rows
        FROM read_parquet('{data_dir / "events.parquet"}')
        GROUP BY 1, 2, 3
        ORDER BY rows DESC
        LIMIT 12
        """
    ).fetchall():
        print(f"  {r[0]:12s}  {r[1]:24s}  {r[2]:28s}  {r[3]:6,d}")

    print("\n=== 6. Collector SLA & Backfill Truncation Summary (coverage.parquet) ===")
    for r in con.execute(
        f"""
        SELECT stream, venue, outcome, COUNT(*) AS rows
        FROM read_parquet('{data_dir / "coverage.parquet"}')
        GROUP BY 1, 2, 3
        ORDER BY 1, 2, 3
        """
    ).fetchall():
        print(f"  {r[0]:20s}  {r[1]:12s}  {r[2]:10s}  {r[3]:4d}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Run verified DuckDB/PyArrow queries on venuediff-pit Open PIT v1.0.")
    ap.add_argument("--data-dir", type=Path, default=None, help="Local directory with the 5 v1.0 Parquet files.")
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

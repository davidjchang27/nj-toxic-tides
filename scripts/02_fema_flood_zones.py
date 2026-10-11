"""Phase 1b: look up the current FEMA flood zone (NFHL) at every KCSL site.

One point-in-polygon query per site against FEMA's National Flood Hazard Layer.
Results are cached to CSV so the script can be stopped and resumed.
"""

import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import geopandas as gpd
import pandas as pd

from arcgis import _get

ROOT = Path(__file__).resolve().parents[1]
NFHL_ZONES = "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query"
OUT = ROOT / "data" / "raw" / "fema_nfhl_by_site.csv"

# When a point touches several zone polygons, keep the most hazardous.
ZONE_PRIORITY = ["VE", "V", "AE", "AO", "AH", "A", "A99", "AR", "D", "X", "OPEN WATER", "AREA NOT INCLUDED"]


def rank(zone):
    return ZONE_PRIORITY.index(zone) if zone in ZONE_PRIORITY else len(ZONE_PRIORITY)


def lookup(pi_number, lon, lat):
    r = _get(
        NFHL_ZONES,
        {
            "geometry": f"{lon},{lat}",
            "geometryType": "esriGeometryPoint",
            "inSR": 4326,
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "FLD_ZONE,ZONE_SUBTY,SFHA_TF,STATIC_BFE",
            "returnGeometry": "false",
            "f": "json",
        },
    )
    feats = [f["attributes"] for f in r.json().get("features", [])]
    if not feats:
        return {"PI_NUMBER": pi_number, "fema_zone": "NO_NFHL_DATA", "fema_subtype": None, "fema_sfha": None,
                "fema_bfe": None, "fema_n_polys": 0}
    best = min(feats, key=lambda a: rank(a["FLD_ZONE"]))
    return {
        "PI_NUMBER": pi_number,
        "fema_zone": best["FLD_ZONE"],
        "fema_subtype": best["ZONE_SUBTY"],
        "fema_sfha": best["SFHA_TF"],
        "fema_bfe": best["STATIC_BFE"],
        "fema_n_polys": len(feats),
    }


if __name__ == "__main__":
    kcsl = gpd.read_file(sorted((ROOT / "data" / "raw").glob("kcsl_*.gpkg"))[-1]).to_crs(4326)
    done = set(pd.read_csv(OUT)["PI_NUMBER"]) if OUT.exists() else set()
    todo = kcsl[~kcsl["PI_NUMBER"].isin(done)]
    print(f"{len(done):,} cached, {len(todo):,} to query", flush=True)

    rows, failures = [], 0
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(lookup, r.PI_NUMBER, r.geometry.x, r.geometry.y) for r in todo.itertuples()]
        for i, fut in enumerate(as_completed(futures), 1):
            try:
                rows.append(fut.result())
            except Exception as exc:  # keep going; failures are retried on the next run
                failures += 1
                print(f"  failed: {exc}", file=sys.stderr)
            if len(rows) >= 500 or i == len(futures):
                pd.DataFrame(rows).to_csv(OUT, mode="a", header=not OUT.exists(), index=False)
                rows = []
                print(f"  {i:,} / {len(futures):,} queried ({failures} failures)", flush=True)

    print(f"Done. {failures} failures (re-run to retry).")

"""Phase 1b (cont.): fill sites the effective NFHL does not cover.

FEMA's effective NFHL service has no flood-zone polygons for parts of NJ (notably Atlantic and
Morris counties as of 2026-10), even though paper/older maps are effective there. For those
sites, fall back to FEMA's Preliminary, then Pending, NFHL and record the source.
These maps are not yet legally effective, so results must be labeled as such.
"""

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import geopandas as gpd
import pandas as pd

from arcgis import _get

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "data" / "raw" / "fema_nfhl_by_site.csv"
SOURCES = {
    "preliminary": "https://hazards.fema.gov/arcgis/rest/services/PrelimPending/Prelim_NFHL/MapServer/28/query",
    "pending": "https://hazards.fema.gov/arcgis/rest/services/PrelimPending/Pending_NFHL/MapServer/28/query",
}
PRIORITY = ["VE", "V", "AE", "AO", "AH", "A", "A99", "AR", "D", "X", "OPEN WATER", "AREA NOT INCLUDED"]


def lookup(lon, lat):
    for source, url in SOURCES.items():
        feats = _get(url, {
            "geometry": f"{lon},{lat}", "geometryType": "esriGeometryPoint", "inSR": 4326,
            "spatialRel": "esriSpatialRelIntersects", "outFields": "FLD_ZONE,ZONE_SUBTY,SFHA_TF,STATIC_BFE",
            "returnGeometry": "false", "f": "json",
        }).json().get("features", [])
        if feats:
            best = min((f["attributes"] for f in feats),
                       key=lambda a: PRIORITY.index(a["FLD_ZONE"]) if a["FLD_ZONE"] in PRIORITY else 99)
            return source, best, len(feats)
    return "none", None, 0


if __name__ == "__main__":
    fema = pd.read_csv(CSV)
    if "fema_source" not in fema:
        fema["fema_source"] = "effective"
    gaps = fema[fema["fema_zone"].eq("NO_NFHL_DATA") & fema["fema_source"].eq("effective")]
    kcsl = gpd.read_file(sorted((ROOT / "data" / "raw").glob("kcsl_*.gpkg"))[-1]).to_crs(4326).set_index("PI_NUMBER")
    pts = kcsl.loc[gaps["PI_NUMBER"], "geometry"]
    print(f"Filling {len(pts)} sites with no effective NFHL data")

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda p: lookup(p.x, p.y), pts))

    for idx, (source, attrs, n) in zip(gaps.index, results):
        fema.loc[idx, "fema_source"] = source
        if attrs:
            fema.loc[idx, ["fema_zone", "fema_subtype", "fema_sfha", "fema_bfe", "fema_n_polys"]] = [
                attrs["FLD_ZONE"], attrs["ZONE_SUBTY"], attrs["SFHA_TF"], attrs["STATIC_BFE"], n]

    tmp = CSV.with_suffix(".tmp")
    fema.to_csv(tmp, index=False)
    os.replace(tmp, CSV)  # atomic swap so a concurrent reader never sees a partial file
    print(fema.loc[gaps.index, "fema_source"].value_counts().to_string())
    print(fema.loc[gaps.index, "fema_zone"].value_counts().to_string())

"""Phase 1c-i: read NOAA's NJ sea-level-rise geodatabases once and cache clean polygons.

Writes data/processed/noaa_slr_{slr,low}.parquet: one row per polygon part with
`level_ft` (0-10 ft above MHHW) and `region`. Kept in NOAA's native CRS (EPSG:4269).

Polygons are NOT repaired. About 1% are invalid (mostly self-touching rings), and both
make_valid and buffer(0) took tens of minutes per layer on the largest shoreline polygons
(>600k vertices). Repair is unnecessary here: the analysis only runs `intersects`
predicates, which GEOS evaluates correctly on these rings. It never runs overlay operations
(intersection/union), which do require valid input. Invalid counts are logged.
"""

import time
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyogrio

# GDAL's default polygon assembly ("organizePolygons") tests every ring against every
# other ring, which ran >30 min on NOAA's Southern NJ layers (tens of thousands of holes).
# ESRI geodatabases store each CW outer ring followed by its CCW holes, so GDAL can rely
# on that order. Verified identical output (area and ring count) on NJ_Middle_slr_0ft.
pyogrio.set_gdal_config_options({"OGR_ORGANIZE_POLYGONS": "CCW_INNER_JUST_AFTER_CW_OUTER"})

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "raw" / "noaa_slr"
OUT = ROOT / "data" / "processed"
REGIONS = ["Northern", "Middle", "Southern"]
LEVELS_FT = range(0, 11)

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for kind in ("slr", "low"):
        parts = []
        for level in LEVELS_FT:
            for region in REGIONS:
                t = time.time()
                gdb = SRC / region / f"NJ_{region}_slr_final_dist.gdb"
                polys = gpd.read_file(gdb, layer=f"NJ_{region}_{kind}_{level}ft", columns=[])
                n_invalid = int((~polys.is_valid).sum())
                polys = polys[~polys.is_empty].explode(index_parts=False)
                polys["level_ft"], polys["region"] = level, region
                parts.append(polys)
                print(f"{kind} {level:>2} ft {region:<8} {len(polys):>7,} parts, "
                      f"{n_invalid:>4} invalid (kept), {time.time() - t:5.1f}s", flush=True)
        out = OUT / f"noaa_slr_{kind}.parquet"
        gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=parts[0].crs).to_parquet(out)
        print(f"saved {out.name}", flush=True)

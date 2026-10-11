"""Phase 2 fix: measure NEW inundation near each site, excluding water that exists today.

NOAA's SLR layers are cumulative AND include current tidal water: open ocean is inside every
level from 0 to 10 ft. A buffer test like "within 100 m of land inundated at <=3 ft" therefore
flags every waterfront site, even where no new land floods. (806 of the 1,536 sites flagged in
Phase 1 were reached only by the 0 ft layer.)

Method: lay a regular grid of sample points inside each site's buffer and find each point's
lowest inundation level (0-10 ft). Points at level 0 are today's water and are ignored. A site
is exposed at N ft if some sample point that is dry today (first level >= 1) floods at <= N ft.

Adds to kcsl_sites_enriched.{gpkg,csv}:
  new_inund_ft_within_{100m,250m}   lowest level (1-10 ft) at which dry-today land within the
                                    buffer floods. NaN if none at <=10 ft.
  frac_new_inund_3ft_{100m,250m}    share of dry-today sample points in the buffer that flood
                                    at <=3 ft (how much of the surroundings floods).
"""

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
CRS = "EPSG:3424"  # US feet
FT_PER_M = 3.28084
RADII = {"100m": (100, 20), "250m": (250, 25)}  # radius m, grid spacing m


def disc_offsets(radius_m, spacing_m):
    r, d = radius_m * FT_PER_M, spacing_m * FT_PER_M
    g = np.arange(-r, r + d / 2, d)
    xx, yy = np.meshgrid(g, g)
    keep = xx ** 2 + yy ** 2 <= r ** 2
    return xx[keep], yy[keep]


def first_levels(points_native, slr):
    """Lowest NOAA level whose polygons contain each point (NaN if none <=10 ft)."""
    first = np.full(len(points_native), np.nan)
    probe = gpd.GeoDataFrame({"i": np.arange(len(points_native))}, geometry=points_native, crs=slr.crs)
    for level in sorted(slr["level_ft"].unique()):
        pending = probe[np.isnan(first)]
        if pending.empty:
            break
        polys = slr.loc[slr["level_ft"] == level, ["geometry"]]
        hit = gpd.sjoin(polys, pending, predicate="intersects")["i"].unique()
        first[hit] = level
        print(f"    level {level:>2}: {np.isfinite(first).sum():>9,} of {len(first):,} sample points inundated",
              flush=True)
    return first


if __name__ == "__main__":
    sites = gpd.read_file(PROC / "kcsl_sites_enriched.gpkg").to_crs(CRS)
    slr = gpd.read_parquet(PROC / "noaa_slr_slr.parquet")[["level_ft", "geometry"]]

    for label, (radius_m, spacing_m) in RADII.items():
        # Only sites whose buffer touches any polygon at <=10 ft can have new inundation nearby.
        cand = sites[sites[f"slr_ft_connected_within_{label}"].notna()]
        dx, dy = disc_offsets(radius_m, spacing_m)
        sx = np.repeat(cand.geometry.x.to_numpy(), len(dx)) + np.tile(dx, len(cand))
        sy = np.repeat(cand.geometry.y.to_numpy(), len(dy)) + np.tile(dy, len(cand))
        owner = np.repeat(cand.index.to_numpy(), len(dx))
        print(f"{label}: {len(cand):,} candidate sites x {len(dx)} sample points = {len(sx):,}", flush=True)

        pts = gpd.GeoSeries(gpd.points_from_xy(sx, sy), crs=CRS).to_crs(slr.crs)
        lvl = first_levels(pts, slr)

        df = pd.DataFrame({"site": owner, "lvl": lvl})
        dry_today = df[~(df["lvl"] == 0)]  # level 0 = today's water; NaN = dry even at 10 ft
        new = dry_today.dropna().groupby("site")["lvl"].min()
        frac = (dry_today.assign(f=dry_today["lvl"] <= 3).groupby("site")["f"].mean())

        sites[f"new_inund_ft_within_{label}"] = new.reindex(sites.index)
        sites[f"frac_new_inund_3ft_{label}"] = frac.reindex(sites.index).fillna(0.0)

    sites.to_file(PROC / "kcsl_sites_enriched.gpkg", driver="GPKG")
    s4326 = sites.to_crs(4326)
    sites.drop(columns="geometry").assign(lon=s4326.geometry.x, lat=s4326.geometry.y).to_csv(
        PROC / "kcsl_sites_enriched.csv", index=False)

    for label in RADII:
        old = (sites[f"slr_ft_connected_within_{label}"] <= 3).sum()
        new = (sites[f"new_inund_ft_within_{label}"] <= 3).sum()
        print(f"Exposed at <=3 ft within {label}: {old:,} (old, incl. today's water) -> {new:,} (new land only)")

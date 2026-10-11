"""Phase 1c: join every KCSL site to sea-level-rise inundation, FEMA flood zone,
Overburdened Community (OBC) status, and its 2020 census block group.

Outputs (data/processed/):
  kcsl_sites_enriched.gpkg / .csv  one row per contaminated site
  block_groups_2020.gpkg           all NJ block groups with 2020 population and OBC flag
"""

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"
OUT.mkdir(parents=True, exist_ok=True)

CRS = "EPSG:3424"  # NAD83 / New Jersey State Plane (US feet), NJDEP's native system
NEAR_BUFFERS_FT = {"100m": 328.084, "250m": 820.21}  # tolerance for approximate KCSL coordinates


def latest(pattern):
    return sorted(RAW.glob(pattern))[-1]


def load_sites():
    sites = gpd.read_file(latest("kcsl_*.gpkg")).to_crs(CRS)
    keep = ["PI_NUMBER", "SITE_ID", "PI_NAME", "ADDRESS", "MUNIC", "COUNTY", "ZIP_CODE", "STATUS", "CATEGORY",
            "LEAD", "REM_LEVEL", "CEA_STATUS", "DN_STATUS", "EC_STATUS", "NPL_STATUS", "STATUS_DT", "geometry"]
    return sites[keep]


def slr_first_levels(points):
    """Lowest SLR level (ft above MHHW) reaching each site, for several probes.

    Uses the polygons cached by 03a_prepare_slr.py. Polygons sit on the LEFT of the
    join so shapely prepares them: some shoreline polygons have >600k vertices, and
    unprepared point-in-polygon tests against them are very slow.
    """
    probes = {"slr_ft_connected": ("slr", 0.0), "slr_ft_lowlying": ("low", 0.0)}
    probes.update({f"slr_ft_connected_within_{k}": ("slr", ft) for k, ft in NEAR_BUFFERS_FT.items()})

    layers = {kind: gpd.read_parquet(OUT / f"noaa_slr_{kind}.parquet") for kind in ("slr", "low")}
    first = pd.DataFrame(np.nan, index=points.index, columns=list(probes))
    for name, (kind, buffer_ft) in probes.items():
        geoms = points.buffer(buffer_ft) if buffer_ft else points.geometry
        probe = gpd.GeoDataFrame({"pid": points.index}, geometry=geoms, crs=CRS).to_crs(layers[kind].crs)
        hits = gpd.sjoin(layers[kind][["level_ft", "geometry"]], probe, predicate="intersects")
        first[name] = hits.groupby("pid")["level_ft"].min()
        print(f"  {name}: {first[name].notna().sum():,} sites reached by 0-10 ft", flush=True)
    return first


def load_block_groups():
    bg = gpd.read_file(f"zip://{RAW / 'tl_2020_34_bg.zip'}").to_crs(CRS)[["GEOID", "ALAND", "AWATER", "geometry"]]

    geo_cols = {2: "SUMLEV", 7: "LOGRECNO", 9: "GEOID"}
    geo = pd.read_csv(RAW / "pl2020" / "njgeo2020.pl", sep="|", header=None, dtype=str, encoding="latin-1",
                      usecols=list(geo_cols)).rename(columns=geo_cols)
    geo = geo[geo["SUMLEV"] == "150"]
    seg1 = pd.read_csv(RAW / "pl2020" / "nj000012020.pl", sep="|", header=None, dtype=str, usecols=[4, 5])
    seg1.columns = ["LOGRECNO", "pop_2020"]
    pop = geo.merge(seg1, on="LOGRECNO")[["GEOID", "pop_2020"]].astype({"pop_2020": int})

    bg = bg.merge(pop, on="GEOID", how="left", validate="1:1")
    assert bg["pop_2020"].notna().all(), "every block group should have a 2020 population"
    return bg


if __name__ == "__main__":
    sites = load_sites()
    print(f"Sites: {len(sites):,}")

    # --- Sea-level rise -------------------------------------------------------
    print("Intersecting NOAA SLR layers (0-10 ft above MHHW)...")
    sites = sites.join(slr_first_levels(sites))

    # --- FEMA ----------------------------------------------------------------
    fema = pd.read_csv(RAW / "fema_nfhl_by_site.csv").drop_duplicates("PI_NUMBER", keep="last")
    sites = sites.merge(fema, on="PI_NUMBER", how="left", validate="1:1")
    sites["fema_sfha"] = sites["fema_sfha"].eq("T")
    print(f"FEMA zone missing for {sites['fema_zone'].isna().sum()} sites")

    # --- OBC + block groups --------------------------------------------------
    obc = gpd.read_file(latest("obc_block_groups_*.gpkg")).to_crs(CRS)
    obc = obc[["GEOID", "OVERBURDENED_COMMUNITY_CRITERI", "LOW_INCOME_PCT", "MINORITY_PCT", "PCTLINGUAGEISO", "geometry"]]
    obc = obc.rename(columns={"OVERBURDENED_COMMUNITY_CRITERI": "obc_criteria", "GEOID": "obc_geoid"})

    # The OBC layer uses 2010 block-group geography (472 GEOIDs differ from 2020) plus 4
    # tribal areas, so OBC status is assigned spatially rather than by GEOID:
    #   sites:            point inside an OBC polygon
    #   2020 block groups: interior representative point inside an OBC polygon
    bg = load_block_groups()
    rep = gpd.GeoDataFrame(bg[["GEOID"]], geometry=bg.representative_point(), crs=CRS)
    bg_in_obc = gpd.sjoin(rep, obc[["geometry"]], predicate="within")["GEOID"].unique()
    bg["is_obc"] = bg["GEOID"].isin(bg_in_obc)
    print(f"2020 block groups flagged OBC: {bg['is_obc'].sum():,} of {len(bg):,} "
          f"({bg.loc[bg['is_obc'], 'pop_2020'].sum() / bg['pop_2020'].sum():.1%} of 2020 population)")

    sites = gpd.sjoin(sites, bg[["GEOID", "pop_2020", "geometry"]], how="left", predicate="within")
    sites = sites.drop(columns="index_right").rename(columns={"GEOID": "bg_geoid", "pop_2020": "bg_pop_2020"})
    print(f"Sites outside any block group (offshore/geocode error): {sites['bg_geoid'].isna().sum()}")

    in_obc = gpd.sjoin(sites[["PI_NUMBER", "geometry"]], obc, predicate="within")
    in_obc = in_obc.drop(columns=["geometry", "index_right"]).drop_duplicates("PI_NUMBER")
    sites = sites.merge(in_obc, on="PI_NUMBER", how="left")
    sites["is_obc"] = sites["obc_geoid"].notna()
    print(f"Sites inside an OBC: {sites['is_obc'].sum():,} of {len(sites):,}")

    # --- Save ----------------------------------------------------------------
    sites.to_file(OUT / "kcsl_sites_enriched.gpkg", driver="GPKG")
    sites.drop(columns="geometry").assign(
        lon=sites.to_crs(4326).geometry.x, lat=sites.to_crs(4326).geometry.y
    ).to_csv(OUT / "kcsl_sites_enriched.csv", index=False)
    bg.to_file(OUT / "block_groups_2020.gpkg", driver="GPKG")
    print(f"Saved {len(sites):,} sites and {len(bg):,} block groups to {OUT}")

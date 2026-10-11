"""Phase 2 maps: statewide overview and town-level maps of flood-exposed contaminated sites.

Each town map shows:
  - land that is dry today but inundated at <=3 ft sea-level rise (NOAA 3 ft extent minus
    the 0 ft extent, which is today's tidal water)
  - NJ Overburdened Community block groups
  - contaminated sites where dry land within 100 m floods at <=3 ft (primary definition)
"""

from pathlib import Path

import contextily as cx
import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd
import shapely
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

ROOT = Path(__file__).resolve().parents[1]
RAW, PROC, FIGS = ROOT / "data" / "raw", ROOT / "data" / "processed", ROOT / "outputs" / "figures"
WEB = "EPSG:3857"

TOWNS = {  # KCSL MUNIC -> Census county-subdivision NAMELSAD
    "ATLANTIC CITY": "Atlantic City city",
    "JERSEY CITY": "Jersey City city",
    "CAMDEN CITY": "Camden city",
    "NEWARK CITY": "Newark city",
    "KEARNY TOWN": "Kearny town",
}

WATER = "#4a90c2"
OBC_FILL = "#c51b7d"
EXPOSED = "#d7301f"
OTHER = "#6b6b6b"
SUPERFUND = "#ffd23f"
INK = "#1a1a1a"


def load():
    sites = gpd.read_file(PROC / "kcsl_sites_enriched.gpkg").to_crs(WEB)
    sites["exposed"] = sites["new_inund_ft_within_100m"] <= 3
    sites["superfund"] = sites["NPL_STATUS"].isin(["Final", "Subsite"])
    obc = gpd.read_file(sorted(RAW.glob("obc_block_groups_*.gpkg"))[-1]).to_crs(WEB)
    munis = gpd.read_file(f"zip://{RAW / 'tl_2020_34_cousub.zip'}").to_crs(WEB)
    slr = gpd.read_parquet(PROC / "noaa_slr_slr.parquet")
    slr = slr[slr["level_ft"].isin([0, 3])]
    return sites, obc, munis, slr


def new_flooding(slr, bbox_web):
    """Land inundated at 3 ft but not at 0 ft, inside the map box (layers are cumulative)."""
    box = gpd.GeoSeries.from_xy([bbox_web[0], bbox_web[2]], [bbox_web[1], bbox_web[3]], crs=WEB).to_crs(slr.crs)
    xmin, ymin, xmax, ymax = box.total_bounds
    near = slr.iloc[slr.sindex.query(shapely.box(xmin, ymin, xmax, ymax))]

    def merged(level):
        g = shapely.clip_by_rect(near.loc[near["level_ft"] == level].geometry.values, xmin, ymin, xmax, ymax)
        return shapely.union_all(shapely.make_valid(g[~shapely.is_empty(g)]))

    return gpd.GeoSeries([shapely.difference(merged(3), merged(0))], crs=slr.crs).to_crs(WEB)


def legend_handles(n_exp, n_other, n_sf):
    h = [
        Patch(facecolor=WATER, alpha=0.55, label="Dry land today that floods at ≤3 ft sea-level rise (NOAA)"),
        Patch(facecolor=OBC_FILL, alpha=0.18, edgecolor=OBC_FILL, label="Overburdened Community (NJ EJ Law)"),
        Line2D([], [], marker="o", ls="none", color=EXPOSED, mec="white", ms=8,
               label=f"Contaminated site with newly flooded land within 100 m (n={n_exp})"),
        Line2D([], [], marker="o", ls="none", color=OTHER, mec="white", ms=5, alpha=0.8,
               label=f"Other contaminated site (n={n_other})"),
    ]
    if n_sf:
        h.append(Line2D([], [], marker="*", ls="none", color=SUPERFUND, mec=INK, ms=15,
                        label=f"Federal Superfund site, flood-exposed (n={n_sf})"))
    return h


def town_map(munic, sites, obc, munis, slr, brief_path=None):
    """brief_path: if set, save a compact version (no title/footer) for the policy brief."""
    boundary = munis[munis["NAMELSAD"] == TOWNS[munic]]
    assert len(boundary) == 1, munic
    minx, miny, maxx, maxy = boundary.total_bounds
    pad = 0.08 * max(maxx - minx, maxy - miny)
    bbox = (minx - pad, miny - pad, maxx + pad, maxy + pad)

    town_sites = sites[sites["MUNIC"] == munic]
    exp, other = town_sites[town_sites["exposed"]], town_sites[~town_sites["exposed"]]
    sf = exp[exp["superfund"]]

    flood = new_flooding(slr, bbox)
    obc_box = obc.cx[bbox[0]:bbox[2], bbox[1]:bbox[3]]

    fig, ax = plt.subplots(figsize=(6.5, 6.5) if brief_path else (10, 10))
    ax.set_xlim(bbox[0], bbox[2])
    ax.set_ylim(bbox[1], bbox[3])
    obc_box.plot(ax=ax, facecolor=OBC_FILL, alpha=0.18, edgecolor=OBC_FILL, linewidth=0.4)
    flood.plot(ax=ax, color=WATER, alpha=0.6, linewidth=0)
    boundary.boundary.plot(ax=ax, color=INK, linewidth=1.6, linestyle="--")
    other.plot(ax=ax, color=OTHER, markersize=14, alpha=0.8, edgecolor="white", linewidth=0.4, zorder=4)
    exp.plot(ax=ax, color=EXPOSED, markersize=34, edgecolor="white", linewidth=0.6, zorder=5)
    if len(sf):
        sf.plot(ax=ax, color=SUPERFUND, marker="*", markersize=320, edgecolor=INK, linewidth=0.8, zorder=6)
    cx.add_basemap(ax, source=cx.providers.Esri.WorldGrayCanvas, crs=WEB, attribution_size=6)
    ax.set_axis_off()

    if brief_path:
        ax.legend(handles=legend_handles(len(exp), len(other), len(sf)), loc="upper right", fontsize=6.5,
                  framealpha=0.94)
        fig.savefig(brief_path, dpi=250, bbox_inches="tight")
        plt.close(fig)
        return brief_path, len(exp), len(town_sites)

    pct_obc = 100 * exp["is_obc"].mean() if len(exp) else 0
    ax.set_title(f"{boundary['NAMELSAD'].iloc[0].rsplit(' ', 1)[0]}, NJ: contaminated sites exposed to sea-level rise\n"
                 f"{len(exp)} of {len(town_sites)} known contaminated sites have land within 100 m that floods at ≤3 ft "
                 f"({pct_obc:.0f}% of them in Overburdened Communities)",
                 loc="left", fontsize=11.5, color=INK)
    ax.legend(handles=legend_handles(len(exp), len(other), len(sf)), loc="upper left", fontsize=8.5,
              framealpha=0.94)
    fig.text(0.01, 0.005, "Sources: NJDEP Known Contaminated Sites List & OBC layer (pulled 2026-10-10); NOAA OCM "
             "sea-level-rise inundation (ft above MHHW); US Census 2020. Site points are approximate addresses. "
             "Screening analysis only.", fontsize=7, color="#666666", wrap=True)
    out = FIGS / f"map_{munic.lower().replace(' ', '_')}.png"
    fig.savefig(out, dpi=250, bbox_inches="tight")
    plt.close(fig)
    return out, len(exp), len(town_sites)


def state_map(sites, obc, munis):
    fig, ax = plt.subplots(figsize=(8.5, 12))
    state = munis.dissolve()
    obc.plot(ax=ax, facecolor=OBC_FILL, alpha=0.22, linewidth=0)
    state.boundary.plot(ax=ax, color=INK, linewidth=0.6)
    sites[~sites["exposed"]].plot(ax=ax, color=OTHER, markersize=1.5, alpha=0.35, zorder=3)
    exp = sites[sites["exposed"]]
    exp.plot(ax=ax, color=EXPOSED, markersize=7, edgecolor="white", linewidth=0.2, zorder=4)
    cx.add_basemap(ax, source=cx.providers.Esri.WorldGrayCanvas, crs=WEB, attribution_size=6)
    ax.set_axis_off()
    ax.set_title(f"New Jersey: {len(exp):,} known contaminated sites have land within 100 m\n"
                 f"that floods at ≤3 ft of sea-level rise ({100 * exp['is_obc'].mean():.0f}% in Overburdened Communities)",
                 loc="left", fontsize=12, color=INK)
    ax.legend(handles=[
        Patch(facecolor=OBC_FILL, alpha=0.22, label="Overburdened Community"),
        Line2D([], [], marker="o", ls="none", color=EXPOSED, mec="white", ms=7, label="Flood-exposed contaminated site"),
        Line2D([], [], marker="o", ls="none", color=OTHER, alpha=0.5, ms=4, label="Other contaminated site"),
    ], loc="lower right", fontsize=9, framealpha=0.94)
    out = FIGS / "map_statewide.png"
    fig.savefig(out, dpi=250, bbox_inches="tight")
    plt.close(fig)
    return out


if __name__ == "__main__":
    sites, obc, munis, slr = load()
    print("statewide ->", state_map(sites, obc, munis).name)
    for munic in TOWNS:
        out, n_exp, n = town_map(munic, sites, obc, munis, slr)
        print(f"{munic:<15} {n_exp:>4} / {n:<4} exposed -> {out.name}")

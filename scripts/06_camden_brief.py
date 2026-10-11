"""Phase 3: two-page policy brief for Camden, NJ (HTML -> PDF via headless Chrome).

Every number in the brief is computed here from data/processed, so the brief can be rebuilt
after a data refresh.
"""

import base64
import html
import importlib.util
import subprocess
from datetime import date
from pathlib import Path

import contextily as cx
import geopandas as gpd
import matplotlib.pyplot as plt
import shapely
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

ROOT = Path(__file__).resolve().parents[1]
PROC, RAW, OUT = ROOT / "data" / "processed", ROOT / "data" / "raw", ROOT / "outputs" / "brief_camden"
OUT.mkdir(parents=True, exist_ok=True)
CRS, WEB = "EPSG:3424", "EPSG:3857"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

AUTHOR = "David Chang"
AFFILIATION = "Magnet High School, Class of 2027"
CONTACT = "david.j.chang27@gmail.com"
REPO_URL = "github.com/davidjchang27/nj-toxic-tides"

spec = importlib.util.spec_from_file_location("maps", Path(__file__).with_name("05_maps.py"))
maps = importlib.util.module_from_spec(spec)
spec.loader.exec_module(maps)


def camden_numbers(sites, bg, cam):
    rep = gpd.GeoDataFrame(bg[["GEOID", "pop_2020", "is_obc"]], geometry=bg.representative_point(), crs=CRS)
    res = gpd.sjoin(rep, cam[["geometry"]], predicate="within").drop(columns="index_right")
    c = sites[sites["MUNIC"] == "CAMDEN CITY"]
    e = c[c["new_inund_ft_within_100m"] <= 3]

    def residents_near(subset):
        buf = gpd.GeoDataFrame(geometry=subset.buffer(3280.84), crs=CRS)
        ids = gpd.sjoin(res, buf, predicate="within")["GEOID"].unique()
        return int(res.loc[res["GEOID"].isin(ids), "pop_2020"].sum())

    corridor = e[e["ADDRESS"].str.contains("ADMIRAL WILSON|BAIRD|MICKLE|17TH", case=False, na=False)
                 | e["PI_NAME"].str.contains("GATEWAY", na=False)]
    return {
        "pop": int(res["pop_2020"].sum()),
        "pop_obc_share": res.loc[res["is_obc"], "pop_2020"].sum() / res["pop_2020"].sum(),
        "n_sites": len(c),
        "n_exp": len(e),
        "n_exp_1": int((e["new_inund_ft_within_100m"] <= 1).sum()),
        "n_exp_2": int((e["new_inund_ft_within_100m"] <= 2).sum()),
        "n_active": int((e["STATUS"] == "Active").sum()),
        "n_cea": int((e["CEA_STATUS"] == "Ongoing").sum()),
        "n_fema": int(e["fema_sfha"].astype(bool).sum()),
        "n_lep": int(e["obc_criteria"].str.contains("Limited English", na=False).sum()),
        "near_3": residents_near(e),
        "near_1": residents_near(e[e["new_inund_ft_within_100m"] <= 1]),
        "corridor": corridor,
        "exposed": e,
    }


def corridor_map(sites, corridor, slr, path):
    cw = corridor.to_crs(WEB)
    minx, miny, maxx, maxy = cw.total_bounds
    pad = 0.35 * max(maxx - minx, maxy - miny)
    bbox = (minx - pad, miny - pad, maxx + pad, maxy + pad)

    box = gpd.GeoSeries.from_xy([bbox[0], bbox[2]], [bbox[1], bbox[3]], crs=WEB).to_crs(slr.crs)
    xmin, ymin, xmax, ymax = box.total_bounds
    near = slr.iloc[slr.sindex.query(shapely.box(xmin, ymin, xmax, ymax))]

    def merged(level):
        g = shapely.clip_by_rect(near.loc[near["level_ft"] == level].geometry.values, xmin, ymin, xmax, ymax)
        return shapely.union_all(shapely.make_valid(g[~shapely.is_empty(g)]))

    water0, f1, f3 = merged(0), merged(1), merged(3)
    new1 = gpd.GeoSeries([shapely.difference(f1, water0)], crs=slr.crs).to_crs(WEB)
    new3 = gpd.GeoSeries([shapely.difference(f3, f1)], crs=slr.crs).to_crs(WEB)

    allw = sites.to_crs(WEB).cx[bbox[0]:bbox[2], bbox[1]:bbox[3]]
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    ax.set_xlim(bbox[0], bbox[2])
    ax.set_ylim(bbox[1], bbox[3])
    new3.plot(ax=ax, color="#9ecae1", alpha=0.85, linewidth=0)
    new1.plot(ax=ax, color="#2171b5", alpha=0.85, linewidth=0)
    other = allw[~allw.index.isin(corridor.index)]
    other.plot(ax=ax, color=maps.OTHER, markersize=12, edgecolor="white", linewidth=0.4, zorder=4)
    cw.plot(ax=ax, color=maps.EXPOSED, markersize=46, edgecolor="white", linewidth=0.7, zorder=5)
    cx.add_basemap(ax, source=cx.providers.Esri.WorldGrayCanvas, crs=WEB, attribution_size=5)
    ax.set_axis_off()
    ax.legend(handles=[
        Patch(color="#2171b5", alpha=0.85, label="Dry land today that floods at 1 ft of sea-level rise"),
        Patch(color="#9ecae1", alpha=0.85, label="... additional land that floods at 2–3 ft"),
        Line2D([], [], marker="o", ls="none", color=maps.EXPOSED, mec="white", ms=7,
               label="Flood-exposed contaminated site in this corridor"),
        Line2D([], [], marker="o", ls="none", color=maps.OTHER, mec="white", ms=5, label="Other contaminated site"),
    ], loc="upper right", fontsize=6.5, framealpha=0.95)
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def img(path):
    return "data:image/png;base64," + base64.b64encode(Path(path).read_bytes()).decode()


KEEP_UPPER = {"ABC", "SJPC", "US", "LLC", "RCA", "DBA", "RMH", "PSE&G", "NJ", "II"}


def nice(name):
    return " ".join(w if w in KEEP_UPPER else w.title() for w in str(name).split())


def site_rows(df, n=7):
    df = df.sort_values(["new_inund_ft_within_100m", "frac_new_inund_3ft_100m"], ascending=[True, False]).head(n)
    rows = []
    for r in df.itertuples():
        status = "Active" if r.STATUS == "Active" else "Post-remediation"
        gw = "Yes" if r.CEA_STATUS == "Ongoing" else "—"
        rows.append(f"<tr><td>{html.escape(nice(r.PI_NAME))}</td><td>{html.escape(nice(r.ADDRESS))}</td>"
                    f"<td class='num'>{int(r.new_inund_ft_within_100m)} ft</td>"
                    f"<td class='num'>{r.frac_new_inund_3ft_100m:.0%}</td><td>{status}</td><td>{gw}</td></tr>")
    return "\n".join(rows)


def build_html(n, state, figs):
    pct_near3 = n["near_3"] / n["pop"]
    pct_near1 = n["near_1"] / n["pop"]
    corr = n["corridor"]
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Rising Water, Buried Contamination: Camden</title>
<style>
@page {{ size: Letter; margin: 0.45in 0.55in; }}
body {{ font-family: "Helvetica Neue", Helvetica, Arial, sans-serif; color: #1a1a1a; font-size: 9.2pt; line-height: 1.34; margin: 0; }}
h1 {{ font-size: 19pt; line-height: 1.15; margin: 0 0 2pt; letter-spacing: -0.2pt; }}
.sub {{ font-size: 10.5pt; color: #444; margin: 0 0 6pt; }}
.byline {{ font-size: 8.5pt; color: #666; border-bottom: 2px solid #b2182b; padding-bottom: 5pt; margin-bottom: 9pt; }}
h2 {{ font-size: 10.5pt; color: #b2182b; margin: 8pt 0 2pt; text-transform: uppercase; letter-spacing: 0.4pt; }}
.key {{ background: #f6f1f1; border-left: 4px solid #b2182b; padding: 7pt 11pt; margin: 6pt 0 8pt; }}
.key ul {{ margin: 0; padding-left: 14pt; }} .key li {{ margin: 3pt 0; }}
.stats {{ display: flex; gap: 8pt; margin: 8pt 0; }}
.stat {{ flex: 1; border: 1px solid #ddd; border-radius: 4pt; padding: 6pt 8pt; }}
.stat b {{ display: block; font-size: 17pt; color: #b2182b; line-height: 1.1; }}
.stat span {{ font-size: 8pt; color: #444; }}
figure {{ margin: 6pt 0; text-align: center; }} figure img {{ max-width: 100%; max-height: 4.6in; }}
figure.corr img {{ max-height: 2.45in; }}
figcaption {{ font-size: 7.6pt; color: #666; }}
table {{ width: 100%; border-collapse: collapse; font-size: 7.8pt; margin: 4pt 0; }}
th {{ text-align: left; border-bottom: 1.5px solid #1a1a1a; padding: 2pt 4pt; }}
td {{ border-bottom: 1px solid #e3e3e3; padding: 2pt 4pt; vertical-align: top; }}
td.num, th.num {{ text-align: right; white-space: nowrap; }}
ol {{ padding-left: 15pt; margin: 3pt 0; }} ol li {{ margin: 3pt 0; }}
.small {{ font-size: 7.3pt; color: #555; line-height: 1.3; }}
.page-break {{ break-before: page; }}
</style></head><body>

<h1>Rising Water, Buried Contamination</h1>
<p class="sub">Sea-level rise and known contaminated sites in Camden, New Jersey</p>
<p class="byline">{AUTHOR} · {AFFILIATION} · {date.today():%B %Y} · Independent student research, data and code: {REPO_URL}</p>

<div class="key"><b>Key findings</b>
<ul>
<li><b>{n['n_exp']} of Camden's {n['n_sites']} known contaminated sites</b> have land within 100 m that is dry today
but would flood with 3 ft of sea-level rise. For <b>{n['n_exp_1']}</b> of them, that flooding begins at just
<b>1 ft</b>, within New Jersey's projected range for 2050 (0.9–2.1 ft).</li>
<li><b>{n['n_active']}</b> of these sites are active cleanups, and <b>{n['n_cea']}</b> have contaminated groundwater
under an ongoing Classification Exception Area. {n['n_fema']} of {n['n_exp']} are already in FEMA's 1% annual-chance floodplain.</li>
<li>About <b>{n['near_3']:,} residents ({pct_near3:.0%} of the city)</b> live within 1 km of one of these sites.
Every Camden neighborhood is an Overburdened Community under the NJ Environmental Justice Law.</li>
<li>The largest cluster is the <b>Admiral Wilson Boulevard / Gateway Park corridor</b> along the Cooper River:
{len(corr)} flood-exposed sites, {(corr['STATUS'] == 'Active').sum()} of them active cleanups.</li>
</ul></div>

<div class="stats">
<div class="stat"><b>{n['n_exp']}</b><span>contaminated sites with new flooding nearby at ≤3 ft</span></div>
<div class="stat"><b>{n['n_exp_1']}</b><span>where it starts at 1 ft (2050-range)</span></div>
<div class="stat"><b>{n['near_1']:,}</b><span>residents within 1 km of a 1-ft site ({pct_near1:.0%} of Camden)</span></div>
<div class="stat"><b>{state['ratio']:.1f}×</b><span>statewide: OBC residents' likelihood of living near such sites vs. other NJ residents</span></div>
</div>

<figure><img src="{img(figs['town'])}" alt="Map of Camden showing contaminated sites and land that floods at 3 ft of sea-level rise">
<figcaption>Red: contaminated sites with land within 100 m that floods at ≤3 ft. Blue: land that is dry today but floods at
≤3 ft (NOAA). Pink: Overburdened Community block groups. Site points are approximate address locations.</figcaption></figure>

<div class="page-break"></div>
<h2>Hotspot: Admiral Wilson Boulevard / Gateway Park</h2>
<figure class="corr"><img src="{img(figs['corridor'])}" alt="Close-up map of the Admiral Wilson Boulevard corridor">
<figcaption>Dark blue floods at 1 ft of sea-level rise. Light blue floods at 2–3 ft. This corridor along the Cooper River
holds a concentration of active cleanups and redevelopment parcels.</figcaption></figure>

<table><thead><tr><th>Site (NJDEP KCSL name)</th><th>Address</th><th class="num">Flooding<br>begins at</th>
<th class="num">Land within 100 m<br>flooded at 3 ft</th><th>Cleanup status</th><th>Groundwater<br>CEA</th></tr></thead>
<tbody>{site_rows(n['exposed'])}</tbody></table>
<p class="small">The seven Camden sites where new flooding begins at the lowest sea level. The full list of {n['n_exp']} sites is in the project repository.</p>

<h2>Why it matters</h2>
<p>Many cleanups leave contamination in place under engineered caps, or rely on restrictions on using contaminated
groundwater. Such remedies may not have been designed for higher sea levels. Repeated tidal or storm flooding can erode caps, raise
groundwater, and carry contaminated soil and water into nearby streets, homes, and the Cooper and Delaware rivers.
New Jersey's REAL flood rules, adopted in January 2026, raise building standards for <i>new</i> development and
substantial improvements in flood areas. Existing contaminated sites raise a separate question: whether their
remedies will hold as sea levels rise.</p>

<h2>Questions and recommendations</h2>
<ol>
<li><b>Remedy resilience review.</b> For the {n['n_exp_1']} sites where flooding begins at 1 ft, ask NJDEP and the responsible
Licensed Site Remediation Professionals whether the remedies account for projected sea-level rise.</li>
<li><b>Plan integration.</b> Add these sites to Camden City and Camden County hazard-mitigation and climate plans, so that
flood projects along the Cooper River consider contamination.</li>
<li><b>Post-flood checks.</b> After major floods, inspect caps and monitoring wells at exposed sites and publish the results.</li>
<li><b>Community notice.</b> Share site-level flood exposure with residents in English and Spanish:
{n['n_lep']} of the {n['n_exp']} exposed sites are in block groups that also meet the Limited-English criterion.</li>
</ol>

<h2>Methods and limitations</h2>
<p class="small">Sites: NJDEP Known Contaminated Sites List (pulled Oct. 10, 2026). Flooding: NOAA Office for Coastal Management
sea-level-rise inundation layers (feet above Mean Higher High Water). Today's tidal water is excluded, so only land that is
dry today counts. Communities: NJDEP Overburdened Community layer and the 2020 Census. A site counts as exposed if any
land within 100 m of its mapped point floods at ≤3 ft. This is a <b>screening analysis</b>. Site points are approximate
addresses, the NOAA layers model permanent inundation only (not storm surge, which reaches farther), and the analysis does
not predict that any specific site will release contamination. Statewide comparison: OBC residents are {state['ratio']:.1f}×
(95% CI {state['lo']:.1f}–{state['hi']:.1f}) as likely as other residents to live within 1 km of a flood-exposed contaminated site.
Projection range: NJ Science and Technical Advisory Panel (2019).
Contact: {CONTACT}.</p>
</body></html>"""


if __name__ == "__main__":
    sites = gpd.read_file(PROC / "kcsl_sites_enriched.gpkg").to_crs(CRS)
    sites["exposed"] = sites["new_inund_ft_within_100m"] <= 3
    sites["superfund"] = sites["NPL_STATUS"].isin(["Final", "Subsite"])
    bg = gpd.read_file(PROC / "block_groups_2020.gpkg").to_crs(CRS)
    munis = gpd.read_file(f"zip://{RAW / 'tl_2020_34_cousub.zip'}").to_crs(CRS)
    cam = munis[munis["NAMELSAD"] == "Camden city"]

    n = camden_numbers(sites, bg, cam)
    import pandas as pd
    pop = pd.read_csv(ROOT / "outputs" / "tables" / "population_level_ratios.csv")
    row = pop[(pop["scope"] == "all NJ") & pop["definition"].str.startswith("New flooding")].iloc[0]
    state = {"ratio": row["ratio"], "lo": row["ratio_lo"], "hi": row["ratio_hi"]}

    slr = gpd.read_parquet(PROC / "noaa_slr_slr.parquet")
    slr = slr[slr["level_ft"].isin([0, 1, 3])]
    corridor_map(sites, n["corridor"], slr, OUT / "camden_corridor_map.png")
    obc = gpd.read_file(sorted(RAW.glob("obc_block_groups_*.gpkg"))[-1]).to_crs(WEB)
    mw = gpd.read_file(f"zip://{RAW / 'tl_2020_34_cousub.zip'}").to_crs(WEB)
    maps.town_map("CAMDEN CITY", sites.to_crs(WEB), obc, mw, slr, brief_path=OUT / "camden_town_map.png")
    figs = {"town": OUT / "camden_town_map.png", "corridor": OUT / "camden_corridor_map.png"}

    html_path = OUT / "camden_brief.html"
    html_path.write_text(build_html(n, state, figs))
    n["exposed"].drop(columns="geometry").sort_values("new_inund_ft_within_100m").to_csv(
        OUT / "camden_exposed_sites.csv", index=False)

    pdf = OUT / "camden_brief.pdf"
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={pdf}", html_path.as_uri()], check=True, capture_output=True)
    print(f"Brief: {pdf} ({pdf.stat().st_size / 1024:,.0f} KB)")
    print({k: v for k, v in n.items() if k not in ("corridor", "exposed")})

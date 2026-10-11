"""Phase 2: are flood-exposed contaminated sites disproportionately in Overburdened Communities?

Two complementary questions:

A. SITE LEVEL. Among NJ's known contaminated sites, are flood-exposed ones more likely to sit
   in an OBC than unexposed ones? Reported as an odds ratio (OR), both crude and
   Mantel-Haenszel (MH) stratified by county. The county-stratified OR compares sites within
   the same county, so it is not driven by coastal counties simply being more urban and diverse.

B. POPULATION LEVEL. What share of OBC vs. non-OBC residents live within 1 km of a
   flood-exposed contaminated site? Reported as a ratio, with a 95% CI from a block-group
   bootstrap.

Every exposure definition is reported, not only the primary one, because the result can
depend on the definition (see the sensitivity table and forest plot).

Primary definition: land within 100 m of the site that is dry today floods at <=3 ft of
sea-level rise (see 03b_new_inundation_near_sites.py; NOAA layers include today's water, so a
plain buffer test would flag every waterfront site).
  - 3 ft ~ NJ's central 2100 projection (2019 STAP / later Rutgers update) and above the
    2050 likely range of 0.9-2.1 ft.
  - 100 m allows for KCSL coordinates that are approximate address points, not parcels.
  NOTE: this definition was fixed after the Phase 1 descriptive look, so it is not
  pre-registered. That is why all definitions are reported side by side.
"""

from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import fisher_exact
from statsmodels.stats.contingency_tables import StratifiedTable, Table2x2

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
TABLES = ROOT / "outputs" / "tables"
FIGS = ROOT / "outputs" / "figures"
for d in (TABLES, FIGS):
    d.mkdir(parents=True, exist_ok=True)

CRS = "EPSG:3424"
NEAR_PEOPLE_FT = 3280.84  # 1 km
N_BOOT = 2000
RNG = np.random.default_rng(20261011)
PRIMARY = "New flooding ≤3 ft within 100 m"

INK, MUTED, ACCENT = "#1a1a1a", "#8a8a8a", "#2b5c8a"


def exposure_definitions(s):
    sfha = s["fema_sfha"].astype(bool)
    effective = s["fema_source"].eq("effective")
    return {
        # name: (exposed mask, analysis subset mask)
        "SLR ≤1 ft (site point)": (s["slr_ft_connected"] <= 1, None),
        "SLR ≤2 ft (site point)": (s["slr_ft_connected"] <= 2, None),
        "SLR ≤3 ft (site point)": (s["slr_ft_connected"] <= 3, None),
        "New flooding ≤1 ft within 100 m": (s["new_inund_ft_within_100m"] <= 1, None),
        "New flooding ≤2 ft within 100 m": (s["new_inund_ft_within_100m"] <= 2, None),
        PRIMARY: (s["new_inund_ft_within_100m"] <= 3, None),
        "New flooding ≤3 ft within 250 m": (s["new_inund_ft_within_250m"] <= 3, None),
        "≥25% of land within 100 m floods at ≤3 ft": (s["frac_new_inund_3ft_100m"] >= 0.25, None),
        "[Flawed] Near today's OR future water ≤3 ft": (s["slr_ft_connected_within_100m"] <= 3, None),
        "FEMA 1% floodplain (effective maps only)": (sfha, effective),
        "FEMA 1% floodplain (incl. preliminary)": (sfha, None),
        "FEMA floodplain OR new flooding ≤3 ft (100 m)": (sfha | (s["new_inund_ft_within_100m"] <= 3), None),
    }


def site_level(s, exposed, label):
    obc = s["is_obc"].to_numpy()
    e = exposed.to_numpy()
    a, b = int((e & obc).sum()), int((e & ~obc).sum())
    c, d = int((~e & obc).sum()), int((~e & ~obc).sum())
    crude = Table2x2(np.array([[a, b], [c, d]]))
    crude_lo, crude_hi = crude.oddsratio_confint()

    strata = []
    for _, g in s.assign(_e=e).groupby("COUNTY"):
        ge, go = g["_e"].to_numpy(), g["is_obc"].to_numpy()
        if ge.any() and (~ge).any():
            strata.append(np.array([[(ge & go).sum(), (ge & ~go).sum()], [(~ge & go).sum(), (~ge & ~go).sum()]]))
    st = StratifiedTable(strata)
    mh_lo, mh_hi = st.oddsratio_pooled_confint()

    return {
        "definition": label,
        "n_sites": len(s),
        "n_exposed": a + b,
        "pct_exposed_in_obc": 100 * a / max(a + b, 1),
        "pct_unexposed_in_obc": 100 * c / max(c + d, 1),
        "or_crude": crude.oddsratio,
        "or_crude_lo": crude_lo,
        "or_crude_hi": crude_hi,
        "p_fisher": fisher_exact([[a, b], [c, d]])[1],
        "n_county_strata": len(strata),
        "or_mh_county": st.oddsratio_pooled,
        "or_mh_lo": mh_lo,
        "or_mh_hi": mh_hi,
        "p_mh": st.test_null_odds().pvalue,
        "p_breslow_day": st.test_equal_odds().pvalue,
    }


def population_level(bg, exposed_sites, label, restrict_counties=None):
    rep = gpd.GeoDataFrame(bg[["GEOID", "pop_2020", "is_obc"]], geometry=bg.representative_point(), crs=CRS)
    if restrict_counties is not None:
        rep = rep[rep["GEOID"].str[2:5].isin(restrict_counties)]
    buf = gpd.GeoDataFrame(geometry=exposed_sites.buffer(NEAR_PEOPLE_FT), crs=CRS)
    near_ids = gpd.sjoin(rep, buf, predicate="within")["GEOID"].unique()

    pop = rep["pop_2020"].to_numpy(float)
    obc = rep["is_obc"].to_numpy()
    near = rep["GEOID"].isin(near_ids).to_numpy()

    def ratio(idx):
        p, o, n = pop[idx], obc[idx], near[idx]
        r_obc = (p * (o & n)).sum() / (p * o).sum()
        r_non = (p * (~o & n)).sum() / (p * ~o).sum()
        return r_obc, r_non, r_obc / r_non

    r_obc, r_non, rr = ratio(np.arange(len(rep)))
    boots = np.array([ratio(RNG.integers(0, len(rep), len(rep)))[2] for _ in range(N_BOOT)])
    return {
        "definition": label,
        "scope": "all NJ" if restrict_counties is None else "counties with ≥1 exposed site",
        "obc_residents_near": int((pop * (obc & near)).sum()),
        "non_obc_residents_near": int((pop * (~obc & near)).sum()),
        "pct_obc_residents_near": 100 * r_obc,
        "pct_non_obc_residents_near": 100 * r_non,
        "ratio": rr,
        "ratio_lo": np.percentile(boots, 2.5),
        "ratio_hi": np.percentile(boots, 97.5),
    }


def municipality_table(s, exposed):
    active = ~s["STATUS"].isin(["Active - Post Rem"]) & ~s["LEAD"].eq("UHOT")
    t = s.assign(
        exposed=exposed,
        exposed_obc=exposed & s["is_obc"],
        exposed_active=exposed & active,
        exposed_npl=exposed & s["NPL_STATUS"].isin(["Final", "Subsite"]),
        sfha=s["fema_sfha"].astype(bool),
        sfha_prelim=s["fema_sfha"].astype(bool) & s["fema_source"].eq("preliminary"),
        point_3ft=s["slr_ft_connected"] <= 3,
    ).groupby(["MUNIC", "COUNTY"]).agg(
        sites=("PI_NUMBER", "size"),
        exposed_3ft_100m=("exposed", "sum"),
        exposed_in_obc=("exposed_obc", "sum"),
        exposed_active_cleanup=("exposed_active", "sum"),
        exposed_superfund=("exposed_npl", "sum"),
        point_inundated_3ft=("point_3ft", "sum"),
        fema_floodplain=("sfha", "sum"),
        fema_floodplain_preliminary_only=("sfha_prelim", "sum"),
    )
    return t.sort_values(["exposed_in_obc", "exposed_3ft_100m"], ascending=False)


def forest_plot(res, path):
    res = res.iloc[::-1].reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(10, 6.2))
    y = np.arange(len(res))
    off = 0.17
    ax.hlines(y + off, res["or_crude_lo"], res["or_crude_hi"], color=MUTED, lw=1.6)
    ax.plot(res["or_crude"], y + off, "o", ms=7, mfc="white", mec=MUTED, mew=1.6, label="Crude (statewide)")
    ax.hlines(y - off, res["or_mh_lo"], res["or_mh_hi"], color=ACCENT, lw=2.2)
    ax.plot(res["or_mh_county"], y - off, "o", ms=8, color=ACCENT, label="Within-county (Mantel-Haenszel)")
    ax.axvline(1, color=INK, lw=1, ls="--")
    ax.set_xscale("log")
    ticks = [0.5, 0.75, 1, 1.5, 2, 3]
    ax.set_xticks(ticks, [f"{t:g}" for t in ticks])
    ax.xaxis.set_minor_formatter(plt.NullFormatter())
    ax.set_xlim(0.3, 3.2)
    ax.set_yticks(y, [f"{d}   (n={n:,})" for d, n in zip(res["definition"], res["n_exposed"])])
    for lbl in ax.get_yticklabels():
        if lbl.get_text().startswith(PRIMARY):
            lbl.set_fontweight("bold")
        if lbl.get_text().startswith("[Flawed]"):
            lbl.set_color(MUTED)
    ax.set_xlabel("Odds ratio that a flood-exposed site (vs. other contaminated sites) is in an OBC\n"
                  ">1 = exposed sites more concentrated in OBCs · bars = 95% CI · log scale")
    fig.suptitle("Is flood exposure among NJ contaminated sites concentrated in Overburdened Communities?",
                 x=0.01, ha="left", fontsize=12, color=INK)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2, frameon=False)
    ax.grid(axis="x", ls=":", color="#bbbbbb")
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def population_plot(pop_res, path):
    """Share of OBC vs. non-OBC residents within 1 km of a flood-exposed contaminated site."""
    r = pop_res[pop_res["scope"] == "all NJ"].reset_index(drop=True)
    labels = {
        "SLR ≤3 ft (site point)": "Site itself inundated\nat ≤3 ft sea-level rise",
        PRIMARY: "Dry land within 100 m of site\nfloods at ≤3 ft sea-level rise",
        "FEMA floodplain OR new flooding ≤3 ft (100 m)": "In FEMA 1% floodplain, or\nnew flooding ≤3 ft within 100 m",
    }
    fig, ax = plt.subplots(figsize=(10, 5.6))
    x = np.arange(len(r))
    w = 0.36
    obc = ax.bar(x - w / 2, r["pct_obc_residents_near"], w, color="#b2182b", label="Overburdened Community residents")
    non = ax.bar(x + w / 2, r["pct_non_obc_residents_near"], w, color="#9aa5b1", label="All other NJ residents")
    for bars, col in ((obc, "obc_residents_near"), (non, "non_obc_residents_near")):
        for b, (_, row) in zip(bars, r.iterrows()):
            ax.annotate(f"{b.get_height():.1f}%\n({row[col] / 1e6:.2f}M)", (b.get_x() + b.get_width() / 2, b.get_height()),
                        xytext=(0, 3), textcoords="offset points", ha="center", va="bottom", fontsize=9, color=INK)
    for i, row in r.iterrows():
        ax.annotate(f"{row['ratio']:.1f}× more likely\n(95% CI {row['ratio_lo']:.1f}–{row['ratio_hi']:.1f})",
                    (i, max(row["pct_obc_residents_near"], row["pct_non_obc_residents_near"]) + 9),
                    ha="center", fontsize=9.5, fontweight="bold", color="#b2182b")
    ax.set_xticks(x, [labels[d] for d in r["definition"]])
    ax.set_ylabel("Residents living within 1 km of a\nflood-exposed contaminated site (%)")
    ax.set_ylim(0, r[["pct_obc_residents_near", "pct_non_obc_residents_near"]].to_numpy().max() * 1.45)
    ax.set_title("Who lives near New Jersey's flood-exposed contaminated sites?", loc="left", fontsize=12,
                 color=INK, pad=30)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2, frameon=False)
    ax.grid(axis="y", ls=":", color="#bbbbbb")
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    fig.text(0.01, -0.02, "Sources: NJDEP Known Contaminated Sites List & Overburdened Communities (2026); NOAA SLR "
             "inundation; FEMA NFHL; 2020 Census. Block-group population by interior point.", fontsize=8, color=MUTED)
    fig.tight_layout()
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    sites = gpd.read_file(PROC / "kcsl_sites_enriched.gpkg").to_crs(CRS)
    bg = gpd.read_file(PROC / "block_groups_2020.gpkg").to_crs(CRS)
    defs = exposure_definitions(sites)

    # --- A. Site level, every definition ---------------------------------------
    rows = []
    for label, (exposed, subset) in defs.items():
        sub = sites if subset is None else sites[subset]
        rows.append(site_level(sub, exposed[sub.index], label))
    site_res = pd.DataFrame(rows)
    site_res.to_csv(TABLES / "site_level_odds_ratios.csv", index=False)
    forest_plot(site_res, FIGS / "fig1_forest_odds_ratios.png")

    # --- A2. Sensitivity of the primary definition to which sites count ----------
    primary = defs[PRIMARY][0]
    subsets = {
        "All KCSL sites": pd.Series(True, index=sites.index),
        "Excl. home heating-oil tanks (UHOT)": ~sites["LEAD"].eq("UHOT"),
        "Active cleanup only (excl. post-remediation, UHOT)":
            ~sites["STATUS"].eq("Active - Post Rem") & ~sites["LEAD"].eq("UHOT"),
        "Complex sites only (remedial level C2/C3/D)": sites["REM_LEVEL"].isin(["C2", "C3", "D"]),
    }
    sens = pd.DataFrame([site_level(sites[m], primary[m], name) for name, m in subsets.items()])
    sens.to_csv(TABLES / "site_level_sensitivity_primary.csv", index=False)

    # --- B. Population level -------------------------------------------------------
    pop_rows = []
    for label in ["SLR ≤3 ft (site point)", PRIMARY, "FEMA floodplain OR new flooding ≤3 ft (100 m)"]:
        exp_sites = sites[defs[label][0]]
        counties = exp_sites["bg_geoid"].str[2:5].unique()
        pop_rows.append(population_level(bg, exp_sites, label))
        pop_rows.append(population_level(bg, exp_sites, label, restrict_counties=counties))
    pop_res = pd.DataFrame(pop_rows)
    pop_res.to_csv(TABLES / "population_level_ratios.csv", index=False)
    population_plot(pop_res, FIGS / "fig2_population_near_exposed_sites.png")

    # --- Municipalities -------------------------------------------------------------
    muni = municipality_table(sites, primary)
    muni.to_csv(TABLES / "municipality_ranking.csv")

    # --- Console report -------------------------------------------------------------
    pd.set_option("display.width", 220)
    fmt = lambda r, k: f"{r[k]:.2f} [{r[k.replace('or_mh_county', 'or_mh') + '_lo' if 'mh' in k else k + '_lo']:.2f}-" \
                       f"{r[k.replace('or_mh_county', 'or_mh') + '_hi' if 'mh' in k else k + '_hi']:.2f}]"
    print("\nA. SITE LEVEL: odds that a flood-exposed site is in an OBC vs. an unexposed site")
    for _, r in site_res.iterrows():
        print(f"  {r['definition']:<42} n_exp={r['n_exposed']:>5,}  inOBC {r['pct_exposed_in_obc']:5.1f}% vs "
              f"{r['pct_unexposed_in_obc']:5.1f}%  crude OR {fmt(r, 'or_crude')} p={r['p_fisher']:.2g}  "
              f"county-adj OR {fmt(r, 'or_mh_county')} p={r['p_mh']:.2g}  BD p={r['p_breslow_day']:.2g}")
    print(f"\nA2. SENSITIVITY ({PRIMARY})")
    for _, r in sens.iterrows():
        print(f"  {r['definition']:<52} n={r['n_sites']:>6,} n_exp={r['n_exposed']:>5,}  "
              f"crude OR {fmt(r, 'or_crude')}  county-adj OR {fmt(r, 'or_mh_county')} p={r['p_mh']:.2g}")
    print("\nB. POPULATION LEVEL: residents within 1 km of a flood-exposed contaminated site")
    for _, r in pop_res.iterrows():
        print(f"  {r['definition']:<40} [{r['scope']:<29}] OBC {r['pct_obc_residents_near']:5.1f}% "
              f"({r['obc_residents_near']:>9,}) vs non-OBC {r['pct_non_obc_residents_near']:5.1f}% "
              f"({r['non_obc_residents_near']:>9,})  ratio {r['ratio']:.2f} [{r['ratio_lo']:.2f}-{r['ratio_hi']:.2f}]")
    print("\nTop municipalities (primary definition):")
    print(muni.head(15).to_string())

# Phase 2 Results: NJ Toxic Tides

*Analysis run 2026-10-11. Data pulled 2026-10-10. Screening-level analysis. All numbers are reproducible from `scripts/`.*

## Bottom line

1. **Residents of Overburdened Communities (OBCs) are about 3 times as likely as other New Jerseyans to live within 1 km of a contaminated site threatened by sea-level rise.** 25.2% of OBC residents (**≈1.19 million people**) live within 1 km of a site where dry land within 100 m floods at ≤3 ft of sea-level rise. For other residents the figure is 8.2% (≈376,000). The ratio is **3.06 (95% CI 2.67–3.54)**. This is the most robust finding: the ratio stays between **2.6× and 3.2×** under every exposure definition tested, including when the comparison is limited to counties that have exposed sites.
2. **Among contaminated sites, those threatened by 3 ft of sea-level rise are concentrated in OBCs, even after comparing within the same county.** 71.1% of exposed sites are in OBCs, compared with 60.7% of other sites. The within-county odds ratio is **1.78 (1.54–2.05)**. This holds when excluding home heating-oil tanks (1.80), restricting to active cleanups (1.71), or restricting to complex sites (1.89).
3. **The site-level disparity grows with sea level.** At 1 ft the odds ratio is 1.05 (no disparity), at 2 ft 1.27, and at 3 ft 1.78. Near-term exposure is spread evenly. The concentration in OBCs emerges at the levels NJ projects for later this century.
4. **Current FEMA floodplains do not show the site-level disparity.** The within-county odds ratio is 0.84 using effective maps only. Today's 1% floodplain includes many contaminated sites in wealthier shore communities. The disparity is specific to *future* sea-level rise. That is the gap the 2026 REAL rules, which apply only to new development, do not address.

## Corrections made during Phase 2 (keep these in the write-up)

- **Today's water was being counted as future flooding.** NOAA's SLR layers are cumulative and include current tidal water: the open ocean is inside every level from 0 to 10 ft. The Phase 1 measure, "within 100 m of land inundated at ≤3 ft", therefore flagged every waterfront site. 806 of the 1,536 sites flagged in Phase 1 were reached only by the 0 ft layer. **Fix:** a grid of sample points inside each buffer. A site counts as exposed only if land that is **dry today** within 100 m floods at ≤3 ft. Exposed sites fell from 1,536 to **1,306**, and the share in OBCs from 72.5% to **71.1%**. The flawed version is kept as a gray row in Figure 1 for transparency.
- **The primary definition was chosen after seeing Phase 1 descriptive results.** It is not pre-registered, so every definition is reported side by side (Figure 1).

## Exposure definitions and site-level results

| Definition | Exposed sites | % in OBC (exposed vs. other) | Within-county OR [95% CI] |
|---|---:|---|---|
| Site point itself flooded at ≤1 ft | 68 | 50.0% vs 61.8% | 0.60 [0.35–1.02] |
| Site point itself flooded at ≤3 ft | 361 | 62.6% vs 61.7% | 1.26 [0.99–1.60] |
| New flooding ≤1 ft within 100 m | 455 | 60.9% vs 61.8% | 1.05 [0.85–1.30] |
| New flooding ≤2 ft within 100 m | 785 | 64.6% vs 61.6% | 1.27 [1.07–1.50] |
| **New flooding ≤3 ft within 100 m (primary)** | **1,306** | **71.1% vs 60.7%** | **1.78 [1.54–2.05]** |
| New flooding ≤3 ft within 250 m | 2,266 | 73.0% vs 59.3% | 1.98 [1.76–2.23] |
| ≥25% of land within 100 m floods at ≤3 ft | 620 | 66.5% vs 61.5% | 1.48 [1.22–1.79] |
| FEMA 1% floodplain, effective maps | 2,038 | 63.6% vs 62.6% | 0.84 [0.75–0.94] |
| FEMA 1% floodplain, incl. preliminary | 2,287 | 65.4% vs 60.9% | 1.00 [0.90–1.11] |

The Breslow-Day test shows strong heterogeneity across counties (p < 0.001 for the primary definition). The pooled odds ratio is an average, and the effect differs by county.

## Population level (residents within 1 km of an exposed site)

| Exposure definition | OBC residents | Other residents | Ratio [95% CI] |
|---|---|---|---|
| Site point flooded at ≤3 ft | 10.1% (478,709) | 3.1% (142,669) | 3.24 [2.58–4.16] |
| **New flooding ≤3 ft within 100 m** | **25.2% (1,191,289)** | **8.2% (375,766)** | **3.06 [2.67–3.54]** |
| FEMA floodplain or new flooding ≤3 ft | 47.4% (2,242,143) | 18.0% (819,718) | 2.64 [2.44–2.90] |

## Municipalities (primary definition)

| Municipality | Contaminated sites | Exposed | Exposed & in OBC | Exposed, active cleanup | Notes |
|---|---:|---:|---:|---:|---|
| Atlantic City | 172 | 117 | 117 | 51 | All 157 FEMA-floodplain sites come from **preliminary** maps. No effective NFHL data. |
| Camden | 243 | 70 | 70 | 48 | Waterfront plus Cooper River and Newton Creek corridors |
| Jersey City | 715 | 71 | 68 | 43 | |
| Kearny | 187 | 71 | 50 | 47 | Includes Standard Chlorine (Superfund). 29 site points themselves flood at ≤3 ft. |
| Newark | 802 | 42 | 42 | 24 | Includes Riverside Industrial Park (Superfund) |

**10 federal Superfund (NPL) sites** have dry land within 100 m that floods at ≤3 ft:
- Hercules Inc. Gibbstown Plant
- Raritan Bay Slag
- Matteo & Sons
- Riverside Industrial Park (Newark)
- Universal Oil Products (East Rutherford)
- Berry's Creek Drainage Basin
- Standard Chlorine (Kearny)
- Chemical Control Corp. (Elizabeth)
- Scientific Chemical Processing
- Ventron/Velsicol

## Figures

- `figures/fig1_forest_odds_ratios.png`: site-level odds ratios for every definition
- `figures/fig2_population_near_exposed_sites.png`: population-level comparison (the headline figure)
- `figures/map_statewide.png`, plus `map_atlantic_city.png`, `map_camden_city.png`, `map_jersey_city.png`, `map_kearny_town.png`, `map_newark_city.png`

## Limitations specific to these statistics

- **Sites are not independent.** Contaminated sites cluster in industrial corridors, so p-values and confidence intervals are somewhat too narrow. The population bootstrap resamples block groups, but spatial autocorrelation remains.
- **Coarse residential location.** Residents are placed at their block group's interior point, so a "1 km" distance is approximate.
- **Permanent inundation only.** NOAA's layers are a static bathtub model with no storm surge. Storm surge on top of higher seas would expose more sites, so these counts are a lower bound.

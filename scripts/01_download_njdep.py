"""Phase 1a: download NJDEP Known Contaminated Sites List and Overburdened Community block groups."""

from datetime import date
from pathlib import Path

from arcgis import download_layer

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
NJDEP = "https://mapsdep.nj.gov/arcgis/rest/services/Features"

LAYERS = {
    "kcsl": f"{NJDEP}/Environmental_NJEMS/MapServer/0",
    "obc_block_groups": f"{NJDEP}/Government/MapServer/42",
}

if __name__ == "__main__":
    stamp = date.today().isoformat()
    for name, url in LAYERS.items():
        print(f"Downloading {name} from {url}")
        gdf = download_layer(url)
        out = RAW / f"{name}_{stamp}.gpkg"
        gdf.to_file(out, driver="GPKG")
        print(f"  saved {len(gdf):,} features -> {out.name}")

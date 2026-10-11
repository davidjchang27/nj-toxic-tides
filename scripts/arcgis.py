"""Minimal paginated downloader for ArcGIS REST feature/map service layers."""

import time

import geopandas as gpd
import pandas as pd
import requests

SESSION = requests.Session()
SESSION.headers["User-Agent"] = "nj-toxic-tides-research/0.1 (student research project)"


def _get(url, params, retries=6):
    """GET with retries. ArcGIS servers sometimes answer HTTP 200 with an HTML error page
    ("Could not access any server machines") or a JSON {"error": ...}; both are retried."""
    for attempt in range(retries):
        try:
            r = SESSION.get(url, params=params, timeout=120)
            r.raise_for_status()
            if r.text.lstrip()[:1] not in ("{", "["):
                raise RuntimeError(f"non-JSON response: {r.text[:200]}")
            if '"error"' in r.text[:200]:
                raise RuntimeError(r.text[:500])
            return r
        except (requests.RequestException, RuntimeError):
            if attempt == retries - 1:
                raise
            time.sleep(min(2 ** attempt, 30))


def count(layer_url, where="1=1"):
    return _get(f"{layer_url}/query", {"where": where, "returnCountOnly": "true", "f": "json"}).json()["count"]


def download_layer(layer_url, where="1=1", page_size=1000, out_crs="EPSG:4326"):
    """Download every feature of a layer as a GeoDataFrame, paging by OBJECTID order."""
    total = count(layer_url, where)
    frames = []
    for offset in range(0, total, page_size):
        r = _get(
            f"{layer_url}/query",
            {
                "where": where,
                "outFields": "*",
                "outSR": 4326,
                "orderByFields": "OBJECTID",
                "resultOffset": offset,
                "resultRecordCount": page_size,
                "f": "geojson",
            },
        )
        frames.append(gpd.read_file(r.text))
        print(f"  {min(offset + page_size, total):>6} / {total}", end="\r", flush=True)
    print()
    gdf = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs="EPSG:4326")
    return gdf.to_crs(out_crs)

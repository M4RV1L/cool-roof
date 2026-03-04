"""
sentinel_service.py
───────────────────
Wraps the Sentinel Hub Process API to retrieve Sentinel-2 L2A surface
reflectance bands and compute broadband albedo over a GeoJSON polygon.

Broadband albedo formula (Liang 2001 — widely used for Sentinel-2):
  α = 0.356·B02 + 0.130·B04 + 0.373·B08 + 0.085·B8A + 0.072·B11 - 0.0018

All bands are Bottom-of-Atmosphere (BOA) reflectances scaled to [0, 1].
"""

import logging
from datetime import datetime

import numpy as np
from sentinelhub import (
    BBox,
    BBoxSplitter,
    CRS,
    DataCollection,
    MimeType,
    MosaickingOrder,
    SentinelHubRequest,
    SHConfig,
    bbox_to_dimensions,
)
from sentinelhub import Geometry as SHGeometry
from shapely.geometry import shape as shapely_shape

from app.config import get_settings

logger = logging.getLogger(__name__)

# ── Evalscript ────────────────────────────────────────────────────────────────
# Returns 6 bands needed for Liang-2001 broadband albedo.
# Values are already DN / 10000 (reflectance [0,1]) in Sentinel-2 L2A.
EVALSCRIPT_ALBEDO_BANDS = """
//VERSION=3
function setup() {
  return {
    input: [{
      bands: ["B02", "B04", "B08", "B8A", "B11"],
      units: "REFLECTANCE"
    }],
    output: {
      bands: 5,
      sampleType: "FLOAT32"
    }
  };
}

function evaluatePixel(sample) {
  // Mask clouds and invalid pixels using SCL (Scene Classification Layer)
  // We request without SCL here and rely on mosaicking; cloud masking is
  // handled by the acquisition filter (cloud_coverage_max) at request level.
  return [sample.B02, sample.B04, sample.B08, sample.B8A, sample.B11];
}
"""

# Liang 2001 coefficients for [B02, B04, B08, B8A, B11]
LIANG_COEFFS = np.array([0.356, 0.130, 0.373, 0.085, 0.072])
LIANG_INTERCEPT = -0.0018

# Resolution in metres for the WMS request (10 m native for most S2 bands)
RESOLUTION_M = 10


def _build_sh_config() -> SHConfig:
    s = get_settings()
    cfg = SHConfig()
    cfg.sh_client_id = s.sentinel_client_id
    cfg.sh_client_secret = s.sentinel_client_secret
    cfg.instance_id = s.sentinel_instance_id
    return cfg


def _geojson_to_bbox_and_geometry(geojson_polygon: dict) -> tuple[BBox, SHGeometry]:
    """Convert a GeoJSON Polygon dict to a Sentinel Hub BBox + Geometry."""
    shapely_geom = shapely_shape(geojson_polygon)
    minx, miny, maxx, maxy = shapely_geom.bounds
    bbox = BBox(bbox=(minx, miny, maxx, maxy), crs=CRS.WGS84)
    sh_geometry = SHGeometry(geojson_polygon, crs=CRS.WGS84)
    return bbox, sh_geometry


def _compute_broadband_albedo(bands: np.ndarray) -> np.ndarray:
    """
    Apply Liang 2001 to a (H, W, 5) array of reflectance bands.
    Returns a (H, W) albedo array clipped to [0, 1].
    """
    albedo = np.dot(bands, LIANG_COEFFS) + LIANG_INTERCEPT
    return np.clip(albedo, 0.0, 1.0)


async def fetch_albedo(
    geojson_polygon: dict,
    date_from: str,
    date_to: str,
    cloud_coverage_max: float = 20.0,
) -> dict:
    """
    Query Sentinel Hub for the best cloud-free Sentinel-2 scene in the
    given time window and compute mean broadband albedo over the polygon.

    Returns
    -------
    dict with keys:
        mean_albedo        : float   – area-averaged broadband albedo
        area_m2            : float   – polygon area in m²
        scene_date         : str     – acquisition date of the selected scene
        cloud_coverage_pct : float   – cloud % of the selected scene
        pixel_count        : int     – number of valid pixels processed
    """
    cfg = _build_sh_config()
    bbox, sh_geometry = _geojson_to_bbox_and_geometry(geojson_polygon)

    # Image size derived from bbox at native 10 m resolution
    size = bbox_to_dimensions(bbox, resolution=RESOLUTION_M)
    logger.info("Requesting Sentinel-2 scene: bbox=%s size=%s", bbox, size)

    request = SentinelHubRequest(
        evalscript=EVALSCRIPT_ALBEDO_BANDS,
        input_data=[
            SentinelHubRequest.input_data(
                data_collection=DataCollection.SENTINEL2_L2A,
                time_interval=(date_from, date_to),
                mosaicking_order=MosaickingOrder.LEAST_CC,
                maxcc=cloud_coverage_max / 100.0,
            )
        ],
        responses=[SentinelHubRequest.output_response("default", MimeType.TIFF)],
        bbox=bbox,
        geometry=sh_geometry,
        size=size,
        config=cfg,
        data_folder=None,
    )

    # Synchronous SDK call — run in thread pool in production if needed
    data = request.get_data()

    if not data or data[0] is None:
        raise ValueError(
            "Sentinel Hub returned no data. "
            "Try widening the date range or raising cloud_coverage_max."
        )

    bands_array: np.ndarray = data[0]  # shape: (H, W, 5)

    # Mask no-data pixels (all bands == 0)
    valid_mask = np.any(bands_array > 0, axis=-1)
    pixel_count = int(valid_mask.sum())

    if pixel_count == 0:
        raise ValueError("All pixels in the selected scene are masked / no-data.")

    albedo_map = _compute_broadband_albedo(bands_array)
    mean_albedo = float(albedo_map[valid_mask].mean())

    # Area: count valid pixels × pixel area
    area_m2 = float(pixel_count * RESOLUTION_M * RESOLUTION_M)

    # Retrieve scene metadata for the best scene selected by LEAST_CC mosaicking
    # (Sentinel Hub does not return metadata inline; we query the catalog separately)
    scene_date, cloud_pct = await _query_best_scene_metadata(
        bbox=bbox,
        sh_geometry=sh_geometry,
        date_from=date_from,
        date_to=date_to,
        cloud_coverage_max=cloud_coverage_max,
        cfg=cfg,
    )

    logger.info(
        "Albedo computed: mean=%.4f area=%.0f m² pixels=%d scene=%s",
        mean_albedo, area_m2, pixel_count, scene_date,
    )

    return {
        "mean_albedo": mean_albedo,
        "area_m2": area_m2,
        "scene_date": scene_date,
        "cloud_coverage_pct": cloud_pct,
        "pixel_count": pixel_count,
    }


async def _query_best_scene_metadata(
    bbox: BBox,
    sh_geometry: SHGeometry,
    date_from: str,
    date_to: str,
    cloud_coverage_max: float,
    cfg: SHConfig,
) -> tuple[str, float]:
    """
    Use the Sentinel Hub Catalog API to find the acquisition date and cloud
    coverage of the least-cloudy scene in the time window.
    """
    from sentinelhub import SentinelHubCatalog

    catalog = SentinelHubCatalog(config=cfg)
    search_results = list(
        catalog.search(
            DataCollection.SENTINEL2_L2A,
            bbox=bbox,
            time=(date_from, date_to),
            fields={"include": ["id", "properties.datetime", "properties.eo:cloud_cover"]},
        )
    )

    if not search_results:
        return ("unknown", 0.0)

    # Filter by cloud coverage manually, then pick the least cloudy
    filtered = [
        f for f in search_results
        if f["properties"].get("eo:cloud_cover", 100) <= cloud_coverage_max
    ]
    candidates = filtered if filtered else search_results

    best = min(candidates, key=lambda f: f["properties"].get("eo:cloud_cover", 100))
    raw_date: str = best["properties"]["datetime"]
    cloud_pct: float = float(best["properties"].get("eo:cloud_cover", 0.0))

    scene_date = raw_date[:10] if len(raw_date) >= 10 else raw_date

    return scene_date, cloud_pct

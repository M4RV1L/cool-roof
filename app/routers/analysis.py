"""
analysis.py  — FastAPI router
──────────────────────────────
Orchestrates the full cool-roof analysis pipeline:
  1. Fetch Sentinel-2 data → compute current albedo
  2. Derive thermal benefits
  3. Fetch dynamic electricity price (GME, cached 24h)
  4. Compute energy & monetary savings
"""

import logging

from fastapi import APIRouter, HTTPException, status

from app.config import get_settings
from app.models.schemas import (
    AlbedoResult,
    AnalysisRequest,
    AnalysisResponse,
    EnergyResult,
    ThermalResult,
)
from app.services.energy_calculator import compute_energy_savings
from app.services.energy_price_service import get_electricity_price
from app.services.sentinel_service import fetch_albedo
from app.services.thermal_engine import compute_thermal_reduction

router = APIRouter(prefix="/analysis", tags=["analysis"])
logger = logging.getLogger(__name__)


@router.post(
    "/cool-roof",
    response_model=AnalysisResponse,
    summary="Analyse cool-roof impact for a GeoJSON polygon",
)
async def analyse_cool_roof(body: AnalysisRequest) -> AnalysisResponse:
    settings = get_settings()
    warnings: list[str] = []

    # ── 1. Satellite albedo ───────────────────────────────────────────────────
    try:
        sentinel_result = await fetch_albedo(
            geojson_polygon=body.geometry.model_dump(),
            date_from=body.date_from,
            date_to=body.date_to,
            cloud_coverage_max=body.cloud_coverage_max,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except Exception as exc:
        logger.exception("Sentinel Hub error")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Sentinel Hub request failed: {exc}",
        )

    current_albedo: float = (
        body.baseline_albedo_override
        if body.baseline_albedo_override is not None
        else sentinel_result["mean_albedo"]
    )
    target_albedo: float = (
        body.cool_roof_albedo_override
        if body.cool_roof_albedo_override is not None
        else settings.cool_roof_albedo
    )

    if body.baseline_albedo_override is not None:
        warnings.append("Baseline albedo was manually overridden; satellite value not used.")

    delta_albedo = max(0.0, target_albedo - current_albedo)
    if delta_albedo == 0.0:
        warnings.append(
            "Target albedo <= current albedo — no thermal improvement expected. "
            "Consider a higher-reflectance product."
        )

    albedo_result = AlbedoResult(
        current_albedo=round(current_albedo, 4),
        target_albedo=round(target_albedo, 4),
        delta_albedo=round(delta_albedo, 4),
        area_m2=round(sentinel_result["area_m2"], 1),
        sentinel_scene_date=sentinel_result["scene_date"],
        cloud_coverage_pct=round(sentinel_result["cloud_coverage_pct"], 1),
    )

    # ── 2. Thermal engine ─────────────────────────────────────────────────────
    thermal = compute_thermal_reduction(
        delta_albedo=delta_albedo,
        climate_zone=body.climate_zone,
    )

    thermal_result = ThermalResult(
        surface_temp_reduction_c=thermal.surface_temp_reduction_c,
        ambient_temp_reduction_c=thermal.ambient_temp_reduction_c,
        indoor_temp_reduction_c=thermal.indoor_temp_reduction_c,
    )

    # ── 3. Dynamic electricity price ─────────────────────────────────────────
    price_data = await get_electricity_price()
    electricity_price = price_data["price_eur_kwh"]

    if price_data["source"] == "fallback":
        warnings.append(
            f"Prezzo energia da configurazione ({electricity_price} EUR/kWh) — "
            "dati GME non disponibili al momento."
        )

    # ── 4. Energy savings ─────────────────────────────────────────────────────
    energy = compute_energy_savings(
        area_m2=sentinel_result["area_m2"],
        delta_t_indoor_c=thermal.indoor_temp_reduction_c,
        climate_zone=body.climate_zone,
        electricity_price_eur_kwh=electricity_price,
    )

    energy_result = EnergyResult(
        annual_cooling_savings_kwh=energy.annual_cooling_savings_kwh,
        annual_savings_eur=energy.annual_savings_eur,
        payback_years=energy.payback_years,
        co2_avoided_kg_year=energy.co2_avoided_kg_year,
        electricity_price_eur_kwh=electricity_price,
        price_source=price_data["source"],
        price_last_updated=price_data["last_updated"],
    )

    return AnalysisResponse(
        albedo=albedo_result,
        thermal=thermal_result,
        energy=energy_result,
        warnings=warnings,
    )


@router.get("/electricity-price", tags=["analysis"])
async def get_current_electricity_price():
    """Returns the current electricity price used for calculations."""
    return await get_electricity_price()

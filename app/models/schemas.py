from pydantic import BaseModel, Field, field_validator
from typing import Literal


class GeoJSONPolygon(BaseModel):
    type: Literal["Polygon"]
    coordinates: list[list[list[float]]] = Field(
        ...,
        examples=[[[
            [16.85, 41.12], [16.86, 41.12],
            [16.86, 41.13], [16.85, 41.13],
            [16.85, 41.12],
        ]]],
    )

    @field_validator("coordinates")
    @classmethod
    def ring_must_be_closed(cls, rings: list) -> list:
        for ring in rings:
            if len(ring) < 4:
                raise ValueError("Each ring must have at least 4 positions.")
            if ring[0] != ring[-1]:
                raise ValueError("Ring must be closed (first == last coordinate).")
        return rings


class AnalysisRequest(BaseModel):
    geometry: GeoJSONPolygon
    date_from: str = Field(default="2024-06-01")
    date_to: str = Field(default="2024-08-31")
    cloud_coverage_max: float = Field(default=20.0, ge=0.0, le=100.0)
    baseline_albedo_override: float | None = Field(default=None, ge=0.0, le=1.0)
    cool_roof_albedo_override: float | None = Field(default=None, ge=0.0, le=1.0)
    building_height_m: float = Field(default=3.0, gt=0)
    floors: int = Field(default=1, ge=1)
    climate_zone: str = "mediterranean"


class AlbedoResult(BaseModel):
    current_albedo: float
    target_albedo: float
    delta_albedo: float
    area_m2: float
    sentinel_scene_date: str
    cloud_coverage_pct: float


class ThermalResult(BaseModel):
    surface_temp_reduction_c: float
    ambient_temp_reduction_c: float
    indoor_temp_reduction_c: float


class EnergyResult(BaseModel):
    annual_cooling_savings_kwh: float
    annual_savings_eur: float
    payback_years: float | None = None
    co2_avoided_kg_year: float
    electricity_price_eur_kwh: float = Field(
        default=0.25,
        description="Electricity price used for calculations (EUR/kWh)."
    )
    price_source: str = Field(
        default="fallback",
        description="Source: 'gme_api' or 'fallback'."
    )
    price_last_updated: str = Field(
        default="static",
        description="Date of the electricity price data."
    )


class AnalysisResponse(BaseModel):
    albedo: AlbedoResult
    thermal: ThermalResult
    energy: EnergyResult
    warnings: list[str] = Field(default_factory=list)

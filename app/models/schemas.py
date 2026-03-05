from pydantic import BaseModel, Field, field_validator
from typing import Literal


# ── GeoJSON primitives ────────────────────────────────────────────────────────

class GeoJSONPolygon(BaseModel):
    """Minimal GeoJSON Polygon (no holes needed for MVP)."""
    type: Literal["Polygon"]
    coordinates: list[list[list[float]]] = Field(
        ...,
        description="Array of linear rings. First ring = exterior boundary. "
                    "Coordinates: [longitude, latitude].",
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


# ── Analysis request ──────────────────────────────────────────────────────────

class AnalysisRequest(BaseModel):
    geometry: GeoJSONPolygon
    date_from: str = Field(
        default="2024-06-01",
        description="Start of the Sentinel-2 acquisition window (YYYY-MM-DD).",
    )
    date_to: str = Field(
        default="2024-08-31",
        description="End of the Sentinel-2 acquisition window (YYYY-MM-DD).",
    )
    cloud_coverage_max: float = Field(
        default=20.0,
        ge=0.0,
        le=100.0,
        description="Maximum allowed cloud coverage percentage for image selection.",
    )
    # Optional overrides (user can tune if they know the building type)
    baseline_albedo_override: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Override the satellite-derived baseline albedo with a known value.",
    )
    cool_roof_albedo_override: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Override the target cool-roof albedo.",
    )
    # Building parameters for energy savings
    building_height_m: float = Field(
        default=3.0,
        gt=0,
        description="Average floor-to-floor height in metres (used for floor count estimate).",
    )
    floors: int = Field(
        default=1,
        ge=1,
        description="Number of floors directly under the roof.",
    )
    climate_zone: str = Field(
        default="mediterranean",
        description="Climate zone for degree-day lookup: 'mediterranean' | 'continental' | 'alpine'.",
    )


# ── Sub-result models ──────────────────────────────────────────────────────────

class AlbedoResult(BaseModel):
    current_albedo: float = Field(description="Mean broadband albedo derived from Sentinel-2 (0-1).")
    target_albedo: float = Field(description="Albedo after cool-roof application (0-1).")
    delta_albedo: float = Field(description="Absolute increase in albedo.")
    area_m2: float = Field(description="Analysed roof area in square metres.")
    sentinel_scene_date: str = Field(description="Date of the best Sentinel-2 scene used.")
    cloud_coverage_pct: float = Field(description="Cloud coverage of the selected scene.")


class ThermalResult(BaseModel):
    surface_temp_reduction_c: float = Field(
        description="Estimated reduction in roof surface temperature (°C)."
    )
    ambient_temp_reduction_c: float = Field(
        description="Estimated reduction in near-surface air temperature (°C) — local UHI effect."
    )
    indoor_temp_reduction_c: float = Field(
        description="Estimated indoor temperature reduction assuming standard insulation (°C)."
    )


class EnergyResult(BaseModel):
    annual_cooling_savings_kwh: float = Field(
        description="Estimated annual electricity saved on cooling (kWh/year)."
    )
    annual_savings_eur: float = Field(
        description="Estimated annual monetary savings on electricity bills (€/year)."
    )
    payback_years: float | None = Field(
        default=None,
        description="Simple payback period in years (requires paint cost input; null if not provided).",
    )
    co2_avoided_kg_year: float = Field(
        description="kg of CO₂ avoided per year (Italian grid emission factor: 233 gCO₂/kWh)."
    )


class AnalysisResponse(BaseModel):
    albedo: AlbedoResult
    thermal: ThermalResult
    energy: EnergyResult
    warnings: list[str] = Field(default_factory=list)

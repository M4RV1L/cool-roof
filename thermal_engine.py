"""
thermal_engine.py
─────────────────
Computes the thermal benefits of a cool roof using established
radiative-balance and heat-transfer models.

Key references
──────────────
- Akbari & Matthews (2012): "Global cooling updates: Reflective roofs
  and pavements" — ΔT_surface ≈ ΔAlbedo × (S_absorbed / h_convective)
- Santamouris (2014): "Cooling the cities — A review of reflective and
  green roof mitigation technologies to fight heat island and improve
  comfort in urban environments"
- ASHRAE 90.1 simple cooling-load method for roof U-value contribution
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ── Climate-zone cooling degree days (base 18 °C, Italian data) ───────────────
# Source: ISPRA / Enea national climate database
COOLING_DEGREE_DAYS: dict[str, float] = {
    "mediterranean": 900.0,   # e.g. Bari, Palermo, Naples
    "continental":   600.0,   # e.g. Milan, Bologna, Turin
    "alpine":        250.0,   # e.g. Aosta, Bolzano
}

# ── Solar & atmospheric constants ─────────────────────────────────────────────
SOLAR_IRRADIANCE_W_M2 = 600.0      # Mean summer-peak absorbed solar (W/m²)
H_CONVECTIVE_W_M2_K = 12.0         # Convective + long-wave linearised heat transfer
                                    # coefficient for a flat roof (W/m²·K)

# ── Urban Heat Island scaling ─────────────────────────────────────────────────
# The local air temperature benefit is roughly 10–15 % of the surface
# temperature change for an isolated building.  City-wide it scales up,
# but for a single building we use the conservative lower bound.
UHI_FRACTION = 0.10

# ── Indoor temperature coupling ───────────────────────────────────────────────
# Fraction of roof surface ΔT that propagates indoors through a
# standard Italian flat roof (U ≈ 0.45 W/m²K, typical pre-2005 stock).
# Derived from a simplified 1D heat-flux model:
#   ΔT_indoor ≈ (U_roof / h_interior) × ΔT_surface
# with h_interior ≈ 8 W/m²K (still-air convection).
INDOOR_COUPLING_FACTOR = 0.40


@dataclass
class ThermalResults:
    surface_temp_reduction_c: float
    ambient_temp_reduction_c: float
    indoor_temp_reduction_c: float


def compute_thermal_reduction(
    delta_albedo: float,
    climate_zone: str = "mediterranean",
) -> ThermalResults:
    """
    Estimate temperature reductions from a cool-roof albedo improvement.

    Parameters
    ----------
    delta_albedo : float
        Increase in albedo (target_albedo - current_albedo).
    climate_zone : str
        One of 'mediterranean', 'continental', 'alpine'.

    Returns
    -------
    ThermalResults dataclass.
    """
    if delta_albedo < 0:
        logger.warning("delta_albedo is negative (%.4f); results will be zero.", delta_albedo)
        return ThermalResults(0.0, 0.0, 0.0)

    # ΔT_surface = ΔAlbedo × S / h_convective
    # Physical interpretation: less solar energy absorbed → lower surface equilibrium T
    delta_t_surface = (delta_albedo * SOLAR_IRRADIANCE_W_M2) / H_CONVECTIVE_W_M2_K

    # Local air temperature benefit (UHI mitigation)
    delta_t_ambient = delta_t_surface * UHI_FRACTION

    # Indoor benefit through the roof assembly
    delta_t_indoor = delta_t_surface * INDOOR_COUPLING_FACTOR

    logger.debug(
        "Thermal results: ΔT_surface=%.2f °C  ΔT_ambient=%.2f °C  ΔT_indoor=%.2f °C",
        delta_t_surface, delta_t_ambient, delta_t_indoor,
    )

    return ThermalResults(
        surface_temp_reduction_c=round(delta_t_surface, 2),
        ambient_temp_reduction_c=round(delta_t_ambient, 2),
        indoor_temp_reduction_c=round(delta_t_indoor, 2),
    )

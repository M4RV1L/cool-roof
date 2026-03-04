"""
energy_calculator.py
─────────────────────
Translates thermal improvements into annual energy savings, monetary
savings on electricity bills, and CO₂ avoidance.

Methodology
───────────
1. Cooling-load reduction (kWh/year)
   ΔQ_cooling = U_roof × A_roof × CDD × 24h × COP_ref⁻¹
   where:
     U_roof  = roof thermal transmittance (W/m²K) — Italian average flat roof
     A_roof  = analysed area (m²)
     CDD     = Cooling Degree Days for the climate zone (K·day)
     COP_ref = Reference COP of the cooling system

   This gives the electrical energy saved by the HVAC system when
   the roof temperature is lowered by the cool-roof effect.

2. Monetary savings
   Savings_€ = ΔQ_cooling × price_€_per_kWh

3. CO₂ avoidance
   Italy national grid emission factor: 233 g CO₂/kWh (ISPRA 2023)

References
──────────
- ISPRA (2023) "Italian national inventory report"
- EN ISO 13790 simplified monthly method adapted for roof contribution
- Akbari & Konopacki (2005): "Calculating energy-saving potentials of
  heat-island reduction strategies"
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ── Physical and economic constants ───────────────────────────────────────────
U_ROOF_W_M2K = 0.45              # W/m²K — Italian average flat roof (pre-2010)
COP_REFERENCE = 2.8              # Seasonal COP for a typical split AC unit
HOURS_PER_DAY = 24.0
CO2_FACTOR_G_PER_KWH = 233.0     # gCO₂/kWh — Italian grid 2023 (ISPRA)

# Cooling Degree Days per climate zone (base 18 °C, Italian cities)
COOLING_DEGREE_DAYS: dict[str, float] = {
    "mediterranean": 900.0,
    "continental":   600.0,
    "alpine":        250.0,
}

# Typical cool-roof paint cost range (€/m²) — used for payback calculation
PAINT_COST_EUR_M2_DEFAULT = 12.0   # mid-range reflective coating


@dataclass
class EnergyResults:
    annual_cooling_savings_kwh: float
    annual_savings_eur: float
    payback_years: float | None
    co2_avoided_kg_year: float


def compute_energy_savings(
    area_m2: float,
    delta_t_indoor_c: float,
    climate_zone: str = "mediterranean",
    electricity_price_eur_kwh: float = 0.25,
    paint_cost_eur_m2: float | None = None,
) -> EnergyResults:
    """
    Estimate annual energy savings from the cool-roof induced indoor
    temperature reduction.

    Parameters
    ----------
    area_m2 : float
        Roof area in square metres.
    delta_t_indoor_c : float
        Indoor temperature reduction in °C (from thermal_engine).
    climate_zone : str
        'mediterranean' | 'continental' | 'alpine'
    electricity_price_eur_kwh : float
        Local electricity tariff in €/kWh.
    paint_cost_eur_m2 : float | None
        Cool-roof paint cost in €/m². If provided, payback period is calculated.

    Returns
    -------
    EnergyResults dataclass.
    """
    cdd = COOLING_DEGREE_DAYS.get(climate_zone, COOLING_DEGREE_DAYS["mediterranean"])

    # ── 1. Cooling load reduction ─────────────────────────────────────────────
    # Thermal energy saved at the room level (Wh/year):
    #   ΔQ_thermal = U × A × ΔT × CDD × 24h  →  convert Wh → kWh
    delta_q_thermal_kwh = (
        U_ROOF_W_M2K * area_m2 * delta_t_indoor_c * cdd * HOURS_PER_DAY / 1000.0
    )

    # Electrical energy saved = thermal saved / COP
    delta_q_electric_kwh = delta_q_thermal_kwh / COP_REFERENCE

    # ── 2. Monetary savings ───────────────────────────────────────────────────
    annual_savings_eur = delta_q_electric_kwh * electricity_price_eur_kwh

    # ── 3. CO₂ avoidance ─────────────────────────────────────────────────────
    co2_avoided_kg = delta_q_electric_kwh * CO2_FACTOR_G_PER_KWH / 1000.0

    # ── 4. Payback period ─────────────────────────────────────────────────────
    payback_years: float | None = None
    effective_paint_cost = paint_cost_eur_m2 or PAINT_COST_EUR_M2_DEFAULT
    total_investment = effective_paint_cost * area_m2
    if annual_savings_eur > 0:
        payback_years = round(total_investment / annual_savings_eur, 1)

    logger.debug(
        "Energy results: ΔQ_elec=%.1f kWh/yr  savings=%.2f €/yr  "
        "payback=%.1f yr  CO₂=%.1f kg/yr",
        delta_q_electric_kwh, annual_savings_eur,
        payback_years or -1, co2_avoided_kg,
    )

    return EnergyResults(
        annual_cooling_savings_kwh=round(delta_q_electric_kwh, 1),
        annual_savings_eur=round(annual_savings_eur, 2),
        payback_years=payback_years,
        co2_avoided_kg_year=round(co2_avoided_kg, 1),
    )

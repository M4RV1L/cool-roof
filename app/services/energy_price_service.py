"""
energy_price_service.py
────────────────────────
Fetches the current Italian electricity price from the GME (Gestore
Mercati Energetici) public API and caches it for 24 hours.

Data source: GME Prezzi di Riferimento — PUN (Prezzo Unico Nazionale)
URL: https://www.mercatoelettrico.org/It/Statistiche/ME/DatiSintesi.aspx

Fallback: uses ELECTRICITY_PRICE_EUR_KWH from .env if the API is unavailable.
"""

import logging
import time
import httpx
from app.config import get_settings

logger = logging.getLogger(__name__)

# ── Cache ─────────────────────────────────────────────────────────────────────
_cache: dict = {
    "price": None,
    "timestamp": 0.0,
    "source": "fallback",
}
CACHE_TTL_SECONDS = 86400  # 24 hours

# ── GME endpoint ──────────────────────────────────────────────────────────────
# GME publishes daily PUN (Prezzo Unico Nazionale) as JSON
GME_URL = "https://gme.mercatoelettrico.org/api/gmereports/getreportdata"
GME_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "CoolRoofAnalyzer/1.0",
}


async def get_electricity_price() -> dict:
    """
    Returns the current Italian electricity price (€/kWh) with metadata.

    Returns
    -------
    dict with keys:
        price_eur_kwh : float  – price in €/kWh
        source        : str   – 'gme_api' | 'fallback'
        last_updated  : str   – ISO date string or 'static'
        cached        : bool
    """
    now = time.time()

    # Return cached value if still valid
    if _cache["price"] is not None and (now - _cache["timestamp"]) < CACHE_TTL_SECONDS:
        logger.debug("Returning cached electricity price: %.4f €/kWh", _cache["price"])
        return {
            "price_eur_kwh": _cache["price"],
            "source": _cache["source"],
            "last_updated": _cache.get("last_updated", "unknown"),
            "cached": True,
        }

    # Try to fetch fresh price
    price, source, last_updated = await _fetch_gme_price()

    # Update cache
    _cache["price"] = price
    _cache["timestamp"] = now
    _cache["source"] = source
    _cache["last_updated"] = last_updated

    return {
        "price_eur_kwh": price,
        "source": source,
        "last_updated": last_updated,
        "cached": False,
    }


async def _fetch_gme_price() -> tuple[float, str, str]:
    """
    Attempts to fetch today's PUN from the GME API.
    Falls back to .env value on any error.

    Returns (price_eur_kwh, source, last_updated_date)
    """
    settings = get_settings()
    fallback = (settings.electricity_price_eur_kwh, "fallback", "static")

    try:
        from datetime import date, timedelta
        today = date.today()
        yesterday = today - timedelta(days=1)

        # GME report parameters for MGP (Mercato del Giorno Prima) — PUN
        params = {
            "reportId": "MGPPrezzi",
            "dateFrom": yesterday.strftime("%Y%m%d"),
            "dateTo": today.strftime("%Y%m%d"),
            "granularity": "Day",
            "zone": "NAT",
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(GME_URL, params=params, headers=GME_HEADERS)
            resp.raise_for_status()
            data = resp.json()

        # Parse the response — GME returns a list of records
        records = data.get("data", data) if isinstance(data, dict) else data
        if not records:
            raise ValueError("Empty response from GME API")

        # Get the most recent record and extract PUN price
        # GME returns prices in €/MWh → convert to €/kWh
        latest = records[-1] if isinstance(records, list) else records
        price_mwh = float(
            latest.get("PUN") or
            latest.get("pun") or
            latest.get("Price") or
            latest.get("price", 0)
        )

        if price_mwh <= 0:
            raise ValueError(f"Invalid price from GME: {price_mwh}")

        price_kwh = round(price_mwh / 1000, 4)
        date_str = latest.get("Date") or latest.get("date") or today.isoformat()

        logger.info("GME PUN price fetched: %.4f €/kWh (%.2f €/MWh) for %s", price_kwh, price_mwh, date_str)
        return price_kwh, "gme_api", str(date_str)[:10]

    except Exception as exc:
        logger.warning("GME API fetch failed (%s), using fallback price %.4f €/kWh", exc, settings.electricity_price_eur_kwh)
        return fallback

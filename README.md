# Cool Roof Analyzer — Backend

API REST per l'analisi dell'impatto di vernici cool roof su edifici, basata su immagini satellitari Sentinel-2.

---

## Architettura

```
cool_roof_backend/
├── app/
│   ├── main.py                  # FastAPI app + CORS + lifespan
│   ├── config.py                # Pydantic settings (.env)
│   ├── routers/
│   │   └── analysis.py          # POST /api/v1/analysis/cool-roof
│   ├── services/
│   │   ├── sentinel_service.py  # Sentinel Hub API + calcolo albedo
│   │   ├── thermal_engine.py    # Riduzioni temperatura (fisica radiativa)
│   │   └── energy_calculator.py # Risparmi kWh / € / CO₂
│   └── models/
│       └── schemas.py           # Request / Response Pydantic models
└── tests/
    └── test_engines.py          # Unit test (no dipendenze esterne)
```

---

## Setup

### 1. Installa le dipendenze

```bash
pip install -r requirements.txt
```

### 2. Configura le credenziali

```bash
cp .env.example .env
# Edita .env con le tue credenziali Sentinel Hub
```

Le variabili richieste:

| Variabile | Descrizione |
|---|---|
| `SENTINEL_CLIENT_ID` | OAuth2 Client ID da Sentinel Hub Dashboard |
| `SENTINEL_CLIENT_SECRET` | OAuth2 Client Secret |
| `SENTINEL_INSTANCE_ID` | Instance ID della tua configurazione |
| `ELECTRICITY_PRICE_EUR_KWH` | Prezzo energia elettrica (default: 0.25 €/kWh) |

### 3. Avvia il server

```bash
uvicorn app.main:app --reload
```

L'API sarà disponibile su `http://localhost:8000`.  
Documentazione interattiva: `http://localhost:8000/docs`

---

## Endpoint principale

### `POST /api/v1/analysis/cool-roof`

**Request body:**

```json
{
  "geometry": {
    "type": "Polygon",
    "coordinates": [[
      [16.85, 41.12],
      [16.86, 41.12],
      [16.86, 41.13],
      [16.85, 41.13],
      [16.85, 41.12]
    ]]
  },
  "date_from": "2024-06-01",
  "date_to": "2024-08-31",
  "cloud_coverage_max": 20.0,
  "climate_zone": "mediterranean",
  "floors": 1
}
```

**Response:**

```json
{
  "albedo": {
    "current_albedo": 0.14,
    "target_albedo": 0.75,
    "delta_albedo": 0.61,
    "area_m2": 850.0,
    "sentinel_scene_date": "2024-07-15",
    "cloud_coverage_pct": 3.2
  },
  "thermal": {
    "surface_temp_reduction_c": 30.5,
    "ambient_temp_reduction_c": 3.05,
    "indoor_temp_reduction_c": 12.2
  },
  "energy": {
    "annual_cooling_savings_kwh": 1843.0,
    "annual_savings_eur": 460.75,
    "payback_years": 5.2,
    "co2_avoided_kg_year": 429.4
  },
  "warnings": []
}
```

---

## Metodologia fisica

### Albedo broadband (Liang 2001)
Calcolata dalle bande Sentinel-2 L2A (riflettanza superficiale):

```
α = 0.356·B02 + 0.130·B04 + 0.373·B08 + 0.085·B8A + 0.072·B11 − 0.0018
```

### Riduzione temperatura superficiale
Bilancio radiativo linearizzato (Akbari & Matthews 2012):

```
ΔT_surface = Δα × S / h_conv
```
- `S` = irradianza solare media estiva assorbita (600 W/m²)
- `h_conv` = coefficiente di scambio termico convettivo + IR (12 W/m²K)

### Risparmio energetico
Metodo semplificato EN ISO 13790 adattato al contributo del tetto:

```
ΔQ_elec = U_roof × A × ΔT_indoor × CDD × 24h / COP
```
- `U_roof` = 0.45 W/m²K (tetto piano italiano medio pre-2010)
- `CDD` = Gradi Giorno di Raffrescamento per zona climatica
- `COP` = 2.8 (split AC tipico)

### Zone climatiche supportate

| Zona | CDD (base 18°C) | Esempio città |
|---|---|---|
| `mediterranean` | 900 | Bari, Palermo, Napoli |
| `continental` | 600 | Milano, Bologna, Torino |
| `alpine` | 250 | Bolzano, Aosta |

---

## Test

```bash
pytest tests/ -v
```

I test unitari non richiedono connessione a Sentinel Hub.

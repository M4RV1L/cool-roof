# Documentazione

## 1. Panoramica del Progetto

[CoolRoof Analyzer](https://cool-roof-frontend.vercel.app/) è un'applicazione web full-stack che permette di analizzare l'albedo (riflettività) di qualsiasi tetto nel mondo usando immagini satellitari reali Sentinel-2, e di calcolare il risparmio energetico ottenibile applicando un cool roof coating (vernice bianca riflettente).

### 1.1 Problema che risolve

I tetti scuri assorbono fino all'85-95% della radiazione solare, riscaldando l'edificio e contribuendo all'isola di calore urbana (UHI). Un cool roof con albedo del 75% può ridurre la temperatura superficiale del tetto fino a 30°C nelle ore più calde, con significativi risparmi in bolletta.
Fino ad oggi, quantificare questo beneficio richiedeva sopralluoghi fisici e strumenti costosi. CoolRoof Analyzer lo fa in pochi secondi, usando dati satellitari gratuiti.

### 1.2 Come funziona in sintesi

- L'utente apre la mappa e disegna un poligono sopra il tetto da analizzare
- Il frontend invia le coordinate al backend FastAPI
- Il backend interroga Sentinel Hub per ottenere le bande spettrali Sentinel-2 L2A
- Viene calcolato l'albedo broadband con la formula di Liang (2001)
- Il motore termico calcola la riduzione di temperatura applicando un cool roof
- Il calcolatore energetico stima kWh risparmiati, risparmio in euro e CO2 evitata
- I risultati vengono visualizzati nel pannello laterale e possono essere esportati in PDF

| Stack tecnologico completo                                                       |
| -------------------------------------------------------------------------------- |
| `Backend`: FastAPI (Python) + Sentinel Hub API + Pydantic                        |
| `Frontend`: HTML/CSS/JS + Leaflet.js + jsPDF + html2canvas                       |
| `Deploy`: Railway (backend) + Vercel (frontend)                                  |
| `Dati`: ESA Sentinel-2 L2A (10m risoluzione) + GME prezzi energia                |
| `Modelli`: Liang 2001 (albedo) + Akbari & Matthews 2012 (termico) + EN ISO 13790 |


## 2. Architettura del Sistema

L'[applicazione](https://cool-roof-frontend.vercel.app/) è divisa in due parti indipendenti che comunicano tramite API REST

### 2.1 Schema architetturale

| Flusso dei dati                                                  |
| ---------------------------------------------------------------- |
| Browser (Vercel)                                                 |
| \|-- disegna poligono su mappa Leaflet                           |
| \|-- invia POST /api/v1/analysis/cool-roof                       |
| v                                                                |
| Backend FastAPI (Railway)                                        |
| \|-- sentinel_service.py --> Sentinel Hub API --> ESA Sentinel-2 |
| \|-- therman_engine.py --> calcolo fisico radiativo              |
| \|-- energy_calculator.py --> risparmio kWh/EUR/CO2              |
| \|-- energy_price_service.py --> GME API (prezzo energia)        |
| v                                                                |
| JSON Response --> Frontend --> Rendering risultati + Export PDF  |

### 2.2 Struttura delle cartelle

```
cool-roof/
	app/
		__init__.py
		config.py                    # Settings da variabili d'ambiente
		main.py                      # Entry point FastAPI + CORS
		routers/
			analysis.py              # POST /cool-roof + GET /electricity-price
		services/
			sentinel_service.py      # Recupero dati Sentinel-2
			thermal_engine.py        # Modello fisico termico
			energy_calculator.py     # Calcolo risparmio energetico
			energy_price_service.py  # Prezzo energia dinamico GME
		models/
			schemas.py               # Modelli Pydentic request/response
	requirements.txt
	Dockerfile
	Procfile
			
```

```
cool-roof-frontend/
	index.html                       # Intera app frontend (single file)
```


## 3. Backend -- FastAPI

### 3.1 FastAPI

FastAPI è un framework Python moderno per costruire API REST. E' scelto per:
- Validazione automatica degli input con Pydantic
- Documentazione automatica (Swagger UI su /docs)
- Supporto nativo async/await per chiamate HTTP non bloccanti
- Prestazioni elevatissime

#### Entry point -- main.py
```
app = FastAPI(title="CoolRoof Analyzer API")
app.add_middleware(CORSMiddleware, allow_origins=["*"])
app.include_router(analysis_router, prefix="/api/v1")
```

CORS (Cross-Origin Resource Sharing) è abilitato per permettere al frontend su Vercel di chiamare il backend su Railway, che si trova su un dominio diverso.

### 3.2 Pydantic -- Validazione dei dati

Pydantic è la libreria di validazione usata da FastAPI. Ogni request e response è definita come una classe Python con tipi espliciti.

#### Esempio -- AnalysisRequest:
```
class AnalysisRequest(BaseModel):
	geometry: GeoJSONPolygon              # Poligono con coordinate
	date_from: str = "2024-06-01"         # Inizio periodo
	date_to: str = "2024-08-31"           # Fine periodo
	cloud_coverage_max: float = 20        # Max copertura nuvolosa %
	climate_zone: str = "mediterranean"
```

GeoJSONPolygon include un validator che verifica che il poligono sia chiuso (primo punto == ultimo punto) e abbia almeno 4 coordinate. Se la validazione fallisce FastAPI risponde automaticamente con HTTP 422.

### 3.3 Config e variabili d'ambiente

Il file config.py usa pydantic-settings per leggere le variabili d'ambiente:
```
class Settings(BaseSettings):
	sentinel_client_id: str
	sentinel_client_secret: str
	sentinel_instance_id: str
	electricity_price_eur_kwh: float = 0.25
	cool_roof_albedo: float = 0.75
```

In locale vengono lette dal file .env. Su railway vengono inserite manualmente nel pannello Variables. Il file .env NON viene mai committato su GitHub grazie al .gitignore.


## 4. Sentinel Hub e Dati Satellitari

### 4.1 Cos'è Sentinel-2

Sentinel-2 è una costellazione di due satelliti dell'Agenzia Spaziale Europea (ESA) che fotografano l'intera superficie terrestre ogni 5 giorni con una risoluzione di 10-20 metri. Le immagini sono gratuite e pubbliche.

Il prodotto usato è Sentinel-2 L2A: immagini già corrette per l'atmosfera (Bottom of Atmosphere), che restituiscono la riflettanza reale della superficie e non quella perturbata dall'atmosfera.

### 4.2 Sentinel Hub API

Sentinel Hub è un servizio cloud che permette di accedere alle immagini Sentinel-2 via API. Invece di scaricare file da gigabyte, si richiede solo il valore medio di specifiche bande spettrali per una specifica area geografica.

#### Credenziali necessarie:
- CLIENT_ID: identifica l'applicazione
- CLIENT_SECRET: password dell'applicazione
- INSTANCE_ID: configurazione specifica con le bande spettrali

### 4.3 Bande spettrali usate

| Banda Sentinel-2 | Lunghezza d'onda / Descrizione     |
| ---------------- | ---------------------------------- |
| B02 -- Blue      | 490 nm -- Blu visibile             |
| B04 -- Red       | 665 nm -- Rosso visibile           |
| B08 -- NIR       | 842 nm -- Infrarosso vicino        |
| B8A -- Red Edge  | 865 nm -- Bordo del rosso          |
| B11 -- SWIR      | 1610 nm -- Infrarosso a onde corte |

### 4.4 Formula albedo di Liang (2001)

L'albedo broadband (visibile + infrarosso) viene calcolata dalla combinazione lineare delle bande con la formula pubblicata da Liang nel 2001 su Remote Sensing of Environment:

$alpha = 0.356*B02 + 0.130*B04 + 0.373*B08 + 0.085*B8A + 0.072*B11 - 0.0018$

Dove B02, B04, B8Ab B11 sono i valori di riflettanza di superficie (Bottom of Atmosphere) normalizzati tra 0 e 1.

Il risultato è l'albedo broadband: la frazione di radiazione solare totale riflessa dalla superficie. Un tetto nero ha alpha ~0.05, un tetto bianco ha alpha ~0.80.

### 4.5 Catalog API -- scelta della scena migliore

Prima di scaricare i dati, il backend interrora Sentinel Hub Catalog API per trovare la scena (passaggio del satellite) con meno nuvole nel periodo selezionato. Questo serve a garantire che i dati di albedo non siano disturbati dalla copertura nuvolosa.

Il filtro avviene in due fasi:
- Query al Catalog per tutte le scene nel periodo e nell'area
- Filtraggio manuale per copertura nuvolosa <= soglia impostata dall'utente
- Selezione della scena con il minimo di nuvole tra quelle filtrate

## 5. Motore Fisico e Calcoli

### 5.1 thermal_engine.py -- Riduzione temperatura

Il motore termico implementa il modello di bilancio radiativo descritto da Akbari & Matthews (2012). Il principio fisico è che aumentando l'albedo, la superficie assorbe meno radiazione solare e si raffredda.

#### Costanti fisiche usate:

| Parametro                      | Valore / Descrizione                                   |
| ------------------------------ | ------------------------------------------------------ |
| Irradianza solare picco estivo | 600 W/m2 (estate, superfici orizzontali)               |
| Coefficiente convettivo h      | 12 W/m2K (tetto esposto al vento)                      |
| Frazione UHI                   | 0.10 (10% della riduzione superficiale va all'aria)    |
| Accoppiamento indoor           | 0.40 (40% della riduzione superficiale va all'interno) |
| U-value tetto standard         | 0.45 W/m2K (tipico edificio italiano anni '70-'80)     |
| COP condizionatore             | 2.8 (split AC standard)                                |

#### Calcolo riduzione temperatura superficiale:
```
delta_T_surface = (delta_albedo * I_solar) / h_conv => (0.60 * 600) / 12 = 30°C
```

Dove delta_albedo è la differenza tra albedo cool roof (0.75) e albedo attuale misurata dal satellite.

#### Riduzione temperatura interna:
```
delta_T_ambient = delta_T_surface * uhi_fraction => 30 * 0.10 = 3°C
```

### 5.2 energy_calculator.py -- Risparmio energetico

Il calcolo del risparmio energetico segue il metodo semplificato della norma EN ISO 13790 (Calcolo del fabbisogno energetico per il riscaldamento e il raffrescamento degli edifici).

#### Gradi Giorno di Raffrescamento (GGR) per zona climatica:

| Zona climatica                                  | GGR (base 18°C) |
| ----------------------------------------------- | --------------- |
| Mediterranea (Bari, Napoli, Roma, Palermo)      | 900 GGR         |
| Continentale (Milano, Bologna, Torino, Firenze) | 600 GGR         |
| Alpina (Bolzano, Aosta, Trento)                 | 250 GGR         |

#### Formula risparmio kWh:
```
kWh_annui = area_m2 * U_roof * delta_T_indoor * GGR * 24 / COP
```

#### Risparmio in euro:
```
risparmio_eur = kWh_annui * prezzo_energia_eur_kWh
```

#### CO2 evitata:
```
co2_kg_anno = kWh_annui * 0.233
```

Il fattore 0.233 kgCO2/kWh è il fattore di emissione della rete elettrica italiana (fonte: ISPRA 2023).

### 5.3 energy_price_service.py -- Prezzo energia dinamico

Il prezzo dell'energia elettrica viene recuperato dinamicamente dall'API del GME (Gestore Mercati Energetici) ogni 24 ore.

#### Funzionamento della cache:
- Al primo utilizzo quotidiano, il backend chiama l'API GME per il PUN (Prezzo Unico Nazionale)
- Il prezzo viene salvato in memoria con un timestamp
- Le successive richieste nelle 24 ore usano il valore in cache senza chiamare il GME
- Se il GME non risponde, viene usato il prezzo di fallback dal .env (default 0.25 EUR/kWh)
- La response include price_source ("gme_api" o "fallback") e price_last_updated
- Il frontend mostra un pallino verde LIVE quando il prezzo è dal GME

## 6. Frontend

### 6.1 Struttura -- Single File App

Il frontend è un singolo file HTML che contiene tutto: HTML, CSS, JavaScript. Non usa framework come React o Vue, nessun processo di build, nessuna dipendenza da installare.
Si apre direttamente nel browser.
Questa scelta è intenzionale: massima semplicità di deploy e massima portabilità.

### 6.2 Leaflet.js -- Mappa interattiva

Leaflet.js è la libreria JavaScript open source più usata per mappe interattive.

#### Layer mappa disponibili:
- Dark (CartoDB Dark Matter) -- mappa scura per visualizzare meglio i poligoni
- Stardale (OpenStreetMap) -- mappa stradale classica
- Satellite (Esri World Imagery) -- immagini satellitari ad alta risoluzione

Leaflet.draw è il plugin usato per disegnare il poligono sulla mappa. Permette di aggiungere vertici con click e chiudere il poligono con doppio click.

### 6.3 Reverse Geocoding -- Zona climatica automatica

Quando l'utente disegna un poligono, il frontend calcola il centroide e fa una chiamata a Nominatim:
```
fetch(`https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lng}&format=json`)
```

Nominatim restituisce l'indirizzo in formato strutturato (città, regione, stato). Il frontend analizza il campo "state" con una lista di keyword per assegnare automaticamente la zona climatica:
- Puglia, Campania, Sicilia, Sardegna, Lazio, ecc => Mediterranea
- Trentino, Valle d'Aosta, Friuli => Alpina
- Tutto il resto => Continentale

### 6.4 Export PDF -- jsPDF + html2canvas

Il PDF viene generato interamente nel browser, senza coinvolgere il backend.
html2canvas cattura uno screenshot del div della mappa (incluso il poligono verde) e lo converte in un'immagine base64. jsPDF è una libreria JavaScript che permette di creare PDF programmaticamente nel browser, posizionando testo e immagini con coordinate precise in millimetri.

#### Struttura del PDF generato:
- Header verde con logo CoolRoof e data
- Riquadro con nome edificio e committente
- Screenshot della mappa con il poligono
- 3 card affiancate: Albedo, Temperatura, Energia
- Riquadro verde con risparmio annuo in evidenza
- Note metodologiche e disclaimer
- Footer con data/ora di generazione

### 6.5 Chiamata API

Il frontend comunica con il backend tramite una singola chiamata fetch POST:
```
const res = await fetch(`${API_BASE}/analysis/cool-roof`, {
	method: "POST",
	headers: { "Content-Type": "application/json" },
	body: JSON.stringify({
		geometry: currentGeoJSON, // GeoJSON Polygon
		date_from: "2024-06-01",
		date_to: "2024-08-31",
		cloud_coverage_max: 20,
		climate_zone: "mediterranean"
	})
});
```

## 7. Deploy e Infrastruttura

### 7.1 Backend -- Railway

Railway è una piattaforma PaaS che deploya automaticamente il backend ogni volta che viene fatto un push su GitHub.

Il deploy avviene tramite Dockerfile:
```
FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

Le variabili d'ambiente (credenziali Sentinel Hub, prezzo energia) vengono inserite nel pannelo Variables di Railway e iniettate nell'ambiente Docker al momento del deploy.

Uvicorn è il server ASGI che esegue l'applicazione FastAPI.

### 7.2 Frontend -- Vercel

Vercel è la piattaforma di deploy più usata per il frontend statici. Rileva automaticamente che index.html è un sito statico e lo serve tramite CDN globale.
Ogni push su GitHub al repository cooo-roof-frontend triggera un deploy automatico in circa 10 secondi.

### 7.3 Flusso di deploy

- Modifica il codice in locale
- Carica su GitHub
- Railway/Vercel rilevano il cambiamento automaticamente
- Railway rebuilda il container Docker e rideploya il backend
- Tutto il processo richiede 2-3 minuti

## 8. API Reference

### 8.1 POST /api/v1/analysis/cool-roof

Endpoint principale. Riceve il poligono GeoJSON e restituisce l'analisi completa.

#### Request body:

| Campo                     | Tipo / Default / Descrizione                       |
| ------------------------- | -------------------------------------------------- |
| geometry                  | GeoJSONPolygon — Poligono del tetto (obbligatorio) |
| date_from                 | string — "2024-06-01" — Inizio periodo analisi     |
| date_to                   | string — "2024-08-31" — Fine periodo analisi       |
| cloud_coverage_max        | float — 20.0 — Max % copertura nuvolosa            |
| climate_zone              | string — "mediterranean" — Zona climatica          |
| baseline_albedo_override  | float \| null — Override albedo attuale            |
| cool_roof_albedo_override | float \| null — Override albedo target             |

#### Response body:

| Campo                             | Descrizione                                 |
| --------------------------------- | ------------------------------------------- |
| albedo.current_albedo             | Albedo attuale misurata da Sentinel-2 (0-1) |
| albedo.targer_albedo              | Albedo dopo cool roof (defualt 0.75)        |
| albedo.area_m2                    | Area del poligono in metri quadrati         |
| albedo.sentinel_scene_date        | Data delle scena satellitare usata          |
| albedo.cloud_coverage_pct         | Copertura nuvolosa della scena (%)          |
| thermal.surface_temp_reduction_c  | Riduzione temperatura superficie tetto (°C) |
| thermal.indoor_temp_reduction_c   | Riduzione temperatura interna (°C)          |
| thermal.ambient_temp_reduction_c  | Riduzione temperatura aria ambiente (°C)    |
| energy.annual_cooling_savings_kwh | kWh risparmiati per anno                    |
| energy.annual_savings_eur         | Risparmio in euro per anno                  |
| energy.co2_avoided_kg_year        | kg di CO2 evitati per anno                  |
| energy.payback_years              | Anni di payback                             |
| energy.electricity_price_eur_kwh  | Prezzo energia usato nel calcolo            |
| energy.price_source               | "gme_api" o "fallback"                      |
| warnings                          | Lista avvisi                                |

### 8.2 GET /api/v1/analysis/electricity-price

Restituisce il prezzo corrente dell'energia elettrica italiana.

| Campo risposta | Descrizione                                   |
| -------------- | --------------------------------------------- |
| price_eur_kwh  | Prezzo in EUR/kWh                             |
| source         | "gme_api" se dal GME, "fallback" se da config |
| last_updated   | Data dell'aggiornamento                       |
| cached         | true se dalla cache delle 24h                 |

### 8.3 GET /health

Health check endpoint. Restituisce {"status": "ok"}. Usato da Railway per verificare che il container sia vivo.


## 9. Sicurezza

### 9.1 Gestione credenziali

- .env non è mai committato su GitHub
- Su Railway le credenziali vivono nelle variabili d'ambiente del container
- Il SENTINEL_CLIENT_SECRET non appare mai nei log o nelle response

### 9.2 CORS

CORS è configurato con ```allow_origins=["*"]``` per semplicità. 

### 9.3 Validazione input

Pydantic valida automaticamente tutti i campi in input. Il poligono GeoJSON viene verificato per chiusura e numero minimo di punti. Valori fuori range (es. cloud_coverage_max > 100) vengono rifiutati con HTTP 422.

# ✈️ ADS-B Flight Tracker

A real-time aircraft tracking system built with Python and JavaScript.  
It receives live ADS-B transponder signals via a Software Defined Radio (SDR) antenna, stores flight data in a local SQLite database, and displays everything on an interactive map in your browser.

> 📦 **No antenna? No problem.** This repo includes a small sample database (`adsb_data.db`) with a handful of synthetic flight records, so you can run the backend and explore the map/UI right away — no RTL-SDR hardware or `dump1090` required. See [Running without hardware](#-running-without-hardware) below.

---

## 📸 Features

- 🟢 **Live tracking** — see aircraft positions update in real time on a Leaflet map
- 🗺️ **Historical trips** — browse every flight recorded by your antenna
- 🎨 **Altitude colour coding**
  - 🟢 Green — below 10,000 ft (takeoff / landing)
  - 🟡 Yellow — 10,000 – 25,000 ft (climb / descent)
  - 🔴 Red — above 25,000 ft (cruise)
- 🔄 **Live trail** — a short trailing path behind each moving aircraft
- 📊 **Aircraft statistics** — records count, max altitude, session history

---

## 🗂️ Project Structure

```
├── adsb_capture.py   # Reads raw ADS-B data from dump1090 → saves to SQLite
├── backend.py        # FastAPI server — REST API + serves the web UI
├── index.html        # Web UI (Leaflet map)
├── scripts.js        # Frontend logic (live map, trips, path rendering)
├── styles.css        # Dark-theme CSS
├── requirements.txt  # Python dependencies
└── README.md
```

---

## ⚙️ Requirements

### Hardware
- An **SDR (Software Defined Radio) dongle** (e.g. RTL-SDR)
- An **antenna** tuned to 1090 MHz

### Software
- Python 3.10+
- [dump1090](https://github.com/MalcolmRobb/dump1090) — decodes ADS-B signals from the SDR
- A browser with Live Server (VS Code extension) **or** just open `index.html` directly

---

## 🚀 Getting Started

### 1 — Install Python dependencies

```bash
pip install -r requirements.txt
```

### 2 — Run dump1090 (Terminal 1)

```bash
cd C:\path\to\dump1090
dump1090.exe --interactive --net
```

> This starts the ADS-B decoder and opens a TCP stream on port **30003**.

### 3 — Start the data capture script (Terminal 2)

```bash
cd C:\path\to\project
python adsb_capture.py
```

> Connects to dump1090, parses incoming messages, and writes aircraft data to `adsb_data.db`.

### 4 — Start the FastAPI backend (Terminal 3)

```bash
cd C:\path\to\project
python -m uvicorn backend:app --reload
```

> API is now available at `http://localhost:8000`

### 5 — Open the web UI (Terminal 4 / Browser)

**Option A — VS Code Live Server**
- Right-click `index.html` in VS Code
- Select **"Open with Live Server"**

**Option B — Direct**
- Open `http://localhost:8000` in your browser (the FastAPI server also serves the frontend)

---

## 🧪 Running without hardware

Don't have an RTL-SDR dongle or antenna handy? The repo ships with a sample `adsb_data.db` containing a small set of synthetic flight records, so you can skip steps 2 and 3 above and go straight to:

```bash
pip install -r requirements.txt
python -m uvicorn backend:app --reload
```

Then open `http://localhost:8000` to browse the sample aircraft, their recorded trips, and flight paths on the map. (The live-tracking view will simply show no aircraft, since that requires a real `dump1090` feed.)

---

## 🔌 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/live-direct` | Live aircraft from dump1090 |
| `GET` | `/api/planes` | All recorded aircraft sessions |
| `GET` | `/api/planes/count` | Total unique aircraft count |
| `GET` | `/api/plane/{icao}/trips` | Trips for a specific aircraft |
| `GET` | `/api/trip/{icao}/{trip_id}` | GPS path for a specific trip |

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| Data capture | Python `socket` + `sqlite3` |
| Backend | [FastAPI](https://fastapi.tiangolo.com/) + [Uvicorn](https://www.uvicorn.org/) |
| Data processing | [Pandas](https://pandas.pydata.org/) |
| Frontend map | [Leaflet.js](https://leafletjs.com/) |
| Tile layer | OpenStreetMap |

---

## 📝 Notes

- A small sample `adsb_data.db` (a handful of synthetic flight records) is included in the repo so you can run and explore the app without an antenna — see [Running without hardware](#-running-without-hardware). If you capture your own data with `adsb_capture.py`, it will overwrite this file with real recordings.
- The system works on any Windows machine — just install the Python dependencies and ensure dump1090 is running before starting the capture script.
- Session gaps of more than **45 minutes** are treated as separate flights.
- A plane is considered "live" if it has been seen within the last **15 minutes**.

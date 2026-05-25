from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import sqlite3
import pandas as pd
import socket
import time
from collections import defaultdict
from pathlib import Path

# Create app FIRST
app = FastAPI()

# Allow all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
)

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "adsb_data.db"
SESSION_GAP_MINUTES = 45
LIVE_TIMEOUT_SECONDS = 900      # 10 minutes (was 60)
LIVE_CLEANUP_SECONDS = 1000      # ~11.5 minutes (was 120)
NO_CACHE_HEADERS = {"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"}

# Store last seen times
last_seen = defaultdict(float)
live_state = {}


def normalize_timestamp_param(value: str | None) -> str | None:
    if not value:
        return None
    return value.replace("T", " ")


def clean_live_state(current_time: float) -> None:
    cutoff_clean = current_time - LIVE_CLEANUP_SECONDS
    for icao in list(last_seen.keys()):
        if last_seen[icao] < cutoff_clean:
            del last_seen[icao]
            live_state.pop(icao, None)

# =====================================================
# HOME PAGE
# =====================================================
@app.get("/")
async def home():
    return FileResponse(BASE_DIR / "index.html", headers=NO_CACHE_HEADERS)


@app.get("/styles.css")
async def styles():
    return FileResponse(BASE_DIR / "styles.css", media_type="text/css", headers=NO_CACHE_HEADERS)


@app.get("/scripts.js")
async def scripts():
    return FileResponse(BASE_DIR / "scripts.js", media_type="application/javascript", headers=NO_CACHE_HEADERS)


@app.get("/favicon.ico")
async def favicon():
    return Response(status_code=204)

# =====================================================
# LIVE PLANES - DIRECT FROM DUMP1090 (with heading)
# =====================================================
@app.get("/api/live-direct")
def get_live_direct():
    global last_seen, live_state
    current_time = time.time()
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        sock.connect(("127.0.0.1", 30003))
        
        data = b""
        while True:
            try:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                data += chunk
                if len(data) > 20000:  # Reduced from 50000 for faster response
                    break
            except socket.timeout:
                break
        
        sock.close()
        
        decoded = data.decode("utf-8", errors="ignore")
        lines = decoded.split("\n")
        
        for line in lines:
            fields = line.split(",")
            if len(fields) > 21 and fields[0] == "MSG":
                icao = fields[4]
                if not icao:
                    continue

                last_seen[icao] = current_time
                plane_state = live_state.setdefault(icao, {
                    "icao": icao,
                    "callsign": "",
                    "altitude": None,
                    "speed": None,
                    "heading": None,
                    "lat": None,
                    "lon": None,
                    "last_position_time": None,
                })

                callsign = fields[10].strip() if len(fields) > 10 and fields[10] else ""
                altitude = fields[11] if len(fields) > 11 and fields[11] else None
                speed = fields[12] if len(fields) > 12 and fields[12] else None
                heading = fields[13] if len(fields) > 13 and fields[13] else None
                lat = fields[14] if len(fields) > 14 and fields[14] else None
                lon = fields[15] if len(fields) > 15 and fields[15] else None

                if callsign:
                    plane_state["callsign"] = callsign
                if altitude is not None:
                    plane_state["altitude"] = altitude
                if speed is not None:
                    plane_state["speed"] = speed
                if heading is not None:
                    plane_state["heading"] = heading
                if lat is not None and lon is not None:
                    plane_state["lat"] = lat
                    plane_state["lon"] = lon
                    plane_state["last_position_time"] = current_time

        live_planes = []
        cutoff = current_time - LIVE_TIMEOUT_SECONDS
        
        for icao, last_time in list(last_seen.items()):
            if last_time > cutoff and icao in live_state:
                plane_state = dict(live_state[icao])
                if (
                    plane_state.get("last_position_time") is None
                    or plane_state["last_position_time"] <= cutoff
                ):
                    plane_state["lat"] = None
                    plane_state["lon"] = None
                live_planes.append(plane_state)

        clean_live_state(current_time)
        
        return live_planes
        
    except Exception as e:
        print(f"Live feed error: {e}")
        return []

# =====================================================
# GET TOTAL COUNT
# =====================================================
@app.get("/api/planes/count")
def get_count():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(DISTINCT icao) FROM aircraft WHERE icao IS NOT NULL")
    count = cursor.fetchone()[0]
    conn.close()
    return {"total": count}

# =====================================================
# GET ALL PLANES
# =====================================================
@app.get("/api/planes")
def get_planes(limit: int = 100, offset: int = 0):
    conn = sqlite3.connect(DB_PATH)
    query = """
        SELECT timestamp, icao, callsign, altitude
        FROM aircraft
        WHERE icao IS NOT NULL
        ORDER BY icao, timestamp
    """
    df = pd.read_sql(query, conn)
    conn.close()

    if len(df) == 0:
        return []

    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["callsign"] = df["callsign"].fillna("").astype(str).str.strip()
    df["icao_gap"] = df.groupby("icao")["timestamp"].diff().dt.total_seconds().div(60)
    df["session_break"] = df["icao_gap"].isna() | (df["icao_gap"] > SESSION_GAP_MINUTES)
    df["session_id"] = df.groupby("icao")["session_break"].cumsum().astype(int)

    session_rows = []
    for (icao, session_id), group in df.groupby(["icao", "session_id"], sort=False):
        non_empty_callsigns = group.loc[group["callsign"] != "", "callsign"]
        if len(non_empty_callsigns) > 0:
            callsign = non_empty_callsigns.value_counts().idxmax()
        else:
            callsign = ""

        max_altitude = group["altitude"].dropna().max()
        session_rows.append({
            "icao": icao,
            "callsign": callsign,
            "total_records": int(len(group)),
            "max_altitude": int(max_altitude) if pd.notna(max_altitude) else None,
            "session_id": int(session_id),
            "session_start": group["timestamp"].min().strftime("%Y-%m-%d %H:%M:%S"),
            "session_end": group["timestamp"].max().strftime("%Y-%m-%d %H:%M:%S"),
        })

    session_df = pd.DataFrame(session_rows)
    session_df = session_df.sort_values(
        by=["total_records", "session_end"],
        ascending=[False, False]
    )

    if offset:
        session_df = session_df.iloc[offset:]
    if limit:
        session_df = session_df.iloc[:limit]

    return session_df.to_dict(orient="records")

# =====================================================
# GET TRIPS FOR A PLANE
# =====================================================
@app.get("/api/plane/{icao}/trips")
def get_plane_trips(icao: str, start_time: str | None = None, end_time: str | None = None):
    start_time = normalize_timestamp_param(start_time)
    end_time = normalize_timestamp_param(end_time)
    conn = sqlite3.connect(DB_PATH)
    query = """
        SELECT timestamp, altitude, lat, lon 
        FROM aircraft 
        WHERE icao = ? 
          AND lat IS NOT NULL 
          AND lon IS NOT NULL
    """
    params = [icao]

    if start_time:
        query += " AND timestamp >= ?"
        params.append(start_time)
    if end_time:
        query += " AND timestamp <= ?"
        params.append(end_time)

    query += " ORDER BY timestamp"
    df = pd.read_sql(query, conn, params=params)
    conn.close()
    
    if len(df) == 0:
        return []
    
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df['time_diff'] = df['timestamp'].diff().dt.total_seconds() / 60
    df['new_trip'] = (df['time_diff'] > SESSION_GAP_MINUTES) | (df['time_diff'].isna())
    df['trip_id'] = df['new_trip'].cumsum()
    
    trips = []
    for trip_num in df['trip_id'].unique():
        trip_data = df[df['trip_id'] == trip_num]
        if len(trip_data) > 5:
            trips.append({
                'trip_id': int(trip_num),
                'start_time': trip_data['timestamp'].min().isoformat(),
                'end_time': trip_data['timestamp'].max().isoformat(),
                'duration_min': int((trip_data['timestamp'].max() - trip_data['timestamp'].min()).total_seconds() / 60),
                'max_altitude': int(trip_data['altitude'].max()),
                'points': len(trip_data),
                'origin_lat': trip_data['lat'].iloc[0],
                'origin_lon': trip_data['lon'].iloc[0],
                'dest_lat': trip_data['lat'].iloc[-1],
                'dest_lon': trip_data['lon'].iloc[-1]
            })
    return trips

# =====================================================
# GET PATH FOR A TRIP
# =====================================================
@app.get("/api/trip/{icao}/{trip_id}")
def get_trip_path(icao: str, trip_id: int, start_time: str | None = None, end_time: str | None = None):
    start_time = normalize_timestamp_param(start_time)
    end_time = normalize_timestamp_param(end_time)
    conn = sqlite3.connect(DB_PATH)
    query = """
        SELECT timestamp, altitude, speed, lat, lon 
        FROM aircraft 
        WHERE icao = ? 
          AND lat IS NOT NULL 
          AND lon IS NOT NULL
    """
    params = [icao]

    if start_time:
        query += " AND timestamp >= ?"
        params.append(start_time)
    if end_time:
        query += " AND timestamp <= ?"
        params.append(end_time)

    query += " ORDER BY timestamp"
    df = pd.read_sql(query, conn, params=params)
    conn.close()
    
    if len(df) == 0:
        return []
    
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df['time_diff'] = df['timestamp'].diff().dt.total_seconds() / 60
    df['new_trip'] = (df['time_diff'] > SESSION_GAP_MINUTES) | (df['time_diff'].isna())
    df['trip_num'] = df['new_trip'].cumsum()
    
    trip_data = df[df['trip_num'] == trip_id]
    return trip_data[['lat', 'lon', 'altitude', 'timestamp']].to_dict(orient="records")


























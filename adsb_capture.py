import socket
import sqlite3
from datetime import datetime

import os
script_dir = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(script_dir, "adsb_data.db")

# Connect to dump1090 data stream
HOST = "127.0.0.1"
PORT = 30003

# Create database
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS aircraft (
    timestamp TEXT,
    icao TEXT,
    callsign TEXT,
    altitude REAL,
    speed REAL,
    lat REAL,
    lon REAL
)
""")

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect((HOST, PORT))

print("Receiving ADS-B data... Press Ctrl+C to stop.")
print("-" * 80)

# Track last position for change detection
last_pos = {}

try:
    while True:
        data = sock.recv(1024).decode("utf-8", errors="ignore")
        lines = data.split("\n")

        for line in lines:
            fields = line.split(",")

            if len(fields) > 21 and fields[0] == "MSG":
                # Extract fields (some may be empty)
                icao = fields[4] if len(fields) > 4 else ""
                callsign = fields[10].strip() if len(fields) > 10 else ""
                altitude = fields[11] if len(fields) > 11 and fields[11] else None
                speed = fields[12] if len(fields) > 12 and fields[12] else None
                lat = fields[14] if len(fields) > 14 and fields[14] else None
                lon = fields[15] if len(fields) > 15 and fields[15] else None

                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                # Convert empty strings to None for numeric fields
                altitude = float(altitude) if altitude and altitude.replace('.','',1).isdigit() else None
                speed = float(speed) if speed and speed.replace('.','',1).isdigit() else None
                lat = float(lat) if lat and lat.replace('.','',1).lstrip('-').isdigit() else None
                lon = float(lon) if lon and lon.replace('.','',1).lstrip('-').isdigit() else None

                # Always insert, even with empty fields
                cursor.execute("""
                INSERT INTO aircraft VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (timestamp, icao, callsign, altitude, speed, lat, lon))
                conn.commit()

                # Check if position changed (visual indicator only)
                current_pos = f"{lat},{lon}" if lat and lon else None
                if icao not in last_pos:
                    last_pos[icao] = current_pos
                    pos_changed = False
                else:
                    pos_changed = (current_pos and current_pos != last_pos[icao])
                    if pos_changed:
                        last_pos[icao] = current_pos
                
                # Create visual indicator
                move_indicator = " 🔄 MOVING" if pos_changed else "      "

                # Create a readable display
                alt_disp = f"{int(altitude)} ft" if altitude else "-----"
                spd_disp = f"{int(speed)} kt" if speed else "-----"
                callsign_disp = callsign if callsign else "------"
                pos_disp = f"{lat:.4f},{lon:.4f}" if lat and lon else "no position"

                print(f"{timestamp} | {icao} | {callsign_disp:7} | {alt_disp:8} | {spd_disp:6} | {pos_disp}{move_indicator}")

except KeyboardInterrupt:
    print("\nStopping capture...")
    sock.close()
    conn.close()
    print(f"Data saved to adsb_data.db")
except Exception as e:
    print(f"Error: {e}")
    sock.close()
    conn.close()
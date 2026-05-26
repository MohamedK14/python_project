import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime
import os

# Connect to your database - UPDATED PATH for micha computer
db_path = r'C:\Users\micha\OneDrive\Documents\python_project\adsb_data.db'
conn = sqlite3.connect(db_path)

print("="*60)
print("PHASE 3 DEMO - ADS-B AIRCRAFT ANALYSIS")
print("="*60)

# SECTION 1: Data Overview
total = pd.read_sql("SELECT COUNT(*) FROM aircraft", conn).iloc[0,0]
unique = pd.read_sql("SELECT COUNT(DISTINCT icao) FROM aircraft", conn).iloc[0,0]
print(f"\n📊 Total records: {total}")
print(f"✈️ Unique aircraft: {unique}")

# SECTION 2: Live data preview (like your capture screen)
print("\n🔴 LIVE DATA PREVIEW (last 10 records):")
preview = pd.read_sql("""
    SELECT timestamp, icao, altitude, lat, lon 
    FROM aircraft 
    WHERE lat IS NOT NULL 
    ORDER BY timestamp DESC 
    LIMIT 10
""", conn)
print(preview.to_string(index=False))

# SECTION 3: Data Quality (your ratio idea)
with_pos = pd.read_sql("SELECT COUNT(*) FROM aircraft WHERE lat IS NOT NULL", conn).iloc[0,0]
pos_pct = (with_pos/total)*100
print(f"\n📈 Position data: {with_pos}/{total} ({pos_pct:.1f}%)")

with_alt = pd.read_sql("SELECT COUNT(*) FROM aircraft WHERE altitude IS NOT NULL", conn).iloc[0,0]
alt_pct = (with_alt/total)*100
print(f"📈 Altitude data: {with_alt}/{total} ({alt_pct:.1f}%)")

with_speed = pd.read_sql("SELECT COUNT(*) FROM aircraft WHERE speed IS NOT NULL", conn).iloc[0,0]
speed_pct = (with_speed/total)*100
print(f"📈 Speed data: {with_speed}/{total} ({speed_pct:.1f}%)")

# SECTION 4: Traffic by hour
df = pd.read_sql("SELECT timestamp FROM aircraft WHERE lat IS NOT NULL", conn)
df['hour'] = pd.to_datetime(df['timestamp']).dt.hour
hourly = df.groupby('hour').size()

# SECTION 5: Create visualizations
plt.figure(figsize=(15, 10))

# Plot 1: Data quality bar
plt.subplot(2, 2, 1)
categories = ['Total', 'With Position', 'With Altitude', 'With Speed']
counts = [total, with_pos, with_alt, with_speed]
plt.bar(categories, counts, color=['gray', 'blue', 'green', 'orange'])
plt.title('Data Quality Overview')
plt.ylabel('Records')
plt.grid(True, alpha=0.3)

# Plot 2: Traffic by hour
plt.subplot(2, 2, 2)
hourly.plot(kind='bar', color='skyblue')
plt.title('Traffic by Hour of Day')
plt.xlabel('Hour')
plt.ylabel('Messages')
plt.grid(True, alpha=0.3)

# Plot 3: Altitude distribution
plt.subplot(2, 2, 3)
alt_data = pd.read_sql("SELECT altitude FROM aircraft WHERE altitude IS NOT NULL", conn)
if len(alt_data) > 0:
    plt.hist(alt_data['altitude'], bins=30, color='green', alpha=0.7)
    plt.title('Altitude Distribution')
    plt.xlabel('Feet')
    plt.ylabel('Count')
    plt.grid(True, alpha=0.3)

# Plot 4: Sample flight path
plt.subplot(2, 2, 4)
path = pd.read_sql("""
    SELECT lat, lon FROM aircraft 
    WHERE icao = (SELECT icao FROM aircraft WHERE lat IS NOT NULL GROUP BY icao ORDER BY COUNT(*) DESC LIMIT 1)
    AND lat IS NOT NULL
    ORDER BY timestamp
    LIMIT 50
""", conn)
if len(path) > 1:
    plt.plot(path['lon'], path['lat'], 'b-', marker='o', markersize=3)
    plt.title('Sample Flight Path')
    plt.xlabel('Longitude')
    plt.ylabel('Latitude')
    plt.grid(True, alpha=0.3)

plt.tight_layout()

# Create analysis folder if it doesn't exist
os.makedirs('analysis', exist_ok=True)
plt.savefig('analysis/phase3_plots.png')
plt.show()

# SECTION 6: ML Plan
print("\n" + "="*60)
print("📋 MACHINE LEARNING PLAN")
print("="*60)
print(f"""
Method: Unsupervised clustering + Regression analysis
Goal: Identify flight patterns and altitude-speed relationships
Dataset: Self-collected ADS-B data ({total} records so far)
Evaluation: Correlation coefficients, cluster quality scores

Research question: 
How can real-time ADS-B data be used to model air traffic patterns?
""")

# SECTION 7: Quick stats for report
print("\n" + "="*60)
print("📊 SUMMARY FOR PHASE 3 REPORT")
print("="*60)
print(f"""
✅ Hardware: RTL-SDR working
✅ Data capture: {total} records collected
✅ Pipeline: dump1090 → Python → SQLite
✅ Preview: Last 10 records shown above
✅ Quality: {pos_pct:.1f}% position data
✅ Visualization: Saved to analysis/phase3_plots.png
""")

conn.close()
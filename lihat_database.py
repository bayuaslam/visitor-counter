import sqlite3
from pathlib import Path

db = Path("lab_visitors.db")
if not db.exists():
    print("lab_visitors.db belum ada. Jalankan visitor_counter.py dulu.")
    raise SystemExit

conn = sqlite3.connect(db)

print("\n=== 20 EVENT TERAKHIR ===\n")
rows = conn.execute("""
    SELECT id, timestamp, track_id, direction, occupancy_after
    FROM visitor_events
    ORDER BY id DESC
    LIMIT 20
""").fetchall()

if not rows:
    print("Belum ada event.")
else:
    for row in rows:
        print(f"#{row[0]} | {row[1]} | track={row[2]} | {row[3]} | inside={row[4]}")

print("\n=== OCCUPANCY TERSIMPAN ===\n")
state = conn.execute("SELECT occupancy, updated_at FROM counter_state WHERE id = 1").fetchone()
print(state)
conn.close()

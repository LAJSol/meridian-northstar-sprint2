import sqlite3
import time
import uuid
import json
from threading import Thread
import requests
from flask import Flask, jsonify, request, render_template

app = Flask(__name__)
DB_FILE = "day4_system.db"
MOCK_PRINTER_URL = "http://127.0.0.1:5001/simulate-printer-hardware"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS local_stock (
            sku TEXT PRIMARY KEY,
            quantity INTEGER,
            last_updated REAL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS checkin_scans (
            scan_id TEXT PRIMARY KEY,
            user_id TEXT,
            status TEXT,
            updated_at REAL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS task_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_type TEXT,
            payload TEXT,
            status TEXT DEFAULT 'PENDING'
        )
    ''')
    conn.commit()
    conn.close()

# Run initialization & background queue worker when file loads
init_db()
Thread(target=lambda: run_queue_worker(), daemon=True).start()

@app.route('/')
def home():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Query live records from all 3 database tables
    cursor.execute("SELECT * FROM task_queue ORDER BY id DESC LIMIT 10")
    tasks = [dict(row) for row in cursor.fetchall()]

    cursor.execute("SELECT * FROM local_stock ORDER BY last_updated DESC LIMIT 10")
    stock = [dict(row) for row in cursor.fetchall()]

    cursor.execute("SELECT * FROM checkin_scans ORDER BY updated_at DESC LIMIT 10")
    checkins = [dict(row) for row in cursor.fetchall()]

    conn.close()
    return render_template('index.html', tasks=tasks, stock=stock, checkins=checkins)
except Exception as e:
    return f"Database Initializing: {str(e)}", 200

# --- WORKER: CHECKS THE WAITING LINE FOR JOBS ---
def run_queue_worker():
    while True:
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("SELECT id, task_type, payload FROM task_queue WHERE status = 'PENDING' ORDER BY id ASC LIMIT 1")
            row = cursor.fetchone()
            
            if row:
                task_id, task_type, raw_payload = row
                cursor.execute("UPDATE task_queue SET status = 'PROCESSING' WHERE id = ?", (task_id,))
                conn.commit()
                payload = json.loads(raw_payload)

                if task_type == "PROCESS_INVENTORY_WEBHOOK":
                    sku = payload.get("sku")
                    qty = payload.get("quantity")
                    cursor.execute('''
                        INSERT INTO local_stock (sku, quantity, last_updated)
                        VALUES (?, ?, ?)
                        ON CONFLICT(sku) DO UPDATE SET quantity=?, last_updated=?
                    ''', (sku, qty, time.time(), qty, time.time()))
                    conn.commit()

                elif task_type == "DISPATCH_PRINT_JOB":
                    try:
                        requests.post(MOCK_PRINTER_URL, json=payload, timeout=2)
                    except Exception:
                        pass  # Handles missing local printer server on cloud

                cursor.execute("UPDATE task_queue SET status = 'COMPLETED' WHERE id = ?", (task_id,))
                conn.commit()
            
            conn.close()
        except Exception as e:
            print(f"[Queue Worker Error] {e}")
            
        time.sleep(0.5)

# --- WEBHOOK 1: RECEIVE STOCK UPDATES FROM WAREHOUSE ---
@app.route('/webhooks/inventory', methods=['POST'])
def webhook_inventory():
    data = request.json or {}
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO task_queue (task_type, payload) VALUES (?, ?)",
        ("PROCESS_INVENTORY_WEBHOOK", json.dumps(data))
    )
    conn.commit()
    conn.close()
    return jsonify({"status": "ACCEPTED"}), 200

# --- READ STOCK LEVEL FOR SUPPORT AGENTS ---
@app.route('/inventory/<sku>', methods=['GET'])
def get_stock(sku):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT quantity, last_updated FROM local_stock WHERE sku = ?", (sku,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return jsonify({"sku": sku, "quantity": row[0], "cached_at": row[1]}), 200
    return jsonify({"error": "SKU not found"}), 404

# --- FAST INSTANT KIOSK CHECK-IN ---
@app.route('/kiosk/check-in', methods=['POST'])
def kiosk_checkin():
    data = request.json or {}
    user_id = data.get("user_id")
    scan_id = str(uuid.uuid4())[:8]

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO checkin_scans (scan_id, user_id, status, updated_at) VALUES (?, ?, 'Pending', ?)",
        (scan_id, user_id, time.time())
    )
    cursor.execute(
        "INSERT INTO task_queue (task_type, payload) VALUES (?, ?)",
        ("DISPATCH_PRINT_JOB", json.dumps({"scan_id": scan_id, "user_id": user_id}))
    )
    conn.commit()
    conn.close()
    return jsonify({"status": "Pending", "scan_id": scan_id}), 202

# --- WEBHOOK 2: RECEIVE CONFIRMATION FROM PRINTER ---
@app.route('/webhooks/print-status', methods=['POST'])
def webhook_print_status():
    data = request.json or {}
    scan_id = data.get("scan_id")
    print_status = data.get("status")

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM checkin_scans WHERE scan_id = ?", (scan_id,))
    row = cursor.fetchone()

    if row and row[0] != "Checked In":
        if print_status == "COMPLETED":
            cursor.execute(
                "UPDATE checkin_scans SET status = 'Checked In', updated_at = ? WHERE scan_id = ?",
                (time.time(), scan_id)
            )
            conn.commit()

    conn.close()
    return jsonify({"status": "ACK"}), 200

# --- READ CHECK-IN STATUS ---
@app.route('/kiosk/status/<scan_id>', methods=['GET'])
def get_scan_status(scan_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, status FROM checkin_scans WHERE scan_id = ?", (scan_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return jsonify({"scan_id": scan_id, "user_id": row[0], "status": row[1]}), 200
    return jsonify({"error": "Scan ID not found"}), 404

if __name__ == '__main__':
    app.run(port=5000)
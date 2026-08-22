import sqlite3
import time
import uuid
import json
from threading import Thread
import requests
from flask import Flask, jsonify, request

app = Flask(__name__)
@app.route('/')
def home():
    return "<h1>Meridian Northstar Pivot Prototype</h1><p>Status: Server & Webhook Listener Active</p>"
DB_FILE = "day4_system.db"
MOCK_PRINTER_URL = "http://127.0.0.1:5001/simulate-printer-hardware"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # Table to store current item quantities
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS local_stock (
            sku TEXT PRIMARY KEY,
            quantity INTEGER,
            last_updated REAL
        )
    ''')
    # Table to track kiosk check-in statuses
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS checkin_scans (
            scan_id TEXT PRIMARY KEY,
            user_id TEXT,
            status TEXT,
            updated_at REAL
        )
    ''')
    # Table acting as our simple background message queue
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

                # Process stock updates pushed from warehouse
                if task_type == "PROCESS_INVENTORY_WEBHOOK":
                    sku = payload.get("sku")
                    qty = payload.get("quantity")
                    cursor.execute('''
                        INSERT INTO local_stock (sku, quantity, last_updated)
                        VALUES (?, ?, ?)
                        ON CONFLICT(sku) DO UPDATE SET quantity=?, last_updated=?
                    ''', (sku, qty, time.time(), qty, time.time()))
                    conn.commit()
                    print(f"[Queue Worker] Updated stock for item {sku} to {qty}")

                # Send badge print requests to printer
                elif task_type == "DISPATCH_PRINT_JOB":
                    requests.post(MOCK_PRINTER_URL, json=payload, timeout=5)
                    print(f"[Queue Worker] Sent print job for scan ID {payload['scan_id']} to printer")

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
    init_db()
    Thread(target=run_queue_worker, daemon=True).start()
    app.run(port=5000)
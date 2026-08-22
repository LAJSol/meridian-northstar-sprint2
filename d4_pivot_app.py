import sqlite3
import time
import uuid
import json
from threading import Thread
import requests
from flask import Flask, jsonify, request, redirect, url_for

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

init_db()

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
                        pass

                cursor.execute("UPDATE task_queue SET status = 'COMPLETED' WHERE id = ?", (task_id,))
                conn.commit()
            
            conn.close()
        except Exception as e:
            print(f"[Queue Worker Error] {e}")
            
        time.sleep(0.5)

Thread(target=run_queue_worker, daemon=True).start()

# --- HOMEPAGE WITH TEST DATA BUTTON ---
@app.route('/')
def home():
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM task_queue ORDER BY id DESC LIMIT 10")
        tasks = cursor.fetchall()

        cursor.execute("SELECT * FROM local_stock ORDER BY last_updated DESC LIMIT 10")
        stock = cursor.fetchall()

        cursor.execute("SELECT * FROM checkin_scans ORDER BY updated_at DESC LIMIT 10")
        checkins = cursor.fetchall()
        conn.close()

        task_rows = "".join([f"<tr><td>#{t['id']}</td><td>{t['task_type']}</td><td>{t['payload']}</td><td>{t['status']}</td></tr>" for t in tasks]) or "<tr><td colspan='4' style='color:#64748b;'>No tasks in queue.</td></tr>"
        stock_rows = "".join([f"<tr><td>{s['sku']}</td><td>{s['quantity']}</td><td>{s['last_updated']}</td></tr>" for s in stock]) or "<tr><td colspan='3' style='color:#64748b;'>No stock records found.</td></tr>"
        checkin_rows = "".join([f"<tr><td>{c['scan_id']}</td><td>{c['user_id']}</td><td>{c['status']}</td></tr>" for c in checkins]) or "<tr><td colspan='3' style='color:#64748b;'>No check-in scans recorded.</td></tr>"

        return f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <title>Meridian Northstar Operations</title>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #f8fafc; padding: 25px; margin: 0; }}
                .container {{ max-width: 1000px; margin: auto; }}
                .header-flex {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }}
                h1 {{ color: #38bdf8; margin: 0; }}
                .status {{ color: #34d399; font-weight: bold; }}
                .btn {{ background: #0284c7; color: white; padding: 10px 18px; border: none; border-radius: 6px; font-weight: bold; cursor: pointer; text-decoration: none; display: inline-block; transition: background 0.2s; }}
                .btn:hover {{ background: #0369a1; }}
                .card {{ background: #1e293b; padding: 20px; border-radius: 8px; margin-bottom: 20px; border: 1px solid #334155; }}
                h2 {{ font-size: 1.1rem; color: #94a3b8; margin-top: 0; }}
                table {{ width: 100%; border-collapse: collapse; text-align: left; margin-top: 10px; }}
                th, td {{ padding: 10px; border-bottom: 1px solid #334155; font-size: 0.9rem; }}
                th {{ color: #38bdf8; font-size: 0.8rem; text-transform: uppercase; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header-flex">
                    <div>
                        <h1>Meridian Northstar Dashboard</h1>
                        <div class="status">● System Live & Listening</div>
                    </div>
                    <div>
                        <a href="/generate-test-data" class="btn"> Generate Test Data</a>
                    </div>
                </div>

                <div class="card">
                    <h2>Task Queue Jobs</h2>
                    <table><thead><tr><th>ID</th><th>Task Type</th><th>Payload</th><th>Status</th></tr></thead><tbody>{task_rows}</tbody></table>
                </div>

                <div class="card">
                    <h2>Local Stock Inventory</h2>
                    <table><thead><tr><th>SKU</th><th>Quantity</th><th>Last Updated</th></tr></thead><tbody>{stock_rows}</tbody></table>
                </div>

                <div class="card">
                    <h2>Kiosk Check-ins</h2>
                    <table><thead><tr><th>Scan ID</th><th>User ID</th><th>Status</th></tr></thead><tbody>{checkin_rows}</tbody></table>
                </div>
            </div>
        </body>
        </html>
        """
    except Exception as e:
        return f"<h2>System Active</h2><p>Database Initializing: {str(e)}</p>"

# --- TEST DATA GENERATOR ROUTE ---
@app.route('/generate-test-data')
def generate_test_data():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Insert mock inventory webhook tasks
    sample_skus = [("SKU-ALPHA-99", 150), ("SKU-BETA-88", 230), ("SKU-GAMMA-77", 45)]
    for sku, qty in sample_skus:
        cursor.execute(
            "INSERT INTO task_queue (task_type, payload) VALUES (?, ?)",
            ("PROCESS_INVENTORY_WEBHOOK", json.dumps({"sku": sku, "quantity": qty}))
        )

    # Insert mock kiosk check-ins and print jobs
    sample_users = ["EVA LUA TOR-01", "SCHOLAR SHI P-02", "TES TER-03", "C ANDY-04"]
    for user_id in sample_users:
        scan_id = str(uuid.uuid4())[:8]
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
    return redirect(url_for('home'))

# --- BACKEND ENDPOINTS ---
@app.route('/webhooks/inventory', methods=['POST'])
def webhook_inventory():
    data = request.json or {}
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO task_queue (task_type, payload) VALUES (?, ?)", ("PROCESS_INVENTORY_WEBHOOK", json.dumps(data)))
    conn.commit()
    conn.close()
    return jsonify({"status": "ACCEPTED"}), 200

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

@app.route('/kiosk/check-in', methods=['POST'])
def kiosk_checkin():
    data = request.json or {}
    user_id = data.get("user_id")
    scan_id = str(uuid.uuid4())[:8]

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO checkin_scans (scan_id, user_id, status, updated_at) VALUES (?, ?, 'Pending', ?)", (scan_id, user_id, time.time()))
    cursor.execute("INSERT INTO task_queue (task_type, payload) VALUES (?, ?)", ("DISPATCH_PRINT_JOB", json.dumps({"scan_id": scan_id, "user_id": user_id})))
    conn.commit()
    conn.close()
    return jsonify({"status": "Pending", "scan_id": scan_id}), 202

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
            cursor.execute("UPDATE checkin_scans SET status = 'Checked In', updated_at = ? WHERE scan_id = ?", (time.time(), scan_id))
            conn.commit()

    conn.close()
    return jsonify({"status": "ACK"}), 200

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

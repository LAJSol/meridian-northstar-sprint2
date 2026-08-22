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

# Asynchronous Background Worker
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

# --- PAGE 1: SOLSTICE EVENTS CO. PIVOT (HOME PAGE) ---
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
            <title>Solstice Events Co. - Pivot Kiosk</title>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #f8fafc; padding: 25px; margin: 0; }}
                .container {{ max-width: 1000px; margin: auto; }}
                .header-flex {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }}
                h1 {{ color: #38bdf8; margin: 0; }}
                .status {{ color: #34d399; font-weight: bold; }}
                .btn {{ background: #0284c7; color: white; padding: 10px 18px; border: none; border-radius: 6px; font-weight: bold; cursor: pointer; text-decoration: none; display: inline-block; transition: background 0.2s; margin-left: 10px; }}
                .btn:hover {{ background: #0369a1; }}
                .btn-secondary {{ background: #334155; }}
                .btn-secondary:hover {{ background: #475569; }}
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
                        <h1>Solstice Events Co. - Kiosk Service</h1>
                        <div class="status">● Asynchronous Pivot Active[cite: 1]</div>
                    </div>
                    <div>
                        <a href="/generate-test-data" class="btn">⚡ Generate Test Data</a>
                        <a href="/northstar-archive" class="btn btn-secondary">📁 Northstar Archive</a>
                    </div>
                </div>

                <div class="card">
                    <h2>Task Queue Jobs (Async Message Queue)[cite: 1]</h2>
                    <table><thead><tr><th>ID</th><th>Task Type</th><th>Payload</th><th>Status</th></tr></thead><tbody>{task_rows}</tbody></table>
                </div>

                <div class="card">
                    <h2>Local Stock Inventory</h2>
                    <table><thead><tr><th>SKU</th><th>Quantity</th><th>Last Updated</th></tr></thead><tbody>{stock_rows}</tbody></table>
                </div>

                <div class="card">
                    <h2>Kiosk Check-ins (Pending & Duplicate Protection)[cite: 1]</h2>
                    <table><thead><tr><th>Scan ID</th><th>User ID</th><th>Status</th></tr></thead><tbody>{checkin_rows}</tbody></table>
                </div>
            </div>
        </body>
        </html>
        """
    except Exception as e:
        return f"<h2>System Active</h2><p>Database Initializing: {str(e)}</p>"

# --- PAGE 2: NORTHSTAR ARCHIVE (SEPARATE PAGE) ---
@app.route('/northstar-archive')
def northstar_archive():
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>Meridian Northstar Archive</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #f8fafc; padding: 25px; margin: 0; }
            .container { max-width: 800px; margin: auto; background: #1e293b; padding: 30px; border-radius: 8px; border: 1px solid #334155; }
            h1 { color: #38bdf8; margin-top: 0; }
            .badge { background: #334155; color: #94a3b8; padding: 4px 10px; border-radius: 4px; font-size: 0.8rem; font-weight: bold; }
            .btn { background: #0284c7; color: white; padding: 10px 18px; border-radius: 6px; text-decoration: none; font-weight: bold; display: inline-block; margin-top: 20px; }
            .btn:hover { background: #0369a1; }
            p { color: #cbd5e1; line-height: 1.6; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Meridian Northstar (Sprint 2 Archive)</h1>
            <span class="badge">DEPRECATED ARCHIVE</span>
            <p>This page archives the initial synchronous architecture before the Solstice Events Co. pivot event requirements were introduced.</p>
            <p><strong>Status:</strong> Replaced entirely by the asynchronous webhook model on the main dashboard.</p>
            <a href="/" class="btn">← Back to Solstice Pivot Dashboard</a>
        </div>
    </body>
    </html>
    """

# --- PIVOT TEST DATA GENERATOR ---
@app.route('/generate-test-data')
def generate_test_data():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    sample_skus = [("SKU-ALPHA-99", 150), ("SKU-BETA-88", 230), ("SKU-GAMMA-77", 45)]
    for sku, qty in sample_skus:
        cursor.execute(
            "INSERT INTO task_queue (task_type, payload) VALUES (?, ?)",
            ("PROCESS_INVENTORY_WEBHOOK", json.dumps({"sku": sku, "quantity": qty}))
        )

    sample_attendees = ["ATTENDEE-01", "ATTENDEE-02", "ATTENDEE-01"]
    for user_id in sample_attendees:
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

# --- ASYNC API ENDPOINTS & WEBHOOKS ---
@app.route('/webhooks/inventory', methods=['POST'])
def webhook_inventory():
    data = request.json or {}
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO task_queue (task_type, payload) VALUES (?, ?)", ("PROCESS_INVENTORY_WEBHOOK", json.dumps(data)))
    conn.commit()
    conn.close()
    return jsonify({"status": "ACCEPTED"}), 200

@app.route('/kiosk/check-in', methods=['POST'])
def kiosk_checkin():
    data = request.json or {}
    user_id = data.get("user_id")
    scan_id = str(uuid.uuid4())[:8]

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("SELECT status FROM checkin_scans WHERE user_id = ? AND status = 'Checked In'", (user_id,))
    if cursor.fetchone():
        conn.close()
        return jsonify({"error": "Duplicate scan: Attendee already checked in and printed."}), 400

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

if __name__ == '__main__':
    app.run(port=5000)
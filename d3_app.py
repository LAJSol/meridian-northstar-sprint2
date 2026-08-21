import sqlite3
import time
from threading import Thread
import requests
from flask import Flask, jsonify, request

app = Flask(__name__)
DB_FILE = "inventory_cache.db"
WAREHOUSE_URL = "http://127.0.0.1:5001/warehouse/inventory"
PRINTER_URL = "http://127.0.0.1:5001/printer/print"

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
    conn.commit()
    conn.close()

# --- 5-MINUTE POLLING SERVICE ---
def poll_warehouse_api():
    """Polls the warehouse API periodically and updates local DB."""
    while True:
        try:
            print("[Polling Job] Querying warehouse API...")
            response = requests.get(WAREHOUSE_URL, timeout=5)
            if response.status_code == 200:
                stock_data = response.json().get("data", {})
                
                conn = sqlite3.connect(DB_FILE)
                cursor = conn.cursor()
                for sku, qty in stock_data.items():
                    cursor.execute('''
                        INSERT INTO local_stock (sku, quantity, last_updated)
                        VALUES (?, ?, ?)
                        ON CONFLICT(sku) DO UPDATE SET quantity=?, last_updated=?
                    ''', (sku, qty, time.time(), qty, time.time()))
                conn.commit()
                conn.close()
                print("[Polling Job] Local database cache updated successfully.")
        except Exception as e:
            print(f"[Polling Job Error] {e}")
            
        # Polling interval (set to 10 seconds for easy testing; set to 300 for 5 minutes)
        time.sleep(10) 

@app.route('/inventory/<sku>', methods=['GET'])
def get_stock(sku):
    """Query cached inventory levels."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT quantity, last_updated FROM local_stock WHERE sku = ?", (sku,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return jsonify({"sku": sku, "quantity": row[0], "cached_at": row[1]}), 200
    return jsonify({"error": "SKU not found"}), 404

# --- SYNCHRONOUS KIOSK CHECK-IN ---
@app.route('/kiosk/check-in', methods=['POST'])
def kiosk_checkin():
    """Synchronous check-in: Wait for printer confirmation before returning."""
    data = request.json or {}
    user_id = data.get("user_id")

    print(f"[Kiosk] Checking in user: {user_id}. Calling printer API directly...")
    
    try:
        # Blocking HTTP request to printer API
        resp = requests.post(PRINTER_URL, json={"user_id": user_id}, timeout=10)
        
        if resp.status_code == 200:
            return jsonify({"status": "Checked In", "user_id": user_id}), 200
        else:
            return jsonify({"status": "Failed", "reason": "Printer error"}), 500
    except Exception as e:
        return jsonify({"status": "Failed", "reason": str(e)}), 500

if __name__ == '__main__':
    init_db()
    Thread(target=poll_warehouse_api, daemon=True).start()
    app.run(port=5000)
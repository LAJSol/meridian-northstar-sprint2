# The New version of the warehouse.py file has been updated to include new features and improvements. The following changes have been made: 
# 1. Switched from polling to webhooks.
import time
import requests
from flask import Flask, jsonify, request

app = Flask(__name__)
MY_APP_URL = "http://127.0.0.1:5000"

@app.route('/trigger-warehouse-push', methods=['POST'])
def trigger_warehouse_push():
    """Sends a stock update directly to our app's webhook."""
    payload = {
        "sku": "ITEM-101",
        "quantity": 99,
        "timestamp": time.time()
    }
    print(f"[Warehouse] Sending stock update to main app: {payload}")
    
    try:
        requests.post(f"{MY_APP_URL}/webhooks/inventory", json=payload, timeout=5)
        return jsonify({"status": "Stock update sent successfully"}), 200
    except Exception as e:
        return jsonify({"status": "Error", "message": str(e)}), 500

@app.route('/simulate-printer-hardware', methods=['POST'])
def simulate_printer_hardware():
    """Simulates physical badge printing in the background."""
    data = request.json or {}
    scan_id = data.get("scan_id")
    user_id = data.get("user_id")

    print(f"[Printer] Starting print job for scan ID: {scan_id}...")
    time.sleep(3)  # Wait 3 seconds to simulate paper printing
    
    callback_payload = {"scan_id": scan_id, "status": "COMPLETED", "user_id": user_id}
    print(f"[Printer] Done printing. Sending confirmation back to app: {callback_payload}")
    
    try:
        requests.post(f"{MY_APP_URL}/webhooks/print-status", json=callback_payload, timeout=5)
    except Exception as e:
        print(f"[Printer Error] Could not send confirmation: {e}")

    return jsonify({"status": "Print job accepted"}), 200

if __name__ == '__main__':
    app.run(port=5001)
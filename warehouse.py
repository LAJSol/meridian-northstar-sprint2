import time
from flask import Flask, jsonify, request

app = Flask(__name__)

# Simulated Warehouse Database
WAREHOUSE_STOCK = {
    "ITEM-101": 50,
    "ITEM-202": 15,
    "ITEM-303": 0
}

@app.route('/warehouse/inventory', methods=['GET'])
def get_warehouse_inventory():
    """Simulates the external warehouse stock API."""
    return jsonify({"status": "success", "data": WAREHOUSE_STOCK}), 200

@app.route('/printer/print', methods=['POST'])
def print_badge():
    """Simulates direct synchronous badge printing."""
    data = request.json or {}
    user_id = data.get("user_id", "UNKNOWN")
    
    # Artificial delay to simulate printing hardware
    time.sleep(2) 
    
    print(f"[Printer Hardware] Printed badge for User: {user_id}")
    return jsonify({"status": "SUCCESS", "message": f"Badge printed for {user_id}"}), 200

if __name__ == '__main__':
    app.run(port=5001)
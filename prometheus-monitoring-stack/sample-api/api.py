from flask import Flask, request, jsonify
from prometheus_client import Counter, Histogram, Gauge, Summary, generate_latest, CONTENT_TYPE_LATEST
import time
import random
import threading
import sqlite3
import os

app = Flask(__name__)

# Prometheus metrics for API
API_REQUEST_COUNT = Counter('api_requests_total', 'Total API requests', ['method', 'endpoint', 'status'])
API_REQUEST_DURATION = Histogram('api_request_duration_seconds', 'API request duration', ['method', 'endpoint'])
API_REQUEST_SUMMARY = Summary('api_request_processing_seconds', 'Time spent processing API requests')
DATABASE_CONNECTIONS = Gauge('database_connections_active', 'Active database connections')
API_ERRORS = Counter('api_errors_total', 'Total API errors', ['error_type'])
QUEUE_SIZE = Gauge('api_queue_size', 'Number of items in processing queue')

# Simulate a processing queue
processing_queue = []

def background_processor():
    """Background thread to process queue items"""
    while True:
        if processing_queue:
            item = processing_queue.pop(0)
            # Simulate processing time
            time.sleep(random.uniform(0.1, 0.5))
            print(f"Processed item: {item}")
        QUEUE_SIZE.set(len(processing_queue))
        time.sleep(1)

# Start background processor
processor_thread = threading.Thread(target=background_processor, daemon=True)
processor_thread.start()

def get_db_connection():
    """Get database connection and update metrics"""
    DATABASE_CONNECTIONS.inc()
    conn = sqlite3.connect(':memory:')
    return conn

def close_db_connection(conn):
    """Close database connection and update metrics"""
    conn.close()
    DATABASE_CONNECTIONS.dec()

@app.before_request
def before_request():
    request.start_time = time.time()

@app.after_request
def after_request(response):
    request_duration = time.time() - request.start_time
    
    # Record metrics
    API_REQUEST_COUNT.labels(
        method=request.method,
        endpoint=request.endpoint or 'unknown',
        status=response.status_code
    ).inc()
    
    API_REQUEST_DURATION.labels(
        method=request.method,
        endpoint=request.endpoint or 'unknown'
    ).observe(request_duration)
    
    return response

@app.route('/api/v1/health')
def health():
    return jsonify({
        "status": "healthy",
        "timestamp": time.time(),
        "queue_size": len(processing_queue)
    })

@app.route('/api/v1/users', methods=['GET'])
def get_users():
    with API_REQUEST_SUMMARY.time():
        # Simulate database query
        conn = get_db_connection()
        try:
            time.sleep(random.uniform(0.01, 0.05))  # Simulate query time
            users = [
                {"id": i, "name": f"User {i}", "email": f"user{i}@example.com"}
                for i in range(1, random.randint(5, 20))
            ]
            return jsonify({"users": users})
        finally:
            close_db_connection(conn)

@app.route('/api/v1/users', methods=['POST'])
def create_user():
    with API_REQUEST_SUMMARY.time():
        try:
            data = request.get_json()
            if not data or 'name' not in data:
                API_ERRORS.labels(error_type='validation_error').inc()
                return jsonify({"error": "Missing required field: name"}), 400
            
            # Add to processing queue
            processing_queue.append(f"create_user_{data['name']}")
            
            return jsonify({
                "message": "User creation queued",
                "user_data": data,
                "queue_position": len(processing_queue)
            }), 201
            
        except Exception as e:
            API_ERRORS.labels(error_type='server_error').inc()
            return jsonify({"error": str(e)}), 500

@app.route('/api/v1/process')
def heavy_process():
    with API_REQUEST_SUMMARY.time():
        # Simulate heavy processing
        start_time = time.time()
        while time.time() - start_time < random.uniform(0.1, 0.3):
            # CPU intensive task
            _ = sum(i * i for i in range(10000))
        
        return jsonify({"message": "Heavy processing completed"})

@app.route('/api/v1/simulate-error')
def simulate_error():
    error_types = ['timeout', 'connection_error', 'validation_error']
    error_type = random.choice(error_types)
    
    API_ERRORS.labels(error_type=error_type).inc()
    
    if error_type == 'timeout':
        time.sleep(2)  # Simulate timeout
        return jsonify({"error": "Request timeout"}), 408
    elif error_type == 'connection_error':
        return jsonify({"error": "Database connection failed"}), 503
    else:
        return jsonify({"error": "Validation failed"}), 400

@app.route('/metrics')
def metrics():
    return generate_latest(), 200, {'Content-Type': CONTENT_TYPE_LATEST}

if __name__ == '__main__':
    print("Starting SRE Sample API Service...")
    app.run(host='0.0.0.0', port=8081, debug=False)

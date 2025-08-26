from flask import Flask, request, jsonify
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CollectorRegistry, CONTENT_TYPE_LATEST
import time
import random
import threading
import psutil
import os

app = Flask(__name__)

# Prometheus metrics
REQUEST_COUNT = Counter('http_requests_total', 'Total HTTP requests', ['method', 'endpoint', 'status'])
REQUEST_DURATION = Histogram('http_request_duration_seconds', 'HTTP request duration', ['method', 'endpoint'])
ACTIVE_CONNECTIONS = Gauge('active_connections', 'Number of active connections')
CPU_USAGE = Gauge('cpu_usage_percent', 'CPU usage percentage')
MEMORY_USAGE = Gauge('memory_usage_percent', 'Memory usage percentage')

def update_system_metrics():
    """Background thread to update system metrics"""
    while True:
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            memory_percent = psutil.virtual_memory().percent
            
            CPU_USAGE.set(cpu_percent)
            MEMORY_USAGE.set(memory_percent)
        except Exception as e:
            print(f"Error updating system metrics: {e}")
        time.sleep(10)

# Start background metrics collection
metrics_thread = threading.Thread(target=update_system_metrics, daemon=True)
metrics_thread.start()

@app.before_request
def before_request():
    request.start_time = time.time()
    ACTIVE_CONNECTIONS.inc()

@app.after_request
def after_request(response):
    request_duration = time.time() - request.start_time
    
    # Record metrics
    REQUEST_COUNT.labels(
        method=request.method, 
        endpoint=request.endpoint or 'unknown',
        status=response.status_code
    ).inc()
    
    REQUEST_DURATION.labels(
        method=request.method,
        endpoint=request.endpoint or 'unknown'
    ).observe(request_duration)
    
    ACTIVE_CONNECTIONS.dec()
    
    return response

@app.route('/')
def home():
    return jsonify({
        "message": "Welcome to SRE Sample Application",
        "version": "1.0.0",
        "status": "healthy"
    })

@app.route('/health')
def health():
    return jsonify({"status": "healthy", "timestamp": time.time()})

@app.route('/slow')
def slow_endpoint():
    # Simulate slow response
    time.sleep(random.uniform(0.5, 2.0))
    return jsonify({"message": "This is a slow endpoint"})

@app.route('/error')
def error_endpoint():
    # Simulate random errors
    if random.random() < 0.3:  # 30% error rate
        return jsonify({"error": "Random server error"}), 500
    return jsonify({"message": "Success"})

@app.route('/cpu-load')
def cpu_load():
    # Simulate CPU intensive task
    start_time = time.time()
    while time.time() - start_time < 0.1:  # Busy wait for 100ms
        pass
    return jsonify({"message": "CPU intensive task completed"})

@app.route('/metrics')
def metrics():
    return generate_latest(), 200, {'Content-Type': CONTENT_TYPE_LATEST}

if __name__ == '__main__':
    print("Starting SRE Sample Application...")
    app.run(host='0.0.0.0', port=8080, debug=False)

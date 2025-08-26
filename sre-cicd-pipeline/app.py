from flask import Flask, request, jsonify
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
import time
import logging
import os
import sys
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/sre-app.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

app = Flask(__name__)

# Prometheus metrics
REQUEST_COUNT = Counter('http_requests_total', 'Total HTTP requests', ['method', 'endpoint', 'status'])
REQUEST_DURATION = Histogram('http_request_duration_seconds', 'HTTP request duration', ['method', 'endpoint'])
ACTIVE_CONNECTIONS = Gauge('active_connections', 'Number of active connections')
APP_VERSION = Gauge('app_version_info', 'Application version', ['version', 'build_date', 'commit'])

# Application metadata
APP_VERSION.labels(
    version=os.environ.get('APP_VERSION', '1.0.0'),
    build_date=os.environ.get('BUILD_DATE', datetime.now().isoformat()),
    commit=os.environ.get('COMMIT_SHA', 'unknown')
).set(1)

@app.before_request
def before_request():
    request.start_time = time.time()
    ACTIVE_CONNECTIONS.inc()
    
    logger.info(f"Request started: {request.method} {request.path} from {request.remote_addr}")

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
    
    logger.info(f"Request completed: {request.method} {request.path} - {response.status_code} - {request_duration:.3f}s")
    
    return response

@app.route('/')
def home():
    """Main application endpoint"""
    return jsonify({
        "service": "SRE CI/CD Demo Application",
        "version": os.environ.get('APP_VERSION', '1.0.0'),
        "environment": os.environ.get('ENVIRONMENT', 'unknown'),
        "instance_id": os.environ.get('INSTANCE_ID', 'local'),
        "commit": os.environ.get('COMMIT_SHA', 'unknown'),
        "build_date": os.environ.get('BUILD_DATE', 'unknown'),
        "timestamp": datetime.utcnow().isoformat()
    })

@app.route('/health')
def health():
    """Health check endpoint for load balancer"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "checks": {
            "database": "ok",
            "cache": "ok",
            "external_api": "ok"
        }
    })

@app.route('/ready')
def ready():
    """Readiness probe for Kubernetes/container orchestration"""
    return jsonify({
        "status": "ready",
        "timestamp": datetime.utcnow().isoformat()
    })

@app.route('/version')
def version():
    """Version information endpoint"""
    return jsonify({
        "version": os.environ.get('APP_VERSION', '1.0.0'),
        "commit": os.environ.get('COMMIT_SHA', 'unknown'),
        "build_date": os.environ.get('BUILD_DATE', 'unknown'),
        "deployment_time": os.environ.get('DEPLOYMENT_TIME', 'unknown')
    })

@app.route('/api/users', methods=['GET'])
def get_users():
    """Sample API endpoint with database simulation"""
    # Simulate database query time
    time.sleep(0.01)
    
    users = [
        {"id": 1, "name": "Alice Johnson", "email": "alice@example.com"},
        {"id": 2, "name": "Bob Smith", "email": "bob@example.com"},
        {"id": 3, "name": "Carol Davis", "email": "carol@example.com"}
    ]
    
    return jsonify({"users": users, "total": len(users)})

@app.route('/api/load-test')
def load_test():
    """Endpoint for load testing"""
    # Simulate variable processing time
    processing_time = float(request.args.get('delay', '0.1'))
    time.sleep(min(processing_time, 2.0))  # Cap at 2 seconds
    
    return jsonify({
        "message": "Load test completed",
        "processing_time": processing_time,
        "timestamp": datetime.utcnow().isoformat()
    })

@app.route('/api/error-test')
def error_test():
    """Endpoint for testing error scenarios"""
    error_type = request.args.get('type', 'random')
    
    if error_type == '500':
        logger.error("Simulated 500 error")
        return jsonify({"error": "Internal server error"}), 500
    elif error_type == '400':
        return jsonify({"error": "Bad request"}), 400
    elif error_type == '404':
        return jsonify({"error": "Not found"}), 404
    else:
        # Random error (30% chance)
        if time.time() % 10 < 3:
            logger.error("Random error occurred")
            return jsonify({"error": "Random server error"}), 500
        return jsonify({"message": "No error"})

@app.route('/metrics')
def metrics():
    """Prometheus metrics endpoint"""
    return generate_latest(), 200, {'Content-Type': CONTENT_TYPE_LATEST}

@app.errorhandler(404)
def not_found(error):
    logger.warning(f"404 error: {request.path}")
    return jsonify({"error": "Not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"500 error: {error}")
    return jsonify({"error": "Internal server error"}), 500

if __name__ == '__main__':
    logger.info("Starting SRE CI/CD Demo Application...")
    logger.info(f"Version: {os.environ.get('APP_VERSION', '1.0.0')}")
    logger.info(f"Environment: {os.environ.get('ENVIRONMENT', 'unknown')}")
    
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)), debug=False)

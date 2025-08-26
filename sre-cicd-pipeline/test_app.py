import pytest
import json
from app import app

@pytest.fixture
def client():
    """Create a test client for the Flask app"""
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_home_endpoint(client):
    """Test the home endpoint"""
    response = client.get('/')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert 'service' in data
    assert 'version' in data
    assert data['service'] == 'SRE CI/CD Demo Application'

def test_health_endpoint(client):
    """Test the health check endpoint"""
    response = client.get('/health')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['status'] == 'healthy'
    assert 'checks' in data

def test_ready_endpoint(client):
    """Test the readiness probe endpoint"""
    response = client.get('/ready')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['status'] == 'ready'

def test_version_endpoint(client):
    """Test the version endpoint"""
    response = client.get('/version')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert 'version' in data
    assert 'commit' in data

def test_users_api(client):
    """Test the users API endpoint"""
    response = client.get('/api/users')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert 'users' in data
    assert 'total' in data
    assert len(data['users']) > 0

def test_load_test_endpoint(client):
    """Test the load test endpoint"""
    response = client.get('/api/load-test?delay=0.01')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert 'message' in data
    assert 'processing_time' in data

def test_error_test_endpoint(client):
    """Test the error test endpoint"""
    # Test 500 error
    response = client.get('/api/error-test?type=500')
    assert response.status_code == 500
    
    # Test 400 error
    response = client.get('/api/error-test?type=400')
    assert response.status_code == 400
    
    # Test 404 error
    response = client.get('/api/error-test?type=404')
    assert response.status_code == 404

def test_metrics_endpoint(client):
    """Test the Prometheus metrics endpoint"""
    response = client.get('/metrics')
    assert response.status_code == 200
    assert b'http_requests_total' in response.data

def test_404_handler(client):
    """Test 404 error handler"""
    response = client.get('/nonexistent')
    assert response.status_code == 404
    data = json.loads(response.data)
    assert data['error'] == 'Not found'

def test_application_performance(client):
    """Test application performance requirements"""
    import time
    
    start_time = time.time()
    response = client.get('/')
    end_time = time.time()
    
    response_time = (end_time - start_time) * 1000  # Convert to ms
    
    # Assert response time is under 100ms for simple endpoint
    assert response_time < 100, f"Response time {response_time}ms exceeds 100ms threshold"
    assert response.status_code == 200

def test_concurrent_requests(client):
    """Test handling of concurrent requests"""
    import threading
    import time
    
    results = []
    
    def make_request():
        response = client.get('/health')
        results.append(response.status_code)
    
    # Create 10 concurrent threads
    threads = []
    for _ in range(10):
        thread = threading.Thread(target=make_request)
        threads.append(thread)
        thread.start()
    
    # Wait for all threads to complete
    for thread in threads:
        thread.join()
    
    # All requests should succeed
    assert len(results) == 10
    assert all(status == 200 for status in results)

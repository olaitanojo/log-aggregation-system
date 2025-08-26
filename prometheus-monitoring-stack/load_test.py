from locust import HttpUser, task, between
import random

class WebsiteUser(HttpUser):
    wait_time = between(1, 3)
    
    def on_start(self):
        """Setup when user starts"""
        self.client.verify = False
    
    @task(10)
    def visit_homepage(self):
        """Normal homepage visits - high frequency"""
        self.client.get("/")
    
    @task(5)
    def health_check(self):
        """Health check endpoint"""
        self.client.get("/health")
    
    @task(3)
    def slow_endpoint(self):
        """Test slow response times"""
        self.client.get("/slow")
    
    @task(2)
    def error_endpoint(self):
        """Test error handling"""
        self.client.get("/error")
    
    @task(1)
    def cpu_load_endpoint(self):
        """Test CPU intensive operations"""
        self.client.get("/cpu-load")

class APIUser(HttpUser):
    wait_time = between(0.5, 2)
    
    def on_start(self):
        """Setup when user starts"""
        self.client.verify = False
        self.host = "http://localhost:8081"
    
    @task(8)
    def get_users(self):
        """Get users list"""
        self.client.get("/api/v1/users")
    
    @task(3)
    def create_user(self):
        """Create new user"""
        user_data = {
            "name": f"User {random.randint(1, 1000)}",
            "email": f"user{random.randint(1, 1000)}@example.com"
        }
        self.client.post("/api/v1/users", json=user_data)
    
    @task(2)
    def heavy_process(self):
        """Test heavy processing"""
        self.client.get("/api/v1/process")
    
    @task(1)
    def simulate_error(self):
        """Test error scenarios"""
        self.client.get("/api/v1/simulate-error")
    
    @task(5)
    def api_health_check(self):
        """API health check"""
        self.client.get("/api/v1/health")

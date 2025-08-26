.PHONY: up down logs clean test load-test build

# Start the monitoring stack
up:
	docker-compose up -d
	@echo "Monitoring stack is starting..."
	@echo "Grafana: http://localhost:3000 (admin/admin123)"
	@echo "Prometheus: http://localhost:9090"
	@echo "Alertmanager: http://localhost:9093"
	@echo "Sample App: http://localhost:8080"
	@echo "Sample API: http://localhost:8081"

# Stop the monitoring stack
down:
	docker-compose down

# Stop and remove volumes
clean:
	docker-compose down -v
	docker system prune -f

# View logs
logs:
	docker-compose logs -f

# Build all images
build:
	docker-compose build

# Run health checks
test:
	@echo "Running health checks..."
	@curl -f http://localhost:8080/health || echo "Sample app not healthy"
	@curl -f http://localhost:8081/api/v1/health || echo "Sample API not healthy"
	@curl -f http://localhost:9090/-/healthy || echo "Prometheus not healthy"
	@curl -f http://localhost:3000/api/health || echo "Grafana not healthy"

# Generate load for testing
load-test:
	@echo "Starting load test..."
	@echo "Install locust first: pip install locust"
	@echo "Then run: locust -f load_test.py --host=http://localhost:8080"

# Check service status
status:
	docker-compose ps

# Restart a specific service
restart-prometheus:
	docker-compose restart prometheus

restart-grafana:
	docker-compose restart grafana

restart-apps:
	docker-compose restart sample-app sample-api

# View metrics
view-metrics:
	@echo "Application metrics:"
	@curl -s http://localhost:8080/metrics | head -20
	@echo "\nAPI metrics:"
	@curl -s http://localhost:8081/metrics | head -20

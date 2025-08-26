#!/bin/bash

# SRE Infrastructure Bootstrap Script
# This script configures instances with monitoring, logging, and application setup

set -e

# Variables from template
PROJECT_NAME="${project_name}"
ENVIRONMENT="${environment}"

# Update system
yum update -y

# Install required packages
yum install -y \
    docker \
    git \
    htop \
    wget \
    curl \
    jq \
    amazon-cloudwatch-agent

# Start and enable Docker
systemctl start docker
systemctl enable docker
usermod -a -G docker ec2-user

# Install Docker Compose
curl -L "https://github.com/docker/compose/releases/download/v2.20.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

# Install Node Exporter for Prometheus monitoring
useradd --no-create-home --shell /bin/false node_exporter
cd /tmp
wget https://github.com/prometheus/node_exporter/releases/download/v1.6.1/node_exporter-1.6.1.linux-amd64.tar.gz
tar xvf node_exporter-1.6.1.linux-amd64.tar.gz
cp node_exporter-1.6.1.linux-amd64/node_exporter /usr/local/bin/
chown node_exporter:node_exporter /usr/local/bin/node_exporter

# Create Node Exporter systemd service
cat > /etc/systemd/system/node_exporter.service << EOF
[Unit]
Description=Node Exporter
Wants=network-online.target
After=network-online.target

[Service]
User=node_exporter
Group=node_exporter
Type=simple
ExecStart=/usr/local/bin/node_exporter

[Install]
WantedBy=multi-user.target
EOF

# Start Node Exporter
systemctl daemon-reload
systemctl start node_exporter
systemctl enable node_exporter

# Configure CloudWatch Agent
cat > /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json << EOF
{
  "agent": {
    "metrics_collection_interval": 60,
    "run_as_user": "cwagent"
  },
  "logs": {
    "logs_collected": {
      "files": {
        "collect_list": [
          {
            "file_path": "/var/log/messages",
            "log_group_name": "/aws/ec2/${PROJECT_NAME}",
            "log_stream_name": "{instance_id}/messages"
          },
          {
            "file_path": "/var/log/secure",
            "log_group_name": "/aws/ec2/${PROJECT_NAME}",
            "log_stream_name": "{instance_id}/secure"
          }
        ]
      }
    }
  },
  "metrics": {
    "namespace": "CWAgent",
    "metrics_collected": {
      "cpu": {
        "measurement": [
          "cpu_usage_idle",
          "cpu_usage_iowait",
          "cpu_usage_user",
          "cpu_usage_system"
        ],
        "metrics_collection_interval": 60
      },
      "disk": {
        "measurement": [
          "used_percent"
        ],
        "metrics_collection_interval": 60,
        "resources": [
          "*"
        ]
      },
      "diskio": {
        "measurement": [
          "io_time"
        ],
        "metrics_collection_interval": 60,
        "resources": [
          "*"
        ]
      },
      "mem": {
        "measurement": [
          "mem_used_percent"
        ],
        "metrics_collection_interval": 60
      },
      "netstat": {
        "measurement": [
          "tcp_established",
          "tcp_time_wait"
        ],
        "metrics_collection_interval": 60
      },
      "swap": {
        "measurement": [
          "swap_used_percent"
        ],
        "metrics_collection_interval": 60
      }
    }
  }
}
EOF

# Start CloudWatch Agent
systemctl start amazon-cloudwatch-agent
systemctl enable amazon-cloudwatch-agent

# Deploy sample application
mkdir -p /opt/sre-app
cd /opt/sre-app

# Create a simple Python web application with metrics
cat > app.py << 'EOF'
from flask import Flask, jsonify
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
import time
import random
import os

app = Flask(__name__)

# Metrics
request_count = Counter('http_requests_total', 'Total HTTP requests', ['method', 'endpoint', 'status'])
request_duration = Histogram('http_request_duration_seconds', 'HTTP request duration')

@app.before_request
def before_request():
    from flask import request as flask_request
    flask_request.start_time = time.time()

@app.after_request
def after_request(response):
    from flask import request as flask_request
    duration = time.time() - flask_request.start_time
    
    request_count.labels(
        method=flask_request.method,
        endpoint=flask_request.endpoint or 'unknown',
        status=response.status_code
    ).inc()
    
    request_duration.observe(duration)
    return response

@app.route('/')
def home():
    return jsonify({
        "message": "SRE Infrastructure Demo",
        "instance_id": os.environ.get('EC2_INSTANCE_ID', 'unknown'),
        "environment": os.environ.get('ENVIRONMENT', 'unknown')
    })

@app.route('/health')
def health():
    return jsonify({"status": "healthy"})

@app.route('/load')
def load_test():
    # Simulate some processing
    time.sleep(random.uniform(0.1, 0.5))
    return jsonify({"message": "Load test endpoint"})

@app.route('/metrics')
def metrics():
    return generate_latest(), 200, {'Content-Type': CONTENT_TYPE_LATEST}

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
EOF

# Install Python dependencies
pip3 install flask prometheus-client

# Create systemd service for the app
cat > /etc/systemd/system/sre-app.service << EOF
[Unit]
Description=SRE Demo Application
After=network.target

[Service]
Type=simple
User=ec2-user
WorkingDirectory=/opt/sre-app
ExecStart=/usr/bin/python3 /opt/sre-app/app.py
Environment=EC2_INSTANCE_ID=$(curl -s http://169.254.169.254/latest/meta-data/instance-id)
Environment=ENVIRONMENT=${ENVIRONMENT}
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

# Start the application
systemctl daemon-reload
systemctl start sre-app
systemctl enable sre-app

# Configure log rotation
cat > /etc/logrotate.d/sre-app << EOF
/var/log/sre-app.log {
    daily
    missingok
    rotate 7
    compress
    notifempty
    create 644 ec2-user ec2-user
}
EOF

# Create health check script
cat > /usr/local/bin/health-check.sh << 'EOF'
#!/bin/bash
curl -f http://localhost:8080/health > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "$(date): Health check passed" >> /var/log/health-check.log
else
    echo "$(date): Health check failed" >> /var/log/health-check.log
    exit 1
fi
EOF

chmod +x /usr/local/bin/health-check.sh

# Add health check to cron (every minute)
echo "* * * * * /usr/local/bin/health-check.sh" | crontab -

echo "Bootstrap completed successfully" >> /var/log/user-data.log

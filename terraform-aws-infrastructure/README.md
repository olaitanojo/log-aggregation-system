# SRE Infrastructure as Code

## Overview
This project demonstrates production-ready infrastructure provisioning using Terraform, showcasing essential SRE practices for reliable, scalable, and maintainable cloud infrastructure.

## 🎯 SRE Concepts Demonstrated

- **Infrastructure as Code**: Version-controlled, reproducible infrastructure
- **High Availability**: Multi-AZ deployment with auto-scaling
- **Security Best Practices**: Security groups, IAM roles, encrypted storage
- **Observability**: Comprehensive monitoring and logging
- **Disaster Recovery**: Automated backups and recovery procedures
- **Auto Scaling**: Dynamic resource allocation based on demand

## 🏗️ Architecture

### Core Components
- **VPC**: Isolated network environment with public/private subnets
- **Auto Scaling Group**: Dynamic scaling based on CPU utilization
- **Application Load Balancer**: High-availability load distribution
- **RDS Database**: Managed database with backups and monitoring
- **CloudWatch**: Comprehensive monitoring and alerting
- **IAM**: Least-privilege access control

### Network Design
```
Internet Gateway
       |
   Public Subnets (2 AZs)
   [Load Balancer]
       |
   Private Subnets (2 AZs)
   [Auto Scaling Group]
       |
   Database Subnets (2 AZs)
   [RDS MySQL]
```

## 📋 Infrastructure Components

### Networking
- VPC with DNS resolution enabled
- Public subnets for load balancers
- Private subnets for application instances
- NAT Gateways for outbound internet access
- Route tables with proper routing

### Compute
- Auto Scaling Group with 2-10 instances
- Launch Template with user data bootstrapping
- Application Load Balancer with health checks
- CloudWatch alarms for scaling triggers

### Database
- RDS MySQL 8.0 with encryption
- Multi-AZ deployment for high availability
- Automated backups with 7-day retention
- Performance monitoring and alerting

### Security
- Security groups with least-privilege access
- IAM roles with minimal required permissions
- Encrypted storage and secure parameter storage
- SSL/TLS termination at load balancer

### Monitoring
- CloudWatch metrics and alarms
- Custom application metrics via Prometheus
- Log aggregation and analysis
- Health check automation

## 🚀 Quick Start

### Prerequisites
```bash
# Install Terraform
# Install AWS CLI and configure credentials
aws configure

# Generate SSH key pair
ssh-keygen -t rsa -b 4096 -f ssh-keys/id_rsa
```

### Deploy Infrastructure
```bash
# Initialize Terraform
terraform init

# Copy and customize variables
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your settings

# Plan deployment
terraform plan

# Deploy infrastructure
terraform apply

# Get outputs
terraform output
```

### Access Applications
```bash
# Get load balancer DNS name
LOAD_BALANCER_DNS=$(terraform output -raw load_balancer_dns)

# Test application
curl http://$LOAD_BALANCER_DNS/health

# View metrics
curl http://$LOAD_BALANCER_DNS/metrics
```

## 📊 Monitoring and Observability

### CloudWatch Alarms
- **CPU Utilization**: Auto-scaling triggers
- **Database Performance**: CPU, connections, storage
- **Load Balancer Health**: Response times, healthy hosts
- **Application Health**: Custom application metrics

### Metrics Collection
- **System Metrics**: CPU, memory, disk, network via CloudWatch Agent
- **Application Metrics**: Custom business metrics via Prometheus
- **Database Metrics**: RDS performance insights
- **Load Balancer Metrics**: Request rates and response times

### Log Management
- **System Logs**: CloudWatch Logs integration
- **Application Logs**: Centralized log collection
- **Database Logs**: Error logs, slow query logs
- **Access Logs**: Load balancer access logging

## 🔧 Operational Procedures

### Scaling Operations
```bash
# Manual scaling
aws autoscaling set-desired-capacity \
  --auto-scaling-group-name sre-demo-asg \
  --desired-capacity 5

# View current status
aws autoscaling describe-auto-scaling-groups \
  --auto-scaling-group-names sre-demo-asg
```

### Database Operations
```bash
# Create snapshot
aws rds create-db-snapshot \
  --db-snapshot-identifier sre-demo-snapshot-$(date +%Y%m%d) \
  --db-instance-identifier sre-demo-database

# Restore from snapshot
terraform import aws_db_instance.restored snapshot-id
```

### Monitoring Operations
```bash
# Check instance health
aws elbv2 describe-target-health \
  --target-group-arn $(terraform output -raw target_group_arn)

# View CloudWatch metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/ApplicationELB \
  --metric-name TargetResponseTime \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Average
```

## 🔒 Security Considerations

### Production Hardening
1. **Network Security**
   - Restrict SSH access to specific IP ranges
   - Use VPN or bastion host for internal access
   - Enable VPC Flow Logs

2. **Data Protection**
   - Enable RDS encryption at rest
   - Use AWS Secrets Manager for sensitive data
   - Implement backup encryption

3. **Access Control**
   - Implement least-privilege IAM policies
   - Use IAM roles instead of access keys
   - Enable CloudTrail for audit logging

4. **Infrastructure Security**
   - Enable deletion protection on critical resources
   - Use WAF for application-layer protection
   - Implement network ACLs for additional security

## 📈 Cost Optimization

### Resource Optimization
- **Right-sizing**: Monitor and adjust instance types
- **Reserved Instances**: Use for predictable workloads
- **Spot Instances**: Consider for non-critical workloads
- **Storage Optimization**: Use appropriate storage classes

### Monitoring Costs
```bash
# Check current costs
aws ce get-cost-and-usage \
  --time-period Start=2023-01-01,End=2023-02-01 \
  --granularity MONTHLY \
  --metrics UnblendedCost \
  --group-by Type=DIMENSION,Key=SERVICE
```

## 🧪 Testing the Infrastructure

### Load Testing
```bash
# Install artillery for load testing
npm install -g artillery

# Run load test
artillery quick \
  --count 10 \
  --num 100 \
  http://$LOAD_BALANCER_DNS/
```

### Chaos Engineering
```bash
# Terminate random instance to test resilience
INSTANCE_ID=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=sre-demo-asg-instance" \
  --query 'Reservations[0].Instances[0].InstanceId' \
  --output text)

aws ec2 terminate-instances --instance-ids $INSTANCE_ID
```

## 🔄 Disaster Recovery

### Backup Strategy
- **RDS**: Automated daily backups with 7-day retention
- **Infrastructure**: Terraform state in S3 with versioning
- **Application Code**: Git repository with CI/CD pipeline

### Recovery Procedures
1. **Database Recovery**: Restore from automated backup or snapshot
2. **Infrastructure Recovery**: Re-deploy using Terraform
3. **Application Recovery**: Auto Scaling Group replaces failed instances

## 📚 Learning Outcomes

This project demonstrates:
- **Infrastructure Design**: Multi-tier, highly available architecture
- **Security Implementation**: Defense in depth security model
- **Monitoring Strategy**: Comprehensive observability approach
- **Automation**: Infrastructure as Code best practices
- **Scalability**: Auto-scaling and load balancing
- **Reliability**: High availability and disaster recovery

## 🔄 Cleanup

```bash
# Destroy infrastructure
terraform destroy

# Clean up local files
rm -rf .terraform/
rm terraform.tfstate*
```

## 📖 Additional Resources

- [AWS Well-Architected Framework](https://aws.amazon.com/architecture/well-architected/)
- [SRE Best Practices](https://sre.google/sre-book/table-of-contents/)
- [Terraform Best Practices](https://www.terraform.io/docs/cloud/guides/recommended-practices/index.html)

---

*This project showcases infrastructure engineering skills essential for SRE roles, including automation, monitoring, security, and reliability engineering.*

output "vpc_id" {
  description = "ID of the VPC"
  value       = aws_vpc.main.id
}

output "vpc_cidr_block" {
  description = "CIDR block of the VPC"
  value       = aws_vpc.main.cidr_block
}

output "public_subnet_ids" {
  description = "IDs of the public subnets"
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "IDs of the private subnets"
  value       = aws_subnet.private[*].id
}

output "load_balancer_dns" {
  description = "DNS name of the load balancer"
  value       = aws_lb.main.dns_name
}

output "load_balancer_zone_id" {
  description = "Zone ID of the load balancer"
  value       = aws_lb.main.zone_id
}

output "database_endpoint" {
  description = "RDS instance endpoint"
  value       = aws_db_instance.main.endpoint
  sensitive   = true
}

output "database_port" {
  description = "RDS instance port"
  value       = aws_db_instance.main.port
}

output "autoscaling_group_arn" {
  description = "ARN of the Auto Scaling Group"
  value       = aws_autoscaling_group.web_app.arn
}

output "key_pair_name" {
  description = "Name of the AWS key pair"
  value       = aws_key_pair.main.key_name
}

output "security_group_alb_id" {
  description = "ID of the ALB security group"
  value       = aws_security_group.alb.id
}

output "security_group_web_app_id" {
  description = "ID of the web application security group"
  value       = aws_security_group.web_app.id
}

output "security_group_database_id" {
  description = "ID of the database security group"
  value       = aws_security_group.database.id
}

# Useful URLs for accessing services
output "application_url" {
  description = "URL to access the application"
  value       = "http://${aws_lb.main.dns_name}"
}

output "health_check_url" {
  description = "URL for health checks"
  value       = "http://${aws_lb.main.dns_name}/health"
}

output "metrics_url" {
  description = "URL for Prometheus metrics"
  value       = "http://${aws_lb.main.dns_name}/metrics"
}

# Infrastructure summary
output "infrastructure_summary" {
  description = "Summary of deployed infrastructure"
  value = {
    environment     = var.environment
    region         = var.aws_region
    vpc_cidr       = aws_vpc.main.cidr_block
    public_subnets = length(aws_subnet.public)
    private_subnets = length(aws_subnet.private)
    min_instances  = var.min_size
    max_instances  = var.max_size
    desired_instances = var.desired_capacity
    database_engine = aws_db_instance.main.engine
    monitoring_enabled = var.enable_monitoring
    backup_enabled = var.enable_backup
  }
}

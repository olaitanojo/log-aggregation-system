#!/bin/bash

# SRE Rolling Deployment Script
# Implements zero-downtime rolling deployment with health checks

set -euo pipefail

IMAGE_TAG=${1:-latest}
ENVIRONMENT=${2:-production}
MAX_RETRIES=10
HEALTH_CHECK_TIMEOUT=300

echo "🚀 Starting rolling deployment..."
echo "Image: $IMAGE_TAG"
echo "Environment: $ENVIRONMENT"

# Function to check service health
check_health() {
    local endpoint=$1
    local retries=0
    
    while [ $retries -lt $MAX_RETRIES ]; do
        if curl -f -s "$endpoint/health" > /dev/null; then
            echo "✅ Health check passed for $endpoint"
            return 0
        fi
        
        retries=$((retries + 1))
        echo "⏳ Health check attempt $retries/$MAX_RETRIES for $endpoint"
        sleep 10
    done
    
    echo "❌ Health check failed for $endpoint after $MAX_RETRIES attempts"
    return 1
}

# Function to update Auto Scaling Group
update_asg() {
    local image_tag=$1
    
    echo "📝 Updating launch template with new image..."
    
    # Update launch template with new image
    aws ec2 create-launch-template-version \
        --launch-template-name "sre-demo-template" \
        --version-description "Deployment $(date +%Y%m%d-%H%M%S)" \
        --source-version '$Latest' \
        --launch-template-data '{
            "ImageId": "'$(aws ec2 describe-images --owners amazon --filters "Name=name,Values=amzn2-ami-hvm-*" --query "Images | sort_by(@, &CreationDate) | [-1].ImageId" --output text)'",
            "UserData": "'$(base64 -w 0 user_data_updated.sh)'"
        }'
    
    # Set the new version as default
    aws ec2 modify-launch-template \
        --launch-template-name "sre-demo-template" \
        --default-version '$Latest'
    
    echo "🔄 Starting instance refresh..."
    
    # Start instance refresh
    aws autoscaling start-instance-refresh \
        --auto-scaling-group-name "sre-demo-asg" \
        --preferences '{
            "InstanceWarmup": 300,
            "MinHealthyPercentage": 50,
            "CheckpointPercentages": [20, 50, 100],
            "CheckpointDelay": 600
        }'
}

# Function to monitor deployment progress
monitor_deployment() {
    echo "📊 Monitoring deployment progress..."
    
    local start_time=$(date +%s)
    local timeout=$HEALTH_CHECK_TIMEOUT
    
    while true; do
        local current_time=$(date +%s)
        local elapsed=$((current_time - start_time))
        
        if [ $elapsed -gt $timeout ]; then
            echo "⏰ Deployment timeout reached"
            return 1
        fi
        
        # Check instance refresh status
        local status=$(aws autoscaling describe-instance-refreshes \
            --auto-scaling-group-name "sre-demo-asg" \
            --query 'InstanceRefreshes[0].Status' \
            --output text)
        
        echo "Instance refresh status: $status"
        
        case $status in
            "Successful")
                echo "✅ Rolling deployment completed successfully"
                return 0
                ;;
            "Failed"|"Cancelled")
                echo "❌ Rolling deployment failed"
                return 1
                ;;
            "InProgress"|"Pending")
                echo "⏳ Deployment in progress..."
                sleep 30
                ;;
            *)
                echo "🤔 Unknown status: $status"
                sleep 30
                ;;
        esac
    done
}

# Function to validate deployment
validate_deployment() {
    echo "🔍 Validating deployment..."
    
    # Get load balancer DNS
    local lb_dns=$(aws elbv2 describe-load-balancers \
        --names "sre-demo-alb" \
        --query 'LoadBalancers[0].DNSName' \
        --output text)
    
    # Check application health
    if ! check_health "http://$lb_dns"; then
        echo "❌ Application health check failed"
        return 1
    fi
    
    # Check metrics endpoint
    if curl -f -s "http://$lb_dns/metrics" > /dev/null; then
        echo "✅ Metrics endpoint is healthy"
    else
        echo "⚠️  Metrics endpoint check failed"
    fi
    
    # Check all target group health
    local healthy_targets=$(aws elbv2 describe-target-health \
        --target-group-arn "$(aws elbv2 describe-target-groups --names sre-demo-web-tg --query 'TargetGroups[0].TargetGroupArn' --output text)" \
        --query 'length(TargetHealthDescriptions[?TargetHealth.State == `healthy`])' \
        --output text)
    
    echo "Healthy targets: $healthy_targets"
    
    if [ "$healthy_targets" -ge 2 ]; then
        echo "✅ Sufficient healthy targets available"
        return 0
    else
        echo "❌ Insufficient healthy targets"
        return 1
    fi
}

# Function to send deployment metrics
send_metrics() {
    local deployment_result=$1
    local deployment_duration=$2
    
    echo "📈 Sending deployment metrics..."
    
    # Send custom metrics to CloudWatch
    aws cloudwatch put-metric-data \
        --namespace "SRE/Deployments" \
        --metric-data \
            MetricName=DeploymentDuration,Value=$deployment_duration,Unit=Seconds \
            MetricName=DeploymentSuccess,Value=$([[ $deployment_result == "success" ]] && echo 1 || echo 0),Unit=Count
}

# Main deployment execution
main() {
    local start_time=$(date +%s)
    local deployment_result="failure"
    
    echo "🎬 Starting rolling deployment process..."
    
    # Pre-deployment checks
    echo "🔍 Running pre-deployment checks..."
    if ! aws sts get-caller-identity > /dev/null; then
        echo "❌ AWS credentials not configured"
        exit 1
    fi
    
    # Update ASG with new image
    if update_asg "$IMAGE_TAG"; then
        echo "✅ Auto Scaling Group update initiated"
    else
        echo "❌ Failed to update Auto Scaling Group"
        exit 1
    fi
    
    # Monitor deployment
    if monitor_deployment; then
        echo "✅ Deployment monitoring completed"
    else
        echo "❌ Deployment monitoring failed"
        exit 1
    fi
    
    # Validate deployment
    if validate_deployment; then
        echo "✅ Deployment validation passed"
        deployment_result="success"
    else
        echo "❌ Deployment validation failed"
        exit 1
    fi
    
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    # Send metrics
    send_metrics "$deployment_result" "$duration"
    
    echo "🎉 Rolling deployment completed successfully in ${duration} seconds"
}

# Execute main function
main "$@"

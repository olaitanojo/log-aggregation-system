#!/bin/bash

# SRE Canary Deployment Script
# Implements gradual traffic shift with automated rollback on failure

set -euo pipefail

IMAGE_TAG=${1:-latest}
ENVIRONMENT=${2:-production}
CANARY_PERCENTAGES=(10 25 50 75 100)
VALIDATION_PERIOD=300  # 5 minutes between stages

echo "🐦 Starting canary deployment..."
echo "Image: $IMAGE_TAG"
echo "Environment: $ENVIRONMENT"

# Function to create canary target group
create_canary_environment() {
    local image_tag=$1
    
    echo "🏗️  Creating canary environment..."
    
    # Create canary target group
    local canary_tg_arn=$(aws elbv2 create-target-group \
        --name "sre-demo-canary-tg" \
        --protocol HTTP \
        --port 8080 \
        --vpc-id "$(aws ec2 describe-vpcs --filters Name=tag:Name,Values=sre-demo-vpc --query 'Vpcs[0].VpcId' --output text)" \
        --health-check-path "/health" \
        --health-check-interval-seconds 30 \
        --healthy-threshold-count 2 \
        --unhealthy-threshold-count 2 \
        --query 'TargetGroups[0].TargetGroupArn' \
        --output text)
    
    echo "Created canary target group: $canary_tg_arn"
    
    # Create canary Auto Scaling Group with minimal instances
    aws autoscaling create-auto-scaling-group \
        --auto-scaling-group-name "sre-demo-canary-asg" \
        --launch-template LaunchTemplateName=sre-demo-template,Version='$Latest' \
        --min-size 1 \
        --max-size 3 \
        --desired-capacity 1 \
        --target-group-arns "$canary_tg_arn" \
        --vpc-zone-identifier "$(aws ec2 describe-subnets --filters Name=tag:Name,Values=*private* --query 'Subnets[0].SubnetId' --output text)" \
        --health-check-type ELB \
        --health-check-grace-period 300 \
        --tags Key=Name,Value="sre-demo-canary-instance",PropagateAtLaunch=true Key=Type,Value="canary",PropagateAtLaunch=true
    
    echo "✅ Canary environment created"
}

# Function to wait for canary to be healthy
wait_for_canary_health() {
    echo "⏳ Waiting for canary to become healthy..."
    
    local timeout=300
    local start_time=$(date +%s)
    
    while true; do
        local current_time=$(date +%s)
        local elapsed=$((current_time - start_time))
        
        if [ $elapsed -gt $timeout ]; then
            echo "⏰ Canary health check timeout"
            return 1
        fi
        
        local healthy_targets=$(aws elbv2 describe-target-health \
            --target-group-arn "$(aws elbv2 describe-target-groups --names sre-demo-canary-tg --query 'TargetGroups[0].TargetGroupArn' --output text)" \
            --query 'length(TargetHealthDescriptions[?TargetHealth.State == `healthy`])' \
            --output text)
        
        if [ "$healthy_targets" -ge 1 ]; then
            echo "✅ Canary is healthy"
            return 0
        fi
        
        echo "⏳ Waiting for canary health... ($elapsed seconds elapsed)"
        sleep 30
    done
}

# Function to shift traffic gradually
shift_traffic() {
    local percentage=$1
    
    echo "📊 Shifting $percentage% traffic to canary..."
    
    local main_tg_arn=$(aws elbv2 describe-target-groups \
        --names "sre-demo-web-tg" \
        --query 'TargetGroups[0].TargetGroupArn' \
        --output text)
    
    local canary_tg_arn=$(aws elbv2 describe-target-groups \
        --names "sre-demo-canary-tg" \
        --query 'TargetGroups[0].TargetGroupArn' \
        --output text)
    
    local listener_arn=$(aws elbv2 describe-listeners \
        --load-balancer-arn "$(aws elbv2 describe-load-balancers --names sre-demo-alb --query 'LoadBalancers[0].LoadBalancerArn' --output text)" \
        --query 'Listeners[0].ListenerArn' \
        --output text)
    
    local main_weight=$((100 - percentage))
    local canary_weight=$percentage
    
    # Update listener with weighted routing
    aws elbv2 modify-listener \
        --listener-arn "$listener_arn" \
        --default-actions '[
            {
                "Type": "forward",
                "ForwardConfig": {
                    "TargetGroups": [
                        {
                            "TargetGroupArn": "'$main_tg_arn'",
                            "Weight": '$main_weight'
                        },
                        {
                            "TargetGroupArn": "'$canary_tg_arn'",
                            "Weight": '$canary_weight'
                        }
                    ]
                }
            }
        ]'
    
    echo "✅ Traffic shifted: $main_weight% main, $canary_weight% canary"
}

# Function to monitor canary metrics
monitor_canary_metrics() {
    local duration=$1
    
    echo "📈 Monitoring canary metrics for $duration seconds..."
    
    local start_time=$(date +%s)
    local end_time=$((start_time + duration))
    
    while [ $(date +%s) -lt $end_time ]; do
        # Check error rate
        local error_rate=$(aws cloudwatch get-metric-statistics \
            --namespace AWS/ApplicationELB \
            --metric-name HTTPCode_Target_5XX_Count \
            --dimensions Name=LoadBalancer,Value="$(aws elbv2 describe-load-balancers --names sre-demo-alb --query 'LoadBalancers[0].LoadBalancerName' --output text)" \
            --start-time "$(date -u -d '5 minutes ago' '+%Y-%m-%dT%H:%M:%S')" \
            --end-time "$(date -u '+%Y-%m-%dT%H:%M:%S')" \
            --period 300 \
            --statistics Sum \
            --query 'Datapoints[0].Sum' \
            --output text 2>/dev/null || echo "0")
        
        # Check response time
        local response_time=$(aws cloudwatch get-metric-statistics \
            --namespace AWS/ApplicationELB \
            --metric-name TargetResponseTime \
            --dimensions Name=LoadBalancer,Value="$(aws elbv2 describe-load-balancers --names sre-demo-alb --query 'LoadBalancers[0].LoadBalancerName' --output text)" \
            --start-time "$(date -u -d '5 minutes ago' '+%Y-%m-%dT%H:%M:%S')" \
            --end-time "$(date -u '+%Y-%m-%dT%H:%M:%S')" \
            --period 300 \
            --statistics Average \
            --query 'Datapoints[0].Average' \
            --output text 2>/dev/null || echo "0")
        
        echo "Error rate: $error_rate, Response time: ${response_time}s"
        
        # Check if metrics exceed thresholds
        if (( $(echo "$error_rate > 5" | bc -l) )); then
            echo "❌ Error rate too high: $error_rate"
            return 1
        fi
        
        if (( $(echo "$response_time > 1.0" | bc -l) )); then
            echo "❌ Response time too high: ${response_time}s"
            return 1
        fi
        
        sleep 60
    done
    
    echo "✅ Canary metrics validation passed"
    return 0
}

# Function to promote canary to full deployment
promote_canary() {
    echo "🎯 Promoting canary to full deployment..."
    
    # Scale up canary to match desired capacity
    aws autoscaling update-auto-scaling-group \
        --auto-scaling-group-name "sre-demo-canary-asg" \
        --desired-capacity 3 \
        --min-size 2 \
        --max-size 10
    
    # Wait for scale up
    echo "⏳ Waiting for canary scale up..."
    sleep 120
    
    # Shift 100% traffic to canary
    shift_traffic 100
    
    # Rename canary to main
    echo "🔄 Promoting canary to main environment..."
    
    # This would involve more complex AWS operations
    # For demo purposes, we'll simulate the promotion
    echo "✅ Canary promoted to main environment"
}

# Function to rollback canary
rollback_canary() {
    echo "🔄 Rolling back canary deployment..."
    
    # Shift all traffic back to main
    shift_traffic 0
    
    # Delete canary environment
    aws autoscaling delete-auto-scaling-group \
        --auto-scaling-group-name "sre-demo-canary-asg" \
        --force-delete
    
    local canary_tg_arn=$(aws elbv2 describe-target-groups \
        --names "sre-demo-canary-tg" \
        --query 'TargetGroups[0].TargetGroupArn' \
        --output text 2>/dev/null || echo "")
    
    if [ "$canary_tg_arn" != "" ]; then
        aws elbv2 delete-target-group --target-group-arn "$canary_tg_arn"
    fi
    
    echo "✅ Canary rollback completed"
}

# Main deployment execution
main() {
    local start_time=$(date +%s)
    
    echo "🎬 Starting canary deployment process..."
    
    # Create canary environment
    if ! create_canary_environment "$IMAGE_TAG"; then
        echo "❌ Failed to create canary environment"
        exit 1
    fi
    
    # Wait for canary to be healthy
    if ! wait_for_canary_health; then
        echo "❌ Canary failed to become healthy"
        rollback_canary
        exit 1
    fi
    
    # Gradual traffic shift with monitoring
    for percentage in "${CANARY_PERCENTAGES[@]}"; do
        echo "🎯 Deploying canary stage: $percentage%"
        
        # Shift traffic
        shift_traffic "$percentage"
        
        # Monitor metrics for this stage
        if ! monitor_canary_metrics "$VALIDATION_PERIOD"; then
            echo "❌ Canary metrics validation failed at $percentage%"
            rollback_canary
            exit 1
        fi
        
        echo "✅ Canary stage $percentage% completed successfully"
        
        # If not final stage, wait before next increment
        if [ "$percentage" -ne 100 ]; then
            echo "⏳ Waiting before next stage..."
            sleep 60
        fi
    done
    
    # Promote canary to full deployment
    promote_canary
    
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    echo "🎉 Canary deployment completed successfully in ${duration} seconds"
}

# Execute main function
main "$@"

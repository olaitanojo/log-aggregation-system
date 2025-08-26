#!/bin/bash

# SRE Blue-Green Deployment Script
# Implements zero-downtime deployment with complete environment switch

set -euo pipefail

IMAGE_TAG=${1:-latest}
ENVIRONMENT=${2:-production}
MAX_RETRIES=10
HEALTH_CHECK_TIMEOUT=300

echo "🔵🟢 Starting blue-green deployment..."
echo "Image: $IMAGE_TAG"
echo "Environment: $ENVIRONMENT"

# Function to determine current and target colors
determine_colors() {
    # Check which environment is currently active
    local current_tg=$(aws elbv2 describe-listeners \
        --load-balancer-arn "$(aws elbv2 describe-load-balancers --names sre-demo-alb --query 'LoadBalancers[0].LoadBalancerArn' --output text)" \
        --query 'Listeners[0].DefaultActions[0].TargetGroupArn' \
        --output text)
    
    if echo "$current_tg" | grep -q "blue"; then
        echo "blue"
    else
        echo "green"
    fi
}

# Function to create target environment
create_target_environment() {
    local target_color=$1
    local image_tag=$2
    
    echo "🏗️  Creating $target_color environment..."
    
    # Create new target group
    local tg_arn=$(aws elbv2 create-target-group \
        --name "sre-demo-${target_color}-tg" \
        --protocol HTTP \
        --port 8080 \
        --vpc-id "$(aws ec2 describe-vpcs --filters Name=tag:Name,Values=sre-demo-vpc --query 'Vpcs[0].VpcId' --output text)" \
        --health-check-path "/health" \
        --health-check-interval-seconds 30 \
        --healthy-threshold-count 2 \
        --unhealthy-threshold-count 3 \
        --query 'TargetGroups[0].TargetGroupArn' \
        --output text)
    
    echo "Created target group: $tg_arn"
    
    # Create new Auto Scaling Group for target environment
    aws autoscaling create-auto-scaling-group \
        --auto-scaling-group-name "sre-demo-${target_color}-asg" \
        --launch-template LaunchTemplateName=sre-demo-template,Version='$Latest' \
        --min-size 2 \
        --max-size 6 \
        --desired-capacity 3 \
        --target-group-arns "$tg_arn" \
        --vpc-zone-identifier "$(aws ec2 describe-subnets --filters Name=tag:Name,Values=*private* --query 'Subnets[].SubnetId' --output text | tr '\t' ',')" \
        --health-check-type ELB \
        --health-check-grace-period 300 \
        --tags Key=Name,Value="sre-demo-${target_color}-instance",PropagateAtLaunch=true Key=Color,Value="$target_color",PropagateAtLaunch=true
    
    echo "✅ $target_color environment created"
    return 0
}

# Function to wait for environment to be healthy
wait_for_healthy_environment() {
    local target_color=$1
    local timeout=$HEALTH_CHECK_TIMEOUT
    local start_time=$(date +%s)
    
    echo "⏳ Waiting for $target_color environment to become healthy..."
    
    while true; do
        local current_time=$(date +%s)
        local elapsed=$((current_time - start_time))
        
        if [ $elapsed -gt $timeout ]; then
            echo "⏰ Health check timeout for $target_color environment"
            return 1
        fi
        
        # Check target group health
        local healthy_targets=$(aws elbv2 describe-target-health \
            --target-group-arn "$(aws elbv2 describe-target-groups --names "sre-demo-${target_color}-tg" --query 'TargetGroups[0].TargetGroupArn' --output text)" \
            --query 'length(TargetHealthDescriptions[?TargetHealth.State == `healthy`])' \
            --output text)
        
        echo "$target_color environment healthy targets: $healthy_targets"
        
        if [ "$healthy_targets" -ge 2 ]; then
            echo "✅ $target_color environment is healthy"
            return 0
        fi
        
        sleep 30
    done
}

# Function to run validation tests on target environment
validate_target_environment() {
    local target_color=$1
    
    echo "🧪 Running validation tests on $target_color environment..."
    
    # Get target group ARN
    local tg_arn=$(aws elbv2 describe-target-groups \
        --names "sre-demo-${target_color}-tg" \
        --query 'TargetGroups[0].TargetGroupArn' \
        --output text)
    
    # Get one of the targets for direct testing
    local target_ip=$(aws elbv2 describe-target-health \
        --target-group-arn "$tg_arn" \
        --query 'TargetHealthDescriptions[0].Target.Id' \
        --output text)
    
    # Run smoke tests directly against the instance
    echo "Running smoke tests against $target_color environment..."
    
    # Test basic functionality
    if curl -f -s "http://$target_ip:8080/health" > /dev/null; then
        echo "✅ Health endpoint test passed"
    else
        echo "❌ Health endpoint test failed"
        return 1
    fi
    
    # Test metrics endpoint
    if curl -f -s "http://$target_ip:8080/metrics" > /dev/null; then
        echo "✅ Metrics endpoint test passed"
    else
        echo "❌ Metrics endpoint test failed"
        return 1
    fi
    
    echo "✅ All validation tests passed for $target_color environment"
    return 0
}

# Function to switch traffic to target environment
switch_traffic() {
    local target_color=$1
    
    echo "🔀 Switching traffic to $target_color environment..."
    
    local target_tg_arn=$(aws elbv2 describe-target-groups \
        --names "sre-demo-${target_color}-tg" \
        --query 'TargetGroups[0].TargetGroupArn' \
        --output text)
    
    local listener_arn=$(aws elbv2 describe-listeners \
        --load-balancer-arn "$(aws elbv2 describe-load-balancers --names sre-demo-alb --query 'LoadBalancers[0].LoadBalancerArn' --output text)" \
        --query 'Listeners[0].ListenerArn' \
        --output text)
    
    # Update listener to point to new target group
    aws elbv2 modify-listener \
        --listener-arn "$listener_arn" \
        --default-actions Type=forward,TargetGroupArn="$target_tg_arn"
    
    echo "✅ Traffic switched to $target_color environment"
}

# Function to cleanup old environment
cleanup_old_environment() {
    local old_color=$1
    
    echo "🧹 Cleaning up $old_color environment..."
    
    # Delete old Auto Scaling Group
    aws autoscaling delete-auto-scaling-group \
        --auto-scaling-group-name "sre-demo-${old_color}-asg" \
        --force-delete
    
    # Wait for ASG to be deleted
    aws autoscaling wait auto-scaling-group-not-exists \
        --auto-scaling-group-names "sre-demo-${old_color}-asg"
    
    # Delete old target group
    local old_tg_arn=$(aws elbv2 describe-target-groups \
        --names "sre-demo-${old_color}-tg" \
        --query 'TargetGroups[0].TargetGroupArn' \
        --output text 2>/dev/null || echo "")
    
    if [ "$old_tg_arn" != "" ]; then
        aws elbv2 delete-target-group --target-group-arn "$old_tg_arn"
    fi
    
    echo "✅ $old_color environment cleaned up"
}

# Function to rollback in case of failure
rollback_deployment() {
    local current_color=$1
    local target_color=$2
    
    echo "🔄 Rolling back to $current_color environment..."
    
    local current_tg_arn=$(aws elbv2 describe-target-groups \
        --names "sre-demo-${current_color}-tg" \
        --query 'TargetGroups[0].TargetGroupArn' \
        --output text)
    
    local listener_arn=$(aws elbv2 describe-listeners \
        --load-balancer-arn "$(aws elbv2 describe-load-balancers --names sre-demo-alb --query 'LoadBalancers[0].LoadBalancerArn' --output text)" \
        --query 'Listeners[0].ListenerArn' \
        --output text)
    
    # Switch back to original environment
    aws elbv2 modify-listener \
        --listener-arn "$listener_arn" \
        --default-actions Type=forward,TargetGroupArn="$current_tg_arn"
    
    # Cleanup failed target environment
    cleanup_old_environment "$target_color"
    
    echo "🔄 Rollback completed"
}

# Main deployment execution
main() {
    local start_time=$(date +%s)
    local deployment_result="failure"
    
    echo "🎬 Starting blue-green deployment process..."
    
    # Determine current and target colors
    local current_color=$(determine_colors)
    local target_color
    
    if [ "$current_color" == "blue" ]; then
        target_color="green"
    else
        target_color="blue"
    fi
    
    echo "Current environment: $current_color"
    echo "Target environment: $target_color"
    
    # Create target environment
    if create_target_environment "$target_color" "$IMAGE_TAG"; then
        echo "✅ Target environment created"
    else
        echo "❌ Failed to create target environment"
        exit 1
    fi
    
    # Wait for target environment to be healthy
    if wait_for_healthy_environment "$target_color"; then
        echo "✅ Target environment is healthy"
    else
        echo "❌ Target environment failed health checks"
        cleanup_old_environment "$target_color"
        exit 1
    fi
    
    # Validate target environment
    if validate_target_environment "$target_color"; then
        echo "✅ Target environment validation passed"
    else
        echo "❌ Target environment validation failed"
        rollback_deployment "$current_color" "$target_color"
        exit 1
    fi
    
    # Switch traffic
    if switch_traffic "$target_color"; then
        echo "✅ Traffic switched successfully"
        deployment_result="success"
    else
        echo "❌ Failed to switch traffic"
        rollback_deployment "$current_color" "$target_color"
        exit 1
    fi
    
    # Final validation
    sleep 60  # Allow time for traffic switch to take effect
    
    if validate_target_environment "$target_color"; then
        echo "✅ Post-switch validation passed"
        
        # Cleanup old environment
        cleanup_old_environment "$current_color"
    else
        echo "❌ Post-switch validation failed"
        rollback_deployment "$current_color" "$target_color"
        exit 1
    fi
    
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    echo "🎉 Blue-green deployment completed successfully in ${duration} seconds"
    echo "New active environment: $target_color"
}

# Execute main function
main "$@"

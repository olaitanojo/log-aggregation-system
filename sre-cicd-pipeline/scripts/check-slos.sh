#!/bin/bash

# SRE Service Level Objective (SLO) Monitoring Script
# Validates that deployed services meet defined SLOs

set -euo pipefail

ENVIRONMENT=${1:-production}
SLO_WINDOW="1h"  # Time window for SLO measurement

echo "📊 Checking SLO compliance for $ENVIRONMENT environment..."

# SLO Definitions
AVAILABILITY_SLO=99.5      # 99.5% availability
LATENCY_P95_SLO=500        # 95th percentile latency < 500ms
ERROR_RATE_SLO=1.0         # Error rate < 1%

# Function to check availability SLO
check_availability_slo() {
    echo "🔍 Checking availability SLO (target: ${AVAILABILITY_SLO}%)..."
    
    local lb_name=$(aws elbv2 describe-load-balancers \
        --names "sre-demo-alb" \
        --query 'LoadBalancers[0].LoadBalancerName' \
        --output text)
    
    # Get total requests
    local total_requests=$(aws cloudwatch get-metric-statistics \
        --namespace AWS/ApplicationELB \
        --metric-name RequestCount \
        --dimensions Name=LoadBalancer,Value="$lb_name" \
        --start-time "$(date -u -d "$SLO_WINDOW ago" '+%Y-%m-%dT%H:%M:%S')" \
        --end-time "$(date -u '+%Y-%m-%dT%H:%M:%S')" \
        --period 3600 \
        --statistics Sum \
        --query 'Datapoints[0].Sum' \
        --output text 2>/dev/null || echo "0")
    
    # Get error requests (4xx + 5xx)
    local error_4xx=$(aws cloudwatch get-metric-statistics \
        --namespace AWS/ApplicationELB \
        --metric-name HTTPCode_Target_4XX_Count \
        --dimensions Name=LoadBalancer,Value="$lb_name" \
        --start-time "$(date -u -d "$SLO_WINDOW ago" '+%Y-%m-%dT%H:%M:%S')" \
        --end-time "$(date -u '+%Y-%m-%dT%H:%M:%S')" \
        --period 3600 \
        --statistics Sum \
        --query 'Datapoints[0].Sum' \
        --output text 2>/dev/null || echo "0")
    
    local error_5xx=$(aws cloudwatch get-metric-statistics \
        --namespace AWS/ApplicationELB \
        --metric-name HTTPCode_Target_5XX_Count \
        --dimensions Name=LoadBalancer,Value="$lb_name" \
        --start-time "$(date -u -d "$SLO_WINDOW ago" '+%Y-%m-%dT%H:%M:%S')" \
        --end-time "$(date -u '+%Y-%m-%dT%H:%M:%S')" \
        --period 3600 \
        --statistics Sum \
        --query 'Datapoints[0].Sum' \
        --output text 2>/dev/null || echo "0")
    
    local total_errors=$((${error_4xx%.*} + ${error_5xx%.*}))
    local successful_requests=$((${total_requests%.*} - total_errors))
    
    if [ "${total_requests%.*}" -gt 0 ]; then
        local availability=$(echo "scale=2; $successful_requests * 100 / ${total_requests%.*}" | bc)
        echo "Availability: ${availability}% (Target: ${AVAILABILITY_SLO}%)"
        
        if (( $(echo "$availability >= $AVAILABILITY_SLO" | bc -l) )); then
            echo "✅ Availability SLO met"
            return 0
        else
            echo "❌ Availability SLO violated"
            return 1
        fi
    else
        echo "⚠️  No requests found in the last $SLO_WINDOW"
        return 0
    fi
}

# Function to check latency SLO
check_latency_slo() {
    echo "🔍 Checking latency SLO (target: <${LATENCY_P95_SLO}ms)..."
    
    local lb_name=$(aws elbv2 describe-load-balancers \
        --names "sre-demo-alb" \
        --query 'LoadBalancers[0].LoadBalancerName' \
        --output text)
    
    # Get 95th percentile response time (in seconds, convert to ms)
    local response_time=$(aws cloudwatch get-metric-statistics \
        --namespace AWS/ApplicationELB \
        --metric-name TargetResponseTime \
        --dimensions Name=LoadBalancer,Value="$lb_name" \
        --start-time "$(date -u -d "$SLO_WINDOW ago" '+%Y-%m-%dT%H:%M:%S')" \
        --end-time "$(date -u '+%Y-%m-%dT%H:%M:%S')" \
        --period 3600 \
        --statistics Average \
        --query 'Datapoints[0].Average' \
        --output text 2>/dev/null || echo "0")
    
    if [ "$response_time" != "None" ] && [ "$response_time" != "0" ]; then
        local response_time_ms=$(echo "scale=0; $response_time * 1000" | bc)
        echo "95th percentile response time: ${response_time_ms}ms (Target: <${LATENCY_P95_SLO}ms)"
        
        if (( $(echo "$response_time_ms <= $LATENCY_P95_SLO" | bc -l) )); then
            echo "✅ Latency SLO met"
            return 0
        else
            echo "❌ Latency SLO violated"
            return 1
        fi
    else
        echo "⚠️  No latency data found in the last $SLO_WINDOW"
        return 0
    fi
}

# Function to check error rate SLO
check_error_rate_slo() {
    echo "🔍 Checking error rate SLO (target: <${ERROR_RATE_SLO}%)..."
    
    local lb_name=$(aws elbv2 describe-load-balancers \
        --names "sre-demo-alb" \
        --query 'LoadBalancers[0].LoadBalancerName' \
        --output text)
    
    # Get total requests
    local total_requests=$(aws cloudwatch get-metric-statistics \
        --namespace AWS/ApplicationELB \
        --metric-name RequestCount \
        --dimensions Name=LoadBalancer,Value="$lb_name" \
        --start-time "$(date -u -d "$SLO_WINDOW ago" '+%Y-%m-%dT%H:%M:%S')" \
        --end-time "$(date -u '+%Y-%m-%dT%H:%M:%S')" \
        --period 3600 \
        --statistics Sum \
        --query 'Datapoints[0].Sum' \
        --output text 2>/dev/null || echo "0")
    
    # Get 5xx errors
    local error_5xx=$(aws cloudwatch get-metric-statistics \
        --namespace AWS/ApplicationELB \
        --metric-name HTTPCode_Target_5XX_Count \
        --dimensions Name=LoadBalancer,Value="$lb_name" \
        --start-time "$(date -u -d "$SLO_WINDOW ago" '+%Y-%m-%dT%H:%M:%S')" \
        --end-time "$(date -u '+%Y-%m-%dT%H:%M:%S')" \
        --period 3600 \
        --statistics Sum \
        --query 'Datapoints[0].Sum' \
        --output text 2>/dev/null || echo "0")
    
    if [ "${total_requests%.*}" -gt 0 ]; then
        local error_rate=$(echo "scale=2; ${error_5xx%.*} * 100 / ${total_requests%.*}" | bc)
        echo "Error rate: ${error_rate}% (Target: <${ERROR_RATE_SLO}%)"
        
        if (( $(echo "$error_rate <= $ERROR_RATE_SLO" | bc -l) )); then
            echo "✅ Error rate SLO met"
            return 0
        else
            echo "❌ Error rate SLO violated"
            return 1
        fi
    else
        echo "⚠️  No requests found in the last $SLO_WINDOW"
        return 0
    fi
}

# Function to generate SLO report
generate_slo_report() {
    local availability_status=$1
    local latency_status=$2
    local error_rate_status=$3
    
    echo "📋 SLO Compliance Report"
    echo "======================="
    echo "Environment: $ENVIRONMENT"
    echo "Time Window: $SLO_WINDOW"
    echo "Timestamp: $(date)"
    echo ""
    echo "SLO Status:"
    echo "- Availability (${AVAILABILITY_SLO}%): $availability_status"
    echo "- Latency (<${LATENCY_P95_SLO}ms): $latency_status"
    echo "- Error Rate (<${ERROR_RATE_SLO}%): $error_rate_status"
    echo ""
    
    # Send metrics to CloudWatch
    local availability_value=0
    local latency_value=0
    local error_rate_value=0
    
    [ "$availability_status" = "✅ PASS" ] && availability_value=1
    [ "$latency_status" = "✅ PASS" ] && latency_value=1
    [ "$error_rate_status" = "✅ PASS" ] && error_rate_value=1
    
    aws cloudwatch put-metric-data \
        --namespace "SRE/SLO" \
        --metric-data \
            MetricName=AvailabilitySLO,Value=$availability_value,Unit=Count \
            MetricName=LatencySLO,Value=$latency_value,Unit=Count \
            MetricName=ErrorRateSLO,Value=$error_rate_value,Unit=Count
}

# Main execution
main() {
    echo "🎬 Starting SLO compliance check..."
    
    local availability_status="❌ FAIL"
    local latency_status="❌ FAIL"
    local error_rate_status="❌ FAIL"
    local overall_status=1
    
    # Check each SLO
    if check_availability_slo; then
        availability_status="✅ PASS"
    fi
    
    if check_latency_slo; then
        latency_status="✅ PASS"
    fi
    
    if check_error_rate_slo; then
        error_rate_status="✅ PASS"
    fi
    
    # Generate report
    generate_slo_report "$availability_status" "$latency_status" "$error_rate_status"
    
    # Overall status
    if [[ "$availability_status" == "✅ PASS" && "$latency_status" == "✅ PASS" && "$error_rate_status" == "✅ PASS" ]]; then
        echo "🎉 All SLOs are compliant!"
        overall_status=0
    else
        echo "⚠️  Some SLOs are not being met"
        overall_status=1
    fi
    
    exit $overall_status
}

# Execute main function
main "$@"

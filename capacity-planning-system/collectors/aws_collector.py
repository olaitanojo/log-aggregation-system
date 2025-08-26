#!/usr/bin/env python3

import os
import asyncio
import logging
import yaml
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

import boto3
import structlog
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)

@dataclass
class AWSConfig:
    regions: List[str]
    services: List[str]
    collection_interval: int = 300  # 5 minutes
    cost_collection_enabled: bool = True

class AWSMetricsCollector:
    """Collects AWS resource metrics and cost data for capacity planning"""
    
    def __init__(self, config: AWSConfig, influx_client: InfluxDBClient):
        self.config = config
        self.influx_client = influx_client
        self.write_api = influx_client.write_api(write_options=SYNCHRONOUS)
        
        # Initialize AWS clients for each region
        self.cloudwatch_clients = {}
        self.ec2_clients = {}
        self.rds_clients = {}
        self.cost_explorer_client = None
        
        self._init_aws_clients()
    
    def _init_aws_clients(self):
        """Initialize AWS service clients"""
        try:
            # Initialize CloudWatch clients for each region
            for region in self.config.regions:
                self.cloudwatch_clients[region] = boto3.client('cloudwatch', region_name=region)
                self.ec2_clients[region] = boto3.client('ec2', region_name=region)
                self.rds_clients[region] = boto3.client('rds', region_name=region)
            
            # Cost Explorer client (global)
            if self.config.cost_collection_enabled:
                self.cost_explorer_client = boto3.client('ce', region_name='us-east-1')
                
            logger.info("AWS clients initialized", regions=self.config.regions)
            
        except Exception as e:
            logger.error("Failed to initialize AWS clients", exc_info=e)
            raise
    
    async def collect_all_metrics(self):
        """Collect all configured AWS metrics"""
        logger.info("Starting AWS metrics collection cycle")
        
        try:
            # Collect metrics for each service
            if 'ec2' in self.config.services:
                await self.collect_ec2_metrics()
            
            if 'rds' in self.config.services:
                await self.collect_rds_metrics()
                
            if 'lambda' in self.config.services:
                await self.collect_lambda_metrics()
                
            if 'ecs' in self.config.services:
                await self.collect_ecs_metrics()
            
            # Collect cost data
            if self.config.cost_collection_enabled:
                await self.collect_cost_data()
                
            logger.info("AWS metrics collection completed successfully")
            
        except Exception as e:
            logger.error("AWS metrics collection failed", exc_info=e)
            raise
    
    async def collect_ec2_metrics(self):
        """Collect EC2 instance metrics"""
        logger.info("Collecting EC2 metrics")
        
        for region, cloudwatch in self.cloudwatch_clients.items():
            try:
                # Get EC2 instances
                ec2 = self.ec2_clients[region]
                instances_response = ec2.describe_instances()
                
                instance_ids = []
                instance_metadata = {}
                
                for reservation in instances_response['Reservations']:
                    for instance in reservation['Instances']:
                        if instance['State']['Name'] == 'running':
                            instance_id = instance['InstanceId']
                            instance_ids.append(instance_id)
                            instance_metadata[instance_id] = {
                                'instance_type': instance['InstanceType'],
                                'tags': {tag['Key']: tag['Value'] for tag in instance.get('Tags', [])}
                            }
                
                if not instance_ids:
                    logger.info(f"No running EC2 instances found in {region}")
                    continue
                
                # Collect metrics for each instance
                metrics_to_collect = [
                    {'metric': 'CPUUtilization', 'stat': 'Average'},
                    {'metric': 'NetworkIn', 'stat': 'Sum'},
                    {'metric': 'NetworkOut', 'stat': 'Sum'},
                    {'metric': 'DiskReadBytes', 'stat': 'Sum'},
                    {'metric': 'DiskWriteBytes', 'stat': 'Sum'}
                ]
                
                end_time = datetime.utcnow()
                start_time = end_time - timedelta(minutes=10)
                
                for metric_config in metrics_to_collect:
                    response = cloudwatch.get_metric_statistics(
                        Namespace='AWS/EC2',
                        MetricName=metric_config['metric'],
                        Dimensions=[],
                        StartTime=start_time,
                        EndTime=end_time,
                        Period=300,
                        Statistics=[metric_config['stat']]
                    )
                    
                    # Process and store metrics
                    for datapoint in response['Datapoints']:
                        for instance_id in instance_ids:
                            # Get instance-specific metric
                            instance_response = cloudwatch.get_metric_statistics(
                                Namespace='AWS/EC2',
                                MetricName=metric_config['metric'],
                                Dimensions=[
                                    {'Name': 'InstanceId', 'Value': instance_id}
                                ],
                                StartTime=start_time,
                                EndTime=end_time,
                                Period=300,
                                Statistics=[metric_config['stat']]
                            )
                            
                            for instance_datapoint in instance_response['Datapoints']:
                                point = Point("aws_ec2") \
                                    .tag("region", region) \
                                    .tag("instance_id", instance_id) \
                                    .tag("instance_type", instance_metadata[instance_id]['instance_type']) \
                                    .tag("metric", metric_config['metric'].lower()) \
                                    .field("value", instance_datapoint[metric_config['stat']]) \
                                    .time(instance_datapoint['Timestamp'])
                                
                                # Add tags from instance metadata
                                for tag_key, tag_value in instance_metadata[instance_id]['tags'].items():
                                    point = point.tag(f"tag_{tag_key.lower()}", tag_value)
                                
                                self.write_api.write(bucket="metrics", record=point)
                
                logger.info(f"Collected EC2 metrics for {len(instance_ids)} instances in {region}")
                
            except Exception as e:
                logger.error(f"Failed to collect EC2 metrics for {region}", exc_info=e)
    
    async def collect_rds_metrics(self):
        """Collect RDS database metrics"""
        logger.info("Collecting RDS metrics")
        
        for region, cloudwatch in self.cloudwatch_clients.items():
            try:
                # Get RDS instances
                rds = self.rds_clients[region]
                db_instances = rds.describe_db_instances()
                
                for db_instance in db_instances['DBInstances']:
                    db_instance_id = db_instance['DBInstanceIdentifier']
                    
                    metrics_to_collect = [
                        {'metric': 'CPUUtilization', 'stat': 'Average'},
                        {'metric': 'DatabaseConnections', 'stat': 'Average'},
                        {'metric': 'FreeStorageSpace', 'stat': 'Average'},
                        {'metric': 'FreeableMemory', 'stat': 'Average'},
                        {'metric': 'ReadIOPS', 'stat': 'Average'},
                        {'metric': 'WriteIOPS', 'stat': 'Average'}
                    ]
                    
                    end_time = datetime.utcnow()
                    start_time = end_time - timedelta(minutes=10)
                    
                    for metric_config in metrics_to_collect:
                        response = cloudwatch.get_metric_statistics(
                            Namespace='AWS/RDS',
                            MetricName=metric_config['metric'],
                            Dimensions=[
                                {'Name': 'DBInstanceIdentifier', 'Value': db_instance_id}
                            ],
                            StartTime=start_time,
                            EndTime=end_time,
                            Period=300,
                            Statistics=[metric_config['stat']]
                        )
                        
                        for datapoint in response['Datapoints']:
                            point = Point("aws_rds") \
                                .tag("region", region) \
                                .tag("db_instance_id", db_instance_id) \
                                .tag("db_instance_class", db_instance['DBInstanceClass']) \
                                .tag("engine", db_instance['Engine']) \
                                .tag("metric", metric_config['metric'].lower()) \
                                .field("value", datapoint[metric_config['stat']]) \
                                .time(datapoint['Timestamp'])
                            
                            self.write_api.write(bucket="metrics", record=point)
                
                logger.info(f"Collected RDS metrics for {region}")
                
            except Exception as e:
                logger.error(f"Failed to collect RDS metrics for {region}", exc_info=e)
    
    async def collect_lambda_metrics(self):
        """Collect Lambda function metrics"""
        logger.info("Collecting Lambda metrics")
        
        for region, cloudwatch in self.cloudwatch_clients.items():
            try:
                # Get Lambda functions
                lambda_client = boto3.client('lambda', region_name=region)
                functions = lambda_client.list_functions()
                
                for function in functions['Functions']:
                    function_name = function['FunctionName']
                    
                    metrics_to_collect = [
                        {'metric': 'Duration', 'stat': 'Average'},
                        {'metric': 'Errors', 'stat': 'Sum'},
                        {'metric': 'Invocations', 'stat': 'Sum'},
                        {'metric': 'Throttles', 'stat': 'Sum'},
                        {'metric': 'ConcurrentExecutions', 'stat': 'Maximum'}
                    ]
                    
                    end_time = datetime.utcnow()
                    start_time = end_time - timedelta(minutes=10)
                    
                    for metric_config in metrics_to_collect:
                        response = cloudwatch.get_metric_statistics(
                            Namespace='AWS/Lambda',
                            MetricName=metric_config['metric'],
                            Dimensions=[
                                {'Name': 'FunctionName', 'Value': function_name}
                            ],
                            StartTime=start_time,
                            EndTime=end_time,
                            Period=300,
                            Statistics=[metric_config['stat']]
                        )
                        
                        for datapoint in response['Datapoints']:
                            point = Point("aws_lambda") \
                                .tag("region", region) \
                                .tag("function_name", function_name) \
                                .tag("runtime", function['Runtime']) \
                                .tag("metric", metric_config['metric'].lower()) \
                                .field("value", datapoint[metric_config['stat']]) \
                                .time(datapoint['Timestamp'])
                            
                            self.write_api.write(bucket="metrics", record=point)
                
                logger.info(f"Collected Lambda metrics for {region}")
                
            except Exception as e:
                logger.error(f"Failed to collect Lambda metrics for {region}", exc_info=e)
    
    async def collect_ecs_metrics(self):
        """Collect ECS cluster and service metrics"""
        logger.info("Collecting ECS metrics")
        
        for region, cloudwatch in self.cloudwatch_clients.items():
            try:
                ecs_client = boto3.client('ecs', region_name=region)
                
                # Get ECS clusters
                clusters = ecs_client.list_clusters()
                
                for cluster_arn in clusters['clusterArns']:
                    cluster_name = cluster_arn.split('/')[-1]
                    
                    # Get services in cluster
                    services = ecs_client.list_services(cluster=cluster_name)
                    
                    for service_arn in services['serviceArns']:
                        service_name = service_arn.split('/')[-1]
                        
                        metrics_to_collect = [
                            {'metric': 'CPUUtilization', 'stat': 'Average'},
                            {'metric': 'MemoryUtilization', 'stat': 'Average'},
                            {'metric': 'RunningTaskCount', 'stat': 'Average'},
                            {'metric': 'PendingTaskCount', 'stat': 'Average'}
                        ]
                        
                        end_time = datetime.utcnow()
                        start_time = end_time - timedelta(minutes=10)
                        
                        for metric_config in metrics_to_collect:
                            response = cloudwatch.get_metric_statistics(
                                Namespace='AWS/ECS',
                                MetricName=metric_config['metric'],
                                Dimensions=[
                                    {'Name': 'ServiceName', 'Value': service_name},
                                    {'Name': 'ClusterName', 'Value': cluster_name}
                                ],
                                StartTime=start_time,
                                EndTime=end_time,
                                Period=300,
                                Statistics=[metric_config['stat']]
                            )
                            
                            for datapoint in response['Datapoints']:
                                point = Point("aws_ecs") \
                                    .tag("region", region) \
                                    .tag("cluster_name", cluster_name) \
                                    .tag("service_name", service_name) \
                                    .tag("metric", metric_config['metric'].lower()) \
                                    .field("value", datapoint[metric_config['stat']]) \
                                    .time(datapoint['Timestamp'])
                                
                                self.write_api.write(bucket="metrics", record=point)
                
                logger.info(f"Collected ECS metrics for {region}")
                
            except Exception as e:
                logger.error(f"Failed to collect ECS metrics for {region}", exc_info=e)
    
    async def collect_cost_data(self):
        """Collect AWS cost and billing data"""
        if not self.cost_explorer_client:
            logger.warning("Cost Explorer client not available")
            return
        
        logger.info("Collecting AWS cost data")
        
        try:
            end_date = datetime.utcnow().strftime('%Y-%m-%d')
            start_date = (datetime.utcnow() - timedelta(days=30)).strftime('%Y-%m-%d')
            
            # Get cost by service
            cost_response = self.cost_explorer_client.get_cost_and_usage(
                TimePeriod={
                    'Start': start_date,
                    'End': end_date
                },
                Granularity='DAILY',
                Metrics=['BlendedCost', 'UnblendedCost', 'UsageQuantity'],
                GroupBy=[
                    {
                        'Type': 'DIMENSION',
                        'Key': 'SERVICE'
                    }
                ]
            )
            
            for result in cost_response['ResultsByTime']:
                date = result['TimePeriod']['Start']
                
                for group in result['Groups']:
                    service = group['Keys'][0]
                    
                    for metric, amount in group['Metrics'].items():
                        if amount['Amount']:
                            point = Point("aws_costs") \
                                .tag("service", service) \
                                .tag("metric", metric.lower()) \
                                .field("amount", float(amount['Amount'])) \
                                .field("unit", amount['Unit']) \
                                .time(datetime.strptime(date, '%Y-%m-%d'))
                            
                            self.write_api.write(bucket="metrics", record=point)
            
            # Get rightsizing recommendations
            rightsizing_response = self.cost_explorer_client.get_rightsizing_recommendation(
                Service='AmazonEC2',
                PageSize=100
            )
            
            for recommendation in rightsizing_response.get('RightsizingRecommendations', []):
                current_instance = recommendation['CurrentInstance']
                
                if 'RightsizingType' in recommendation:
                    point = Point("aws_rightsizing") \
                        .tag("instance_id", current_instance['InstanceId']) \
                        .tag("current_type", current_instance['InstanceType']) \
                        .tag("recommendation_type", recommendation['RightsizingType']) \
                        .field("estimated_monthly_savings", 
                               float(recommendation.get('EstimatedMonthlySavings', {}).get('Amount', 0))) \
                        .time(datetime.utcnow())
                    
                    if 'ModifyRecommendationDetail' in recommendation:
                        modify_detail = recommendation['ModifyRecommendationDetail']
                        if 'TargetInstances' in modify_detail:
                            target = modify_detail['TargetInstances'][0]
                            point = point.tag("recommended_type", target['InstanceType'])
                    
                    self.write_api.write(bucket="metrics", record=point)
            
            logger.info("Collected AWS cost data")
            
        except Exception as e:
            logger.error("Failed to collect AWS cost data", exc_info=e)
    
    async def collect_resource_inventory(self):
        """Collect AWS resource inventory for capacity planning"""
        logger.info("Collecting AWS resource inventory")
        
        for region in self.config.regions:
            try:
                # EC2 inventory
                ec2 = self.ec2_clients[region]
                instances = ec2.describe_instances()
                
                instance_count_by_type = {}
                total_vcpus = 0
                total_memory = 0
                
                for reservation in instances['Reservations']:
                    for instance in reservation['Instances']:
                        if instance['State']['Name'] == 'running':
                            instance_type = instance['InstanceType']
                            instance_count_by_type[instance_type] = instance_count_by_type.get(instance_type, 0) + 1
                            
                            # Get instance type details (simplified - in real implementation, use AWS API)
                            # This is a simplified mapping - should use actual AWS API
                            vcpu_map = {'t3.micro': 2, 't3.small': 2, 't3.medium': 2, 't3.large': 2}
                            memory_map = {'t3.micro': 1, 't3.small': 2, 't3.medium': 4, 't3.large': 8}
                            
                            total_vcpus += vcpu_map.get(instance_type, 2)
                            total_memory += memory_map.get(instance_type, 2)
                
                # Store inventory data
                point = Point("aws_inventory") \
                    .tag("region", region) \
                    .tag("resource_type", "ec2") \
                    .field("total_instances", sum(instance_count_by_type.values())) \
                    .field("total_vcpus", total_vcpus) \
                    .field("total_memory_gb", total_memory) \
                    .time(datetime.utcnow())
                
                self.write_api.write(bucket="metrics", record=point)
                
                # Store breakdown by instance type
                for instance_type, count in instance_count_by_type.items():
                    point = Point("aws_inventory_by_type") \
                        .tag("region", region) \
                        .tag("resource_type", "ec2") \
                        .tag("instance_type", instance_type) \
                        .field("count", count) \
                        .time(datetime.utcnow())
                    
                    self.write_api.write(bucket="metrics", record=point)
                
                logger.info(f"Collected inventory for {region}")
                
            except Exception as e:
                logger.error(f"Failed to collect inventory for {region}", exc_info=e)

async def main():
    """Main collection loop"""
    # Load configuration
    with open('/app/config.yml', 'r') as f:
        config_data = yaml.safe_load(f)
    
    aws_config = AWSConfig(**config_data['aws'])
    
    # Initialize InfluxDB client
    influx_client = InfluxDBClient(
        url=os.getenv('INFLUXDB_URL'),
        token=os.getenv('INFLUXDB_TOKEN'),
        org=os.getenv('INFLUXDB_ORG', 'capacity-org')
    )
    
    collector = AWSMetricsCollector(aws_config, influx_client)
    
    logger.info("Starting AWS metrics collection service", config=config_data)
    
    while True:
        try:
            await collector.collect_all_metrics()
            await collector.collect_resource_inventory()
            
            # Wait for next collection cycle
            await asyncio.sleep(aws_config.collection_interval)
            
        except Exception as e:
            logger.error("Collection cycle failed", exc_info=e)
            # Wait before retrying
            await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(main())

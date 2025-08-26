#!/usr/bin/env python3

import os
import asyncio
import pickle
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass

import pandas as pd
import numpy as np
from prophet import Prophet
from sklearn.metrics import mean_absolute_error, mean_squared_error
import structlog
from influxdb_client import InfluxDBClient
import redis
import yaml

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
class ForecastConfig:
    model_type: str = "prophet"
    forecast_horizon: str = "30d"
    confidence_levels: List[float] = None
    seasonality: bool = True
    include_holidays: bool = False
    min_data_points: int = 100

class CapacityForecaster:
    """Machine learning-based capacity forecasting service"""
    
    def __init__(self, influx_client: InfluxDBClient, redis_client: redis.Redis):
        self.influx_client = influx_client
        self.redis_client = redis_client
        self.query_api = influx_client.query_api()
        self.models = {}  # Cache for trained models
        
    async def generate_forecast(
        self, 
        metric: str, 
        resource_id: str, 
        config: ForecastConfig
    ) -> Dict[str, Any]:
        """Generate capacity forecast for a specific metric and resource"""
        
        logger.info(
            "Generating forecast", 
            metric=metric, 
            resource_id=resource_id,
            horizon=config.forecast_horizon
        )
        
        try:
            # Get historical data
            historical_data = await self._get_historical_data(metric, resource_id)
            
            if len(historical_data) < config.min_data_points:
                raise ValueError(f"Insufficient data points: {len(historical_data)} < {config.min_data_points}")
            
            # Prepare data for Prophet
            df = self._prepare_prophet_data(historical_data)
            
            # Train or get cached model
            model = await self._get_or_train_model(metric, resource_id, df, config)
            
            # Generate forecast
            forecast_df = self._generate_prophet_forecast(model, config)
            
            # Calculate accuracy metrics if we have enough data
            accuracy_metrics = self._calculate_accuracy(model, df) if len(df) > 200 else None
            
            # Extract forecast results
            forecast_results = self._extract_forecast_results(forecast_df, config)
            
            # Store forecast in cache
            await self._cache_forecast(metric, resource_id, forecast_results)
            
            return {
                "metric": metric,
                "resource_id": resource_id,
                "forecast_horizon": config.forecast_horizon,
                "model_type": config.model_type,
                "confidence_levels": config.confidence_levels or [0.80, 0.95],
                "forecast": forecast_results,
                "accuracy_metrics": accuracy_metrics,
                "data_points_used": len(df),
                "generated_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error("Forecast generation failed", exc_info=e, metric=metric, resource_id=resource_id)
            raise
    
    async def _get_historical_data(self, metric: str, resource_id: str) -> pd.DataFrame:
        """Retrieve historical data from InfluxDB"""
        
        # Build InfluxDB query
        query = f'''
        from(bucket: "metrics")
        |> range(start: -90d)
        |> filter(fn: (r) => r._measurement == "{self._get_measurement_name(metric)}")
        |> filter(fn: (r) => r.resource_id == "{resource_id}")
        |> filter(fn: (r) => r._field == "value")
        |> aggregateWindow(every: 1h, fn: mean, createEmpty: false)
        |> yield(name: "mean")
        '''
        
        result = self.query_api.query(query=query)
        
        data = []
        for table in result:
            for record in table.records:
                data.append({
                    'time': record.get_time(),
                    'value': record.get_value()
                })
        
        if not data:
            raise ValueError(f"No historical data found for {metric} on {resource_id}")
        
        df = pd.DataFrame(data)
        df['time'] = pd.to_datetime(df['time'])
        df = df.sort_values('time').reset_index(drop=True)
        
        logger.info(f"Retrieved {len(df)} historical data points", metric=metric, resource_id=resource_id)
        return df
    
    def _prepare_prophet_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Prepare data in Prophet format (ds, y columns)"""
        prophet_df = pd.DataFrame({
            'ds': df['time'],
            'y': df['value']
        })
        
        # Remove outliers (values beyond 3 standard deviations)
        mean_val = prophet_df['y'].mean()
        std_val = prophet_df['y'].std()
        prophet_df = prophet_df[
            (prophet_df['y'] >= mean_val - 3 * std_val) & 
            (prophet_df['y'] <= mean_val + 3 * std_val)
        ]
        
        return prophet_df
    
    async def _get_or_train_model(
        self, 
        metric: str, 
        resource_id: str, 
        df: pd.DataFrame, 
        config: ForecastConfig
    ) -> Prophet:
        """Get cached model or train a new one"""
        
        model_key = f"{metric}:{resource_id}"
        
        # Check if model exists in cache and is recent
        cached_model = await self._get_cached_model(model_key)
        if cached_model:
            logger.info("Using cached model", model_key=model_key)
            return cached_model
        
        # Train new model
        logger.info("Training new Prophet model", model_key=model_key)
        
        model = Prophet(
            yearly_seasonality=config.seasonality,
            weekly_seasonality=config.seasonality,
            daily_seasonality=False,
            interval_width=0.95,  # 95% confidence interval
            changepoint_prior_scale=0.05
        )
        
        if config.include_holidays:
            # Add holidays (can be customized for specific regions)
            model.add_country_holidays(country_name='US')
        
        # Fit the model
        model.fit(df)
        
        # Cache the model
        await self._cache_model(model_key, model)
        
        logger.info("Model training completed", model_key=model_key)
        return model
    
    def _generate_prophet_forecast(self, model: Prophet, config: ForecastConfig) -> pd.DataFrame:
        """Generate forecast using Prophet model"""
        
        # Parse forecast horizon
        horizon_map = {"7d": 7, "30d": 30, "90d": 90, "180d": 180, "365d": 365}
        days = horizon_map.get(config.forecast_horizon, 30)
        
        # Create future dataframe
        future = model.make_future_dataframe(periods=days, freq='D')
        
        # Generate forecast
        forecast = model.predict(future)
        
        # Filter to only future dates
        forecast_only = forecast[forecast['ds'] > forecast['ds'].max() - pd.Timedelta(days=days)]
        
        return forecast_only
    
    def _extract_forecast_results(self, forecast_df: pd.DataFrame, config: ForecastConfig) -> Dict[str, Any]:
        """Extract forecast results in structured format"""
        
        results = {
            "timeline": [],
            "summary": {
                "min_predicted": float(forecast_df['yhat'].min()),
                "max_predicted": float(forecast_df['yhat'].max()),
                "mean_predicted": float(forecast_df['yhat'].mean()),
                "growth_rate": self._calculate_growth_rate(forecast_df),
                "trend": "increasing" if forecast_df['trend'].iloc[-1] > forecast_df['trend'].iloc[0] else "decreasing"
            }
        }
        
        # Extract timeline data
        for _, row in forecast_df.iterrows():
            timeline_point = {
                "date": row['ds'].isoformat(),
                "predicted_value": float(row['yhat']),
                "lower_bound": float(row['yhat_lower']),
                "upper_bound": float(row['yhat_upper']),
                "trend": float(row['trend'])
            }
            
            # Add confidence intervals if specified
            if config.confidence_levels:
                for confidence in config.confidence_levels:
                    ci_lower = row['yhat'] - (row['yhat_upper'] - row['yhat']) * (1 - confidence)
                    ci_upper = row['yhat'] + (row['yhat_upper'] - row['yhat']) * (1 - confidence)
                    timeline_point[f"ci_{int(confidence*100)}_lower"] = float(ci_lower)
                    timeline_point[f"ci_{int(confidence*100)}_upper"] = float(ci_upper)
            
            results["timeline"].append(timeline_point)
        
        return results
    
    def _calculate_growth_rate(self, forecast_df: pd.DataFrame) -> float:
        """Calculate the growth rate from the forecast"""
        if len(forecast_df) < 2:
            return 0.0
        
        start_value = forecast_df['yhat'].iloc[0]
        end_value = forecast_df['yhat'].iloc[-1]
        
        if start_value == 0:
            return 0.0
        
        growth_rate = (end_value - start_value) / start_value * 100
        return float(growth_rate)
    
    def _calculate_accuracy(self, model: Prophet, df: pd.DataFrame) -> Dict[str, float]:
        """Calculate model accuracy metrics using cross-validation"""
        try:
            from prophet.diagnostics import cross_validation, performance_metrics
            
            # Perform cross-validation (last 30 days as test set)
            cutoffs = [df['ds'].max() - pd.Timedelta(days=30)]
            df_cv = cross_validation(model, cutoffs=cutoffs, horizon='30 days')
            
            # Calculate performance metrics
            df_p = performance_metrics(df_cv)
            
            return {
                "mae": float(df_p['mae'].mean()),
                "mse": float(df_p['mse'].mean()),
                "rmse": float(df_p['rmse'].mean()),
                "mape": float(df_p['mape'].mean())
            }
            
        except Exception as e:
            logger.warning("Could not calculate accuracy metrics", exc_info=e)
            return None
    
    async def _get_cached_model(self, model_key: str) -> Optional[Prophet]:
        """Get cached model from Redis"""
        try:
            model_data = self.redis_client.get(f"model:{model_key}")
            if model_data:
                model = pickle.loads(model_data)
                # Check if model is recent (within 24 hours)
                model_age = datetime.utcnow() - model.history['ds'].max().to_pydatetime()
                if model_age < timedelta(hours=24):
                    return model
        except Exception as e:
            logger.warning("Failed to get cached model", exc_info=e, model_key=model_key)
        
        return None
    
    async def _cache_model(self, model_key: str, model: Prophet):
        """Cache trained model in Redis"""
        try:
            model_data = pickle.dumps(model)
            # Cache for 24 hours
            self.redis_client.setex(f"model:{model_key}", 86400, model_data)
            logger.info("Model cached successfully", model_key=model_key)
        except Exception as e:
            logger.warning("Failed to cache model", exc_info=e, model_key=model_key)
    
    async def _cache_forecast(self, metric: str, resource_id: str, forecast: Dict[str, Any]):
        """Cache forecast results"""
        try:
            forecast_key = f"forecast:{metric}:{resource_id}"
            forecast_data = pickle.dumps(forecast)
            # Cache for 1 hour
            self.redis_client.setex(forecast_key, 3600, forecast_data)
            logger.info("Forecast cached", metric=metric, resource_id=resource_id)
        except Exception as e:
            logger.warning("Failed to cache forecast", exc_info=e)
    
    def _get_measurement_name(self, metric: str) -> str:
        """Get InfluxDB measurement name for metric"""
        metric_mapping = {
            "cpu_utilization": "aws_ec2",
            "memory_utilization": "aws_ec2",
            "network_in": "aws_ec2",
            "network_out": "aws_ec2",
            "disk_read": "aws_ec2",
            "disk_write": "aws_ec2",
            "database_connections": "aws_rds",
            "lambda_duration": "aws_lambda",
            "lambda_invocations": "aws_lambda"
        }
        
        return metric_mapping.get(metric, "aws_ec2")

class ForecastingAPI:
    """FastAPI service for capacity forecasting"""
    
    def __init__(self):
        self.forecaster = None
        
    async def initialize(self):
        """Initialize the forecasting service"""
        # Initialize InfluxDB client
        influx_client = InfluxDBClient(
            url=os.getenv('INFLUXDB_URL'),
            token=os.getenv('INFLUXDB_TOKEN'),
            org=os.getenv('INFLUXDB_ORG', 'capacity-org')
        )
        
        # Initialize Redis client
        redis_client = redis.from_url(os.getenv('REDIS_URL'))
        
        self.forecaster = CapacityForecaster(influx_client, redis_client)
        
        logger.info("Forecasting service initialized")
    
    async def forecast_resource_capacity(
        self,
        resource_type: str,
        resource_id: str, 
        metric: str,
        horizon: str = "30d",
        confidence_level: float = 0.95
    ) -> Dict[str, Any]:
        """Generate capacity forecast for a resource"""
        
        config = ForecastConfig(
            forecast_horizon=horizon,
            confidence_levels=[0.80, confidence_level],
            seasonality=True
        )
        
        forecast = await self.forecaster.generate_forecast(
            metric=f"{resource_type}_{metric}",
            resource_id=resource_id,
            config=config
        )
        
        # Add capacity planning insights
        forecast["insights"] = await self._generate_capacity_insights(forecast, resource_type)
        
        return forecast
    
    async def bulk_forecast_generation(self, resources: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """Generate forecasts for multiple resources"""
        forecasts = []
        
        for resource in resources:
            try:
                forecast = await self.forecast_resource_capacity(
                    resource_type=resource['type'],
                    resource_id=resource['id'],
                    metric=resource.get('metric', 'cpu_utilization'),
                    horizon=resource.get('horizon', '30d')
                )
                forecasts.append(forecast)
                
            except Exception as e:
                logger.error(
                    "Failed to generate forecast for resource",
                    exc_info=e,
                    resource=resource
                )
                forecasts.append({
                    "resource_id": resource['id'],
                    "error": str(e),
                    "status": "failed"
                })
        
        return forecasts
    
    async def _generate_capacity_insights(self, forecast: Dict[str, Any], resource_type: str) -> Dict[str, Any]:
        """Generate actionable insights from forecast data"""
        
        timeline = forecast["forecast"]["timeline"]
        summary = forecast["forecast"]["summary"]
        
        insights = {
            "recommendations": [],
            "alerts": [],
            "capacity_utilization": {},
            "growth_analysis": {}
        }
        
        # Analyze growth trend
        growth_rate = summary["growth_rate"]
        
        if growth_rate > 20:  # 20% growth
            insights["alerts"].append({
                "severity": "high",
                "message": f"High growth rate detected: {growth_rate:.1f}% over forecast period",
                "action": "Consider scaling up resources proactively"
            })
            insights["recommendations"].append({
                "type": "scale_up",
                "priority": "high",
                "description": f"Scale up {resource_type} resources due to high growth trend"
            })
        
        elif growth_rate < -10:  # 10% decline
            insights["recommendations"].append({
                "type": "scale_down",
                "priority": "medium", 
                "description": f"Consider scaling down {resource_type} resources due to declining usage"
            })
        
        # Analyze peak capacity requirements
        max_predicted = summary["max_predicted"]
        mean_predicted = summary["mean_predicted"]
        
        if max_predicted > mean_predicted * 1.5:
            insights["alerts"].append({
                "severity": "medium",
                "message": "High variability in predicted usage - consider auto-scaling",
                "action": "Review and optimize auto-scaling policies"
            })
        
        # Capacity threshold analysis
        if resource_type in ['ec2', 'cpu']:
            if max_predicted > 80:  # 80% CPU utilization
                insights["alerts"].append({
                    "severity": "high",
                    "message": f"Predicted peak {resource_type} usage: {max_predicted:.1f}%",
                    "action": "Scale up before reaching capacity limits"
                })
        
        # Growth analysis
        insights["growth_analysis"] = {
            "growth_rate_percent": growth_rate,
            "trend_direction": summary["trend"],
            "volatility": "high" if max_predicted > mean_predicted * 2 else "normal",
            "seasonality_detected": len([p for p in timeline if abs(p["predicted_value"] - mean_predicted) > mean_predicted * 0.2]) > len(timeline) * 0.3
        }
        
        return insights

async def main():
    """Main forecasting service loop"""
    
    forecasting_api = ForecastingAPI()
    await forecasting_api.initialize()
    
    # Load configuration
    with open('/app/config.yml', 'r') as f:
        config = yaml.safe_load(f)
    
    logger.info("Starting forecasting service", config=config)
    
    # Run continuous forecasting for configured resources
    update_interval = int(os.getenv('MODEL_UPDATE_INTERVAL', 3600))  # 1 hour default
    
    while True:
        try:
            # Update models and generate forecasts
            await update_all_forecasts(forecasting_api, config)
            
            logger.info("Forecasting update cycle completed")
            await asyncio.sleep(update_interval)
            
        except Exception as e:
            logger.error("Forecasting update failed", exc_info=e)
            await asyncio.sleep(300)  # Wait 5 minutes before retry

async def update_all_forecasts(api: ForecastingAPI, config: Dict[str, Any]):
    """Update forecasts for all configured resources"""
    
    forecast_configs = config.get('forecasting', {}).get('resources', [])
    
    for resource_config in forecast_configs:
        try:
            forecast = await api.forecast_resource_capacity(
                resource_type=resource_config['type'],
                resource_id=resource_config['id'],
                metric=resource_config['metric'],
                horizon=resource_config.get('horizon', '30d')
            )
            
            logger.info(
                "Forecast updated",
                resource_id=resource_config['id'],
                metric=resource_config['metric']
            )
            
        except Exception as e:
            logger.error(
                "Failed to update forecast",
                exc_info=e,
                resource_config=resource_config
            )

if __name__ == "__main__":
    asyncio.run(main())

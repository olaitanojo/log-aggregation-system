#!/usr/bin/env python3

import os
import asyncio
import logging
import structlog
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import redis.asyncio as aioredis
from prometheus_client import Counter, Histogram, Gauge, generate_latest
from starlette.responses import Response

from .models import ChaosExperiment, ExperimentExecution, SafetyRule
from .services.experiment_service import ExperimentService
from .services.safety_service import SafetyService
from .services.metrics_service import MetricsService
from .services.target_service import TargetService
from .executors import ExperimentExecutorFactory
from .config import get_settings

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)

# Metrics
EXPERIMENTS_TOTAL = Counter(
    'chaos_experiments_total',
    'Total number of chaos experiments',
    ['type', 'status', 'environment']
)

EXPERIMENT_DURATION = Histogram(
    'chaos_experiment_duration_seconds',
    'Duration of chaos experiments',
    ['type', 'environment']
)

ACTIVE_EXPERIMENTS = Gauge(
    'chaos_active_experiments',
    'Number of currently active chaos experiments'
)

SAFETY_TRIGGERS = Counter(
    'chaos_safety_triggers_total',
    'Total number of safety rule triggers',
    ['rule_type', 'action']
)

# Global services
experiment_service: ExperimentService = None
safety_service: SafetyService = None
metrics_service: MetricsService = None
target_service: TargetService = None
redis_client: aioredis.Redis = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    global experiment_service, safety_service, metrics_service, target_service, redis_client
    
    settings = get_settings()
    
    # Initialize database
    engine = create_async_engine(
        settings.database_url,
        echo=settings.debug,
        pool_pre_ping=True
    )
    
    SessionLocal = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    
    # Initialize Redis
    redis_client = aioredis.from_url(settings.redis_url)
    
    # Initialize services
    experiment_service = ExperimentService(SessionLocal)
    safety_service = SafetyService(redis_client, settings)
    metrics_service = MetricsService(settings)
    target_service = TargetService(settings)
    
    # Start background tasks
    asyncio.create_task(safety_monitor_task())
    asyncio.create_task(experiment_scheduler_task())
    
    logger.info("Chaos Engineering Framework started successfully")
    
    yield
    
    # Cleanup
    await redis_client.close()
    await engine.dispose()
    logger.info("Chaos Engineering Framework shutdown complete")

# Create FastAPI app
app = FastAPI(
    title="Chaos Engineering Framework",
    description="Framework for running controlled chaos engineering experiments",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security
security = HTTPBearer()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Extract user from JWT token"""
    # Implementation would verify JWT token and extract user info
    return {"id": "user-123", "email": "user@example.com", "role": "SRE"}

# Background tasks
async def safety_monitor_task():
    """Background task to monitor experiment safety"""
    while True:
        try:
            await safety_service.check_all_experiments()
            await asyncio.sleep(10)  # Check every 10 seconds
        except Exception as e:
            logger.error("Error in safety monitor", exc_info=e)
            await asyncio.sleep(30)  # Back off on error

async def experiment_scheduler_task():
    """Background task to handle scheduled experiments"""
    while True:
        try:
            await experiment_service.process_scheduled_experiments()
            await asyncio.sleep(60)  # Check every minute
        except Exception as e:
            logger.error("Error in experiment scheduler", exc_info=e)
            await asyncio.sleep(60)

# API Endpoints

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Chaos Engineering Framework",
        "version": "1.0.0",
        "status": "healthy"
    }

@app.get("/experiments")
async def get_experiments(
    status: Optional[str] = None,
    experiment_type: Optional[str] = None,
    environment: Optional[str] = None,
    limit: int = 100
):
    """Get all experiments with optional filtering"""
    experiments = await experiment_service.get_experiments(
        status=status,
        experiment_type=experiment_type,
        environment=environment,
        limit=limit
    )
    return experiments

@app.get("/experiments/active")
async def get_active_experiments():
    """Get currently running experiments"""
    return await experiment_service.get_active_experiments()

@app.get("/experiments/{experiment_id}")
async def get_experiment(experiment_id: str):
    """Get specific experiment details"""
    experiment = await experiment_service.get_experiment(experiment_id)
    if not experiment:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return experiment

@app.post("/experiments")
async def create_experiment(
    experiment_data: dict,
    background_tasks: BackgroundTasks,
    user = Depends(get_current_user)
):
    """Create a new chaos experiment"""
    experiment = await experiment_service.create_experiment(experiment_data, user['id'])
    
    # Validate target and safety rules
    validation_result = await target_service.validate_target(experiment.target)
    if not validation_result['valid']:
        raise HTTPException(status_code=400, detail=validation_result['message'])
    
    EXPERIMENTS_TOTAL.labels(
        type=experiment.type,
        status='CREATED',
        environment=experiment.target.scope.environment
    ).inc()
    
    return experiment

@app.post("/experiments/{experiment_id}/start")
async def start_experiment(
    experiment_id: str,
    background_tasks: BackgroundTasks,
    user = Depends(get_current_user)
):
    """Start a chaos experiment"""
    experiment = await experiment_service.get_experiment(experiment_id)
    if not experiment:
        raise HTTPException(status_code=404, detail="Experiment not found")
    
    if experiment.status not in ['DRAFT', 'SCHEDULED']:
        raise HTTPException(status_code=400, detail="Experiment cannot be started in current status")
    
    # Pre-flight safety checks
    safety_check = await safety_service.pre_flight_check(experiment)
    if not safety_check['safe']:
        raise HTTPException(status_code=400, detail=f"Safety check failed: {safety_check['message']}")
    
    # Start the experiment in background
    background_tasks.add_task(execute_experiment, experiment_id, user['id'])
    
    await experiment_service.update_status(experiment_id, 'PENDING')
    
    return {"message": "Experiment starting", "experiment_id": experiment_id}

@app.post("/experiments/{experiment_id}/stop")
async def stop_experiment(experiment_id: str, user = Depends(get_current_user)):
    """Stop a running experiment"""
    await experiment_service.stop_experiment(experiment_id, user['id'])
    return {"message": "Experiment stopped", "experiment_id": experiment_id}

@app.post("/experiments/{experiment_id}/rollback")
async def rollback_experiment(experiment_id: str, user = Depends(get_current_user)):
    """Rollback the effects of an experiment"""
    await experiment_service.rollback_experiment(experiment_id, user['id'])
    return {"message": "Experiment rolled back", "experiment_id": experiment_id}

@app.get("/experiments/{experiment_id}/logs")
async def get_experiment_logs(experiment_id: str):
    """Get experiment execution logs"""
    logs = await experiment_service.get_experiment_logs(experiment_id)
    return {"logs": logs}

@app.get("/experiments/{experiment_id}/metrics")
async def get_experiment_metrics(experiment_id: str):
    """Get experiment metrics"""
    metrics = await metrics_service.get_experiment_metrics(experiment_id)
    return metrics

@app.post("/experiments/blast-radius-preview")
async def get_blast_radius_preview(target_data: dict):
    """Preview the blast radius of an experiment target"""
    preview = await target_service.get_blast_radius_preview(target_data)
    return preview

@app.get("/templates")
async def get_experiment_templates():
    """Get available experiment templates"""
    return await experiment_service.get_templates()

@app.post("/templates/{template_id}/create")
async def create_from_template(
    template_id: str,
    customizations: dict,
    user = Depends(get_current_user)
):
    """Create an experiment from a template"""
    experiment = await experiment_service.create_from_template(template_id, customizations, user['id'])
    return experiment

@app.websocket("/experiments/{experiment_id}/ws")
async def experiment_websocket(websocket: WebSocket, experiment_id: str):
    """WebSocket endpoint for real-time experiment updates"""
    await websocket.accept()
    
    try:
        # Subscribe to experiment updates
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(f"experiment:{experiment_id}")
        
        async for message in pubsub.listen():
            if message['type'] == 'message':
                await websocket.send_text(message['data'].decode())
                
    except Exception as e:
        logger.error("WebSocket error", exc_info=e, experiment_id=experiment_id)
    finally:
        await pubsub.unsubscribe(f"experiment:{experiment_id}")
        await websocket.close()

@app.get("/metrics")
async def prometheus_metrics():
    """Prometheus metrics endpoint"""
    return Response(
        generate_latest(),
        media_type="text/plain"
    )

async def execute_experiment(experiment_id: str, user_id: str):
    """Background task to execute a chaos experiment"""
    try:
        experiment = await experiment_service.get_experiment(experiment_id)
        
        # Create executor for the experiment type
        executor = ExperimentExecutorFactory.create(experiment.type)
        
        # Update status to running
        await experiment_service.update_status(experiment_id, 'RUNNING')
        ACTIVE_EXPERIMENTS.inc()
        
        start_time = datetime.utcnow()
        
        # Execute the experiment
        with EXPERIMENT_DURATION.labels(
            type=experiment.type,
            environment=experiment.target.scope.environment
        ).time():
            results = await executor.execute(experiment, safety_service, metrics_service)
        
        end_time = datetime.utcnow()
        
        # Update experiment with results
        await experiment_service.update_results(experiment_id, results)
        await experiment_service.update_status(experiment_id, 'COMPLETED')
        
        EXPERIMENTS_TOTAL.labels(
            type=experiment.type,
            status='COMPLETED',
            environment=experiment.target.scope.environment
        ).inc()
        
        logger.info(
            "Experiment completed successfully",
            experiment_id=experiment_id,
            duration=(end_time - start_time).total_seconds()
        )
        
    except Exception as e:
        logger.error(
            "Experiment execution failed",
            exc_info=e,
            experiment_id=experiment_id
        )
        
        await experiment_service.update_status(experiment_id, 'FAILED')
        await experiment_service.add_error(experiment_id, str(e))
        
        EXPERIMENTS_TOTAL.labels(
            type=experiment.type if 'experiment' in locals() else 'UNKNOWN',
            status='FAILED',
            environment=experiment.target.scope.environment if 'experiment' in locals() else 'UNKNOWN'
        ).inc()
        
    finally:
        ACTIVE_EXPERIMENTS.dec()

# Dependency providers
def get_experiment_service() -> ExperimentService:
    return experiment_service

def get_safety_service() -> SafetyService:
    return safety_service

def get_metrics_service() -> MetricsService:
    return metrics_service

def get_target_service() -> TargetService:
    return target_service

def get_redis() -> aioredis.Redis:
    return redis_client

if __name__ == "__main__":
    import uvicorn
    
    settings = get_settings()
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level="info"
    )

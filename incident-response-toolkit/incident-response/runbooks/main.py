#!/usr/bin/env python3

import os
import logging
import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import redis.asyncio as aioredis
from prometheus_client import Counter, Histogram, generate_latest
from starlette.responses import Response

from .database import Base, get_db
from .models import Runbook, RunbookExecution, RunbookStep
from .services.runbook_service import RunbookService
from .services.execution_service import ExecutionService
from .services.notification_service import NotificationService
from .api import runbooks, executions, health
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
RUNBOOK_EXECUTIONS = Counter(
    'runbook_executions_total',
    'Total number of runbook executions',
    ['runbook_id', 'status']
)

EXECUTION_DURATION = Histogram(
    'runbook_execution_duration_seconds',
    'Duration of runbook executions',
    ['runbook_id']
)

# Global services
runbook_service: RunbookService = None
execution_service: ExecutionService = None
notification_service: NotificationService = None
redis_client: aioredis.Redis = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    global runbook_service, execution_service, notification_service, redis_client
    
    settings = get_settings()
    
    # Initialize database
    engine = create_async_engine(
        settings.database_url,
        echo=settings.debug,
        pool_pre_ping=True
    )
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    SessionLocal = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    
    # Initialize Redis
    redis_client = aioredis.from_url(settings.redis_url)
    
    # Initialize services
    runbook_service = RunbookService(SessionLocal)
    execution_service = ExecutionService(SessionLocal, redis_client)
    notification_service = NotificationService(redis_client, settings)
    
    logger.info("Runbook Engine started successfully")
    
    yield
    
    # Cleanup
    await redis_client.close()
    await engine.dispose()
    logger.info("Runbook Engine shutdown complete")

# Create FastAPI app
app = FastAPI(
    title="Incident Response Runbook Engine",
    description="Automated runbook execution engine for incident response",
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
    # For now, return a mock user
    return {"id": "user-123", "email": "user@example.com", "role": "SRE"}

# Include routers
app.include_router(runbooks.router, prefix="/api/runbooks", tags=["runbooks"])
app.include_router(executions.router, prefix="/api/executions", tags=["executions"])
app.include_router(health.router, prefix="/health", tags=["health"])

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Incident Response Runbook Engine",
        "version": "1.0.0",
        "status": "healthy"
    }

@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return Response(
        generate_latest(),
        media_type="text/plain"
    )

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error("Unhandled exception", exc_info=exc, request=request.url)
    return HTTPException(
        status_code=500,
        detail="Internal server error"
    )

# Dependency providers
def get_runbook_service() -> RunbookService:
    return runbook_service

def get_execution_service() -> ExecutionService:
    return execution_service

def get_notification_service() -> NotificationService:
    return notification_service

def get_redis() -> aioredis.Redis:
    return redis_client

if __name__ == "__main__":
    import uvicorn
    
    settings = get_settings()
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level="info"
    )

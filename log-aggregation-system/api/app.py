#!/usr/bin/env python3

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from fastapi import FastAPI, HTTPException, Query, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
import redis
from elasticsearch import AsyncElasticsearch
import structlog

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

# Configuration
ELASTICSEARCH_URL = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Initialize clients
es_client = AsyncElasticsearch([ELASTICSEARCH_URL])
redis_client = redis.from_url(REDIS_URL)

# FastAPI app
app = FastAPI(
    title="Log Analysis API",
    description="REST API for querying and analyzing centralized logs",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security
security = HTTPBearer()

# Pydantic models
class LogQuery(BaseModel):
    query: str = Field(..., description="Elasticsearch query string")
    start_time: Optional[datetime] = Field(None, description="Start time for log search")
    end_time: Optional[datetime] = Field(None, description="End time for log search")
    index_pattern: str = Field("logs-*", description="Elasticsearch index pattern")
    size: int = Field(100, description="Maximum number of results", le=1000)
    sort_field: str = Field("@timestamp", description="Field to sort by")
    sort_order: str = Field("desc", description="Sort order (asc/desc)")

class LogAnalysisRequest(BaseModel):
    services: Optional[List[str]] = Field(None, description="Services to analyze")
    log_levels: Optional[List[str]] = Field(None, description="Log levels to include")
    time_range: str = Field("1h", description="Time range (1h, 24h, 7d)")
    analysis_type: str = Field("error_analysis", description="Type of analysis")

class AlertRule(BaseModel):
    name: str
    description: str
    query: str
    threshold: int
    timeframe: str
    notification_channels: List[str]
    severity: str = Field("medium", regex="^(low|medium|high|critical)$")

# Dependency functions
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Extract user from JWT token (mock implementation)"""
    return {"id": "user-123", "email": "user@example.com", "role": "analyst"}

# API Endpoints

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Log Analysis API",
        "version": "1.0.0",
        "status": "healthy",
        "elasticsearch_status": await check_elasticsearch_health()
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    es_health = await check_elasticsearch_health()
    redis_health = check_redis_health()
    
    return {
        "status": "healthy" if es_health and redis_health else "unhealthy",
        "elasticsearch": es_health,
        "redis": redis_health,
        "timestamp": datetime.utcnow().isoformat()
    }

@app.post("/logs/search")
async def search_logs(
    query: LogQuery,
    user = Depends(get_current_user)
):
    """Search logs using Elasticsearch query"""
    try:
        # Build Elasticsearch query
        es_query = {
            "query": {
                "bool": {
                    "must": [
                        {"query_string": {"query": query.query}}
                    ]
                }
            },
            "sort": [
                {query.sort_field: {"order": query.sort_order}}
            ],
            "size": query.size
        }
        
        # Add time range filter if provided
        if query.start_time or query.end_time:
            time_filter = {"range": {"@timestamp": {}}}
            if query.start_time:
                time_filter["range"]["@timestamp"]["gte"] = query.start_time.isoformat()
            if query.end_time:
                time_filter["range"]["@timestamp"]["lte"] = query.end_time.isoformat()
            es_query["query"]["bool"]["must"].append(time_filter)
        
        # Execute search
        response = await es_client.search(
            index=query.index_pattern,
            body=es_query
        )
        
        # Process results
        hits = response["hits"]["hits"]
        results = []
        
        for hit in hits:
            log_entry = hit["_source"]
            log_entry["_id"] = hit["_id"]
            log_entry["_index"] = hit["_index"]
            results.append(log_entry)
        
        return {
            "total": response["hits"]["total"]["value"],
            "results": results,
            "took": response["took"],
            "query_info": {
                "index_pattern": query.index_pattern,
                "query": query.query,
                "time_range": f"{query.start_time} to {query.end_time}" if query.start_time else "all time"
            }
        }
        
    except Exception as e:
        logger.error("Log search failed", exc_info=e, query=query.dict())
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

@app.get("/logs/recent")
async def get_recent_logs(
    minutes: int = Query(60, description="Number of minutes to look back"),
    service: Optional[str] = Query(None, description="Filter by service"),
    log_level: Optional[str] = Query(None, description="Filter by log level"),
    limit: int = Query(100, description="Maximum number of results", le=500),
    user = Depends(get_current_user)
):
    """Get recent logs with optional filtering"""
    try:
        # Build query
        must_clauses = [
            {
                "range": {
                    "@timestamp": {
                        "gte": f"now-{minutes}m"
                    }
                }
            }
        ]
        
        if service:
            must_clauses.append({"term": {"service": service}})
        
        if log_level:
            must_clauses.append({"term": {"log_level": log_level}})
        
        query = {
            "query": {
                "bool": {
                    "must": must_clauses
                }
            },
            "sort": [
                {"@timestamp": {"order": "desc"}}
            ],
            "size": limit
        }
        
        response = await es_client.search(
            index="logs-*",
            body=query
        )
        
        results = []
        for hit in response["hits"]["hits"]:
            log_entry = hit["_source"]
            log_entry["_id"] = hit["_id"]
            results.append(log_entry)
        
        return {
            "total": response["hits"]["total"]["value"],
            "results": results,
            "filters": {
                "minutes": minutes,
                "service": service,
                "log_level": log_level
            }
        }
        
    except Exception as e:
        logger.error("Recent logs query failed", exc_info=e)
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")

@app.post("/logs/analyze")
async def analyze_logs(
    analysis_request: LogAnalysisRequest,
    user = Depends(get_current_user)
):
    """Perform log analysis based on specified criteria"""
    try:
        analysis_type = analysis_request.analysis_type
        
        if analysis_type == "error_analysis":
            return await perform_error_analysis(analysis_request)
        elif analysis_type == "performance_analysis":
            return await perform_performance_analysis(analysis_request)
        elif analysis_type == "security_analysis":
            return await perform_security_analysis(analysis_request)
        elif analysis_type == "trend_analysis":
            return await perform_trend_analysis(analysis_request)
        else:
            raise HTTPException(status_code=400, detail=f"Unknown analysis type: {analysis_type}")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Log analysis failed", exc_info=e, request=analysis_request.dict())
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

@app.get("/logs/services")
async def get_services(user = Depends(get_current_user)):
    """Get list of services that have logs"""
    try:
        query = {
            "aggs": {
                "services": {
                    "terms": {
                        "field": "service",
                        "size": 100
                    }
                }
            },
            "size": 0
        }
        
        response = await es_client.search(
            index="logs-*",
            body=query
        )
        
        services = []
        if "aggregations" in response:
            buckets = response["aggregations"]["services"]["buckets"]
            services = [bucket["key"] for bucket in buckets]
        
        return {"services": services}
        
    except Exception as e:
        logger.error("Failed to get services", exc_info=e)
        raise HTTPException(status_code=500, detail=f"Failed to get services: {str(e)}")

@app.get("/logs/metrics")
async def get_log_metrics(
    time_range: str = Query("1h", description="Time range (1h, 24h, 7d)"),
    user = Depends(get_current_user)
):
    """Get aggregated log metrics and statistics"""
    try:
        # Convert time range to Elasticsearch format
        time_map = {"1h": "now-1h", "24h": "now-24h", "7d": "now-7d"}
        es_time_range = time_map.get(time_range, "now-1h")
        
        query = {
            "query": {
                "range": {
                    "@timestamp": {
                        "gte": es_time_range
                    }
                }
            },
            "aggs": {
                "log_levels": {
                    "terms": {
                        "field": "log_level",
                        "size": 10
                    }
                },
                "services": {
                    "terms": {
                        "field": "service", 
                        "size": 20
                    }
                },
                "errors_over_time": {
                    "filter": {
                        "terms": {
                            "log_level": ["ERROR", "FATAL", "CRITICAL"]
                        }
                    },
                    "aggs": {
                        "timeline": {
                            "date_histogram": {
                                "field": "@timestamp",
                                "calendar_interval": "1h"
                            }
                        }
                    }
                },
                "log_volume": {
                    "date_histogram": {
                        "field": "@timestamp",
                        "calendar_interval": "1h"
                    }
                }
            },
            "size": 0
        }
        
        response = await es_client.search(
            index="logs-*",
            body=query
        )
        
        return {
            "total_logs": response["hits"]["total"]["value"],
            "time_range": time_range,
            "log_levels": response["aggregations"]["log_levels"]["buckets"],
            "services": response["aggregations"]["services"]["buckets"],
            "errors_timeline": response["aggregations"]["errors_over_time"]["timeline"]["buckets"],
            "log_volume": response["aggregations"]["log_volume"]["buckets"]
        }
        
    except Exception as e:
        logger.error("Failed to get log metrics", exc_info=e)
        raise HTTPException(status_code=500, detail=f"Failed to get metrics: {str(e)}")

@app.get("/logs/errors")
async def get_error_summary(
    hours: int = Query(24, description="Hours to look back"),
    group_by: str = Query("service", description="Field to group errors by"),
    user = Depends(get_current_user)
):
    """Get error summary and statistics"""
    try:
        query = {
            "query": {
                "bool": {
                    "must": [
                        {
                            "range": {
                                "@timestamp": {
                                    "gte": f"now-{hours}h"
                                }
                            }
                        },
                        {
                            "terms": {
                                "log_level": ["ERROR", "FATAL", "CRITICAL"]
                            }
                        }
                    ]
                }
            },
            "aggs": {
                "error_groups": {
                    "terms": {
                        "field": group_by,
                        "size": 50
                    },
                    "aggs": {
                        "error_types": {
                            "terms": {
                                "field": "log_level",
                                "size": 10
                            }
                        },
                        "timeline": {
                            "date_histogram": {
                                "field": "@timestamp",
                                "calendar_interval": "1h"
                            }
                        }
                    }
                },
                "top_errors": {
                    "terms": {
                        "field": "message.keyword",
                        "size": 10
                    }
                }
            },
            "size": 0
        }
        
        response = await es_client.search(
            index="error-logs-*",
            body=query
        )
        
        return {
            "total_errors": response["hits"]["total"]["value"],
            "time_range": f"{hours}h",
            "grouped_by": group_by,
            "error_groups": response["aggregations"]["error_groups"]["buckets"],
            "top_error_messages": response["aggregations"]["top_errors"]["buckets"]
        }
        
    except Exception as e:
        logger.error("Failed to get error summary", exc_info=e)
        raise HTTPException(status_code=500, detail=f"Failed to get error summary: {str(e)}")

# Helper functions
async def check_elasticsearch_health():
    """Check Elasticsearch cluster health"""
    try:
        health = await es_client.cluster.health()
        return health["status"] in ["green", "yellow"]
    except:
        return False

def check_redis_health():
    """Check Redis connectivity"""
    try:
        return redis_client.ping()
    except:
        return False

async def perform_error_analysis(request: LogAnalysisRequest):
    """Perform error pattern analysis"""
    # Implementation for error analysis
    time_range_map = {"1h": "now-1h", "24h": "now-24h", "7d": "now-7d"}
    es_time = time_range_map.get(request.time_range, "now-1h")
    
    query = {
        "query": {
            "bool": {
                "must": [
                    {"range": {"@timestamp": {"gte": es_time}}},
                    {"terms": {"log_level": ["ERROR", "FATAL", "CRITICAL"]}}
                ]
            }
        },
        "aggs": {
            "error_patterns": {
                "terms": {
                    "field": "message.keyword",
                    "size": 20
                }
            },
            "services_affected": {
                "terms": {
                    "field": "service",
                    "size": 10
                }
            },
            "error_timeline": {
                "date_histogram": {
                    "field": "@timestamp",
                    "calendar_interval": "1h"
                }
            }
        },
        "size": 0
    }
    
    if request.services:
        query["query"]["bool"]["must"].append(
            {"terms": {"service": request.services}}
        )
    
    response = await es_client.search(index="error-logs-*", body=query)
    
    return {
        "analysis_type": "error_analysis",
        "total_errors": response["hits"]["total"]["value"],
        "time_range": request.time_range,
        "error_patterns": response["aggregations"]["error_patterns"]["buckets"],
        "services_affected": response["aggregations"]["services_affected"]["buckets"],
        "error_timeline": response["aggregations"]["error_timeline"]["buckets"]
    }

async def perform_performance_analysis(request: LogAnalysisRequest):
    """Perform performance analysis"""
    # Implementation for performance analysis
    time_range_map = {"1h": "now-1h", "24h": "now-24h", "7d": "now-7d"}
    es_time = time_range_map.get(request.time_range, "now-1h")
    
    query = {
        "query": {
            "bool": {
                "must": [
                    {"range": {"@timestamp": {"gte": es_time}}},
                    {"exists": {"field": "response_time"}}
                ]
            }
        },
        "aggs": {
            "response_time_stats": {
                "stats": {
                    "field": "response_time"
                }
            },
            "slow_requests": {
                "filter": {
                    "range": {
                        "response_time": {"gte": 5000}
                    }
                },
                "aggs": {
                    "by_service": {
                        "terms": {
                            "field": "service",
                            "size": 10
                        }
                    }
                }
            },
            "response_time_percentiles": {
                "percentiles": {
                    "field": "response_time",
                    "percents": [50, 90, 95, 99]
                }
            }
        },
        "size": 0
    }
    
    response = await es_client.search(index="logs-*", body=query)
    
    return {
        "analysis_type": "performance_analysis",
        "time_range": request.time_range,
        "response_time_stats": response["aggregations"]["response_time_stats"],
        "slow_requests": response["aggregations"]["slow_requests"],
        "percentiles": response["aggregations"]["response_time_percentiles"]["values"]
    }

async def perform_security_analysis(request: LogAnalysisRequest):
    """Perform security event analysis"""
    # Implementation for security analysis
    time_range_map = {"1h": "now-1h", "24h": "now-24h", "7d": "now-7d"}
    es_time = time_range_map.get(request.time_range, "now-1h")
    
    query = {
        "query": {
            "bool": {
                "must": [
                    {"range": {"@timestamp": {"gte": es_time}}},
                    {"exists": {"field": "security_category"}}
                ]
            }
        },
        "aggs": {
            "security_events": {
                "terms": {
                    "field": "event_type",
                    "size": 20
                }
            },
            "failed_logins": {
                "filter": {
                    "bool": {
                        "must": [
                            {"term": {"event_type": "authentication"}},
                            {"term": {"auth_result": "failed"}}
                        ]
                    }
                },
                "aggs": {
                    "by_user": {
                        "terms": {
                            "field": "username",
                            "size": 10
                        }
                    },
                    "by_ip": {
                        "terms": {
                            "field": "client_ip_hash",
                            "size": 10
                        }
                    }
                }
            }
        },
        "size": 0
    }
    
    response = await es_client.search(index="security-logs-*", body=query)
    
    return {
        "analysis_type": "security_analysis",
        "time_range": request.time_range,
        "total_security_events": response["hits"]["total"]["value"],
        "security_events": response["aggregations"]["security_events"]["buckets"],
        "failed_logins": response["aggregations"]["failed_logins"]
    }

async def perform_trend_analysis(request: LogAnalysisRequest):
    """Perform trend analysis"""
    # Implementation for trend analysis
    return {
        "analysis_type": "trend_analysis",
        "message": "Trend analysis implementation coming soon"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8080, reload=True)

#!/usr/bin/env python3

import asyncio
import psutil
import time
import multiprocessing
from typing import Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta

from ..framework.base_experiment import BaseExperiment
from ..framework.safety import SafetyController
from ..framework.metrics import MetricsCollector

@dataclass
class CPUStressConfig:
    cpu_percent: int = 80  # Target CPU utilization percentage
    duration: int = 60     # Duration in seconds
    workers: Optional[int] = None  # Number of worker processes (default: CPU count)
    target_pids: Optional[list] = None  # Specific process IDs to stress

class CPUStressExperiment(BaseExperiment):
    """
    CPU stress chaos experiment that consumes CPU resources to test system behavior
    under high CPU load conditions.
    """
    
    def __init__(self, config: CPUStressConfig):
        super().__init__(
            name="CPU Stress Test",
            description="Generates high CPU load to test system resilience",
            type="CPU_STRESS"
        )
        self.config = config
        self.worker_processes = []
        self.original_cpu_usage = 0.0
        
    async def validate_parameters(self) -> Dict[str, Any]:
        """Validate experiment parameters"""
        validation_result = {"valid": True, "errors": []}
        
        if self.config.cpu_percent < 10 or self.config.cpu_percent > 95:
            validation_result["errors"].append(
                "CPU percentage must be between 10% and 95%"
            )
            validation_result["valid"] = False
            
        if self.config.duration < 10 or self.config.duration > 3600:
            validation_result["errors"].append(
                "Duration must be between 10 seconds and 1 hour"
            )
            validation_result["valid"] = False
            
        if self.config.workers and self.config.workers > multiprocessing.cpu_count() * 2:
            validation_result["errors"].append(
                f"Worker count cannot exceed {multiprocessing.cpu_count() * 2}"
            )
            validation_result["valid"] = False
            
        return validation_result
    
    async def pre_flight_check(self) -> Dict[str, Any]:
        """Perform pre-flight safety checks"""
        checks = {"safe": True, "warnings": [], "blockers": []}
        
        # Check current CPU usage
        current_cpu = psutil.cpu_percent(interval=1)
        self.original_cpu_usage = current_cpu
        
        if current_cpu > 70:
            checks["warnings"].append(
                f"Current CPU usage is already high ({current_cpu:.1f}%)"
            )
            
        if current_cpu > 85:
            checks["blockers"].append(
                "Current CPU usage too high to safely run experiment"
            )
            checks["safe"] = False
            
        # Check available memory
        memory = psutil.virtual_memory()
        if memory.percent > 90:
            checks["blockers"].append(
                "Memory usage too high - risk of system instability"
            )
            checks["safe"] = False
            
        # Check disk space
        disk = psutil.disk_usage('/')
        if disk.percent > 95:
            checks["warnings"].append(
                "Low disk space - may affect logging and metrics"
            )
            
        return checks
    
    async def setup(self) -> Dict[str, Any]:
        """Setup the experiment environment"""
        self.logger.info("Setting up CPU stress experiment", config=self.config.__dict__)
        
        # Determine number of workers
        if not self.config.workers:
            self.config.workers = max(1, multiprocessing.cpu_count() - 1)
            
        # Record baseline metrics
        baseline_metrics = {
            "cpu_percent": psutil.cpu_percent(interval=1),
            "load_avg": psutil.getloadavg() if hasattr(psutil, 'getloadavg') else [0, 0, 0],
            "memory_percent": psutil.virtual_memory().percent,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        self.logger.info("Baseline metrics recorded", metrics=baseline_metrics)
        
        return {
            "setup_complete": True,
            "workers_planned": self.config.workers,
            "baseline_metrics": baseline_metrics
        }
    
    async def execute(self, safety_controller: SafetyController, metrics_collector: MetricsCollector) -> Dict[str, Any]:
        """Execute the CPU stress experiment"""
        self.logger.info("Starting CPU stress experiment")
        
        start_time = datetime.utcnow()
        
        try:
            # Start CPU stress workers
            await self._start_cpu_stress_workers()
            
            # Monitor experiment progress
            elapsed = 0
            interval = 5  # Check every 5 seconds
            
            while elapsed < self.config.duration:
                # Check safety conditions
                safety_status = await safety_controller.check_safety(self)
                if not safety_status["safe"]:
                    self.logger.warning("Safety check failed", status=safety_status)
                    await self._stop_cpu_stress_workers()
                    raise Exception(f"Safety violation: {safety_status['message']}")
                
                # Collect metrics
                current_metrics = {
                    "cpu_percent": psutil.cpu_percent(interval=1),
                    "load_avg": psutil.getloadavg() if hasattr(psutil, 'getloadavg') else [0, 0, 0],
                    "memory_percent": psutil.virtual_memory().percent,
                    "active_workers": len(self.worker_processes),
                    "elapsed_time": elapsed,
                    "timestamp": datetime.utcnow().isoformat()
                }
                
                await metrics_collector.record_metrics(self.experiment_id, current_metrics)
                
                self.logger.info("Experiment progress", metrics=current_metrics, elapsed=elapsed)
                
                # Wait for next check
                await asyncio.sleep(interval)
                elapsed += interval
            
            # Stop workers
            await self._stop_cpu_stress_workers()
            
            end_time = datetime.utcnow()
            duration = (end_time - start_time).total_seconds()
            
            # Final metrics
            final_metrics = {
                "cpu_percent": psutil.cpu_percent(interval=1),
                "load_avg": psutil.getloadavg() if hasattr(psutil, 'getloadavg') else [0, 0, 0],
                "memory_percent": psutil.virtual_memory().percent,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            return {
                "success": True,
                "duration": duration,
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "final_metrics": final_metrics,
                "workers_used": self.config.workers,
                "target_cpu_percent": self.config.cpu_percent
            }
            
        except Exception as e:
            self.logger.error("CPU stress experiment failed", exc_info=e)
            await self._stop_cpu_stress_workers()
            raise
    
    async def cleanup(self) -> Dict[str, Any]:
        """Cleanup experiment resources"""
        self.logger.info("Cleaning up CPU stress experiment")
        
        # Ensure all workers are stopped
        await self._stop_cpu_stress_workers()
        
        # Wait for CPU to stabilize
        await asyncio.sleep(10)
        
        # Record cleanup metrics
        cleanup_metrics = {
            "cpu_percent": psutil.cpu_percent(interval=1),
            "memory_percent": psutil.virtual_memory().percent,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        return {
            "cleanup_complete": True,
            "final_metrics": cleanup_metrics,
            "workers_terminated": len(self.worker_processes)
        }
    
    async def rollback(self) -> Dict[str, Any]:
        """Rollback any changes (same as cleanup for CPU stress)"""
        return await self.cleanup()
    
    async def get_impact_assessment(self) -> Dict[str, Any]:
        """Assess the impact of the experiment"""
        current_cpu = psutil.cpu_percent(interval=1)
        cpu_increase = current_cpu - self.original_cpu_usage
        
        return {
            "blast_radius": {
                "scope": "system-wide",
                "affected_resources": ["CPU", "system responsiveness"],
                "severity": "medium" if cpu_increase > 50 else "low"
            },
            "performance_impact": {
                "cpu_usage_increase": cpu_increase,
                "estimated_response_time_impact": cpu_increase * 0.02,  # Rough estimate
                "system_load_factor": current_cpu / 100
            },
            "risk_level": "medium" if self.config.cpu_percent > 80 else "low"
        }
    
    async def _start_cpu_stress_workers(self):
        """Start CPU stress worker processes"""
        self.logger.info(f"Starting {self.config.workers} CPU stress workers")
        
        for i in range(self.config.workers):
            process = multiprocessing.Process(
                target=self._cpu_stress_worker,
                args=(self.config.cpu_percent / self.config.workers,)
            )
            process.start()
            self.worker_processes.append(process)
            
        self.logger.info(f"Started {len(self.worker_processes)} CPU stress workers")
    
    async def _stop_cpu_stress_workers(self):
        """Stop all CPU stress worker processes"""
        self.logger.info("Stopping CPU stress workers")
        
        for process in self.worker_processes:
            if process.is_alive():
                process.terminate()
                
        # Wait for processes to terminate gracefully
        for process in self.worker_processes:
            process.join(timeout=5)
            if process.is_alive():
                process.kill()  # Force kill if not terminated
                
        self.worker_processes.clear()
        self.logger.info("All CPU stress workers stopped")
    
    @staticmethod
    def _cpu_stress_worker(target_percent: float):
        """Worker function that generates CPU load"""
        def cpu_bound_task():
            # Simple CPU-intensive calculation
            x = 0
            while True:
                x += 1
                x = x % 1000000
        
        # Calculate work/sleep ratio to achieve target CPU percentage
        work_time = target_percent / 100.0
        sleep_time = 1.0 - work_time
        
        while True:
            start = time.time()
            
            # Do CPU-intensive work
            end_work = start + work_time
            while time.time() < end_work:
                cpu_bound_task()
            
            # Sleep to control CPU usage
            if sleep_time > 0:
                time.sleep(sleep_time)

# src/resilience_manager.py
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Set, Optional, Callable
import logging
from collections import defaultdict


class ComponentStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILING = "failing"
    FAILED = "failed"


class FailureType(Enum):
    TIMEOUT = "timeout"
    ERROR = "error"
    RESOURCE_EXHAUSTED = "resource_exhausted"
    DEPENDENCY_FAILED = "dependency_failed"


@dataclass
class ComponentHealth:
    name: str
    status: ComponentStatus
    error_rate: float
    response_time: float
    last_check: datetime
    dependencies: Set[str]
    failures: List[FailureType] = field(default_factory=list)
    recovery_attempts: int = 0


@dataclass
class SystemHealth:
    healthy_components: List[str]
    degraded_components: List[str]
    failed_components: List[str]
    overall_status: ComponentStatus
    failure_cascade_risk: bool


class SystemResilienceManager:
    def __init__(self):
        # Initialize logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger("SystemResilienceManager")

        # Component health tracking
        self.components: Dict[str, ComponentHealth] = {}

        # Component dependencies
        self.dependencies: Dict[str, Set[str]] = defaultdict(set)

        # Recovery handlers
        self.recovery_handlers: Dict[str, Callable] = {}

        # Health check thresholds
        self.error_threshold = 0.15  # 15% error rate
        self.response_time_threshold = 2.0  # 2 seconds

        # Component metrics
        self.error_counts: Dict[str, int] = defaultdict(int)
        self.request_counts: Dict[str, int] = defaultdict(int)
        self.response_times: Dict[str, List[float]] = defaultdict(list)

        # Start monitoring
        asyncio.create_task(self._monitor_health())

    def register_component(self,
                           name: str,
                           dependencies: Optional[List[str]] = None):
        """Register component for health monitoring"""
        self.components[name] = ComponentHealth(
            name=name,
            status=ComponentStatus.HEALTHY,
            error_rate=0.0,
            response_time=0.0,
            last_check=datetime.now(),
            dependencies=set(dependencies or [])
        )

        if dependencies:
            self.dependencies[name].update(dependencies)

    def register_recovery_handler(self,
                                  component: str,
                                  handler: Callable):
        """Register recovery handler for component"""
        if component not in self.components:
            raise ValueError(f"Unknown component: {component}")
        self.recovery_handlers[component] = handler

    async def _monitor_health(self):
        """Monitor component health and handle failures"""
        while True:
            try:
                for component in self.components.values():
                    await self._check_component_health(component)
                    if component.status in [ComponentStatus.FAILING,
                                            ComponentStatus.FAILED]:
                        await self._handle_component_failure(component)

                await asyncio.sleep(10)  # Check every 10 seconds
            except Exception as e:
                self.logger.error(f"Health monitor error: {str(e)}")
                await asyncio.sleep(5)

    async def _check_component_health(self, component: ComponentHealth):
        """Check health of individual component"""
        try:
            # Calculate error rate
            total_requests = (self.request_counts[component.name] or 1)
            error_rate = self.error_counts[component.name] / total_requests

            # Calculate average response time
            times = self.response_times[component.name]
            avg_response_time = sum(times) / len(times) if times else 0

            # Update metrics
            component.error_rate = error_rate
            component.response_time = avg_response_time
            component.last_check = datetime.now()

            # Check dependencies
            dependency_failures = [
                dep for dep in component.dependencies
                if self.components[dep].status == ComponentStatus.FAILED
            ]

            # Determine status
            if dependency_failures:
                component.status = ComponentStatus.FAILED
                component.failures.append(FailureType.DEPENDENCY_FAILED)
            elif error_rate >= self.error_threshold * 2:
                component.status = ComponentStatus.FAILED
            elif error_rate >= self.error_threshold:
                component.status = ComponentStatus.FAILING
            elif avg_response_time >= self.response_time_threshold * 2:
                component.status = ComponentStatus.FAILING
            elif avg_response_time >= self.response_time_threshold:
                component.status = ComponentStatus.DEGRADED
            else:
                component.status = ComponentStatus.HEALTHY
                component.failures.clear()

        except Exception as e:
            self.logger.error(f"Health check failed for {component.name}: {str(e)}")
            component.status = ComponentStatus.FAILING
            component.failures.append(FailureType.ERROR)

    async def _handle_component_failure(self, component: ComponentHealth):
        """Handle component failure with recovery attempt"""
        try:
            self.logger.warning(
                f"Component {component.name} is {component.status.value}"
            )

            # Check for cascading failures
            if self._detect_failure_cascade(component.name):
                self.logger.error(
                    f"Detected failure cascade from {component.name}"
                )
                await self._prevent_cascade(component.name)
                return

            # Attempt recovery if handler exists
            if component.name in self.recovery_handlers:
                component.recovery_attempts += 1
                try:
                    handler = self.recovery_handlers[component.name]
                    await handler()
                    self.logger.info(
                        f"Recovery attempted for {component.name}"
                    )
                except Exception as e:
                    self.logger.error(
                        f"Recovery failed for {component.name}: {str(e)}"
                    )

            # Implement graceful degradation
            await self._degrade_gracefully(component)

        except Exception as e:
            self.logger.error(
                f"Error handling failure of {component.name}: {str(e)}"
            )

    def _detect_failure_cascade(self, component: str) -> bool:
        """Detect potential cascading failures"""
        failing_deps = set()

        def check_dependencies(comp: str, seen: Set[str]):
            if comp in seen:
                return
            seen.add(comp)

            component_health = self.components[comp]
            if component_health.status in [ComponentStatus.FAILING,
                                           ComponentStatus.FAILED]:
                failing_deps.add(comp)

            for dep in self.dependencies[comp]:
                check_dependencies(dep, seen)

        check_dependencies(component, set())
        return len(failing_deps) >= 2  # Consider cascade if 2+ failing components

    async def _prevent_cascade(self, component: str):
        """Prevent cascade failure by isolating component"""
        # Find all dependent components
        dependents = set()
        for comp, deps in self.dependencies.items():
            if component in deps:
                dependents.add(comp)

        # Implement graceful degradation for dependents
        for dependent in dependents:
            await self._degrade_gracefully(self.components[dependent])

    async def _degrade_gracefully(self, component: ComponentHealth):
        """Implement graceful degradation strategies"""
        if component.status == ComponentStatus.FAILED:
            # Full failure - disable component
            component.status = ComponentStatus.FAILED
            self.logger.warning(f"Component {component.name} disabled")
        else:
            # Partial degradation
            component.status = ComponentStatus.DEGRADED
            self.logger.info(
                f"Component {component.name} operating in degraded mode"
            )

    async def get_system_health(self) -> SystemHealth:
        """Get overall system health status"""
        healthy = []
        degraded = []
        failed = []

        for component in self.components.values():
            if component.status == ComponentStatus.HEALTHY:
                healthy.append(component.name)
            elif component.status in [ComponentStatus.DEGRADED,
                                      ComponentStatus.FAILING]:
                degraded.append(component.name)
            else:
                failed.append(component.name)

        # Determine overall status
        if failed:
            overall = ComponentStatus.FAILED
        elif degraded:
            overall = ComponentStatus.DEGRADED
        else:
            overall = ComponentStatus.HEALTHY

        # Check for cascade risk
        cascade_risk = any(
            self._detect_failure_cascade(comp)
            for comp in failed + degraded
        )

        return SystemHealth(
            healthy_components=healthy,
            degraded_components=degraded,
            failed_components=failed,
            overall_status=overall,
            failure_cascade_risk=cascade_risk
        )

    async def record_request(self, component: str, duration: float,
                             error: bool = False):
        """Record request metrics for component"""
        if component not in self.components:
            raise ValueError(f"Unknown component: {component}")

        self.request_counts[component] += 1
        if error:
            self.error_counts[component] += 1

        self.response_times[component].append(duration)
        if len(self.response_times[component]) > 100:
            self.response_times[component] = self.response_times[component][-100:]

    async def reset_component(self, component: str):
        """Manually reset component status"""
        if component not in self.components:
            raise ValueError(f"Unknown component: {component}")

        comp = self.components[component]
        comp.status = ComponentStatus.HEALTHY
        comp.failures.clear()
        comp.recovery_attempts = 0

        self.error_counts[component] = 0
        self.request_counts[component] = 0
        self.response_times[component].clear()

        self.logger.info(f"Component {component} manually reset")

    async def get_component_metrics(self, component: str) -> Dict:
        """Get detailed metrics for component"""
        if component not in self.components:
            raise ValueError(f"Unknown component: {component}")

        comp = self.components[component]
        return {
            'name': comp.name,
            'status': comp.status.value,
            'error_rate': comp.error_rate,
            'response_time': comp.response_time,
            'last_check': comp.last_check.isoformat(),
            'dependencies': list(comp.dependencies),
            'failures': [f.value for f in comp.failures],
            'recovery_attempts': comp.recovery_attempts,
            'requests': self.request_counts[component],
            'errors': self.error_counts[component]
        }
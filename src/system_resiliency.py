# src/system_resiliency.py
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, Optional, List, Callable, Any
import logging
from collections import defaultdict


class CircuitState(Enum):
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing recovery


class ServiceStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"


@dataclass
class CircuitBreaker:
    name: str
    failure_threshold: int = 5
    recovery_timeout: int = 60  # seconds
    half_open_timeout: int = 30  # seconds
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    last_failure_time: Optional[datetime] = None
    last_success_time: Optional[datetime] = None


@dataclass
class FailureEvent:
    service: str
    error_type: str
    timestamp: datetime
    details: dict
    recovery_action: Optional[str] = None


@dataclass
class SystemHealth:
    status: ServiceStatus
    circuit_states: Dict[str, CircuitState]
    error_rates: Dict[str, float]
    response_times: Dict[str, float]
    degraded_services: List[str]


class SystemResiliency:
    def __init__(self):
        # Initialize logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger("SystemResiliency")

        # Circuit breakers for different services
        self.circuit_breakers: Dict[str, CircuitBreaker] = {
            "eth_network": CircuitBreaker("Ethereum Network",
                                          failure_threshold=5,
                                          recovery_timeout=300),
            "btc_network": CircuitBreaker("Bitcoin Network",
                                          failure_threshold=5,
                                          recovery_timeout=300),
            "key_management": CircuitBreaker("Key Management",
                                             failure_threshold=3,
                                             recovery_timeout=120),
            "payment_processor": CircuitBreaker("Payment Processor",
                                                failure_threshold=3,
                                                recovery_timeout=180),
        }

        # Failure tracking
        self.failures: List[FailureEvent] = []
        self.error_counters = defaultdict(int)

        # Service response times
        self.response_times: Dict[str, List[float]] = defaultdict(list)

        # Recovery handlers
        self.recovery_handlers: Dict[str, Callable] = {}

        # Start monitoring
        asyncio.create_task(self._monitor_circuit_states())

    async def _monitor_circuit_states(self):
        """Monitor and update circuit breaker states"""
        while True:
            try:
                current_time = datetime.now()

                for breaker in self.circuit_breakers.values():
                    if breaker.state == CircuitState.OPEN:
                        # Check if recovery timeout has elapsed
                        if (breaker.last_failure_time and
                                (current_time - breaker.last_failure_time).total_seconds()
                                >= breaker.recovery_timeout):
                            breaker.state = CircuitState.HALF_OPEN
                            self.logger.info(f"Circuit {breaker.name} entering half-open state")

                    elif breaker.state == CircuitState.HALF_OPEN:
                        # Check if half-open timeout has elapsed without failures
                        if (breaker.last_success_time and
                                (current_time - breaker.last_success_time).total_seconds()
                                >= breaker.half_open_timeout):
                            breaker.state = CircuitState.CLOSED
                            breaker.failure_count = 0
                            self.logger.info(f"Circuit {breaker.name} closed after recovery")

                await asyncio.sleep(1)  # Check every second

            except Exception as e:
                self.logger.error(f"Error in circuit monitor: {str(e)}")
                await asyncio.sleep(5)

    async def execute_with_resilience(self,
                                      service: str,
                                      operation: Callable,
                                      *args,
                                      fallback: Optional[Callable] = None,
                                      **kwargs) -> Any:
        """Execute operation with circuit breaker and failover"""
        breaker = self.circuit_breakers.get(service)
        if not breaker:
            raise ValueError(f"No circuit breaker configured for service: {service}")

        start_time = datetime.now()

        try:
            if breaker.state == CircuitState.OPEN:
                raise Exception(f"Circuit breaker open for {service}")

            result = await operation(*args, **kwargs)

            # Record success
            breaker.last_success_time = datetime.now()
            if breaker.state == CircuitState.HALF_OPEN:
                breaker.failure_count = 0

            # Record response time
            duration = (datetime.now() - start_time).total_seconds()
            self.response_times[service].append(duration)

            return result

        except Exception as e:
            self.logger.error(f"Operation failed for {service}: {str(e)}")

            # Record failure
            breaker.failure_count += 1
            breaker.last_failure_time = datetime.now()

            # Update failure tracking
            self.error_counters[service] += 1
            self.failures.append(FailureEvent(
                service=service,
                error_type=type(e).__name__,
                timestamp=datetime.now(),
                details={'error': str(e)}
            ))

            # Check circuit breaker state
            if (breaker.state == CircuitState.CLOSED and
                    breaker.failure_count >= breaker.failure_threshold):
                breaker.state = CircuitState.OPEN
                self.logger.warning(f"Circuit breaker opened for {service}")

                # Attempt recovery if handler exists
                if service in self.recovery_handlers:
                    asyncio.create_task(self._attempt_recovery(service))

            # Use fallback if provided
            if fallback:
                try:
                    return await fallback(*args, **kwargs)
                except Exception as fallback_error:
                    self.logger.error(f"Fallback also failed: {str(fallback_error)}")

            raise

    async def _attempt_recovery(self, service: str):
        """Attempt to recover failed service"""
        try:
            handler = self.recovery_handlers[service]
            self.logger.info(f"Attempting recovery for {service}")

            await handler()

            # Record recovery attempt
            self.failures[-1].recovery_action = "automatic_recovery_attempted"

        except Exception as e:
            self.logger.error(f"Recovery failed for {service}: {str(e)}")

    def register_recovery_handler(self, service: str, handler: Callable):
        """Register recovery handler for service"""
        self.recovery_handlers[service] = handler

    async def get_system_health(self) -> SystemHealth:
        """Get current system health status"""
        degraded_services = []
        error_rates = {}
        avg_response_times = {}

        for service in self.circuit_breakers:
            # Calculate error rate
            total_requests = (
                    len(self.response_times.get(service, [])) +
                    self.error_counters.get(service, 0)
            )
            if total_requests > 0:
                error_rate = self.error_counters.get(service, 0) / total_requests
                error_rates[service] = error_rate

                if error_rate > 0.1:  # 10% error rate threshold
                    degraded_services.append(service)

            # Calculate average response time
            if service in self.response_times and self.response_times[service]:
                avg_response_times[service] = (
                        sum(self.response_times[service]) /
                        len(self.response_times[service])
                )

        # Determine overall status
        if any(cb.state == CircuitState.OPEN
               for cb in self.circuit_breakers.values()):
            status = ServiceStatus.FAILED
        elif degraded_services:
            status = ServiceStatus.DEGRADED
        else:
            status = ServiceStatus.HEALTHY

        return SystemHealth(
            status=status,
            circuit_states={
                name: cb.state for name, cb in self.circuit_breakers.items()
            },
            error_rates=error_rates,
            response_times=avg_response_times,
            degraded_services=degraded_services
        )

    async def get_recent_failures(self,
                                  hours: int = 24,
                                  service: Optional[str] = None) -> List[FailureEvent]:
        """Get recent failure events"""
        cutoff = datetime.now() - timedelta(hours=hours)
        failures = [f for f in self.failures if f.timestamp >= cutoff]

        if service:
            failures = [f for f in failures if f.service == service]

        return sorted(failures, key=lambda x: x.timestamp, reverse=True)

    def reset_circuit_breaker(self, service: str):
        """Manually reset circuit breaker to closed state"""
        if service not in self.circuit_breakers:
            raise ValueError(f"Unknown service: {service}")

        breaker = self.circuit_breakers[service]
        breaker.state = CircuitState.CLOSED
        breaker.failure_count = 0
        breaker.last_failure_time = None
        self.logger.info(f"Circuit breaker manually reset for {service}")

    async def graceful_shutdown(self):
        """Perform graceful system shutdown"""
        self.logger.info("Initiating graceful shutdown...")

        # Wait for any recovery attempts to complete
        pending_recoveries = [
            asyncio.create_task(self._attempt_recovery(service))
            for service, breaker in self.circuit_breakers.items()
            if breaker.state == CircuitState.OPEN
        ]

        if pending_recoveries:
            await asyncio.wait(pending_recoveries, timeout=30)

        # Log final system state
        health = await self.get_system_health()
        self.logger.info(f"Final system status: {health.status.value}")
        for service, state in health.circuit_states.items():
            self.logger.info(f"{service}: {state.value}")
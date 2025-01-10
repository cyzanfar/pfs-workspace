# tests/test_system_resiliency.py
import pytest
import asyncio
from datetime import datetime, timedelta
from src.system_resiliency import (
    SystemResiliency, CircuitState, ServiceStatus,
    CircuitBreaker, FailureEvent
)


@pytest.fixture
async def resiliency():
    system = SystemResiliency()
    yield system
    await system.graceful_shutdown()


class TestSystemResiliency:
    """Test suite for system resiliency features"""

    async def test_circuit_breaker_basic(self, resiliency):
        """Test basic circuit breaker functionality"""

        # Mock failing operation
        async def failing_operation():
            raise Exception("Simulated failure")

        # Attempt operations until circuit opens
        for _ in range(6):  # Threshold is 5
            try:
                await resiliency.execute_with_resilience(
                    "eth_network",
                    failing_operation
                )
            except Exception:
                pass

        # Verify circuit is open
        assert resiliency.circuit_breakers["eth_network"].state == CircuitState.OPEN

        # Verify operation is rejected when circuit is open
        with pytest.raises(Exception) as exc:
            await resiliency.execute_with_resilience(
                "eth_network",
                failing_operation
            )
        assert "Circuit breaker open" in str(exc.value)

    async def test_circuit_breaker_recovery(self, resiliency):
        """Test circuit breaker recovery"""
        success_count = 0

        async def operation():
            nonlocal success_count
            if success_count < 3:  # Fail first 3 attempts
                raise Exception("Simulated failure")
            return "success"

        # Fail until circuit opens
        for _ in range(5):
            try:
                await resiliency.execute_with_resilience(
                    "eth_network",
                    operation
                )
            except Exception:
                pass

        # Verify circuit is open
        breaker = resiliency.circuit_breakers["eth_network"]
        assert breaker.state == CircuitState.OPEN

        # Simulate time passing
        breaker.last_failure_time = (
                datetime.now() - timedelta(seconds=breaker.recovery_timeout + 1)
        )
        await asyncio.sleep(2)  # Allow monitor to update state

        # Should now be half-open
        assert breaker.state == CircuitState.HALF_OPEN

        # Successful operation should start closing the circuit
        success_count = 3  # Allow success
        result = await resiliency.execute_with_resilience(
            "eth_network",
            operation
        )
        assert result == "success"

        # Verify successful recovery
        assert breaker.failure_count == 0

    async def test_fallback_mechanism(self, resiliency):
        """Test fallback operation"""

        async def main_operation():
            raise Exception("Main operation failed")

        async def fallback_operation():
            return "fallback result"

        result = await resiliency.execute_with_resilience(
            "eth_network",
            main_operation,
            fallback=fallback_operation
        )

        assert result == "fallback result"

    async def test_recovery_handler(self, resiliency):
        """Test recovery handler execution"""
        recovery_attempted = False

        async def recovery_handler():
            nonlocal recovery_attempted
            recovery_attempted = True

        resiliency.register_recovery_handler("eth_network", recovery_handler)

        # Trigger failures
        async def failing_operation():
            raise Exception("Simulated failure")

        for _ in range(5):
            try:
                await resiliency.execute_with_resilience(
                    "eth_network",
                    failing_operation
                )
            except Exception:
                pass

        await asyncio.sleep(1)  # Allow recovery to attempt
        assert recovery_attempted

    async def test_system_health_monitoring(self, resiliency):
        """Test system health status"""

        # Simulate some failures
        async def failing_operation():
            raise Exception("Simulated failure")

        for _ in range(3):
            try:
                await resiliency.execute_with_resilience(
                    "eth_network",
                    failing_operation
                )
            except Exception:
                pass

        # Check health status
        health = await resiliency.get_system_health()

        assert health.status == ServiceStatus.DEGRADED
        assert "eth_network" in health.degraded_services
        assert health.error_rates["eth_network"] > 0

    async def test_response_time_tracking(self, resiliency):
        """Test response time tracking"""

        async def slow_operation():
            await asyncio.sleep(0.1)
            return "success"

        # Execute operation several times
        for _ in range(3):
            await resiliency.execute_with_resilience(
                "eth_network",
                slow_operation
            )

        health = await resiliency.get_system_health()
        assert "eth_network" in health.response_times
        assert health.response_times["eth_network"] >= 0.1

    async def test_failure_tracking(self, resiliency):
        """Test failure event tracking"""

        async def failing_operation():
            raise Exception("Simulated failure")

        # Generate some failures
        for _ in range(3):
            try:
                await resiliency.execute_with_resilience(
                    "eth_network",
                    failing_operation
                )
            except Exception:
                pass

        # Check recent failures
        failures = await resiliency.get_recent_failures(hours=1)
        assert len(failures) == 3
        assert all(f.service == "eth_network" for f in failures)
        assert all(isinstance(f.timestamp, datetime) for f in failures)

    async def test_multiple_services(self, resiliency):
        """Test handling multiple service circuits"""

        async def failing_operation():
            raise Exception("Simulated failure")

        # Fail both services
        services = ["eth_network", "btc_network"]
        for service in services:
            for _ in range(5):
                try:
                    await resiliency.execute_with_resilience(
                        service,
                        failing_operation
                    )
                except Exception:
                    pass

        # Verify both circuits are open
        for service in services:
            assert resiliency.circuit_breakers[service].state == CircuitState.OPEN

    async def test_circuit_reset(self, resiliency):
        """Test manual circuit reset"""

        async def failing_operation():
            raise Exception("Simulated failure")

        # Fail until circuit opens
        for _ in range(5):
            try:
                await resiliency.execute_with_resilience(
                    "eth_network",
                    failing_operation
                )
            except Exception:
                pass

        assert resiliency.circuit_breakers["eth_network"].state == CircuitState.OPEN

        # Reset circuit
        resiliency.reset_circuit_breaker("eth_network")

        # Verify circuit is closed
        assert resiliency.circuit_breakers["eth_network"].state == CircuitState.CLOSED
        assert resiliency.circuit_breakers["eth_network"].failure_count == 0

    async def test_graceful_shutdown(self, resiliency):
        """Test graceful shutdown process"""
        recovery_called = False

        async def recovery_handler():
            nonlocal recovery_called
            recovery_called = True
            await asyncio.sleep(0.1)

        resiliency.register_recovery_handler("eth_network", recovery_handler)

        # Open a circuit
        async def failing_operation():
            raise Exception("Simulated failure")

        for _ in range(5):
            try:
                await resiliency.execute_with_resilience(
                    "eth_network",
                    failing_operation
                )
            except Exception:
                pass

        # Initiate shutdown
        await resiliency.graceful_shutdown()

        # Verify recovery was attempted
        assert recovery_called

    async def test_concurrent_operations(self, resiliency):
        """Test handling concurrent operations"""

        async def slow_operation():
            await asyncio.sleep(0.1)
            return "success"

        # Execute multiple operations concurrently
        tasks = [
            resiliency.execute_with_resilience(
                "eth_network",
                slow_operation
            )
            for _ in range(5)
        ]

        results = await asyncio.gather(*tasks)
        assert all(r == "success" for r in results)

        # Verify response times were recorded
        health = await resiliency.get_system_health()
        assert len(resiliency.response_times["eth_network"]) == 5
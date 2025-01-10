# src/integration_test_suite.py
import asyncio
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Set, Any, Callable
import json
import logging

from .key_management import KeyManagement, KeyManagementError
from .security_monitor import SecurityMonitor, SecurityEventType
from .audit_logger import AuditLogger, AuditEventType
from .resilience_manager import SystemResilienceManager, ComponentStatus


class TestScenario(Enum):
    KEY_ROTATION = "key_rotation"
    SECURITY_BREACH = "security_breach"
    SYSTEM_OVERLOAD = "system_overload"
    NETWORK_PARTITION = "network_partition"
    CASCADING_FAILURE = "cascading_failure"
    RECOVERY_PROCEDURE = "recovery_procedure"


@dataclass
class TestResult:
    scenario: TestScenario
    success: bool
    start_time: datetime
    end_time: datetime
    components_tested: List[str]
    error_message: Optional[str] = None
    details: Dict[str, Any] = None


class IntegrationTestSuite:
    def __init__(self,
                 key_manager: KeyManagement,
                 security_monitor: SecurityMonitor,
                 audit_logger: AuditLogger,
                 resilience_manager: SystemResilienceManager):
        # Store component references
        self.key_manager = key_manager
        self.security_monitor = security_monitor
        self.audit_logger = audit_logger
        self.resilience_manager = resilience_manager

        # Initialize logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger("IntegrationTestSuite")

        # Store test results
        self.test_results: List[TestResult] = []

        # Register test scenarios
        self.test_scenarios: Dict[TestScenario, Callable] = {
            TestScenario.KEY_ROTATION: self.test_key_rotation,
            TestScenario.SECURITY_BREACH: self.test_security_breach,
            TestScenario.SYSTEM_OVERLOAD: self.test_system_overload,
            TestScenario.NETWORK_PARTITION: self.test_network_partition,
            TestScenario.CASCADING_FAILURE: self.test_cascading_failure,
            TestScenario.RECOVERY_PROCEDURE: self.test_recovery_procedure
        }

    async def run_test_scenario(self, scenario: TestScenario) -> TestResult:
        """Run specific test scenario"""
        if scenario not in self.test_scenarios:
            raise ValueError(f"Unknown test scenario: {scenario}")

        self.logger.info(f"Starting test scenario: {scenario.value}")
        start_time = datetime.now()

        try:
            test_func = self.test_scenarios[scenario]
            details = await test_func()

            result = TestResult(
                scenario=scenario,
                success=True,
                start_time=start_time,
                end_time=datetime.now(),
                components_tested=details.get('components_tested', []),
                details=details
            )

        except Exception as e:
            self.logger.error(f"Test scenario failed: {str(e)}")
            result = TestResult(
                scenario=scenario,
                success=False,
                start_time=start_time,
                end_time=datetime.now(),
                components_tested=[],
                error_message=str(e)
            )

        self.test_results.append(result)
        return result

    async def test_key_rotation(self) -> Dict:
        """Test key rotation and validation process"""
        components = ['key_management', 'audit_logger']

        # Register key for testing
        test_key = await self.key_manager.generate_new_key('test_password')

        # Record initial state
        initial_state = await self.audit_logger.search_logs(
            event_types=[AuditEventType.KEY_MANAGEMENT]
        )

        # Perform key rotation
        await self.key_manager.rotate_key(
            test_key['key_id'],
            'test_password',
            'new_password'
        )

        # Verify audit logs
        rotation_logs = await self.audit_logger.search_logs(
            event_types=[AuditEventType.KEY_MANAGEMENT]
        )
        assert len(rotation_logs) > len(initial_state)

        # Verify key access
        rotated_key = await self.key_manager.retrieve_key(
            test_key['key_id'],
            'new_password'
        )
        assert rotated_key is not None

        return {
            'components_tested': components,
            'key_id': test_key['key_id'],
            'rotation_logged': True
        }

    async def test_security_breach(self) -> Dict:
        """Test security breach detection and response"""
        components = ['security_monitor', 'audit_logger', 'resilience_manager']

        # Simulate multiple failed login attempts
        for _ in range(5):
            await self.security_monitor.log_event({
                'event_type': SecurityEventType.FAILED_LOGIN,
                'source_ip': '192.168.1.100',
                'user_id': 'test_user',
                'timestamp': datetime.now()
            })

        # Verify security alert generation
        alerts = await self.security_monitor.get_active_alerts()
        assert any(a.event_type == SecurityEventType.FAILED_LOGIN
                   for a in alerts)

        # Check audit logging
        security_logs = await self.audit_logger.search_logs(
            event_types=[AuditEventType.SECURITY]
        )
        assert len(security_logs) >= 5

        # Verify system resilience response
        system_health = await self.resilience_manager.get_system_health()

        return {
            'components_tested': components,
            'alerts_generated': len(alerts),
            'logs_recorded': len(security_logs),
            'system_status': system_health.overall_status.value
        }

    async def test_system_overload(self) -> Dict:
        """Test system behavior under load"""
        components = ['resilience_manager', 'security_monitor', 'audit_logger']

        # Register test component
        self.resilience_manager.register_component('test_component')

        # Simulate high load
        for _ in range(20):
            await self.resilience_manager.record_request(
                'test_component',
                2.0  # High response time
            )

        # Verify degradation detection
        health = await self.resilience_manager.get_system_health()
        assert 'test_component' in health.degraded_components

        # Check security monitoring
        alerts = await self.security_monitor.get_active_alerts()
        performance_alerts = [
            a for a in alerts
            if 'performance' in a.description.lower()
        ]

        return {
            'components_tested': components,
            'system_status': health.overall_status.value,
            'performance_alerts': len(performance_alerts)
        }

    async def test_network_partition(self) -> Dict:
        """Test system resilience during network partition"""
        components = ['resilience_manager', 'key_management']

        # Setup test components
        self.resilience_manager.register_component('network_a')
        self.resilience_manager.register_component('network_b')

        # Simulate network partition
        await self.resilience_manager.record_request(
            'network_a',
            0.0,
            error=True
        )
        await self.resilience_manager.record_request(
            'network_b',
            0.0,
            error=True
        )

        # Verify partition handling
        health = await self.resilience_manager.get_system_health()
        metrics_a = await self.resilience_manager.get_component_metrics('network_a')
        metrics_b = await self.resilience_manager.get_component_metrics('network_b')

        return {
            'components_tested': components,
            'system_status': health.overall_status.value,
            'partition_detected': health.failure_cascade_risk,
            'component_metrics': {
                'network_a': metrics_a,
                'network_b': metrics_b
            }
        }

    async def test_cascading_failure(self) -> Dict:
        """Test cascading failure prevention"""
        components = ['resilience_manager', 'audit_logger']

        # Setup dependent components
        self.resilience_manager.register_component('primary')
        self.resilience_manager.register_component(
            'secondary',
            dependencies=['primary']
        )
        self.resilience_manager.register_component(
            'tertiary',
            dependencies=['secondary']
        )

        # Trigger primary failure
        for _ in range(5):
            await self.resilience_manager.record_request(
                'primary',
                0.0,
                error=True
            )

        # Verify cascade prevention
        health = await self.resilience_manager.get_system_health()
        audit_logs = await self.audit_logger.search_logs(
            event_types=[AuditEventType.SYSTEM]
        )

        return {
            'components_tested': components,
            'cascade_prevented': not health.failure_cascade_risk,
            'affected_components': {
                'primary': 'primary' in health.failed_components,
                'secondary': 'secondary' in health.degraded_components,
                'tertiary': 'tertiary' in health.degraded_components
            },
            'prevention_logged': len(audit_logs) > 0
        }

    async def test_recovery_procedure(self) -> Dict:
        """Test automated recovery procedures"""
        components = ['resilience_manager', 'security_monitor', 'audit_logger']

        # Setup test component
        self.resilience_manager.register_component('recoverable')

        # Register recovery handler
        recovery_called = False

        async def recovery_handler():
            nonlocal recovery_called
            recovery_called = True

        self.resilience_manager.register_recovery_handler(
            'recoverable',
            recovery_handler
        )

        # Trigger failure
        for _ in range(5):
            await self.resilience_manager.record_request(
                'recoverable',
                0.0,
                error=True
            )

        # Wait for recovery attempt
        await asyncio.sleep(1)

        # Verify recovery
        health = await self.resilience_manager.get_system_health()
        audit_logs = await self.audit_logger.search_logs(
            event_types=[AuditEventType.SYSTEM]
        )

        return {
            'components_tested': components,
            'recovery_attempted': recovery_called,
            'final_status': health.overall_status.value,
            'recovery_logged': len(audit_logs) > 0
        }

    async def generate_test_report(self) -> Dict[str, Any]:
        """Generate comprehensive test report"""
        total_tests = len(self.test_results)
        successful_tests = sum(1 for r in self.test_results if r.success)

        component_coverage = set()
        for result in self.test_results:
            component_coverage.update(result.components_tested)

        return {
            'timestamp': datetime.now().isoformat(),
            'total_tests': total_tests,
            'successful_tests': successful_tests,
            'success_rate': (successful_tests / total_tests * 100)
            if total_tests > 0 else 0,
            'component_coverage': list(component_coverage),
            'scenarios_tested': [r.scenario.value for r in self.test_results],
            'failed_scenarios': [
                r.scenario.value for r in self.test_results
                if not r.success
            ],
            'test_results': [
                {
                    'scenario': r.scenario.value,
                    'success': r.success,
                    'duration': (r.end_time - r.start_time).total_seconds(),
                    'components': r.components_tested,
                    'error': r.error_message,
                    'details': r.details
                }
                for r in self.test_results
            ]
        }

    def get_available_scenarios(self) -> List[str]:
        """Get list of available test scenarios"""
        return [scenario.value for scenario in TestScenario]

    async def clear_test_results(self):
        """Clear previous test results"""
        self.test_results.clear()
        self.logger.info("Test results cleared")
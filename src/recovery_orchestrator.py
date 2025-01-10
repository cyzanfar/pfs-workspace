# src/recovery_orchestrator.py
import asyncio
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Set, Callable
import logging
from collections import defaultdict


class ComponentType(Enum):
    KEY_MANAGER = "key_manager"
    SECURITY_MONITOR = "security_monitor"
    AUDIT_LOGGER = "audit_logger"
    RESILIENCE_MANAGER = "resilience_manager"
    PAYMENT_PROCESSOR = "payment_processor"


class RecoveryStage(Enum):
    INITIATED = "initiated"
    ISOLATING = "isolating"
    RESETTING = "resetting"
    RESTORING = "restoring"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"


class RecoveryPriority(Enum):
    CRITICAL = 1
    HIGH = 2
    MEDIUM = 3
    LOW = 4


@dataclass
class RecoveryState:
    component: ComponentType
    stage: RecoveryStage
    started_at: datetime
    error: Optional[str] = None
    dependencies: Set[ComponentType] = None
    verification_checks: Dict[str, bool] = None


class RecoveryOrchestrator:
    def __init__(self):
        # Initialize logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger("RecoveryOrchestrator")

        # Component handlers
        self.component_handlers: Dict[ComponentType, object] = {}

        # Recovery procedures
        self.recovery_procedures: Dict[ComponentType, Callable] = {}

        # Verification checks
        self.verification_checks: Dict[ComponentType, List[Callable]] = defaultdict(list)

        # Component dependencies
        self.dependencies: Dict[ComponentType, Set[ComponentType]] = defaultdict(set)

        # Active recovery states
        self.active_recoveries: Dict[ComponentType, RecoveryState] = {}

        # Recovery history
        self.recovery_history: List[Dict] = []

        # Initialize component dependencies
        self._init_dependencies()

    def _init_dependencies(self):
        """Initialize component dependency graph"""
        # Key Manager dependencies
        self.dependencies[ComponentType.KEY_MANAGER].update([
            ComponentType.AUDIT_LOGGER
        ])

        # Security Monitor dependencies
        self.dependencies[ComponentType.SECURITY_MONITOR].update([
            ComponentType.AUDIT_LOGGER,
            ComponentType.KEY_MANAGER
        ])

        # Payment Processor dependencies
        self.dependencies[ComponentType.PAYMENT_PROCESSOR].update([
            ComponentType.KEY_MANAGER,
            ComponentType.SECURITY_MONITOR,
            ComponentType.AUDIT_LOGGER
        ])

    def register_component(self,
                           component_type: ComponentType,
                           handler: object):
        """Register component handler"""
        self.component_handlers[component_type] = handler

    def register_recovery_procedure(self,
                                    component_type: ComponentType,
                                    procedure: Callable):
        """Register component recovery procedure"""
        self.recovery_procedures[component_type] = procedure

    def register_verification_check(self,
                                    component_type: ComponentType,
                                    check: Callable):
        """Register component verification check"""
        self.verification_checks[component_type].append(check)

    async def initiate_recovery(self,
                                component: ComponentType,
                                error: Optional[str] = None) -> RecoveryState:
        """Initiate component recovery process"""
        if component not in self.component_handlers:
            raise ValueError(f"Unregistered component: {component}")

        # Create recovery state
        state = RecoveryState(
            component=component,
            stage=RecoveryStage.INITIATED,
            started_at=datetime.now(),
            error=error,
            dependencies=self.dependencies[component].copy(),
            verification_checks={}
        )

        self.active_recoveries[component] = state
        self.logger.info(f"Initiated recovery for {component.value}")

        # Start recovery process
        asyncio.create_task(self._execute_recovery(state))

        return state

    async def _execute_recovery(self, state: RecoveryState):
        """Execute staged recovery process"""
        try:
            # Isolation stage
            state.stage = RecoveryStage.ISOLATING
            await self._isolate_component(state.component)

            # Reset stage
            state.stage = RecoveryStage.RESETTING
            await self._reset_component(state.component)

            # Restore stage
            state.stage = RecoveryStage.RESTORING
            await self._restore_component(state.component)

            # Verification stage
            state.stage = RecoveryStage.VERIFYING
            success = await self._verify_recovery(state)

            if success:
                state.stage = RecoveryStage.COMPLETED
                self.logger.info(
                    f"Recovery completed for {state.component.value}"
                )
            else:
                state.stage = RecoveryStage.FAILED
                state.error = "Verification failed"
                self.logger.error(
                    f"Recovery verification failed for {state.component.value}"
                )

        except Exception as e:
            state.stage = RecoveryStage.FAILED
            state.error = str(e)
            self.logger.error(
                f"Recovery failed for {state.component.value}: {str(e)}"
            )

        finally:
            # Record recovery attempt
            self.recovery_history.append({
                'component': state.component.value,
                'started_at': state.started_at.isoformat(),
                'completed_at': datetime.now().isoformat(),
                'stage': state.stage.value,
                'error': state.error,
                'verification_checks': state.verification_checks
            })

    async def _isolate_component(self, component: ComponentType):
        """Isolate component from system"""
        self.logger.info(f"Isolating {component.value}")

        # Check dependencies
        for dep in self.dependencies[component]:
            if dep in self.active_recoveries:
                raise RuntimeError(
                    f"Dependent component {dep.value} is also in recovery"
                )

        # Isolate component
        handler = self.component_handlers[component]
        if hasattr(handler, 'isolate'):
            await handler.isolate()

        await asyncio.sleep(1)  # Allow isolation to take effect

    async def _reset_component(self, component: ComponentType):
        """Reset component state"""
        self.logger.info(f"Resetting {component.value}")

        handler = self.component_handlers[component]
        if hasattr(handler, 'reset'):
            await handler.reset()

        await asyncio.sleep(1)  # Allow reset to complete

    async def _restore_component(self, component: ComponentType):
        """Restore component functionality"""
        self.logger.info(f"Restoring {component.value}")

        if component in self.recovery_procedures:
            procedure = self.recovery_procedures[component]
            await procedure()

        await asyncio.sleep(1)  # Allow restoration to complete

    async def _verify_recovery(self, state: RecoveryState) -> bool:
        """Verify component recovery"""
        self.logger.info(f"Verifying recovery of {state.component.value}")

        all_passed = True
        verification_checks = self.verification_checks[state.component]

        for check in verification_checks:
            try:
                result = await check()
                check_name = check.__name__
                state.verification_checks[check_name] = result
                if not result:
                    all_passed = False
            except Exception as e:
                state.verification_checks[check.__name__] = False
                self.logger.error(
                    f"Verification check failed: {str(e)}"
                )
                all_passed = False

        return all_passed

    async def get_recovery_status(self,
                                  component: ComponentType) -> Optional[RecoveryState]:
        """Get current recovery status"""
        return self.active_recoveries.get(component)

    async def get_active_recoveries(self) -> Dict[ComponentType, RecoveryState]:
        """Get all active recovery processes"""
        return self.active_recoveries.copy()

    async def abort_recovery(self, component: ComponentType):
        """Abort active recovery process"""
        if component not in self.active_recoveries:
            raise ValueError(f"No active recovery for {component.value}")

        state = self.active_recoveries[component]
        state.stage = RecoveryStage.FAILED
        state.error = "Recovery aborted"

        self.logger.warning(f"Recovery aborted for {component.value}")

        # Remove from active recoveries
        del self.active_recoveries[component]

    def get_recovery_history(self,
                             component: Optional[ComponentType] = None) -> List[Dict]:
        """Get recovery attempt history"""
        if component:
            return [
                h for h in self.recovery_history
                if h['component'] == component.value
            ]
        return self.recovery_history

    async def simulate_failure(self, component: ComponentType,
                               error_type: str) -> RecoveryState:
        """Simulate component failure for testing"""
        self.logger.info(
            f"Simulating {error_type} failure for {component.value}"
        )

        # Trigger component failure
        handler = self.component_handlers[component]
        if hasattr(handler, 'simulate_failure'):
            await handler.simulate_failure(error_type)

        # Initiate recovery
        return await self.initiate_recovery(
            component,
            f"Simulated {error_type} failure"
        )

    async def verify_system_health(self) -> Dict[ComponentType, bool]:
        """Verify health of all components"""
        results = {}

        for component in ComponentType:
            if component in self.component_handlers:
                checks_passed = True
                handler = self.component_handlers[component]

                if hasattr(handler, 'check_health'):
                    try:
                        checks_passed = await handler.check_health()
                    except Exception:
                        checks_passed = False

                results[component] = checks_passed

        return results
import json
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta


class ComponentHealthTracker:
    """
    Manages health tracking for system components and their dependencies.
    """

    @dataclass
    class ComponentHealth:
        name: str
        status: str = 'unknown'
        last_checked: datetime = field(default_factory=datetime.now)
        dependencies: List[str] = field(default_factory=list)
        health_checks: List[Dict[str, Any]] = field(default_factory=list)

        def update_status(self, new_status: str):
            """
            Update component status and log the change.
            """
            if new_status != self.status:
                self.health_checks.append({
                    'timestamp': datetime.now(),
                    'old_status': self.status,
                    'new_status': new_status
                })
                self.status = new_status
                self.last_checked = datetime.now()

    def __init__(self):
        """
        Initialize the health tracker.
        """
        self._components: Dict[str, self.ComponentHealth] = {}
        self._health_check_callbacks: Dict[str, Callable] = {}

    def register_component(
            self,
            name: str,
            dependencies: Optional[List[str]] = None,
            health_check_callback: Optional[Callable] = None
    ):
        """
        Register a new system component.

        Args:
            name (str): Unique name of the component
            dependencies (List[str], optional): List of dependent components
            health_check_callback (Callable, optional): Function to check component health
        """
        if name in self._components:
            raise ValueError(f"Component {name} already exists")

        self._components[name] = self.ComponentHealth(
            name=name,
            dependencies=dependencies or []
        )

        if health_check_callback:
            self._health_check_callbacks[name] = health_check_callback

    def perform_health_checks(self):
        """
        Perform health checks for all registered components.
        """
        for name, callback in self._health_check_callbacks.items():
            try:
                status = callback()
                component = self._components[name]
                component.update_status(status)

                # Check dependencies
                if component.dependencies:
                    self._validate_dependencies(component)
            except Exception as e:
                # Mark component as failed if health check fails
                self._components[name].update_status('failed')

    def _validate_dependencies(self, component: ComponentHealth):
        """
        Validate the status of component dependencies.

        Args:
            component (ComponentHealth): Component to validate dependencies for
        """
        for dep_name in component.dependencies:
            if dep_name not in self._components:
                raise ValueError(f"Dependency {dep_name} not registered")

            dep_component = self._components[dep_name]
            if dep_component.status != 'operational':
                # If a dependency is not operational, mark this component as degraded
                component.update_status('degraded')
                break

    def get_component_health(self, name: str) -> Dict[str, Any]:
        """
        Retrieve health information for a specific component.

        Args:
            name (str): Name of the component

        Returns:
            Dict containing component health information
        """
        if name not in self._components:
            raise ValueError(f"Component {name} not found")

        component = self._components[name]
        return {
            'name': component.name,
            'status': component.status,
            'last_checked': component.last_checked.isoformat(),
            'dependencies': component.dependencies,
            'health_history': [
                {
                    'timestamp': check['timestamp'].isoformat(),
                    'old_status': check['old_status'],
                    'new_status': check['new_status']
                } for check in component.health_checks
            ]
        }


class AlertManager:
    """
    Manages system alerts and notification mechanisms.
    """

    def __init__(self, max_history: int = 100):
        """
        Initialize the AlertManager.

        Args:
            max_history (int): Maximum number of alerts to keep in history
        """
        self._alerts: List[Dict[str, Any]] = []
        self._max_history = max_history
        self._notification_callbacks: List[Callable] = []

    def record_alert(
            self,
            metric_name: str,
            severity: str,
            message: str
    ):
        """
        Record a new alert.

        Args:
            metric_name (str): Name of the metric triggering the alert
            severity (str): Alert severity (e.g., 'warning', 'critical')
            message (str): Detailed alert message
        """
        alert = {
            'id': f"{metric_name}_{datetime.now().isoformat()}",
            'timestamp': datetime.now().isoformat(),
            'metric_name': metric_name,
            'severity': severity,
            'message': message
        }

        # Add alert to history
        self._alerts.append(alert)

        # Trim history if exceeds max
        if len(self._alerts) > self._max_history:
            self._alerts = self._alerts[-self._max_history:]

        # Trigger notification callbacks
        for callback in self._notification_callbacks:
            try:
                callback(alert)
            except Exception as e:
                print(f"Notification callback failed: {e}")

    def get_alerts(
            self,
            severity: Optional[str] = None,
            start_time: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve alerts with optional filtering.

        Args:
            severity (str, optional): Filter by alert severity
            start_time (datetime, optional): Filter alerts after this time

        Returns:
            List of filtered alerts
        """
        filtered_alerts = self._alerts

        if severity:
            filtered_alerts = [
                alert for alert in filtered_alerts
                if alert['severity'] == severity
            ]

        if start_time:
            filtered_alerts = [
                alert for alert in filtered_alerts
                if datetime.fromisoformat(alert['timestamp']) >= start_time
            ]

        return filtered_alerts

    def add_notification_callback(self, callback: Callable):
        """
        Add a callback to be triggered on new alerts.

        Args:
            callback (Callable): Function to call with new alert details
        """
        self._notification_callbacks.append(callback)


class MonitoringDashboard:
    """
    Comprehensive system monitoring dashboard.
    """

    def __init__(
            self,
            data_dir: str = './monitoring_data',
            config_file: str = 'dashboard_config.json'
    ):
        """
        Initialize the monitoring dashboard.

        Args:
            data_dir (str): Directory to store monitoring data
            config_file (str): Configuration file name
        """
        # Ensure data directory exists
        self.data_dir = os.path.abspath(data_dir)
        os.makedirs(self.data_dir, exist_ok=True)

        # Configuration management
        self.config_path = os.path.join(self.data_dir, config_file)
        self._config = self._load_config()

        # Component and alert management
        self.component_health = ComponentHealthTracker()
        self.alert_manager = AlertManager()

        # Background health check thread
        self._start_health_check_thread()

    def _load_config(self) -> Dict[str, Any]:
        """
        Load dashboard configuration.

        Returns:
            Dict containing dashboard configuration
        """
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r') as f:
                return json.load(f)

        # Default configuration
        return {
            'health_check_interval': 60,  # seconds
            'metrics_retention_days': 30,
            'alert_severity_thresholds': {
                'warning': 0.7,
                'critical': 0.9
            }
        }

    def save_config(self):
        """
        Save current configuration to file.
        """
        with open(self.config_path, 'w') as f:
            json.dump(self._config, f, indent=2)

    def _start_health_check_thread(self):
        """
        Start a background thread for periodic health checks.
        """

        def health_check_worker():
            while True:
                self.component_health.perform_health_checks()
                time.sleep(self._config['health_check_interval'])

        health_thread = threading.Thread(
            target=health_check_worker,
            daemon=True,
            name='HealthCheckThread'
        )
        health_thread.start()

    def register_component(
            self,
            name: str,
            dependencies: Optional[List[str]] = None,
            health_check_callback: Optional[Callable] = None
    ):
        """
        Register a new system component.

        Wrapper around ComponentHealthTracker's register_component method.
        """
        self.component_health.register_component(
            name,
            dependencies,
            health_check_callback
        )

    def add_alert_notification(self, callback: Callable):
        """
        Add a notification callback to the alert manager.

        Args:
            callback (Callable): Function to call on new alerts
        """
        self.alert_manager.add_notification_callback(callback)

    def generate_dashboard_report(self) -> Dict[str, Any]:
        """
        Generate a comprehensive dashboard report.

        Returns:
            Dict containing system health overview
        """
        # Collect component healths
        component_healths = {}
        for component_name in self.component_health._components:
            component_healths[component_name] = self.component_health.get_component_health(component_name)

        return {
            'timestamp': datetime.now().isoformat(),
            'components': component_healths,
            'recent_alerts': self.alert_manager.get_alerts(
                start_time=datetime.now() - timedelta(hours=24)
            )
        }

    def export_dashboard_report(
            self,
            output_file: Optional[str] = None
    ) -> str:
        """
        Export dashboard report to a JSON file.

        Args:
            output_file (str, optional): Path to export file

        Returns:
            Path to the exported file
        """
        # Generate report
        report = self.generate_dashboard_report()

        # Use default filename if not provided
        if not output_file:
            output_file = os.path.join(
                self.data_dir,
                f'dashboard_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
            )

        # Write report to file
        with open(output_file, 'w') as f:
            json.dump(report, f, indent=2)

        return output_file
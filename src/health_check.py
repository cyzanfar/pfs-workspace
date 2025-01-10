import psutil
import platform
import socket
import subprocess
import threading
import time
import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Callable
from datetime import datetime, timedelta


class SystemHealthCheck:
    """
    Comprehensive system health diagnostic and monitoring class.

    Provides in-depth system health analysis across multiple dimensions:
    - Hardware resources
    - Network connectivity
    - Process monitoring
    - Predictive failure detection
    """

    @dataclass
    class ComponentHealth:
        """
        Represents the health status of a system component.
        """
        name: str
        status: str = 'unknown'
        details: Dict[str, Any] = field(default_factory=dict)
        dependencies: List[str] = field(default_factory=list)
        last_checked: datetime = field(default_factory=datetime.now)
        health_score: float = 100.0  # 0-100 scale

    def __init__(
            self,
            config_path: str = './system_health_config.json',
            log_dir: str = './health_check_logs'
    ):
        """
        Initialize the SystemHealthCheck.

        Args:
            config_path (str): Path to configuration file
            log_dir (str): Directory to store health check logs
        """
        # Ensure log directory exists
        self.log_dir = os.path.abspath(log_dir)
        os.makedirs(self.log_dir, exist_ok=True)

        # Load configuration
        self.config_path = config_path
        self.config = self._load_config()

        # Component health tracking
        self.components: Dict[str, self.ComponentHealth] = {}

        # Predictive failure tracking
        self._failure_predictors: Dict[str, Callable] = {}

    def _load_config(self) -> Dict[str, Any]:
        """
        Load system health configuration.

        Returns:
            Dict containing configuration parameters
        """
        default_config = {
            'resource_thresholds': {
                'cpu_usage': 80.0,  # Percent
                'memory_usage': 85.0,  # Percent
                'disk_usage': 90.0,  # Percent
                'network_latency': 200  # Milliseconds
            },
            'critical_components': [
                'cpu', 'memory', 'disk', 'network'
            ]
        }

        # Load from file if exists
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    user_config = json.load(f)
                    default_config.update(user_config)
            except Exception as e:
                print(f"Error loading config: {e}")

        return default_config

    def register_component(
            self,
            name: str,
            dependencies: Optional[List[str]] = None,
            health_check_callback: Optional[Callable] = None
    ):
        """
        Register a system component for health monitoring.

        Args:
            name (str): Unique name of the component
            dependencies (List[str], optional): Components this depends on
            health_check_callback (Callable, optional): Custom health check function
        """
        if name in self.components:
            raise ValueError(f"Component {name} already registered")

        component = self.ComponentHealth(
            name=name,
            dependencies=dependencies or []
        )
        self.components[name] = component

        # Store health check callback if provided
        if health_check_callback:
            self._failure_predictors[name] = health_check_callback

    def _check_hardware_resources(self) -> Dict[str, Any]:
        """
        Perform comprehensive hardware resource check.

        Returns:
            Dict containing resource utilization details
        """
        # CPU usage
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_cores = psutil.cpu_count()
        cpu_freq = psutil.cpu_freq()

        # Memory usage
        memory = psutil.virtual_memory()

        # Disk usage
        disk_usage = psutil.disk_usage('/')

        # Network connectivity
        try:
            socket.create_connection(("8.8.8.8", 53), timeout=3)
            network_status = 'operational'
        except (socket.error, socket.timeout):
            network_status = 'disconnected'

        # Aggregate resource health
        resource_health = {
            'cpu': {
                'usage_percent': cpu_percent,
                'total_cores': cpu_cores,
                'current_frequency': cpu_freq.current if cpu_freq else None,
                'health_score': max(0, 100 - cpu_percent)
            },
            'memory': {
                'total': memory.total,
                'available': memory.available,
                'used_percent': memory.percent,
                'health_score': max(0, 100 - memory.percent)
            },
            'disk': {
                'total': disk_usage.total,
                'free': disk_usage.free,
                'used_percent': disk_usage.percent,
                'health_score': max(0, 100 - disk_usage.percent)
            },
            'network': {
                'status': network_status,
                'health_score': 100 if network_status == 'operational' else 0
            }
        }

        return resource_health

    def _check_running_processes(self) -> Dict[str, Any]:
        """
        Analyze running processes and system load.

        Returns:
            Dict containing process and load information
        """
        # Get all running processes
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
            try:
                processes.append({
                    'pid': proc.info['pid'],
                    'name': proc.info['name'],
                    'cpu_percent': proc.info['cpu_percent'],
                    'memory_percent': proc.info['memory_percent']
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        # System load
        load_avg = os.getloadavg()

        return {
            'total_processes': len(processes),
            'high_cpu_processes': [
                p for p in processes if p['cpu_percent'] > 50
            ],
            'high_memory_processes': [
                p for p in processes if p['memory_percent'] > 50
            ],
            'system_load': {
                '1_min': load_avg[0],
                '5_min': load_avg[1],
                '15_min': load_avg[2]
            }
        }

    def perform_health_check(self, depth: str = 'quick') -> Dict[str, Any]:
        """
        Perform a comprehensive system health check.

        Args:
            depth (str): Depth of health check ('quick' or 'full')

        Returns:
            Dict containing health check results
        """
        # Timestamp for this health check
        check_timestamp = datetime.now()

        # Start with basic resource check
        health_report = {
            'timestamp': check_timestamp.isoformat(),
            'resources': self._check_hardware_resources()
        }

        # Perform additional checks based on depth
        if depth == 'full':
            # Add detailed process information
            health_report['processes'] = self._check_running_processes()

            # Run component-specific health checks
            component_healths = {}
            for name, component in self.components.items():
                try:
                    # Run custom health check if available
                    if name in self._failure_predictors:
                        component_health = self._failure_predictors[name]()
                    else:
                        # Default to using resource health
                        component_health = self._infer_component_health(name, health_report)

                    # Update component health
                    component.status = component_health.get('status', 'unknown')
                    component.details = component_health
                    component.last_checked = check_timestamp

                    # Calculate health score
                    component.health_score = component_health.get('health_score', 0)

                    component_healths[name] = {
                        'status': component.status,
                        'health_score': component.health_score,
                        'details': component.details
                    }
                except Exception as e:
                    component_healths[name] = {
                        'status': 'error',
                        'error': str(e)
                    }

            health_report['components'] = component_healths

        # Log the health check
        self._log_health_check(health_report)

        return health_report

    def _infer_component_health(
            self,
            component_name: str,
            health_report: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Infer component health based on system resources.

        Args:
            component_name (str): Name of the component
            health_report (Dict): Existing health report

        Returns:
            Dict containing inferred health status
        """
        # Default mapping of system resources to component health
        resource_mappings = {
            'cpu': health_report['resources']['cpu']['health_score'],
            'memory': health_report['resources']['memory']['health_score'],
            'disk': health_report['resources']['disk']['health_score'],
            'network': health_report['resources']['network']['health_score']
        }

        # Determine status based on health score
        def get_status(health_score):
            if health_score >= 90:
                return 'optimal'
            elif health_score >= 70:
                return 'degraded'
            else:
                return 'critical'

        # Use exact match or best guess for component
        health_score = resource_mappings.get(
            component_name.lower(),
            sum(resource_mappings.values()) / len(resource_mappings)
        )

        return {
            'status': get_status(health_score),
            'health_score': health_score,
            'inferred_from': 'system_resources'
        }

    def _log_health_check(self, health_report: Dict[str, Any]):
        """
        Log health check results to a file.

        Args:
            health_report (Dict): Health check results to log
        """
        log_file = os.path.join(
            self.log_dir,
            f'health_check_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        )

        with open(log_file, 'w') as f:
            json.dump(health_report, f, indent=2)

    def predict_potential_failures(self) -> Dict[str, Any]:
        """
        Analyze historical data to predict potential system failures.

        Returns:
            Dict containing failure predictions
        """
        # Collect health check logs
        health_logs = []
        for filename in os.listdir(self.log_dir):
            if filename.startswith('health_check_') and filename.endswith('.json'):
                filepath = os.path.join(self.log_dir, filename)
                try:
                    with open(filepath, 'r') as f:
                        health_logs.append(json.load(f))
                except Exception as e:
                    print(f"Error reading log {filename}: {e}")

        # Analyze trends
        failure_predictions = {
            'timestamp': datetime.now().isoformat(),
            'potential_failures': {}
        }

        # Basic trend analysis
        for component_name in self.components:
            try:
                # Look at trend of health scores
                component_scores = [
                    log.get('components', {}).get(component_name, {}).get('health_score', 100)
                    for log in health_logs
                ]

                # Simple trend detection
                if component_scores:
                    avg_score = sum(component_scores) / len(component_scores)
                    score_trend = (component_scores[-1] - avg_score) / avg_score

                    failure_predictions['potential_failures'][component_name] = {
                        'trend': 'declining' if score_trend < -0.1 else 'stable',
                        'avg_health_score': avg_score,
                        'recent_score': component_scores[-1]
                    }
            except Exception as e:
                failure_predictions['potential_failures'][component_name] = {
                    'error': str(e)
                }

        return failure_predictions
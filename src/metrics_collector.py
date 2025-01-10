import typing
import time
import threading
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime, timedelta
import json
import os


@dataclass
class MetricDefinition:
    """
    Defines the structure and rules for a specific metric.

    Attributes:
        name (str): Unique identifier for the metric
        description (str): Human-readable description of the metric
        unit (str): Unit of measurement (e.g., 'ms', 'bytes', '%')
        warning_threshold (float, optional): Warning level threshold
        critical_threshold (float, optional): Critical level threshold
        alert_callback (Optional[Callable]): Function to call on threshold breach
    """
    name: str
    description: str
    unit: str
    warning_threshold: Optional[float] = None
    critical_threshold: Optional[float] = None
    alert_callback: Optional[Callable] = None


class MetricsCollector:
    """
    A comprehensive metrics collection and analysis system.

    Provides real-time metric tracking, historical trend analysis,
    and automated alerting capabilities.
    """

    def __init__(self,
                 data_dir: str = './metrics_data',
                 retention_days: int = 30):
        """
        Initialize the MetricsCollector.

        Args:
            data_dir (str): Directory to store metric logs
            retention_days (int): Number of days to retain historical metrics
        """
        self._metrics: Dict[str, List[Dict[str, Any]]] = {}
        self._metric_definitions: Dict[str, MetricDefinition] = {}
        self._lock = threading.Lock()

        # Ensure data directory exists
        self.data_dir = os.path.abspath(data_dir)
        os.makedirs(self.data_dir, exist_ok=True)

        # Retention policy setup
        self.retention_days = retention_days

        # Logging setup
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger('MetricsCollector')

        # Start retention cleanup thread
        self._start_retention_cleanup()

    def register_metric(self, metric_def: MetricDefinition):
        """
        Register a new metric definition.

        Args:
            metric_def (MetricDefinition): Metric definition to register

        Raises:
            ValueError: If metric already exists
        """
        with self._lock:
            if metric_def.name in self._metric_definitions:
                raise ValueError(f"Metric {metric_def.name} already exists")

            self._metric_definitions[metric_def.name] = metric_def
            self._metrics[metric_def.name] = []

    def collect_metric(self, name: str, value: float):
        """
        Collect a metric value and perform threshold checks.

        Args:
            name (str): Name of the metric
            value (float): Value of the metric

        Raises:
            ValueError: If metric is not registered
        """
        with self._lock:
            if name not in self._metric_definitions:
                raise ValueError(f"Metric {name} not registered")

            metric_def = self._metric_definitions[name]
            metric_entry = {
                'timestamp': datetime.now(),
                'value': value
            }

            # Threshold checking
            if metric_def.critical_threshold is not None and \
                    value >= metric_def.critical_threshold:
                self.logger.critical(
                    f"CRITICAL: {name} exceeded critical threshold. "
                    f"Current: {value}, Threshold: {metric_def.critical_threshold}"
                )
                if metric_def.alert_callback:
                    try:
                        metric_def.alert_callback(metric_entry)
                    except Exception as e:
                        self.logger.error(f"Alert callback failed: {e}")

            elif metric_def.warning_threshold is not None and \
                    value >= metric_def.warning_threshold:
                self.logger.warning(
                    f"WARNING: {name} exceeded warning threshold. "
                    f"Current: {value}, Threshold: {metric_def.warning_threshold}"
                )

            self._metrics[name].append(metric_entry)

    def get_metric_history(self,
                           name: str,
                           start_time: Optional[datetime] = None,
                           end_time: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """
        Retrieve historical metrics for a given metric.

        Args:
            name (str): Name of the metric
            start_time (datetime, optional): Start of time range
            end_time (datetime, optional): End of time range

        Returns:
            List of metric entries within the specified time range
        """
        with self._lock:
            if name not in self._metrics:
                raise ValueError(f"Metric {name} not found")

            history = self._metrics[name]

            # Filter by time range if specified
            if start_time or end_time:
                history = [
                    entry for entry in history
                    if (not start_time or entry['timestamp'] >= start_time) and
                       (not end_time or entry['timestamp'] <= end_time)
                ]

            return history

    def calculate_metric_stats(self, name: str) -> Dict[str, Any]:
        """
        Calculate statistical summary for a metric.

        Args:
            name (str): Name of the metric

        Returns:
            Dictionary of statistical metrics
        """
        history = self.get_metric_history(name)

        if not history:
            return {
                'count': 0,
                'mean': None,
                'min': None,
                'max': None,
                'latest': None
            }

        values = [entry['value'] for entry in history]

        return {
            'count': len(values),
            'mean': sum(values) / len(values),
            'min': min(values),
            'max': max(values),
            'latest': history[-1]['value']
        }

    def _start_retention_cleanup(self):
        """
        Start a background thread to clean up old metrics periodically.
        """

        def cleanup():
            while True:
                time.sleep(3600)  # Run every hour
                cutoff = datetime.now() - timedelta(days=self.retention_days)

                with self._lock:
                    for metric_name in self._metrics:
                        self._metrics[metric_name] = [
                            entry for entry in self._metrics[metric_name]
                            if entry['timestamp'] >= cutoff
                        ]

        cleanup_thread = threading.Thread(
            target=cleanup,
            daemon=True,
            name='MetricsRetentionCleanup'
        )
        cleanup_thread.start()

    def export_metrics(self, output_file: Optional[str] = None) -> str:
        """
        Export all collected metrics to a JSON file.

        Args:
            output_file (str, optional): Path to export file

        Returns:
            Path to the exported file
        """
        # Prepare exportable data
        export_data = {}
        for name, entries in self._metrics.items():
            export_data[name] = [
                {
                    'timestamp': entry['timestamp'].isoformat(),
                    'value': entry['value']
                } for entry in entries
            ]

        # Use default filename if not provided
        if not output_file:
            output_file = os.path.join(
                self.data_dir,
                f'metrics_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
            )

        with open(output_file, 'w') as f:
            json.dump(export_data, f, indent=2)

        return output_file
import time
import json
import logging
import threading
from typing import Dict, List, Optional, Set, Union, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict
import psutil
import click
import plotly.graph_objects as go
from prometheus_client import start_http_server, Counter, Gauge, Histogram


@dataclass
class MetricSchema:
    """Schema definition for a metric."""
    name: str
    type: str  # counter, gauge, histogram
    description: str
    labels: List[str] = field(default_factory=list)
    buckets: Optional[List[float]] = None  # For histograms


@dataclass
class Alert:
    """Alert configuration for a metric."""
    metric_name: str
    threshold: float
    comparison: str  # >, <, >=, <=
    duration: timedelta
    labels: Dict[str, str] = field(default_factory=dict)
    callback: Optional[Callable] = None


class MetricsCollector:
    """
    System-wide performance monitoring and metrics collection.

    Features:
    - Collects system and application metrics
    - Supports counters, gauges, and histograms
    - Provides threshold-based alerting
    - Exposes Prometheus metrics endpoint
    - Includes CLI for querying and visualization
    """

    def __init__(
            self,
            prometheus_port: int = 8000,
            collection_interval: int = 60
    ):
        """
        Initialize the MetricsCollector.

        Args:
            prometheus_port: Port for Prometheus metrics endpoint
            collection_interval: Metric collection interval in seconds
        """
        self.schemas: Dict[str, MetricSchema] = {}
        self.metrics: Dict[str, Union[Counter, Gauge, Histogram]] = {}
        self.alerts: List[Alert] = []
        self.alert_history: List[Dict] = []
        self.collection_interval = collection_interval
        self.logger = self._setup_logger()

        # Start Prometheus endpoint
        start_http_server(prometheus_port)

        # Start collection thread
        self.running = True
        self.collector_thread = threading.Thread(
            target=self._collection_loop,
            daemon=True
        )
        self.collector_thread.start()

    def _setup_logger(self) -> logging.Logger:
        """Configure logging for metrics collection."""
        logger = logging.getLogger("MetricsCollector")
        logger.setLevel(logging.INFO)

        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        return logger

    def register_metric(self, schema: MetricSchema) -> None:
        """
        Register a new metric schema.

        Args:
            schema: MetricSchema defining the metric
        """
        if schema.name in self.schemas:
            raise ValueError(f"Metric {schema.name} already registered")

        self.schemas[schema.name] = schema

        # Create Prometheus metric
        if schema.type == 'counter':
            metric = Counter(
                schema.name,
                schema.description,
                schema.labels
            )
        elif schema.type == 'gauge':
            metric = Gauge(
                schema.name,
                schema.description,
                schema.labels
            )
        elif schema.type == 'histogram':
            metric = Histogram(
                schema.name,
                schema.description,
                schema.labels,
                buckets=schema.buckets or Histogram.DEFAULT_BUCKETS
            )
        else:
            raise ValueError(f"Invalid metric type: {schema.type}")

        self.metrics[schema.name] = metric
        self.logger.info(f"Registered metric: {schema.name}")

    def collect_system_metrics(self) -> None:
        """Collect standard system metrics."""
        # CPU metrics
        cpu_schema = MetricSchema(
            name='system_cpu_usage',
            type='gauge',
            description='CPU usage percentage',
            labels=['cpu']
        )
        self.register_metric(cpu_schema)

        for i, percentage in enumerate(psutil.cpu_percent(percpu=True)):
            self.metrics['system_cpu_usage'].labels(cpu=str(i)).set(percentage)

        # Memory metrics
        memory = psutil.virtual_memory()
        mem_schema = MetricSchema(
            name='system_memory_usage_bytes',
            type='gauge',
            description='Memory usage in bytes',
            labels=['type']
        )
        self.register_metric(mem_schema)

        self.metrics['system_memory_usage_bytes'].labels(type='total').set(
            memory.total
        )
        self.metrics['system_memory_usage_bytes'].labels(type='used').set(
            memory.used
        )

        # Disk metrics
        disk_schema = MetricSchema(
            name='system_disk_usage_bytes',
            type='gauge',
            description='Disk usage in bytes',
            labels=['device', 'mountpoint', 'type']
        )
        self.register_metric(disk_schema)

        for partition in psutil.disk_partitions():
            usage = psutil.disk_usage(partition.mountpoint)
            self.metrics['system_disk_usage_bytes'].labels(
                device=partition.device,
                mountpoint=partition.mountpoint,
                type='total'
            ).set(usage.total)
            self.metrics['system_disk_usage_bytes'].labels(
                device=partition.device,
                mountpoint=partition.mountpoint,
                type='used'
            ).set(usage.used)

    def register_alert(self, alert: Alert) -> None:
        """
        Register a new metric alert.

        Args:
            alert: Alert configuration
        """
        if alert.metric_name not in self.schemas:
            raise ValueError(f"Metric {alert.metric_name} not registered")

        self.alerts.append(alert)
        self.logger.info(
            f"Registered alert for {alert.metric_name} "
            f"(threshold: {alert.threshold})"
        )

    def check_alerts(self) -> None:
        """Check all registered alerts against current metric values."""
        for alert in self.alerts:
            metric = self.metrics[alert.metric_name]
            current_value = metric._value.get()

            alert_triggered = False
            if alert.comparison == '>':
                alert_triggered = current_value > alert.threshold
            elif alert.comparison == '<':
                alert_triggered = current_value < alert.threshold
            elif alert.comparison == '>=':
                alert_triggered = current_value >= alert.threshold
            elif alert.comparison == '<=':
                alert_triggered = current_value <= alert.threshold

            if alert_triggered:
                alert_data = {
                    'timestamp': datetime.now().isoformat(),
                    'metric': alert.metric_name,
                    'value': current_value,
                    'threshold': alert.threshold,
                    'comparison': alert.comparison
                }
                self.alert_history.append(alert_data)
                self.logger.warning(
                    f"Alert triggered for {alert.metric_name}: "
                    f"{current_value} {alert.comparison} {alert.threshold}"
                )

                if alert.callback:
                    alert.callback(alert_data)

    def _collection_loop(self) -> None:
        """Background thread for periodic metric collection."""
        while self.running:
            try:
                self.collect_system_metrics()
                self.check_alerts()
            except Exception as e:
                self.logger.error(f"Error collecting metrics: {str(e)}")

            time.sleep(self.collection_interval)

    def get_metric_values(
            self,
            metric_name: str,
            start_time: Optional[datetime] = None,
            end_time: Optional[datetime] = None,
            labels: Optional[Dict[str, str]] = None
    ) -> List[Dict]:
        """
        Get historical values for a metric.

        Args:
            metric_name: Name of the metric
            start_time: Start of time range
            end_time: End of time range
            labels: Label filters

        Returns:
            List of metric values with timestamps
        """
        if metric_name not in self.metrics:
            raise ValueError(f"Metric {metric_name} not found")

        # This is a simplified implementation that would need to be
        # replaced with actual time series storage in production
        metric = self.metrics[metric_name]
        return [{
            'timestamp': datetime.now().isoformat(),
            'value': metric._value.get()
        }]

    def visualize_metric(
            self,
            metric_name: str,
            start_time: Optional[datetime] = None,
            end_time: Optional[datetime] = None,
            labels: Optional[Dict[str, str]] = None
    ) -> None:
        """
        Create visualization for metric values.

        Args:
            metric_name: Name of the metric
            start_time: Start of time range
            end_time: End of time range
            labels: Label filters
        """
        values = self.get_metric_values(
            metric_name,
            start_time,
            end_time,
            labels
        )

        timestamps = [v['timestamp'] for v in values]
        metric_values = [v['value'] for v in values]

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=timestamps,
            y=metric_values,
            mode='lines+markers',
            name=metric_name
        ))

        fig.update_layout(
            title=f"Metric: {metric_name}",
            xaxis_title="Time",
            yaxis_title="Value"
        )

        fig.show()

    def export_metrics(self, filepath: str) -> None:
        """
        Export all metric values to JSON file.

        Args:
            filepath: Output JSON file path
        """
        export_data = {
            'metrics': {},
            'alerts': self.alert_history
        }

        for name, metric in self.metrics.items():
            export_data['metrics'][name] = {
                'schema': vars(self.schemas[name]),
                'values': self.get_metric_values(name)
            }

        with open(filepath, 'w') as f:
            json.dump(export_data, f, indent=2)


@click.group()
def cli():
    """CLI commands for MetricsCollector."""
    pass


@cli.command()
@click.option('--port', default=8000, help='Prometheus metrics port')
@click.option('--interval', default=60, help='Collection interval in seconds')
def start(port: int, interval: int):
    """Start the metrics collector."""
    collector = MetricsCollector(port, interval)
    click.echo(f"Started MetricsCollector on port {port}")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        collector.running = False
        collector.collector_thread.join()


@cli.command()
@click.argument('metric_name')
@click.option('--start', help='Start time (ISO format)')
@click.option('--end', help='End time (ISO format)')
@click.option('--labels', help='Label filters (key=value,key2=value2)')
def query(
        metric_name: str,
        start: Optional[str],
        end: Optional[str],
        labels: Optional[str]
):
    """Query metric values."""
    collector = MetricsCollector()

    label_dict = {}
    if labels:
        for item in labels.split(','):
            key, value = item.split('=')
            label_dict[key] = value

    start_time = datetime.fromisoformat(start) if start else None
    end_time = datetime.fromisoformat(end) if end else None

    values = collector.get_metric_values(
        metric_name,
        start_time,
        end_time,
        label_dict
    )
    click.echo(json.dumps(values, indent=2))


@cli.command()
@click.argument('metric_name')
@click.option('--start', help='Start time (ISO format)')
@click.option('--end', help='End time (ISO format)')
@click.option('--labels', help='Label filters (key=value,key2=value2)')
def visualize(
        metric_name: str,
        start: Optional[str],
        end: Optional[str],
        labels: Optional[str]
):
    """Visualize metric values."""
    collector = MetricsCollector()

    label_dict = {}
    if labels:
        for item in labels.split(','):
            key, value = item.split('=')
            label_dict[key] = value

    start_time = datetime.fromisoformat(start) if start else None
    end_time = datetime.fromisoformat(end) if end else None

    collector.visualize_metric(metric_name, start_time, end_time, label_dict)


@cli.command()
@click.argument('output_file')
def export(output_file: str):
    """Export all metrics to JSON file."""
    collector = MetricsCollector()
    collector.export_metrics(output_file)
    click.echo(f"Exported metrics to {output_file}")


if __name__ == '__main__':
    cli()
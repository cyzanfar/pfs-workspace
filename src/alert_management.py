import json
import smtplib
import logging
import requests
import threading
from typing import Dict, List, Optional, Union, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from collections import defaultdict
import click


@dataclass
class AlertRule:
    """Alert rule definition."""
    name: str
    query: str  # Metrics query or log pattern
    condition: str  # Expression: >, <, ==, etc.
    threshold: float
    duration: timedelta
    severity: str  # critical, warning, info
    labels: Dict[str, str] = field(default_factory=dict)
    annotations: Dict[str, str] = field(default_factory=dict)


@dataclass
class NotificationChannel:
    """Notification channel configuration."""
    name: str
    type: str  # email, webhook, slack
    config: Dict[str, str]
    enabled: bool = True


class AlertManager:
    """
    System-wide alert handling and notification routing.

    Features:
    - Alert rule management
    - Alert aggregation and deduplication
    - Multi-channel notifications
    - Integration with MetricsCollector
    - Integration with StructuredLogger
    """

    def __init__(
            self,
            metrics_collector=None,
            structured_logger=None,
            check_interval: int = 60
    ):
        """
        Initialize AlertManager.

        Args:
            metrics_collector: Optional MetricsCollector instance
            structured_logger: Optional StructuredLogger instance
            check_interval: Alert check interval in seconds
        """
        self.rules: Dict[str, AlertRule] = {}
        self.channels: Dict[str, NotificationChannel] = {}
        self.active_alerts: Dict[str, Dict] = {}
        self.alert_history: List[Dict] = []

        self.metrics_collector = metrics_collector
        self.structured_logger = structured_logger
        self.check_interval = check_interval
        self.logger = self._setup_logger()

        # Start alert checking thread
        self.running = True
        self.checker_thread = threading.Thread(
            target=self._check_loop,
            daemon=True
        )
        self.checker_thread.start()

    def _setup_logger(self) -> logging.Logger:
        """Configure logging for alert management."""
        logger = logging.getLogger("AlertManager")
        logger.setLevel(logging.INFO)

        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        return logger

    def add_rule(self, rule: AlertRule) -> None:
        """
        Add a new alert rule.

        Args:
            rule: AlertRule configuration
        """
        if rule.name in self.rules:
            raise ValueError(f"Alert rule {rule.name} already exists")

        self.rules[rule.name] = rule
        self.logger.info(f"Added alert rule: {rule.name}")

    def update_rule(self, rule: AlertRule) -> None:
        """
        Update an existing alert rule.

        Args:
            rule: Updated AlertRule configuration
        """
        if rule.name not in self.rules:
            raise ValueError(f"Alert rule {rule.name} not found")

        self.rules[rule.name] = rule
        self.logger.info(f"Updated alert rule: {rule.name}")

    def delete_rule(self, rule_name: str) -> None:
        """
        Delete an alert rule.

        Args:
            rule_name: Name of rule to delete
        """
        if rule_name not in self.rules:
            raise ValueError(f"Alert rule {rule_name} not found")

        del self.rules[rule_name]
        self.logger.info(f"Deleted alert rule: {rule_name}")

    def add_channel(self, channel: NotificationChannel) -> None:
        """
        Add a notification channel.

        Args:
            channel: NotificationChannel configuration
        """
        if channel.name in self.channels:
            raise ValueError(f"Channel {channel.name} already exists")

        self.channels[channel.name] = channel
        self.logger.info(f"Added notification channel: {channel.name}")

    def update_channel(self, channel: NotificationChannel) -> None:
        """
        Update a notification channel.

        Args:
            channel: Updated NotificationChannel configuration
        """
        if channel.name not in self.channels:
            raise ValueError(f"Channel {channel.name} not found")

        self.channels[channel.name] = channel
        self.logger.info(f"Updated notification channel: {channel.name}")

    def delete_channel(self, channel_name: str) -> None:
        """
        Delete a notification channel.

        Args:
            channel_name: Name of channel to delete
        """
        if channel_name not in self.channels:
            raise ValueError(f"Channel {channel_name} not found")

        del self.channels[channel_name]
        self.logger.info(f"Deleted notification channel: {channel_name}")

    def check_rule(self, rule: AlertRule) -> Optional[Dict]:
        """
        Check if an alert rule is triggered.

        Args:
            rule: AlertRule to check

        Returns:
            Alert data if triggered, None otherwise
        """
        try:
            # Check metrics-based rules
            if self.metrics_collector and rule.query.startswith('metric:'):
                metric_name = rule.query.split(':', 1)[1]
                value = self.metrics_collector.get_metric_values(
                    metric_name,
                    datetime.now() - rule.duration,
                    datetime.now(),
                    rule.labels
                )[-1]['value']

                if self._evaluate_condition(value, rule.condition, rule.threshold):
                    return {
                        'rule': rule.name,
                        'value': value,
                        'threshold': rule.threshold,
                        'severity': rule.severity,
                        'labels': rule.labels,
                        'annotations': rule.annotations,
                        'timestamp': datetime.now().isoformat()
                    }

            # Check log-based rules
            elif self.structured_logger and rule.query.startswith('log:'):
                pattern = rule.query.split(':', 1)[1]
                matches = self.structured_logger.search_logs(
                    pattern,
                    datetime.now() - rule.duration,
                    datetime.now()
                )

                if len(matches) > rule.threshold:
                    return {
                        'rule': rule.name,
                        'value': len(matches),
                        'threshold': rule.threshold,
                        'severity': rule.severity,
                        'labels': rule.labels,
                        'annotations': rule.annotations,
                        'timestamp': datetime.now().isoformat()
                    }

        except Exception as e:
            self.logger.error(f"Error checking rule {rule.name}: {str(e)}")

        return None

    def _evaluate_condition(
            self,
            value: float,
            condition: str,
            threshold: float
    ) -> bool:
        """Evaluate alert condition."""
        if condition == '>':
            return value > threshold
        elif condition == '<':
            return value < threshold
        elif condition == '>=':
            return value >= threshold
        elif condition == '<=':
            return value <= threshold
        elif condition == '==':
            return value == threshold
        else:
            raise ValueError(f"Invalid condition: {condition}")

    def _check_loop(self) -> None:
        """Background thread for checking alert rules."""
        while self.running:
            try:
                for rule in self.rules.values():
                    alert = self.check_rule(rule)

                    if alert:
                        alert_key = f"{rule.name}:{json.dumps(rule.labels)}"

                        # New alert
                        if alert_key not in self.active_alerts:
                            self.active_alerts[alert_key] = alert
                            self.alert_history.append(alert)
                            self._send_notifications(alert)

                        # Update existing alert
                        else:
                            self.active_alerts[alert_key].update(alert)

                    # Clear resolved alert
                    elif alert_key in self.active_alerts:
                        del self.active_alerts[alert_key]

            except Exception as e:
                self.logger.error(f"Error in alert check loop: {str(e)}")

            time.sleep(self.check_interval)

    def _send_notifications(self, alert: Dict) -> None:
        """
        Send alert notifications via configured channels.

        Args:
            alert: Alert data to send
        """
        for channel in self.channels.values():
            if not channel.enabled:
                continue

            try:
                if channel.type == 'email':
                    self._send_email(channel, alert)
                elif channel.type == 'webhook':
                    self._send_webhook(channel, alert)
                elif channel.type == 'slack':
                    self._send_slack(channel, alert)

            except Exception as e:
                self.logger.error(
                    f"Error sending notification via {channel.name}: {str(e)}"
                )

    def _send_email(self, channel: NotificationChannel, alert: Dict) -> None:
        """Send email notification."""
        msg = MIMEText(json.dumps(alert, indent=2))
        msg['Subject'] = f"Alert: {alert['rule']} ({alert['severity']})"
        msg['From'] = channel.config['from_address']
        msg['To'] = channel.config['to_address']

        with smtplib.SMTP(
                channel.config['smtp_host'],
                int(channel.config['smtp_port'])
        ) as smtp:
            if channel.config.get('smtp_user'):
                smtp.login(
                    channel.config['smtp_user'],
                    channel.config['smtp_password']
                )
            smtp.send_message(msg)

    def _send_webhook(self, channel: NotificationChannel, alert: Dict) -> None:
        """Send webhook notification."""
        response = requests.post(
            channel.config['url'],
            json=alert,
            headers=channel.config.get('headers', {})
        )
        response.raise_for_status()

    def _send_slack(self, channel: NotificationChannel, alert: Dict) -> None:
        """Send Slack notification."""
        message = {
            'text': f"Alert: {alert['rule']} ({alert['severity']})",
            'attachments': [{
                'color': 'danger' if alert['severity'] == 'critical' else 'warning',
                'fields': [
                    {'title': k, 'value': str(v), 'short': True}
                    for k, v in alert.items()
                ]
            }]
        }

        response = requests.post(
            channel.config['webhook_url'],
            json=message
        )
        response.raise_for_status()


@click.group()
def cli():
    """CLI commands for AlertManager."""
    pass


@cli.group()
def rules():
    """Manage alert rules."""
    pass


@rules.command()
@click.argument('name')
@click.option('--query', required=True, help='Metrics query or log pattern')
@click.option('--condition', required=True, help='Alert condition')
@click.option('--threshold', required=True, type=float, help='Alert threshold')
@click.option('--duration', required=True, help='Duration (e.g. 5m, 1h)')
@click.option('--severity', default='warning', help='Alert severity')
@click.option('--labels', help='Labels (key=value,key2=value2)')
@click.option('--annotations', help='Annotations (key=value,key2=value2)')
def add_rule(
        name: str,
        query: str,
        condition: str,
        threshold: float,
        duration: str,
        severity: str,
        labels: Optional[str],
        annotations: Optional[str]
):
    """Add a new alert rule."""
    manager = AlertManager()

    # Parse duration
    duration_map = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}
    duration_val = int(duration[:-1])
    duration_unit = duration[-1]
    duration_secs = duration_val * duration_map[duration_unit]

    # Parse labels and annotations
    label_dict = {}
    if labels:
        for item in labels.split(','):
            key, value = item.split('=')
            label_dict[key] = value

    annotation_dict = {}
    if annotations:
        for item in annotations.split(','):
            key, value = item.split('=')
            annotation_dict[key] = value

    rule = AlertRule(
        name=name,
        query=query,
        condition=condition,
        threshold=threshold,
        duration=timedelta(seconds=duration_secs),
        severity=severity,
        labels=label_dict,
        annotations=annotation_dict
    )

    manager.add_rule(rule)
    click.echo(f"Added alert rule: {name}")


@rules.command()
@click.argument('name')
def delete_rule(name: str):
    """Delete an alert rule."""
    manager = AlertManager()
    manager.delete_rule(name)
    click.echo(f"Deleted alert rule: {name}")


@cli.group()
def channels():
    """Manage notification channels."""
    pass


@channels.command()
@click.argument('name')
@click.option('--type', required=True, help='Channel type (email/webhook/slack)')
@click.option('--config', required=True, help='Channel config (key=value,...)')
def add_channel(name: str, type: str, config: str):
    """Add a notification channel."""
    manager = AlertManager()

    config_dict = {}
    for item in config.split(','):
        key, value = item.split('=')
        config_dict[key] = value

    channel = NotificationChannel(
        name=name,
        type=type,
        config=config_dict
    )

    manager.add_channel(channel)
    click.echo(f"Added notification channel: {name}")


@channels.command()
@click.argument('name')
def delete_channel(name: str):
    """Delete a notification channel."""
    manager = AlertManager()
    manager.delete_channel(name)
    click.echo(f"Deleted notification channel: {name}")


if __name__ == '__main__':
    cli()
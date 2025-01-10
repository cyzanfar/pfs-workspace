# src/security_monitor.py
import asyncio
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Set
import json
import aiofiles
import logging
import statistics
import aiohttp


class SecurityEventType(Enum):
    FAILED_LOGIN = "failed_login"
    INVALID_TRANSACTION = "invalid_transaction"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    KEY_ROTATION = "key_rotation"
    SYSTEM_ERROR = "system_error"


class AlertSeverity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class SecurityEvent:
    event_type: SecurityEventType
    timestamp: datetime
    severity: AlertSeverity
    description: str
    source_ip: Optional[str] = None
    user_id: Optional[str] = None
    details: Optional[dict] = None


@dataclass
class SecurityMetrics:
    total_events: int
    events_by_type: Dict[SecurityEventType, int]
    events_by_severity: Dict[AlertSeverity, int]
    average_events_per_hour: float
    active_alerts: int


class SecurityMonitor:
    def __init__(self,
                 log_path: str = "logs/security.log",
                 webhook_url: Optional[str] = None,
                 rate_limit_window: int = 3600,  # 1 hour
                 rate_limit_max: int = 1000):
        self.log_path = log_path
        self.webhook_url = webhook_url
        self.rate_limit_window = rate_limit_window
        self.rate_limit_max = rate_limit_max

        # Initialize logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger("SecurityMonitor")

        # Event storage
        self.events: deque = deque(maxlen=10000)  # Keep last 10k events
        self.alerts: List[SecurityEvent] = []

        # Rate limiting
        self.request_counts: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=rate_limit_window)
        )

        # Baseline metrics for anomaly detection
        self.baseline_metrics: Dict[SecurityEventType, float] = {}
        self.anomaly_thresholds: Dict[SecurityEventType, float] = {}

        # Start monitoring
        asyncio.create_task(self._monitor_loop())

    async def _monitor_loop(self):
        """Main monitoring loop"""
        while True:
            try:
                await self._update_baseline_metrics()
                await self._check_anomalies()
                await self._cleanup_old_data()
                await asyncio.sleep(60)  # Check every minute
            except Exception as e:
                self.logger.error(f"Monitor loop error: {str(e)}")
                await asyncio.sleep(5)

    async def log_event(self, event: SecurityEvent):
        """Log security event and trigger alerts if needed"""
        self.events.append(event)

        # Log to file
        async with aiofiles.open(self.log_path, 'a') as f:
            await f.write(json.dumps({
                'timestamp': event.timestamp.isoformat(),
                'type': event.event_type.value,
                'severity': event.severity.value,
                'description': event.description,
                'source_ip': event.source_ip,
                'user_id': event.user_id,
                'details': event.details
            }) + '\n')

        # Check for alerts
        await self._check_for_alerts(event)

        # Update rate limiting
        if event.source_ip:
            self.request_counts[event.source_ip].append(event.timestamp)

    async def _check_for_alerts(self, event: SecurityEvent):
        """Check if event should trigger alerts"""
        # Check rate limits
        if event.source_ip and self._is_rate_limited(event.source_ip):
            await self._trigger_alert(SecurityEvent(
                event_type=SecurityEventType.RATE_LIMIT_EXCEEDED,
                timestamp=datetime.now(),
                severity=AlertSeverity.HIGH,
                description=f"Rate limit exceeded for IP: {event.source_ip}",
                source_ip=event.source_ip
            ))

        # Check for suspicious patterns
        if self._is_suspicious_pattern(event):
            await self._trigger_alert(SecurityEvent(
                event_type=SecurityEventType.SUSPICIOUS_ACTIVITY,
                timestamp=datetime.now(),
                severity=AlertSeverity.HIGH,
                description="Suspicious activity pattern detected",
                source_ip=event.source_ip,
                user_id=event.user_id,
                details={'trigger_event': event.event_type.value}
            ))

        # Check for anomalies
        if self._is_anomalous_event(event):
            await self._trigger_alert(SecurityEvent(
                event_type=SecurityEventType.SUSPICIOUS_ACTIVITY,
                timestamp=datetime.now(),
                severity=AlertSeverity.MEDIUM,
                description="Anomalous event pattern detected",
                details={'event_type': event.event_type.value}
            ))

    def _is_rate_limited(self, source_ip: str) -> bool:
        """Check if source IP has exceeded rate limit"""
        recent_requests = self.request_counts[source_ip]
        if len(recent_requests) >= self.rate_limit_max:
            window_start = datetime.now() - timedelta(seconds=self.rate_limit_window)
            return recent_requests[0] >= window_start
        return False

    def _is_suspicious_pattern(self, event: SecurityEvent) -> bool:
        """Check for suspicious activity patterns"""
        if event.event_type == SecurityEventType.FAILED_LOGIN:
            # Check for multiple failed logins
            recent_failed_logins = sum(
                1 for e in self.events
                if e.event_type == SecurityEventType.FAILED_LOGIN
                and e.source_ip == event.source_ip
                and e.timestamp >= datetime.now() - timedelta(minutes=5)
            )
            return recent_failed_logins >= 5

        if event.event_type == SecurityEventType.INVALID_TRANSACTION:
            # Check for multiple invalid transactions
            recent_invalid_tx = sum(
                1 for e in self.events
                if e.event_type == SecurityEventType.INVALID_TRANSACTION
                and e.user_id == event.user_id
                and e.timestamp >= datetime.now() - timedelta(minutes=15)
            )
            return recent_invalid_tx >= 3

        return False

    async def _update_baseline_metrics(self):
        """Update baseline metrics for anomaly detection"""
        for event_type in SecurityEventType:
            recent_events = [
                e for e in self.events
                if e.event_type == event_type
                   and e.timestamp >= datetime.now() - timedelta(hours=24)
            ]

            if recent_events:
                # Calculate events per hour
                events_per_hour = len(recent_events) / 24
                self.baseline_metrics[event_type] = events_per_hour

                # Set threshold at 2 standard deviations above mean
                if len(recent_events) > 1:
                    std_dev = statistics.stdev(
                        self._events_per_hour_for_period(recent_events, period=1)
                    )
                    self.anomaly_thresholds[event_type] = (
                            events_per_hour + (2 * std_dev)
                    )
                else:
                    self.anomaly_thresholds[event_type] = events_per_hour * 2

    def _events_per_hour_for_period(self,
                                    events: List[SecurityEvent],
                                    period: int) -> List[float]:
        """Calculate events per hour for each period"""
        counts = defaultdict(int)
        for event in events:
            hour = event.timestamp.replace(minute=0, second=0, microsecond=0)
            counts[hour] += 1
        return list(counts.values())

    def _is_anomalous_event(self, event: SecurityEvent) -> bool:
        """Check if event frequency is anomalous"""
        if event.event_type not in self.baseline_metrics:
            return False

        recent_count = sum(
            1 for e in self.events
            if e.event_type == event.event_type
            and e.timestamp >= datetime.now() - timedelta(hours=1)
        )

        return recent_count > self.anomaly_thresholds[event.event_type]

    async def _trigger_alert(self, event: SecurityEvent):
        """Trigger alert for security event"""
        self.alerts.append(event)
        self.logger.warning(
            f"Security Alert: {event.description} "
            f"[{event.severity.value.upper()}]"
        )

        # Send webhook if configured
        if self.webhook_url:
            await self._send_webhook_alert(event)

    async def _send_webhook_alert(self, event: SecurityEvent):
        """Send alert to webhook endpoint"""
        async with aiohttp.ClientSession() as session:
            try:
                await session.post(self.webhook_url, json={
                    'timestamp': event.timestamp.isoformat(),
                    'type': event.event_type.value,
                    'severity': event.severity.value,
                    'description': event.description,
                    'source_ip': event.source_ip,
                    'user_id': event.user_id,
                    'details': event.details
                })
            except Exception as e:
                self.logger.error(f"Webhook alert failed: {str(e)}")

    async def _cleanup_old_data(self):
        """Clean up old data"""
        # Clean up old rate limit data
        current_time = datetime.now()
        for ip in list(self.request_counts.keys()):
            self.request_counts[ip] = deque(
                dt for dt in self.request_counts[ip]
                if dt >= current_time - timedelta(seconds=self.rate_limit_window)
                , maxlen=self.rate_limit_window)

            if not self.request_counts[ip]:
                del self.request_counts[ip]

        # Clean up old alerts
        self.alerts = [
            alert for alert in self.alerts
            if alert.timestamp >= current_time - timedelta(days=7)
        ]

    async def get_metrics(self) -> SecurityMetrics:
        """Get current security metrics"""
        current_time = datetime.now()
        recent_events = [
            e for e in self.events
            if e.timestamp >= current_time - timedelta(hours=1)
        ]

        return SecurityMetrics(
            total_events=len(self.events),
            events_by_type=defaultdict(int, {
                event_type: sum(1 for e in self.events if e.event_type == event_type)
                for event_type in SecurityEventType
            }),
            events_by_severity=defaultdict(int, {
                severity: sum(1 for e in self.events if e.severity == severity)
                for severity in AlertSeverity
            }),
            average_events_per_hour=len(recent_events),
            active_alerts=len(self.alerts)
        )

    async def get_active_alerts(self) -> List[SecurityEvent]:
        """Get current active alerts"""
        return self.alerts

    async def get_events(self,
                         start_time: Optional[datetime] = None,
                         end_time: Optional[datetime] = None,
                         event_types: Optional[Set[SecurityEventType]] = None,
                         severities: Optional[Set[AlertSeverity]] = None
                         ) -> List[SecurityEvent]:
        """Get filtered security events"""
        events = self.events

        if start_time:
            events = [e for e in events if e.timestamp >= start_time]
        if end_time:
            events = [e for e in events if e.timestamp <= end_time]
        if event_types:
            events = [e for e in events if e.event_type in event_types]
        if severities:
            events = [e for e in events if e.severity in severities]

        return sorted(events, key=lambda e: e.timestamp, reverse=True)
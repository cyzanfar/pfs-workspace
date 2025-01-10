# src/security_cli.py
import click
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Set
from .security_monitor import (
    SecurityMonitor, SecurityEventType, AlertSeverity, SecurityEvent
)


def init_security_monitor(ctx) -> SecurityMonitor:
    """Initialize security monitor"""
    if 'security_monitor' not in ctx.obj:
        ctx.obj['security_monitor'] = SecurityMonitor()
    return ctx.obj['security_monitor']


@click.group()
def security():
    """Security monitoring commands"""
    pass


@security.command()
@click.pass_context
async def metrics(ctx):
    """Show current security metrics"""
    monitor = init_security_monitor(ctx)
    metrics = await monitor.get_metrics()

    click.echo("\nSecurity Metrics:")
    click.echo("-" * 40)
    click.echo(f"Total Events: {metrics.total_events}")
    click.echo(f"Active Alerts: {metrics.active_alerts}")
    click.echo(f"Events/Hour: {metrics.average_events_per_hour}")

    click.echo("\nEvents by Type:")
    for event_type, count in metrics.events_by_type.items():
        click.echo(f"  {event_type.value}: {count}")

    click.echo("\nEvents by Severity:")
    for severity, count in metrics.events_by_severity.items():
        click.echo(f"  {severity.value}: {count}")


@security.command()
@click.option('--hours', default=24, help='Hours of history to show')
@click.option('--type', 'event_types', multiple=True,
              type=click.Choice([t.value for t in SecurityEventType]),
              help='Filter by event type')
@click.option('--severity', 'severities', multiple=True,
              type=click.Choice([s.value for s in AlertSeverity]),
              help='Filter by severity')
@click.pass_context
async def events(ctx, hours: int, event_types: tuple, severities: tuple):
    """Show security events"""
    monitor = init_security_monitor(ctx)

    # Convert string values to enums
    event_type_enums = {SecurityEventType(t) for t in event_types} if event_types else None
    severity_enums = {AlertSeverity(s) for s in severities} if severities else None

    # Get filtered events
    events = await monitor.get_events(
        start_time=datetime.now() - timedelta(hours=hours),
        event_types=event_type_enums,
        severities=severity_enums
    )

    if not events:
        click.echo("No events found matching criteria")
        return

    click.echo(f"\nSecurity Events (last {hours} hours):")
    click.echo("-" * 60)

    for event in events:
        click.echo(f"\nTime: {event.timestamp}")
        click.echo(f"Type: {event.event_type.value}")
        click.echo(f"Severity: {event.severity.value}")
        click.echo(f"Description: {event.description}")
        if event.source_ip:
            click.echo(f"Source IP: {event.source_ip}")
        if event.user_id:
            click.echo(f"User ID: {event.user_id}")
        if event.details:
            click.echo("Details:")
            for key, value in event.details.items():
                click.echo(f"  {key}: {value}")


@security.command()
@click.pass_context
async def alerts(ctx):
    """Show active security alerts"""
    monitor = init_security_monitor(ctx)
    alerts = await monitor.get_active_alerts()

    if not alerts:
        click.echo("No active alerts")
        return

    click.echo("\nActive Security Alerts:")
    click.echo("-" * 60)

    for alert in alerts:
        click.echo(f"\nTime: {alert.timestamp}")
        click.echo(f"Type: {alert.event_type.value}")
        click.echo(f"Severity: {alert.severity.value}")
        click.echo(f"Description: {alert.description}")
        if alert.source_ip:
            click.echo(f"Source IP: {alert.source_ip}")
        if alert.user_id:
            click.echo(f"User ID: {alert.user_id}")
        if alert.details:
            click.echo("Details:")
            for key, value in alert.details.items():
                click.echo(f"  {key}: {value}")


@security.command()
@click.option('--ip', help='Show rate limit info for specific IP')
@click.pass_context
async def ratelimits(ctx, ip: Optional[str]):
    """Show rate limit information"""
    monitor = init_security_monitor(ctx)

    if ip:
        # Show specific IP
        count = len(monitor.request_counts.get(ip, []))
        limit = monitor.rate_limit_max
        window = monitor.rate_limit_window

        click.echo(f"\nRate Limit Info for {ip}:")
        click.echo(f"Requests: {count}/{limit}")
        click.echo(f"Window: {window} seconds")
        click.echo(f"Status: {'BLOCKED' if monitor._is_rate_limited(ip) else 'OK'}")
    else:
        # Show all rate-limited IPs
        limited_ips = [
            ip for ip in monitor.request_counts.keys()
            if monitor._is_rate_limited(ip)
        ]

        if not limited_ips:
            click.echo("No IPs currently rate limited")
            return

        click.echo("\nRate Limited IPs:")
        for ip in limited_ips:
            count = len(monitor.request_counts[ip])
            click.echo(f"{ip}: {count} requests")


@security.command()
@click.option('--output', type=click.Path(), help='Save events to file')
@click.option('--hours', default=24, help='Hours of history to export')
@click.pass_context
async def export(ctx, output: Optional[str], hours: int):
    """Export security events"""
    monitor = init_security_monitor(ctx)

    events = await monitor.get_events(
        start_time=datetime.now() - timedelta(hours=hours)
    )

    export_data = {
        'generated_at': datetime.now().isoformat(),
        'period_hours': hours,
        'events': [
            {
                'timestamp': event.timestamp.isoformat(),
                'type': event.event_type.value,
                'severity': event.severity.value,
                'description': event.description,
                'source_ip': event.source_ip,
                'user_id': event.user_id,
                'details': event.details
            }
            for event in events
        ]
    }

    if output:
        with open(output, 'w') as f:
            json.dump(export_data, f, indent=2)
        click.echo(f"\nExported {len(events)} events to {output}")
    else:
        click.echo(json.dumps(export_data, indent=2))


def setup_cli():
    """Setup CLI with async command handling"""

    async def async_security(ctx, *args, **kwargs):
        """Async wrapper for security command group"""
        return await ctx.forward(security)

    return click.command()(click.pass_context(async_security))


if __name__ == '__main__':
    cli = setup_cli()
    cli(obj={})
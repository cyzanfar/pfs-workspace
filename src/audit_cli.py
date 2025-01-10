# src/audit_cli.py
import click
from datetime import datetime, timedelta
import json
from pathlib import Path
from typing import Optional, List
from .audit_logger import AuditLogger, AuditEventType


def init_audit_logger(ctx) -> AuditLogger:
    """Initialize audit logger"""
    if 'audit_logger' not in ctx.obj:
        ctx.obj['audit_logger'] = AuditLogger()
    return ctx.obj['audit_logger']


@click.group()
def audit():
    """Audit logging commands"""
    pass


@audit.command()
@click.option('--days', default=7, help='Number of days to analyze')
@click.option('--type', 'event_types', multiple=True,
              type=click.Choice([t.value for t in AuditEventType]),
              help='Filter by event type')
@click.option('--user', help='Filter by user ID')
@click.option('--ip', help='Filter by source IP')
@click.pass_context
async def logs(ctx, days: int, event_types: tuple, user: Optional[str],
               ip: Optional[str]):
    """View audit logs with filters"""
    logger = init_audit_logger(ctx)

    end_time = datetime.now()
    start_time = end_time - timedelta(days=days)

    # Convert string values to enums
    event_type_enums = None
    if event_types:
        event_type_enums = [AuditEventType(t) for t in event_types]

    events = await logger.search_logs(
        start_time=start_time,
        end_time=end_time,
        event_types=event_type_enums,
        user_id=user,
        source_ip=ip
    )

    if not events:
        click.echo("No audit events found matching criteria")
        return

    click.echo(f"\nAudit Events (last {days} days):")
    click.echo("-" * 80)

    for event in events:
        click.echo(f"\nTimestamp: {event.timestamp}")
        click.echo(f"Event Type: {event.event_type.value}")
        click.echo(f"Event ID: {event.event_id}")
        if event.user_id:
            click.echo(f"User: {event.user_id}")
        if event.source_ip:
            click.echo(f"Source IP: {event.source_ip}")
        click.echo(f"Action: {event.action}")
        click.echo(f"Status: {event.status}")
        if event.correlation_id:
            click.echo(f"Correlation ID: {event.correlation_id}")
        if event.details:
            click.echo("Details:")
            for key, value in event.details.items():
                click.echo(f"  {key}: {value}")


@audit.command()
@click.option('--output', type=click.Path(), required=True,
              help='Report output file')
@click.option('--start-date', type=click.DateTime(),
              default=str(datetime.now().date() - timedelta(days=30)),
              help='Start date (YYYY-MM-DD)')
@click.option('--end-date', type=click.DateTime(),
              default=str(datetime.now().date()),
              help='End date (YYYY-MM-DD)')
@click.pass_context
async def report(ctx, output: str, start_date: datetime, end_date: datetime):
    """Generate compliance report"""
    logger = init_audit_logger(ctx)

    click.echo(f"Generating compliance report from {start_date.date()} "
               f"to {end_date.date()}...")

    report = await logger.generate_compliance_report(start_date, end_date)

    # Save report
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w') as f:
        json.dump(report, f, indent=2)

    click.echo(f"\nReport generated successfully:")
    click.echo(f"Total Events: {report['total_events']}")
    click.echo("\nEvents by Type:")
    for event_type, count in report['events_by_type'].items():
        click.echo(f"  {event_type}: {count}")

    click.echo(f"\nSystem Health:")
    click.echo(f"  Errors: {report['system_health']['errors']}")
    click.echo(f"  Warnings: {report['system_health']['warnings']}")

    click.echo(f"\nFull report saved to: {output}")


@audit.command()
@click.option('--output', required=True, type=click.Path(),
              help='Export file location')
@click.option('--days', default=30, help='Number of days to export')
@click.option('--type', 'event_types', multiple=True,
              type=click.Choice([t.value for t in AuditEventType]),
              help='Filter by event type')
@click.pass_context
async def export(ctx, output: str, days: int, event_types: tuple):
    """Export audit logs to file"""
    logger = init_audit_logger(ctx)

    end_time = datetime.now()
    start_time = end_time - timedelta(days=days)

    # Convert string values to enums
    event_type_enums = None
    if event_types:
        event_type_enums = [AuditEventType(t) for t in event_types]

    click.echo(f"Exporting audit logs from the last {days} days...")

    await logger.export_logs(
        output_file=output,
        start_time=start_time,
        end_time=end_time,
        event_types=event_type_enums
    )

    click.echo(f"\nLogs exported successfully to: {output}")


@audit.command()
@click.pass_context
async def status(ctx):
    """Show audit logging status"""
    logger = init_audit_logger(ctx)

    log_dir = Path(logger.log_dir)

    # Gather statistics
    total_files = len(list(log_dir.glob('*.log.enc')))
    current_log = logger.current_file.name if logger.current_file else "None"
    current_size = logger.current_size / 1024  # Convert to KB

    click.echo("\nAudit Logger Status:")
    click.echo("-" * 40)
    click.echo(f"Log Directory: {log_dir}")
    click.echo(f"Archived Files: {total_files}")
    click.echo(f"Current Log: {current_log}")
    click.echo(f"Current Size: {current_size:.2f}KB")
    click.echo(f"Max File Size: {logger.max_file_size / 1024 / 1024:.0f}MB")
    click.echo(f"Retention Period: {logger.retention_days} days")


def setup_cli():
    """Setup CLI with async command handling"""

    async def async_audit(ctx, *args, **kwargs):
        """Async wrapper for audit command group"""
        return await ctx.forward(audit)

    return click.command()(click.pass_context(async_audit))


if __name__ == '__main__':
    cli = setup_cli()
    cli(obj={})
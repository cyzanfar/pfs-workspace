# src/resilience_cli.py
import click
import asyncio
from datetime import datetime
from .resilience_manager import (
    SystemResilienceManager, ComponentStatus, FailureType
)


def init_resilience_manager(ctx) -> SystemResilienceManager:
    """Initialize resilience manager"""
    if 'resilience_manager' not in ctx.obj:
        ctx.obj['resilience_manager'] = SystemResilienceManager()
    return ctx.obj['resilience_manager']


@click.group()
def resilience():
    """System resilience monitoring commands"""
    pass


@resilience.command()
@click.pass_context
async def health(ctx):
    """Show system health status"""
    manager = init_resilience_manager(ctx)
    health = await manager.get_system_health()

    click.echo("\nSystem Health Status:")
    click.echo("-" * 40)
    click.echo(f"Overall Status: {health.overall_status.value.upper()}")

    if health.failure_cascade_risk:
        click.echo("\n⚠️  CASCADE FAILURE RISK DETECTED!")

    if health.healthy_components:
        click.echo("\nHealthy Components:")
        for comp in health.healthy_components:
            click.echo(f"  ✓ {comp}")

    if health.degraded_components:
        click.echo("\nDegraded Components:")
        for comp in health.degraded_components:
            click.echo(f"  ⚠️  {comp}")

    if health.failed_components:
        click.echo("\nFailed Components:")
        for comp in health.failed_components:
            click.echo(f"  ✗ {comp}")


@resilience.command()
@click.argument('component')
@click.pass_context
async def metrics(ctx, component: str):
    """Show detailed metrics for component"""
    manager = init_resilience_manager(ctx)

    try:
        metrics = await manager.get_component_metrics(component)

        click.echo(f"\nComponent Metrics: {component}")
        click.echo("-" * 40)
        click.echo(f"Status: {metrics['status'].upper()}")
        click.echo(f"Error Rate: {metrics['error_rate']:.2%}")
        click.echo(f"Response Time: {metrics['response_time']:.3f}s")
        click.echo(f"Last Check: {metrics['last_check']}")
        click.echo(f"Total Requests: {metrics['requests']}")
        click.echo(f"Total Errors: {metrics['errors']}")
        click.echo(f"Recovery Attempts: {metrics['recovery_attempts']}")

        if metrics['dependencies']:
            click.echo("\nDependencies:")
            for dep in metrics['dependencies']:
                click.echo(f"  - {dep}")

        if metrics['failures']:
            click.echo("\nRecent Failures:")
            for failure in metrics['failures']:
                click.echo(f"  - {failure}")

    except ValueError as e:
        click.echo(f"Error: {str(e)}", err=True)
        ctx.exit(1)


@resilience.command()
@click.argument('component')
@click.confirmation_option(
    prompt='Are you sure you want to reset this component?'
)
@click.pass_context
async def reset(ctx, component: str):
    """Reset component status"""
    manager = init_resilience_manager(ctx)

    try:
        await manager.reset_component(component)
        click.echo(f"Component {component} has been reset")

    except ValueError as e:
        click.echo(f"Error: {str(e)}", err=True)
        ctx.exit(1)


@resilience.command()
@click.argument('component')
@click.option('--name', required=True, help='Component name')
@click.option('--dependency', multiple=True, help='Component dependencies')
@click.pass_context
async def register(ctx, name: str, dependency: tuple):
    """Register new component for monitoring"""
    manager = init_resilience_manager(ctx)

    try:
        manager.register_component(name, list(dependency) if dependency else None)
        click.echo(f"Component {name} registered for monitoring")
        if dependency:
            click.echo("Dependencies:")
            for dep in dependency:
                click.echo(f"  - {dep}")

    except ValueError as e:
        click.echo(f"Error: {str(e)}", err=True)
        ctx.exit(1)


@resilience.command()
@click.option('--watch', is_flag=True, help='Watch mode with live updates')
@click.option('--interval', default=5, help='Update interval in seconds')
@click.pass_context
async def monitor(ctx, watch: bool, interval: int):
    """Monitor system health in real-time"""
    manager = init_resilience_manager(ctx)

    async def display_health():
        health = await manager.get_system_health()
        click.clear()
        click.echo(f"\nSystem Health Monitor - {datetime.now()}")
        click.echo("-" * 50)
        click.echo(f"Status: {health.overall_status.value.upper()}")

        if health.failure_cascade_risk:
            click.echo("\n⚠️  CASCADE FAILURE RISK!")

        for category, components in [
            ("Healthy", health.healthy_components),
            ("Degraded", health.degraded_components),
            ("Failed", health.failed_components)
        ]:
            if components:
                click.echo(f"\n{category} Components:")
                for comp in components:
                    metrics = await manager.get_component_metrics(comp)
                    click.echo(
                        f"  {comp}: "
                        f"{metrics['error_rate']:.1%} errors, "
                        f"{metrics['response_time']:.2f}s response"
                    )

    if watch:
        while True:
            try:
                await display_health()
                click.echo("\nPress Ctrl+C to stop monitoring...")
                await asyncio.sleep(interval)
            except KeyboardInterrupt:
                click.echo("\nMonitoring stopped")
                break
    else:
        await display_health()


@resilience.command()
@click.argument('component')
@click.argument('duration', type=float)
@click.option('--error', is_flag=True, help='Record as error')
@click.pass_context
async def record(ctx, component: str, duration: float, error: bool):
    """Record request metric for component"""
    manager = init_resilience_manager(ctx)

    try:
        await manager.record_request(component, duration, error)
        click.echo(
            f"Recorded {'error' if error else 'request'} "
            f"for {component} ({duration:.3f}s)"
        )
    except ValueError as e:
        click.echo(f"Error: {str(e)}", err=True)
        ctx.exit(1)


def setup_cli():
    """Setup CLI with async command handling"""

    async def async_resilience(ctx, *args, **kwargs):
        """Async wrapper for resilience command group"""
        return await ctx.forward(resilience)

    return click.command()(click.pass_context(async_resilience))


if __name__ == '__main__':
    cli = setup_cli()
    cli(obj={})
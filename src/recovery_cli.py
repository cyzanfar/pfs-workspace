# src/recovery_cli.py
import click
from datetime import datetime
import asyncio
from typing import Optional
from .recovery_orchestrator import (
    RecoveryOrchestrator, ComponentType, RecoveryStage
)


def init_recovery_orchestrator(ctx) -> RecoveryOrchestrator:
    """Initialize recovery orchestrator"""
    if 'recovery_orchestrator' not in ctx.obj:
        ctx.obj['recovery_orchestrator'] = RecoveryOrchestrator()
    return ctx.obj['recovery_orchestrator']


@click.group()
def recovery():
    """Recovery orchestration commands"""
    pass


@recovery.command()
@click.argument('component', type=click.Choice([c.value for c in ComponentType]))
@click.pass_context
async def status(ctx, component: str):
    """Show recovery status for component"""
    orchestrator = init_recovery_orchestrator(ctx)
    comp_type = ComponentType(component)

    status = await orchestrator.get_recovery_status(comp_type)
    if status:
        click.echo(f"\nRecovery Status: {component}")
        click.echo("-" * 40)
        click.echo(f"Stage: {status.stage.value}")
        click.echo(f"Started: {status.started_at}")
        if status.error:
            click.echo(f"Error: {status.error}")

        if status.verification_checks:
            click.echo("\nVerification Checks:")
            for check, result in status.verification_checks.items():
                click.echo(f"  {check}: {'✓' if result else '✗'}")
    else:
        click.echo(f"No active recovery for {component}")


@recovery.command()
@click.argument('component', type=click.Choice([c.value for c in ComponentType]))
@click.option('--error', help='Error description')
@click.pass_context
async def initiate(ctx, component: str, error: Optional[str]):
    """Initiate component recovery"""
    orchestrator = init_recovery_orchestrator(ctx)
    comp_type = ComponentType(component)

    try:
        state = await orchestrator.initiate_recovery(comp_type, error)
        click.echo(f"\nInitiated recovery for {component}")
        click.echo(f"Stage: {state.stage.value}")
        click.echo(f"Started: {state.started_at}")

    except ValueError as e:
        click.echo(f"Error: {str(e)}", err=True)
        ctx.exit(1)


@recovery.command()
@click.argument('component', type=click.Choice([c.value for c in ComponentType]))
@click.argument('error_type')
@click.confirmation_option(
    prompt='Are you sure you want to simulate a failure?'
)
@click.pass_context
async def simulate(ctx, component: str, error_type: str):
    """Simulate component failure"""
    orchestrator = init_recovery_orchestrator(ctx)
    comp_type = ComponentType(component)

    try:
        state = await orchestrator.simulate_failure(comp_type, error_type)
        click.echo(f"\nSimulated {error_type} failure for {component}")
        click.echo(f"Recovery initiated: {state.stage.value}")

    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)
        ctx.exit(1)


@recovery.command()
@click.pass_context
async def active(ctx):
    """Show all active recoveries"""
    orchestrator = init_recovery_orchestrator(ctx)

    recoveries = await orchestrator.get_active_recoveries()

    if not recoveries:
        click.echo("No active recoveries")
        return

    click.echo("\nActive Recoveries:")
    click.echo("-" * 40)

    for component, state in recoveries.items():
        click.echo(f"\n{component.value}:")
        click.echo(f"Stage: {state.stage.value}")
        click.echo(f"Started: {state.started_at}")
        if state.error:
            click.echo(f"Error: {state.error}")


@recovery.command()
@click.argument('component', type=click.Choice([c.value for c in ComponentType]))
@click.confirmation_option(
    prompt='Are you sure you want to abort recovery?'
)
@click.pass_context
async def abort(ctx, component: str):
    """Abort active recovery"""
    orchestrator = init_recovery_orchestrator(ctx)
    comp_type = ComponentType(component)

    try:
        await orchestrator.abort_recovery(comp_type)
        click.echo(f"Recovery aborted for {component}")
    except ValueError as e:
        click.echo(f"Error: {str(e)}", err=True)
        ctx.exit(1)


@recovery.command()
@click.argument('component', type=click.Choice([c.value for c in ComponentType]), required=False)
@click.pass_context
async def history(ctx, component: Optional[str]):
    """Show recovery history"""
    orchestrator = init_recovery_orchestrator(ctx)
    comp_type = ComponentType(component) if component else None

    history = orchestrator.get_recovery_history(comp_type)

    if not history:
        click.echo("No recovery history found")
        return

    click.echo("\nRecovery History:")
    click.echo("-" * 40)

    for entry in sorted(history, key=lambda x: x['started_at'], reverse=True):
        click.echo(f"\nComponent: {entry['component']}")
        click.echo(f"Started: {entry['started_at']}")
        click.echo(f"Completed: {entry['completed_at']}")
        click.echo(f"Stage: {entry['stage']}")
        if entry['error']:
            click.echo(f"Error: {entry['error']}")
        if entry.get('verification_checks'):
            click.echo("Verification Results:")
            for check, result in entry['verification_checks'].items():
                click.echo(f"  {check}: {'✓' if result else '✗'}")


@recovery.command()
@click.option('--watch', is_flag=True, help='Watch mode with live updates')
@click.option('--interval', default=5, help='Update interval in seconds')
@click.pass_context
async def monitor(ctx, watch: bool, interval: int):
    """Monitor recovery status"""
    orchestrator = init_recovery_orchestrator(ctx)

    async def display_status():
        # Get system health
        health = await orchestrator.verify_system_health()
        active = await orchestrator.get_active_recoveries()

        click.clear()
        click.echo(f"\nSystem Status - {datetime.now()}")
        click.echo("-" * 40)

        # Show component health
        click.echo("\nComponent Health:")
        for component, is_healthy in health.items():
            status = "✓ Healthy" if is_healthy else "✗ Unhealthy"
            click.echo(f"{component.value}: {status}")

        # Show active recoveries
        if active:
            click.echo("\nActive Recoveries:")
            for component, state in active.items():
                click.echo(f"{component.value}: {state.stage.value}")

    if watch:
        while True:
            try:
                await display_status()
                click.echo("\nPress Ctrl+C to stop monitoring...")
                await asyncio.sleep(interval)
            except KeyboardInterrupt:
                click.echo("\nMonitoring stopped")
                break
    else:
        await display_status()


def setup_cli():
    """Setup CLI with async command handling"""

    async def async_recovery(ctx, *args, **kwargs):
        """Async wrapper for recovery command group"""
        return await ctx.forward(recovery)

    return click.command()(click.pass_context(async_recovery))


if __name__ == '__main__':
    cli = setup_cli()
    cli(obj={})
# src/integration_cli.py
import click
import asyncio
from datetime import datetime
import json
from .integration_test_suite import IntegrationTestSuite, TestScenario
from .key_management import KeyManagement
from .security_monitor import SecurityMonitor
from .audit_logger import AuditLogger
from .resilience_manager import SystemResilienceManager


def init_test_suite(ctx) -> IntegrationTestSuite:
    """Initialize integration test suite"""
    if 'test_suite' not in ctx.obj:
        # Initialize all required components
        key_manager = KeyManagement()
        security_monitor = SecurityMonitor()
        audit_logger = AuditLogger()
        resilience_manager = SystemResilienceManager()

        ctx.obj['test_suite'] = IntegrationTestSuite(
            key_manager,
            security_monitor,
            audit_logger,
            resilience_manager
        )
    return ctx.obj['test_suite']


@click.group()
def integration():
    """Integration test commands"""
    pass


@integration.command()
@click.argument('scenario', required=False)
@click.pass_context
async def test(ctx, scenario: str = None):
    """Run integration test scenarios"""
    suite = init_test_suite(ctx)

    if scenario:
        # Run specific scenario
        try:
            test_scenario = TestScenario(scenario)
            result = await suite.run_test_scenario(test_scenario)

            click.echo(f"\nTest Scenario: {scenario}")
            click.echo("-" * 40)
            click.echo(f"Status: {'✓ Success' if result.success else '✗ Failed'}")
            click.echo(f"Duration: {(result.end_time - result.start_time).total_seconds():.2f}s")
            click.echo(f"Components Tested: {', '.join(result.components_tested)}")

            if result.error_message:
                click.echo(f"Error: {result.error_message}")

            if result.details:
                click.echo("\nDetails:")
                for key, value in result.details.items():
                    click.echo(f"  {key}: {value}")

        except ValueError as e:
            click.echo(f"Error: {str(e)}", err=True)
            click.echo("\nAvailable scenarios:")
            for s in suite.get_available_scenarios():
                click.echo(f"  - {s}")
            ctx.exit(1)

    else:
        # Run all scenarios
        click.echo("Running all test scenarios...")

        for scenario in TestScenario:
            click.echo(f"\nRunning: {scenario.value}")
            result = await suite.run_test_scenario(scenario)
            click.echo(f"Status: {'✓ Success' if result.success else '✗ Failed'}")

        click.echo("\nAll scenarios completed.")


@integration.command()
@click.option('--output', type=click.Path(), help='Report output file')
@click.pass_context
async def report(ctx, output: str = None):
    """Generate test report"""
    suite = init_test_suite(ctx)

    report_data = await suite.generate_test_report()

    if output:
        # Save to file
        with open(output, 'w') as f:
            json.dump(report_data, f, indent=2)
        click.echo(f"Report saved to: {output}")
    else:
        # Display report
        click.echo("\nTest Report")
        click.echo("-" * 40)
        click.echo(f"Total Tests: {report_data['total_tests']}")
        click.echo(f"Successful: {report_data['successful_tests']}")
        click.echo(f"Success Rate: {report_data['success_rate']:.1f}%")

        if report_data['failed_scenarios']:
            click.echo("\nFailed Scenarios:")
            for scenario in report_data['failed_scenarios']:
                click.echo(f"  - {scenario}")

        click.echo("\nComponent Coverage:")
        for component in report_data['component_coverage']:
            click.echo(f"  - {component}")


@integration.command()
@click.pass_context
async def scenarios(ctx):
    """List available test scenarios"""
    suite = init_test_suite(ctx)

    click.echo("\nAvailable Test Scenarios:")
    click.echo("-" * 40)

    for scenario in suite.get_available_scenarios():
        click.echo(f"- {scenario}")


@integration.command()
@click.option('--watch', is_flag=True, help='Watch mode with continuous testing')
@click.option('--interval', default=300, help='Test interval in seconds')
@click.pass_context
async def monitor(ctx, watch: bool, interval: int):
    """Run continuous integration tests"""
    suite = init_test_suite(ctx)

    async def run_tests():
        click.echo(f"\nRunning tests at {datetime.now()}")
        for scenario in TestScenario:
            result = await suite.run_test_scenario(scenario)
            status = "✓" if result.success else "✗"
            click.echo(f"{status} {scenario.value}")

        report = await suite.generate_test_report()
        click.echo(f"\nSuccess Rate: {report['success_rate']:.1f}%")

    if watch:
        while True:
            try:
                await run_tests()
                click.echo(f"\nWaiting {interval} seconds...")
                await asyncio.sleep(interval)
            except KeyboardInterrupt:
                click.echo("\nMonitoring stopped")
                break
    else:
        await run_tests()


@integration.command()
@click.confirmation_option(
    prompt='Are you sure you want to clear all test results?'
)
@click.pass_context
async def clear(ctx):
    """Clear test results"""
    suite = init_test_suite(ctx)
    await suite.clear_test_results()
    click.echo("Test results cleared")


def setup_cli():
    """Setup CLI with async command handling"""

    async def async_integration(ctx, *args, **kwargs):
        """Async wrapper for integration command group"""
        return await ctx.forward(integration)

    return click.command()(click.pass_context(async_integration))


if __name__ == '__main__':
    cli = setup_cli()
    cli(obj={})
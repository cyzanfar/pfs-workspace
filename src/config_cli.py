# src/config_cli.py
import click
from datetime import datetime
import yaml
from pathlib import Path
from typing import Optional
from .config_manager import ConfigurationManager, ConfigScope


def init_config_manager(ctx) -> ConfigurationManager:
    """Initialize configuration manager"""
    if 'config_manager' not in ctx.obj:
        ctx.obj['config_manager'] = ConfigurationManager()
    return ctx.obj['config_manager']


@click.group()
def config():
    """Configuration management commands"""
    pass


@config.command()
@click.argument('scope', type=click.Choice([s.value for s in ConfigScope]))
@click.pass_context
async def show(ctx, scope: str):
    """Show current configuration"""
    manager = init_config_manager(ctx)
    config_scope = ConfigScope(scope)

    config = manager.get_config(config_scope)
    schema = manager.get_config_schema(config_scope)

    click.echo(f"\nConfiguration: {scope}")
    click.echo("-" * 40)

    for key, value in config.items():
        if key in schema:
            schema_info = schema[key]
            click.echo(f"{key}:")
            click.echo(f"  Value: {value}")
            click.echo(f"  Type: {schema_info['type']}")
            if schema_info['description']:
                click.echo(f"  Description: {schema_info['description']}")
        else:
            click.echo(f"{key}: {value}")


@config.command()
@click.argument('scope', type=click.Choice([s.value for s in ConfigScope]))
@click.option('--param', required=True, help='Parameter to update')
@click.option('--value', required=True, help='New value')
@click.option('--author', required=True, help='Update author')
@click.option('--comment', help='Update comment')
@click.pass_context
async def update(ctx, scope: str, param: str, value: str,
                 author: str, comment: Optional[str]):
    """Update configuration parameter"""
    manager = init_config_manager(ctx)
    config_scope = ConfigScope(scope)

    # Convert value to appropriate type
    current_config = manager.get_config(config_scope)
    if param in current_config:
        current_value = current_config[param]
        try:
            if isinstance(current_value, bool):
                value = value.lower() == 'true'
            else:
                value = type(current_value)(value)
        except ValueError:
            click.echo(f"Error: Invalid value type for {param}", err=True)
            ctx.exit(1)

    try:
        version = await manager.update_config(
            config_scope,
            {param: value},
            author,
            comment
        )

        click.echo(f"\nConfiguration updated (version {version.version})")
        click.echo(f"Parameter: {param}")
        click.echo(f"New value: {value}")
        click.echo(f"Updated by: {author}")
        if comment:
            click.echo(f"Comment: {comment}")

    except ValueError as e:
        click.echo(f"Error: {str(e)}", err=True)
        ctx.exit(1)


@config.command()
@click.argument('scope', type=click.Choice([s.value for s in ConfigScope]))
@click.pass_context
async def history(ctx, scope: str):
    """Show configuration version history"""
    manager = init_config_manager(ctx)
    config_scope = ConfigScope(scope)

    history = manager.get_version_history(config_scope)

    if not history:
        click.echo("No version history found")
        return

    click.echo(f"\nVersion History: {scope}")
    click.echo("-" * 40)

    for version in sorted(history, key=lambda v: v.version):
        click.echo(f"\nVersion {version.version}")
        click.echo(f"Timestamp: {version.timestamp}")
        click.echo(f"Author: {version.author}")
        if version.comment:
            click.echo(f"Comment: {version.comment}")
        click.echo("Changes:")
        for key, value in version.changes.items():
            click.echo(f"  {key}: {value}")


@config.command()
@click.argument('scope', type=click.Choice([s.value for s in ConfigScope]))
@click.pass_context
async def validate(ctx, scope: str):
    """Validate current configuration"""
    manager = init_config_manager(ctx)
    config_scope = ConfigScope(scope)

    config = manager.get_config(config_scope)
    errors = manager.validate_config(config_scope, config)

    if errors:
        click.echo("\nValidation errors found:")
        for error in errors:
            click.echo(f"- {error}")
    else:
        click.echo("\nConfiguration is valid")


@config.command()
@click.option('--output', required=True, type=click.Path(),
              help='Export file location')
@click.pass_context
async def export(ctx, output: str):
    """Export all configurations"""
    manager = init_config_manager(ctx)

    try:
        await manager.export_configs(output)
        click.echo(f"\nConfigurations exported to: {output}")
    except Exception as e:
        click.echo(f"Error exporting configurations: {str(e)}", err=True)
        ctx.exit(1)


@config.command()
@click.argument('scope', type=click.Choice([s.value for s in ConfigScope]))
@click.pass_context
async def schema(ctx, scope: str):
    """Show configuration schema"""
    manager = init_config_manager(ctx)
    config_scope = ConfigScope(scope)

    schema = manager.get_config_schema(config_scope)

    click.echo(f"\nConfiguration Schema: {scope}")
    click.echo("-" * 40)

    for param, info in schema.items():
        click.echo(f"\n{param}:")
        click.echo(f"  Type: {info['type']}")
        click.echo(f"  Current Value: {info['current_value']}")
        if info['description']:
            click.echo(f"  Description: {info['description']}")


def setup_cli():
    """Setup CLI with async command handling"""

    async def async_config(ctx, *args, **kwargs):
        """Async wrapper for config command group"""
        return await ctx.forward(config)

    return click.command()(click.pass_context(async_config))


if __name__ == '__main__':
    cli = setup_cli()
    cli(obj={})
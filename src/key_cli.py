# src/key_cli.py
import click
import asyncio
from datetime import datetime
from pathlib import Path
from .key_management import KeyManagement, KeyManagementError


def init_key_manager(ctx) -> KeyManagement:
    """Initialize key management system"""
    if 'key_manager' not in ctx.obj:
        ctx.obj['key_manager'] = KeyManagement()
    return ctx.obj['key_manager']


@click.group()
def keys():
    """Key management commands"""
    pass


@keys.command()
@click.option('--password', prompt=True, hide_input=True,
              confirmation_prompt=True, help='Key encryption password')
@click.pass_context
async def generate(ctx, password: str):
    """Generate new key pair"""
    manager = init_key_manager(ctx)

    try:
        result = await manager.generate_new_key(password)
        click.echo("\nGenerated new key pair:")
        click.echo(f"Key ID: {result['key_id']}")
        click.echo(f"Address: {result['address']}")
        click.echo(f"Created: {result['created_at']}")
        click.echo("\nStore your Key ID and password safely!")

    except KeyManagementError as e:
        click.echo(f"Error generating key: {str(e)}", err=True)
        ctx.exit(1)


@keys.command()
@click.option('--key-id', required=True, help='Key identifier')
@click.option('--password', prompt=True, hide_input=True,
              help='Key encryption password')
@click.pass_context
async def retrieve(ctx, key_id: str, password: str):
    """Retrieve private key"""
    manager = init_key_manager(ctx)

    try:
        private_key = await manager.retrieve_key(key_id, password)
        click.echo(f"\nPrivate Key: {private_key}")
        click.echo("\nWARNING: Store this private key securely!")

    except KeyManagementError as e:
        click.echo(f"Error retrieving key: {str(e)}", err=True)
        ctx.exit(1)


@keys.command()
@click.option('--key-id', required=True, help='Key identifier')
@click.option('--old-password', prompt=True, hide_input=True,
              help='Current password')
@click.option('--new-password', prompt=True, hide_input=True,
              confirmation_prompt=True, help='New password')
@click.pass_context
async def rotate(ctx, key_id: str, old_password: str, new_password: str):
    """Rotate key with new password"""
    manager = init_key_manager(ctx)

    try:
        result = await manager.rotate_key(key_id, old_password, new_password)
        click.echo("\nKey rotated successfully:")
        click.echo(f"Key ID: {result['key_id']}")
        click.echo(f"Rotated: {result['rotated_at']}")
        click.echo(f"Version: {result['version']}")

    except KeyManagementError as e:
        click.echo(f"Error rotating key: {str(e)}", err=True)
        ctx.exit(1)


@keys.command()
@click.pass_context
async def list(ctx):
    """List all stored keys"""
    manager = init_key_manager(ctx)

    try:
        keys = await manager.list_keys()

        if not keys:
            click.echo("No keys found")
            return

        click.echo("\nStored Keys:")
        click.echo("-" * 60)

        for key in sorted(keys, key=lambda k: k['created_at']):
            click.echo(f"\nKey ID: {key['key_id']}")
            click.echo(f"Created: {key['created_at']}")
            click.echo(f"Last Rotated: {key['last_rotated'] or 'Never'}")
            click.echo(f"Version: {key['version']}")

    except KeyManagementError as e:
        click.echo(f"Error listing keys: {str(e)}", err=True)
        ctx.exit(1)


@keys.command()
@click.option('--output', required=True, type=click.Path(),
              help='Backup file location')
@click.pass_context
async def backup(ctx, output: str):
    """Create encrypted backup of all keys"""
    manager = init_key_manager(ctx)

    try:
        backup_path = await manager.create_backup()

        # Move backup to specified location if different
        if output != backup_path:
            output_path = Path(output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            Path(backup_path).rename(output_path)
            backup_path = output

        click.echo(f"\nBackup created successfully:")
        click.echo(f"Location: {backup_path}")

    except KeyManagementError as e:
        click.echo(f"Error creating backup: {str(e)}", err=True)
        ctx.exit(1)


@keys.command()
@click.option('--backup-file', required=True, type=click.Path(exists=True),
              help='Backup file to restore from')
@click.confirmation_option(prompt='Are you sure you want to restore from backup?')
@click.pass_context
async def restore(ctx, backup_file: str):
    """Restore keys from backup"""
    manager = init_key_manager(ctx)

    try:
        result = await manager.restore_from_backup(backup_file)

        click.echo("\nRestore completed successfully:")
        click.echo(f"Backup Date: {result['backup_timestamp']}")
        click.echo("\nRestored Keys:")
        for key_id in result['restored_keys']:
            click.echo(f"- {key_id}")

    except KeyManagementError as e:
        click.echo(f"Error restoring from backup: {str(e)}", err=True)
        ctx.exit(1)


def setup_cli():
    """Setup CLI with async command handling"""

    async def async_keys(ctx, *args, **kwargs):
        """Async wrapper for keys command group"""
        return await ctx.forward(keys)

    return click.command()(click.pass_context(async_keys))


if __name__ == '__main__':
    cli = setup_cli()
    cli(obj={})
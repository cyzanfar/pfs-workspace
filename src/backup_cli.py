import argparse
import json
from datetime import datetime
from backup_manager import BackupManager


class BackupManagerCLI:
    """
    Command-line interface for the BackupManager.

    Provides commands for creating, verifying,
    and restoring system backups.
    """

    def __init__(self, backup_manager: BackupManager):
        """
        Initialize the CLI with a BackupManager instance.

        Args:
            backup_manager (BackupManager): Backup management system
        """
        self.backup_manager = backup_manager

    def create_backup(self, args):
        """
        Create a system backup.

        Args:
            args (Namespace): Parsed CLI arguments
        """
        try:
            # Parse components if specified
            components = args.components.split(',') if args.components else None

            # Create backup
            backup_result = self.backup_manager.create_backup(
                backup_type=args.type,
                components=components
            )

            # Output backup details
            print(json.dumps(backup_result, indent=2))
        except Exception as e:
            print(f"Backup creation failed: {e}")

    def verify_backup(self, args):
        """
        Verify the integrity of a specific backup.

        Args:
            args (Namespace): Parsed CLI arguments
        """
        try:
            # Verify backup
            verification_result = self.backup_manager.verify_backup(args.backup_id)

            # Output verification details
            print(json.dumps(verification_result, indent=2))
        except Exception as e:
            print(f"Backup verification failed: {e}")

    def restore_backup(self, args):
        """
        Restore a specific backup.

        Args:
            args (Namespace): Parsed CLI arguments
        """
        try:
            # Parse components if specified
            components = args.components.split(',') if args.components else None

            # Restore backup
            restoration_result = self.backup_manager.restore_backup(
                backup_id=args.backup_id,
                components=components
            )

            # Output restoration details
            print(json.dumps(restoration_result, indent=2))
        except Exception as e:
            print(f"Backup restoration failed: {e}")

    def list_backups(self, args):
        """
        List available backups.

        Args:
            args (Namespace): Parsed CLI arguments
        """
        try:
            # Convert backup registry to list for display
            backup_list = [
                {
                    'id': backup_id,
                    'timestamp': metadata['timestamp'],
                    'type': metadata['type'],
                    'total_size': metadata.get('total_size', 0),
                    'components': list(metadata['components'].keys())
                }
                for backup_id, metadata in self.backup_manager.backup_registry.items()
            ]

            # Sort backups by timestamp
            backup_list.sort(key=lambda x: x['timestamp'], reverse=True)

            # Output backup list
            print(json.dumps(backup_list, indent=2))
        except Exception as e:
            print(f"Failed to list backups: {e}")

    def register_component(self, args):
        """
        Register a new backup component.

        Args:
            args (Namespace): Parsed CLI arguments
        """
        try:
            # Placeholder for dynamic handler import
            def default_backup_handler(backup_path, backup_type):
                """
                Default backup handler for demonstration.
                In a real system, this would be replaced with component-specific logic.
                """
                return {
                    'message': f'Backup created for {backup_path}',
                    'type': backup_type
                }

            # Register the component
            self.backup_manager.register_component(
                args.name,
                backup_handler=default_backup_handler
            )

            print(f"Component {args.name} registered for backup.")
        except Exception as e:
            print(f"Component registration failed: {e}")

    def run(self):
        """
        Set up and run the CLI argument parser.
        """
        parser = argparse.ArgumentParser(
            description="Backup Management System CLI"
        )
        subparsers = parser.add_subparsers(
            dest='command',
            help='Available commands'
        )

        # Create Backup Command
        backup_parser = subparsers.add_parser(
            'create',
            help='Create a new backup'
        )
        backup_parser.add_argument(
            '--type',
            choices=['incremental', 'full'],
            default='incremental',
            help='Type of backup (default: incremental)'
        )
        backup_parser.add_argument(
            '--components',
            help='Comma-separated list of components to backup'
        )

        # Verify Backup Command
        verify_parser = subparsers.add_parser(
            'verify',
            help='Verify backup integrity'
        )
        verify_parser.add_argument(
            'backup_id',
            help='ID of the backup to verify'
        )

        # Restore Backup Command
        restore_parser = subparsers.add_parser(
            'restore',
            help='Restore from a backup'
        )
        restore_parser.add_argument(
            'backup_id',
            help='ID of the backup to restore'
        )
        restore_parser.add_argument(
            '--components',
            help='Comma-separated list of components to restore'
        )

        # List Backups Command
        list_parser = subparsers.add_parser(
            'list',
            help='List available backups'
        )

        # Register Component Command
        register_parser = subparsers.add_parser(
            'register-component',
            help='Register a new backup component'
        )
        register_parser.add_argument(
            'name',
            help='Name of the component to register'
        )

        # Parse arguments and dispatch
        args = parser.parse_args()

        # Map commands to methods
        command_map = {
            'create': self.create_backup,
            'verify': self.verify_backup,
            'restore': self.restore_backup,
            'list': self.list_backups,
            'register-component': self.register_component
        }

        # Execute the appropriate command
        if args.command:
            command_map[args.command](args)
        else:
            parser.print_help()


def main():
    """
    Entry point for the Backup Manager CLI.
    """
    # Create a backup manager instance
    backup_manager = BackupManager()

    # Create and run CLI
    cli = BackupManagerCLI(backup_manager)
    cli.run()


if __name__ == '__main__':
    main()
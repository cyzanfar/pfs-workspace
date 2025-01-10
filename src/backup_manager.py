import os
import shutil
import hashlib
import json
import threading
import time
import tarfile
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Callable


class BackupManager:
    """
    Comprehensive system-wide backup management system.

    Provides robust backup and restoration capabilities with:
    - Incremental and full backup support
    - Backup verification mechanisms
    - Configurable backup strategies
    - Detailed backup metadata tracking
    """

    def __init__(
            self,
            backup_dir: str = './system_backups',
            config_path: str = './backup_config.json',
            max_backup_retention: int = 10
    ):
        """
        Initialize the BackupManager.

        Args:
            backup_dir (str): Directory to store backups
            config_path (str): Path to backup configuration file
            max_backup_retention (int): Maximum number of backups to retain
        """
        # Ensure backup directory exists
        self.backup_dir = os.path.abspath(backup_dir)
        os.makedirs(self.backup_dir, exist_ok=True)

        # Logging setup
        self.logger = logging.getLogger('BackupManager')
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

        # Configuration management
        self.config_path = config_path
        self.config = self._load_config()

        # Backup tracking
        self.backup_registry: Dict[str, Dict[str, Any]] = {}

        # Backup component handlers
        self._backup_handlers: Dict[str, Callable] = {}
        self._restore_handlers: Dict[str, Callable] = {}

        # Backup retention configuration
        self.max_backup_retention = max_backup_retention

        # Start backup cleanup thread
        self._start_backup_cleanup_thread()

    def _load_config(self) -> Dict[str, Any]:
        """
        Load backup configuration.

        Returns:
            Dict containing backup configuration
        """
        default_config = {
            'backup_schedule': {
                'full_backup_interval_days': 7,
                'incremental_backup_interval_hours': 24
            },
            'backup_locations': {},
            'compression_level': 6,
            'encryption_enabled': False
        }

        # Load from file if exists
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    user_config = json.load(f)
                    default_config.update(user_config)
            except Exception as e:
                self.logger.error(f"Error loading config: {e}")

        return default_config

    def register_component(
            self,
            component_name: str,
            backup_handler: Callable,
            restore_handler: Optional[Callable] = None
    ):
        """
        Register a backup handler for a specific system component.

        Args:
            component_name (str): Unique name of the component
            backup_handler (Callable): Function to create backup for the component
            restore_handler (Callable, optional): Function to restore the component
        """
        if component_name in self._backup_handlers:
            raise ValueError(f"Component {component_name} already registered")

        self._backup_handlers[component_name] = backup_handler

        # Optional restore handler
        if restore_handler:
            self._restore_handlers[component_name] = restore_handler

    def create_backup(
            self,
            backup_type: str = 'incremental',
            components: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Create a system-wide or component-specific backup.

        Args:
            backup_type (str): Type of backup ('incremental' or 'full')
            components (List[str], optional): Specific components to backup

        Returns:
            Dict containing backup metadata
        """
        # Generate unique backup ID
        backup_id = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        backup_path = os.path.join(self.backup_dir, backup_id)
        os.makedirs(backup_path)

        # Prepare backup metadata
        backup_metadata = {
            'id': backup_id,
            'timestamp': datetime.now().isoformat(),
            'type': backup_type,
            'components': {},
            'total_size': 0
        }

        # Determine components to backup
        target_components = (
                components or list(self._backup_handlers.keys())
        )

        # Perform backups for each component
        for component in target_components:
            if component not in self._backup_handlers:
                self.logger.warning(f"No backup handler for component: {component}")
                continue

            try:
                # Create component-specific subdirectory
                component_backup_path = os.path.join(backup_path, component)
                os.makedirs(component_backup_path)

                # Call component's backup handler
                handler_result = self._backup_handlers[component](
                    backup_path=component_backup_path,
                    backup_type=backup_type
                )

                # Update backup metadata
                component_metadata = {
                    'backup_path': component_backup_path,
                    'handler_result': handler_result
                }

                # Calculate component backup size
                component_size = self._calculate_directory_size(component_backup_path)
                component_metadata['size'] = component_size
                backup_metadata['total_size'] += component_size

                backup_metadata['components'][component] = component_metadata
            except Exception as e:
                self.logger.error(
                    f"Backup failed for component {component}: {e}"
                )
                backup_metadata['components'][component] = {
                    'status': 'failed',
                    'error': str(e)
                }

        # Create backup archive
        archive_path = self._create_backup_archive(backup_path, backup_id)
        backup_metadata['archive_path'] = archive_path

        # Verify backup integrity
        backup_metadata['integrity_check'] = self.verify_backup(backup_id)

        # Store backup in registry
        self.backup_registry[backup_id] = backup_metadata

        return backup_metadata

    def _create_backup_archive(
            self,
            backup_path: str,
            backup_id: str
    ) -> str:
        """
        Create a compressed archive of the backup.

        Args:
            backup_path (str): Path to backup directory
            backup_id (str): Unique backup identifier

        Returns:
            Path to created archive
        """
        archive_path = os.path.join(
            self.backup_dir,
            f"{backup_id}.tar.gz"
        )

        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(backup_path, arcname=os.path.basename(backup_path))

        return archive_path

    def verify_backup(self, backup_id: str) -> Dict[str, Any]:
        """
        Verify the integrity of a specific backup.

        Args:
            backup_id (str): Unique identifier of the backup to verify

        Returns:
            Dict containing verification results
        """
        # Retrieve backup metadata
        if backup_id not in self.backup_registry:
            raise ValueError(f"Backup {backup_id} not found")

        backup_metadata = self.backup_registry[backup_id]
        verification_results = {
            'overall_status': 'success',
            'components': {}
        }

        # Verify each component
        for component, component_data in backup_metadata['components'].items():
            try:
                # Skip failed backups
                if 'backup_path' not in component_data:
                    continue

                # Compute directory hash
                directory_hash = self._calculate_directory_hash(
                    component_data['backup_path']
                )

                verification_results['components'][component] = {
                    'status': 'success',
                    'directory_hash': directory_hash
                }
            except Exception as e:
                verification_results['components'][component] = {
                    'status': 'failed',
                    'error': str(e)
                }
                verification_results['overall_status'] = 'partial_failure'

        return verification_results

    def restore_backup(
            self,
            backup_id: str,
            components: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Restore system from a specific backup.

        Args:
            backup_id (str): Unique identifier of the backup to restore
            components (List[str], optional): Specific components to restore

        Returns:
            Dict containing restoration results
        """
        # Retrieve backup metadata
        if backup_id not in self.backup_registry:
            raise ValueError(f"Backup {backup_id} not found")

        backup_metadata = self.backup_registry[backup_id]
        restoration_results = {
            'overall_status': 'success',
            'components': {}
        }

        # Determine components to restore
        target_components = (
                components or list(backup_metadata['components'].keys())
        )

        # Restore each component
        for component in target_components:
            if component not in backup_metadata['components']:
                restoration_results['components'][component] = {
                    'status': 'skipped',
                    'reason': 'Not in backup'
                }
                continue

            try:
                # Get component backup path
                component_backup = backup_metadata['components'][component]
                backup_path = component_backup['backup_path']

                # Call component's restore handler if available
                if component in self._restore_handlers:
                    restore_result = self._restore_handlers[component](
                        backup_path=backup_path
                    )

                    restoration_results['components'][component] = {
                        'status': 'success',
                        'restore_details': restore_result
                    }
                else:
                    restoration_results['components'][component] = {
                        'status': 'failed',
                        'error': 'No restore handler found'
                    }
                    restoration_results['overall_status'] = 'partial_failure'
            except Exception as e:
                restoration_results['components'][component] = {
                    'status': 'failed',
                    'error': str(e)
                }
                restoration_results['overall_status'] = 'partial_failure'

        return restoration_results

    def _start_backup_cleanup_thread(self):
        """
        Start a background thread to manage backup retention.
        """

        def cleanup_backups():
            while True:
                try:
                    # Sort backups by timestamp
                    sorted_backups = sorted(
                        self.backup_registry.items(),
                        key=lambda x: x[1]['timestamp']
                    )

                    # Remove excess backups
                    while len(sorted_backups) > self.max_backup_retention:
                        oldest_backup_id, oldest_backup = sorted_backups.pop(0)

                        # Remove backup files
                        if 'archive_path' in oldest_backup:
                            os.remove(oldest_backup['archive_path'])

                        # Remove backup directory
                        backup_dir = os.path.join(
                            self.backup_dir,
                            oldest_backup['id']
                        )
                        if os.path.exists(backup_dir):
                            shutil.rmtree(backup_dir)

                        # Remove from registry
                        del self.backup_registry[oldest_backup_id]
                except Exception as e:
                # Sleep for 24 hours
                    time.sleep(24 * 3600)

        cleanup_thread = threading.Thread(
            target=cleanup_backups,
            daemon=True,
            name='BackupCleanupThread'
        )
        cleanup_thread.start()

    def _calculate_directory_size(self, directory: str) -> int:
        """
        Calculate total size of a directory.

        Args:
            directory (str): Path to directory

        Returns:
            Total size in bytes
        """
        total_size = 0
        for dirpath, _, filenames in os.walk(directory):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                total_size += os.path.getsize(fp)
        return total_size

    def _calculate_directory_hash(self, directory: str) -> str:
        """
        Calculate a hash representing the directory contents.

        Args:
            directory (str): Path to directory

        Returns:
            Cryptographic hash of directory contents
        """
        # Collect all file paths and their contents
        file_contents = []
        for dirpath, _, filenames in os.walk(directory):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                with open(filepath, 'rb') as f:
                    file_contents.append(f.read())

        # Create a combined hash
        hasher = hashlib.sha256()
        for content in sorted(file_contents):
            hasher.update(content)

        return hasher.hexdigest()
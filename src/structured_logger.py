import os
import json
import time
import threading
import logging
import gzip
import re
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Union, Callable


class StructuredLogger:
    """
    Advanced logging system with comprehensive logging capabilities.

    Features:
    - Context-aware structured logging
    - Multi-level log aggregation
    - Flexible log rotation policies
    - Advanced querying capabilities
    """

    class LogLevel:
        """
        Custom log levels with numeric and semantic representations.
        """
        TRACE = 5
        DEBUG = 10
        INFO = 20
        WARNING = 30
        ERROR = 40
        CRITICAL = 50

    def __init__(
            self,
            log_dir: str = './system_logs',
            config_path: str = './logger_config.json',
            default_retention_days: int = 30,
            max_log_file_size_mb: int = 100,
            max_log_files: int = 10
    ):
        """
        Initialize the StructuredLogger.

        Args:
            log_dir (str): Directory to store log files
            config_path (str): Path to logger configuration
            default_retention_days (int): Default log retention period
            max_log_file_size_mb (int): Maximum log file size before rotation
            max_log_files (int): Maximum number of log files to retain
        """
        # Ensure log directory exists
        self.log_dir = os.path.abspath(log_dir)
        os.makedirs(self.log_dir, exist_ok=True)

        # Configuration management
        self.config_path = config_path
        self.config = self._load_config()

        # Logging parameters
        self.retention_days = self.config.get(
            'retention_days',
            default_retention_days
        )
        self.max_log_file_size = max_log_file_size_mb * 1024 * 1024  # Convert to bytes
        self.max_log_files = max_log_files

        # Logging infrastructure
        self._log_handlers: Dict[str, List[Callable]] = {}
        self._global_log_handlers: List[Callable] = []

        # Log storage and management
        self._log_registry: List[Dict[str, Any]] = []
        self._log_lock = threading.Lock()

        # Start log cleanup thread
        self._start_log_cleanup_thread()

    def _load_config(self) -> Dict[str, Any]:
        """
        Load logger configuration.

        Returns:
            Dict containing logger configuration
        """
        default_config = {
            'log_levels': {
                'default': 'INFO',
                'components': {}
            },
            'log_format': {
                'timestamp': 'iso',
                'include_context': True
            },
            'retention_days': 30
        }

        # Load from file if exists
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    user_config = json.load(f)
                    default_config.update(user_config)
            except Exception as e:
                print(f"Error loading config: {e}")

        return default_config

    def log(
            self,
            message: str,
            level: int = LogLevel.INFO,
            component: Optional[str] = None,
            context: Optional[Dict[str, Any]] = None
    ):
        """
        Central logging method with advanced logging capabilities.

        Args:
            message (str): Log message
            level (int): Log severity level
            component (str, optional): Source component
            context (dict, optional): Additional context information
        """
        # Prepare log entry
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'level': self._get_level_name(level),
            'message': message,
            'component': component or 'system',
            'context': context or {}
        }

        # Thread-safe log storage
        with self._log_lock:
            self._log_registry.append(log_entry)

        # Call component-specific handlers
        if component and component in self._log_handlers:
            for handler in self._log_handlers[component]:
                try:
                    handler(log_entry)
                except Exception as e:
                    # Fallback logging for handler errors
                    print(f"Log handler error for {component}: {e}")

        # Call global handlers
        for handler in self._global_log_handlers:
            try:
                handler(log_entry)
            except Exception as e:
                print(f"Global log handler error: {e}")

        # Write to log file
        self._write_log_to_file(log_entry)

    def _write_log_to_file(self, log_entry: Dict[str, Any]):
        """
        Write log entry to an appropriate log file.

        Args:
            log_entry (dict): Log entry to write
        """
        # Determine log file path
        log_file_path = os.path.join(
            self.log_dir,
            f"{log_entry['component']}_{datetime.now().strftime('%Y%m%d')}.log"
        )

        # Check file size and rotate if needed
        self._rotate_log_file(log_file_path)

        # Write log entry
        with open(log_file_path, 'a') as f:
            json.dump(log_entry, f)
            f.write('\n')

    def _rotate_log_file(self, log_file_path: str):
        """
        Rotate log file if it exceeds size threshold.

        Args:
            log_file_path (str): Path to log file
        """
        if os.path.exists(log_file_path):
            file_size = os.path.getsize(log_file_path)

            if file_size >= self.max_log_file_size:
                # Create compressed backup
                backup_path = f"{log_file_path}.{datetime.now().strftime('%Y%m%d_%H%M%S')}.gz"
                with open(log_file_path, 'rb') as f_in:
                    with gzip.open(backup_path, 'wb') as f_out:
                        f_out.writelines(f_in)

                # Clear original log file
                open(log_file_path, 'w').close()

    def _start_log_cleanup_thread(self):
        """
        Start a background thread to manage log retention.
        """

        def cleanup_logs():
            while True:
                try:
                    # Get cutoff date
                    cutoff_date = datetime.now() - timedelta(days=self.retention_days)

                    # Find and remove old log files
                    for filename in os.listdir(self.log_dir):
                        filepath = os.path.join(self.log_dir, filename)

                        # Check file modification time
                        file_mod_time = datetime.fromtimestamp(os.path.getmtime(filepath))
                        if file_mod_time < cutoff_date:
                            os.remove(filepath)
                except Exception as e:
                    # Sleep for 24 hours
                    time.sleep(24 * 3600)

        cleanup_thread = threading.Thread(
            target=cleanup_logs,
            daemon=True,
            name='LogCleanupThread'
        )
        cleanup_thread.start()

    def _get_level_name(self, level: int) -> str:
        """
        Convert numeric log level to string representation.

        Args:
            level (int): Numeric log level

        Returns:
            String representation of log level
        """
        level_names = {
            self.LogLevel.TRACE: 'TRACE',
            self.LogLevel.DEBUG: 'DEBUG',
            self.LogLevel.INFO: 'INFO',
            self.LogLevel.WARNING: 'WARNING',
            self.LogLevel.ERROR: 'ERROR',
            self.LogLevel.CRITICAL: 'CRITICAL'
        }
        return level_names.get(level, 'UNKNOWN')

    def query_logs(
            self,
            component: Optional[str] = None,
            log_level: Optional[Union[int, str]] = None,
            start_time: Optional[datetime] = None,
            end_time: Optional[datetime] = None,
            keyword: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Query logs with advanced filtering capabilities.

        Args:
            component (str, optional): Filter by component
            log_level (int/str, optional): Filter by log level
            start_time (datetime, optional): Start of time range
            end_time (datetime, optional): End of time range
            keyword (str, optional): Keyword search in log message

        Returns:
            List of matching log entries
        """
        with self._log_lock:
            filtered_logs = self._log_registry

            # Filter by component
            if component:
                filtered_logs = [
                    log for log in filtered_logs
                    if log['component'] == component
                ]

            # Filter by log level
            if log_level:
                # Convert string level to numeric if needed
                if isinstance(log_level, str):
                    level_map = {
                        'TRACE': self.LogLevel.TRACE,
                        'DEBUG': self.LogLevel.DEBUG,
                        'INFO': self.LogLevel.INFO,
                        'WARNING': self.LogLevel.WARNING,
                        'ERROR': self.LogLevel.ERROR,
                        'CRITICAL': self.LogLevel.CRITICAL
                    }
                    log_level = level_map.get(log_level.upper(), self.LogLevel.INFO)

                filtered_logs = [
                    log for log in filtered_logs
                    if self._get_log_level_numeric(log['level']) >= log_level
                ]

            # Filter by time range
            if start_time:
                filtered_logs = [
                    log for log in filtered_logs
                    if datetime.fromisoformat(log['timestamp']) >= start_time
                ]

            if end_time:
                filtered_logs = [
                    log for log in filtered_logs
                    if datetime.fromisoformat(log['timestamp']) <= end_time
                ]

            # Keyword search
            if keyword:
                filtered_logs = [
                    log for log in filtered_logs
                    if re.search(keyword, log['message'], re.IGNORECASE)
                ]

            return filtered_logs

    def _get_log_level_numeric(self, level_name: str) -> int:
        """
        Convert log level name to numeric value.

        Args:
            level_name (str): Name of log level

        Returns:
            Numeric log level
        """
        level_map = {
            'TRACE': self.LogLevel.TRACE,
            'DEBUG': self.LogLevel.DEBUG,
            'INFO': self.LogLevel.INFO,
            'WARNING': self.LogLevel.WARNING,
            'ERROR': self.LogLevel.ERROR,
            'CRITICAL': self.LogLevel.CRITICAL
        }
        return level_map.get(level_name.upper(), self.LogLevel.INFO)

    def register_log_handler(
            self,
            handler: Callable,
            component: Optional[str] = None
    ):
        """
        Register a custom log handler.

        Args:
            handler (Callable): Function to handle log entries
            component (str, optional): Specific component to handle
        """
        if component:
            if component not in self._log_handlers:
                self._log_handlers[component] = []
            self._log_handlers[component].append(handler)
        else:
            self._global_log_handlers.append(handler)
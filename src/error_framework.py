import json
import logging
import os
import threading
import traceback
from datetime import datetime
from enum import Enum, auto
from typing import Dict, Any, Optional, Callable, List, Union


class ErrorSeverity(Enum):
    """
    Standardized error severity levels.
    """
    TRACE = auto()  # Very detailed tracing information
    DEBUG = auto()  # Debugging information
    INFO = auto()  # General information
    WARNING = auto()  # Warning conditions
    ERROR = auto()  # Error conditions
    CRITICAL = auto()  # Critical conditions requiring immediate attention
    FATAL = auto()  # Fatal errors that prevent system operation


class ErrorCategory(Enum):
    """
    Standardized error categorization.
    """
    NETWORK = auto()  # Network-related errors
    AUTHENTICATION = auto()  # Authentication and authorization errors
    DATABASE = auto()  # Database-related errors
    RESOURCE_ALLOCATION = auto()  # Resource management errors
    CONFIGURATION = auto()  # Configuration-related errors
    VALIDATION = auto()  # Input validation errors
    EXTERNAL_SERVICE = auto()  # Third-party service errors
    SYSTEM = auto()  # Low-level system errors
    APPLICATION = auto()  # High-level application errors
    UNKNOWN = auto()  # Uncategorized errors


class SystemError(Exception):
    """
    Custom exception for standardized error handling.
    """

    def __init__(
            self,
            message: str,
            category: ErrorCategory = ErrorCategory.UNKNOWN,
            severity: ErrorSeverity = ErrorSeverity.ERROR,
            context: Optional[Dict[str, Any]] = None,
            original_exception: Optional[Exception] = None
    ):
        """
        Initialize a standardized system error.

        Args:
            message (str): Human-readable error description
            category (ErrorCategory): Error categorization
            severity (ErrorSeverity): Error severity level
            context (dict, optional): Additional error context
            original_exception (Exception, optional): Original exception if wrapping
        """
        super().__init__(message)
        self.category = category
        self.severity = severity
        self.context = context or {}
        self.timestamp = datetime.now()
        self.original_exception = original_exception

        # Add traceback if an original exception is provided
        if original_exception:
            self.context['traceback'] = traceback.format_exc()


class ErrorHandlingFramework:
    """
    Comprehensive error handling and management system.
    """

    def __init__(
            self,
            log_dir: str = './error_logs',
            max_log_files: int = 10,
            max_log_age_days: int = 30
    ):
        """
        Initialize the Error Handling Framework.

        Args:
            log_dir (str): Directory to store error logs
            max_log_files (int): Maximum number of log files to retain
            max_log_age_days (int): Maximum age of log files in days
        """
        # Ensure log directory exists
        self.log_dir = os.path.abspath(log_dir)
        os.makedirs(self.log_dir, exist_ok=True)

        # Configure logging
        self._configure_logging()

        # Error handlers and callbacks
        self._error_handlers: Dict[ErrorCategory, List[Callable]] = {}
        self._global_error_handlers: List[Callable] = []

        # Error tracking
        self._error_registry: List[SystemError] = []
        self._error_lock = threading.Lock()

        # Log cleanup configuration
        self.max_log_files = max_log_files
        self.max_log_age_days = max_log_age_days

        # Start log cleanup thread
        self._start_log_cleanup_thread()

    def _configure_logging(self):
        """
        Configure logging infrastructure.
        """
        # Create a formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

        # Create file handler
        log_file = os.path.join(
            self.log_dir,
            f'system_errors_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'
        )
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)

        # Create console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)

        # Configure root logger
        logging.basicConfig(
            level=logging.INFO,
            handlers=[file_handler, console_handler]
        )

        # Create module-specific loggers
        self.logger = logging.getLogger('ErrorHandlingFramework')

    def register_error_handler(
            self,
            handler: Callable,
            category: Optional[ErrorCategory] = None
    ):
        """
        Register an error handler.

        Args:
            handler (Callable): Function to handle errors
            category (ErrorCategory, optional): Specific error category to handle
        """
        if category:
            # Category-specific handler
            if category not in self._error_handlers:
                self._error_handlers[category] = []
            self._error_handlers[category].append(handler)
        else:
            # Global handler
            self._global_error_handlers.append(handler)

    def handle_error(
            self,
            error: Union[Exception, SystemError]
    ) -> bool:
        """
        Centralized error handling method.

        Args:
            error (Exception or SystemError): Error to handle

        Returns:
            bool: Whether error was successfully handled
        """
        # Convert standard exception to SystemError if needed
        if not isinstance(error, SystemError):
            system_error = SystemError(
                message=str(error),
                original_exception=error
            )
        else:
            system_error = error

        # Log the error
        self._log_error(system_error)

        # Track error in registry
        with self._error_lock:
            self._error_registry.append(system_error)

        # Try category-specific handlers first
        handled = self._handle_by_category(system_error)

        # If not handled, try global handlers
        if not handled:
            handled = self._handle_globally(system_error)

        return handled

    def _handle_by_category(self, error: SystemError) -> bool:
        """
        Attempt to handle error using category-specific handlers.

        Args:
            error (SystemError): Error to handle

        Returns:
            bool: Whether error was handled
        """
        handlers = self._error_handlers.get(error.category, [])

        for handler in handlers:
            try:
                result = handler(error)
                if result:
                    return True
            except Exception as handling_error:
                # Log error handling failure
                self.logger.error(
                    f"Error in category handler: {handling_error}"
                )

        return False

    def _handle_globally(self, error: SystemError) -> bool:
        """
        Attempt to handle error using global handlers.

        Args:
            error (SystemError): Error to handle

        Returns:
            bool: Whether error was handled
        """
        for handler in self._global_error_handlers:
            try:
                result = handler(error)
                if result:
                    return True
            except Exception as handling_error:
                # Log error handling failure
                self.logger.error(
                    f"Error in global handler: {handling_error}"
                )

        return False

    def _log_error(self, error: SystemError):
        """
        Log error details.

        Args:
            error (SystemError): Error to log
        """
        # Map severity to logging levels
        severity_map = {
            ErrorSeverity.TRACE: logging.DEBUG,
            ErrorSeverity.DEBUG: logging.DEBUG,
            ErrorSeverity.INFO: logging.INFO,
            ErrorSeverity.WARNING: logging.WARNING,
            ErrorSeverity.ERROR: logging.ERROR,
            ErrorSeverity.CRITICAL: logging.CRITICAL,
            ErrorSeverity.FATAL: logging.CRITICAL
        }

        # Log error
        log_method = getattr(
            self.logger,
            logging.getLevelName(severity_map[error.severity]).lower()
        )

        log_method(
            f"[{error.category.name}] {error.message}\n"
            f"Context: {json.dumps(error.context, indent=2)}"
        )

    def _start_log_cleanup_thread(self):
        """
        Start a background thread to clean up old log files.
        """

        def cleanup_logs():
            while True:
                try:
                    # Find all log files
                    log_files = [
                        f for f in os.listdir(self.log_dir)
                        if f.startswith('system_errors_') and f.endswith('.log')
                    ]

                    # Sort files by creation time
                    log_files.sort(
                        key=lambda f: os.path.getctime(
                            os.path.join(self.log_dir, f)
                        )
                    )

                    # Remove excess log files
                    while len(log_files) > self.max_log_files:
                        oldest_log = log_files.pop(0)
                        os.remove(os.path.join(self.log_dir, oldest_log))

                    # Sleep for 24 hours
                    threading.Event().wait(24 * 3600)
                except Exception as e:
                    self.logger.error(f"Log cleanup failed: {e}")

        cleanup_thread = threading.Thread(
            target=cleanup_logs,
            daemon=True,
            name='LogCleanupThread'
        )
        cleanup_thread.start()

    def get_error_history(
            self,
            category: Optional[ErrorCategory] = None,
            severity: Optional[ErrorSeverity] = None,
            start_time: Optional[datetime] = None
    ) -> List[SystemError]:
        """
        Retrieve error history with optional filtering.

        Args:
            category (ErrorCategory, optional): Filter by error category
            severity (ErrorSeverity, optional): Filter by error severity
            start_time (datetime, optional): Retrieve errors after this time

        Returns:
            List of filtered errors
        """
        with self._error_lock:
            filtered_errors = self._error_registry

            if category:
                filtered_errors = [
                    error for error in filtered_errors
                    if error.category == category
                ]

            if severity:
                filtered_errors = [
                    error for error in filtered_errors
                    if error.severity == severity
                ]

            if start_time:
                filtered_errors = [
                    error for error in filtered_errors
                    if error.timestamp >= start_time
                ]

            return filtered_errors
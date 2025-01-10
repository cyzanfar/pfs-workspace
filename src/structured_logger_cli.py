import argparse
import json
from datetime import datetime, timedelta
from structured_logger import StructuredLogger


class StructuredLoggerCLI:
    """
    Command-line interface for the StructuredLogger.

    Provides commands for log querying,
    retention management, and log analysis.
    """

    def __init__(self, logger: StructuredLogger):
        """
        Initialize the CLI with a StructuredLogger instance.

        Args:
            logger (StructuredLogger): Logger system to manage
        """
        self.logger = logger

    def query_logs(self, args):
        """
        Query and display log entries based on filters.

        Args:
            args (Namespace): Parsed CLI arguments
        """
        try:
            # Parse optional start and end times
            start_time = (
                datetime.fromisoformat(args.start_time)
                if args.start_time
                else None
            )
            end_time = (
                datetime.fromisoformat(args.end_time)
                if args.end_time
                else None
            )

            # Query logs
            log_results = self.logger.query_logs(
                component=args.component,
                log_level=args.level,
                start_time=start_time,
                end_time=end_time,
                keyword=args.keyword
            )

            # Output results
            print(json.dumps(log_results, indent=2))
        except Exception as e:
            print(f"Log query failed: {e}")

    def set_retention(self, args):
        """
        Update log retention policy.

        Args:
            args (Namespace): Parsed CLI arguments
        """
        try:
            # Update retention days in configuration
            self.logger.config['retention_days'] = args.days

            # Save updated configuration
            with open(self.logger.config_path, 'w') as f:
                json.dump(self.logger.config, f, indent=2)

            print(f"Log retention set to {args.days} days.")
        except Exception as e:
            print(f"Failed to set retention policy: {e}")

    def log_message(self, args):
        """
        Log a message through the structured logger.

        Args:
            args (Namespace): Parsed CLI arguments
        """
        try:
            # Parse log level
            level_map = {
                'trace': StructuredLogger.LogLevel.TRACE,
                'debug': StructuredLogger.LogLevel.DEBUG,
                'info': StructuredLogger.LogLevel.INFO,
                'warning': StructuredLogger.LogLevel.WARNING,
                'error': StructuredLogger.LogLevel.ERROR,
                'critical': StructuredLogger.LogLevel.CRITICAL
            }

            # Get numeric log level
            log_level = level_map.get(args.level.lower(), StructuredLogger.LogLevel.INFO)

            # Prepare context if provided
            context = None
            if args.context:
                try:
                    context = json.loads(args.context)
                except json.JSONDecodeError:
                    print("Invalid context JSON. Using empty context.")
                    context = {}

            # Log the message
            self.logger.log(
                message=args.message,
                level=log_level,
                component=args.component,
                context=context
            )

            print("Message logged successfully.")
        except Exception as e:
            print(f"Failed to log message: {e}")

    def export_logs(self, args):
        """
        Export logs to a JSON file.

        Args:
            args (Namespace): Parsed CLI arguments
        """
        try:
            # Query logs with optional filters
            start_time = (
                datetime.fromisoformat(args.start_time)
                if args.start_time
                else None
            )
            end_time = (
                datetime.fromisoformat(args.end_time)
                if args.end_time
                else None
            )

            log_results = self.logger.query_logs(
                component=args.component,
                log_level=args.level,
                start_time=start_time,
                end_time=end_time,
                keyword=args.keyword
            )

            # Determine output file
            output_file = args.output or f"logs_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

            # Write logs to file
            with open(output_file, 'w') as f:
                json.dump(log_results, f, indent=2)

            print(f"Logs exported to {output_file}")
        except Exception as e:
            print(f"Log export failed: {e}")

    def run(self):
        """
        Set up and run the CLI argument parser.
        """
        parser = argparse.ArgumentParser(
            description="Structured Logger Management CLI"
        )
        subparsers = parser.add_subparsers(
            dest='command',
            help='Available commands'
        )

        # Query Logs Command
        query_parser = subparsers.add_parser(
            'query',
            help='Query and filter log entries'
        )
        query_parser.add_argument(
            '--component',
            help='Filter by specific component'
        )
        query_parser.add_argument(
            '--level',
            help='Minimum log level (TRACE/DEBUG/INFO/WARNING/ERROR/CRITICAL)'
        )
        query_parser.add_argument(
            '--start-time',
            help='Start time for log query (ISO format)'
        )
        query_parser.add_argument(
            '--end-time',
            help='End time for log query (ISO format)'
        )
        query_parser.add_argument(
            '--keyword',
            help='Search keyword in log messages'
        )

        # Set Retention Command
        retention_parser = subparsers.add_parser(
            'set-retention',
            help='Set log retention period'
        )
        retention_parser.add_argument(
            'days',
            type=int,
            help='Number of days to retain logs'
        )

        # Log Message Command
        log_parser = subparsers.add_parser(
            'log',
            help='Log a new message'
        )
        log_parser.add_argument(
            'message',
            help='Log message content'
        )
        log_parser.add_argument(
            '--level',
            default='info',
            help='Log level (default: info)'
        )
        log_parser.add_argument(
            '--component',
            default='system',
            help='Component name (default: system)'
        )
        log_parser.add_argument(
            '--context',
            help='Additional context as JSON string'
        )

        # Export Logs Command
        export_parser = subparsers.add_parser(
            'export',
            help='Export logs to a file'
        )
        export_parser.add_argument(
            '--component',
            help='Filter by specific component'
        )
        export_parser.add_argument(
            '--level',
            help='Minimum log level'
        )
        export_parser.add_argument(
            '--start-time',
            help='Start time for log export (ISO format)'
        )
        export_parser.add_argument(
            '--end-time',
            help='End time for log export (ISO format)'
        )
        export_parser.add_argument(
            '--output',
            help='Output file path'
        )

        # Parse arguments and dispatch
        args = parser.parse_args()

        # Map commands to methods
        command_map = {
            'query': self.query_logs,
            'set-retention': self.set_retention,
            'log': self.log_message,
            'export': self.export_logs
        }

        # Execute the appropriate command
        if args.command:
            command_map[args.command](args)
        else:
            parser.print_help()


def main():
    """
    Entry point for the Structured Logger CLI.
    """
    # Create a logger instance
    logger = StructuredLogger()

    # Create and run CLI
    cli = StructuredLoggerCLI(logger)
    cli.run()


if __name__ == '__main__':
    main()
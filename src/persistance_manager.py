from typing import Any, Dict, List, Optional, Set
import sqlite3
import json
import logging
import argparse
from datetime import datetime
import threading
import hashlib
import shutil
import os
from dataclasses import dataclass
from enum import Enum
from contextlib import contextmanager


class PersistenceError(Exception):
    """Base class for persistence-related exceptions."""
    pass


class TransactionError(Exception):
    """Base class for transaction-related exceptions."""
    pass


class DataIntegrityError(Exception):
    """Base class for data integrity-related exceptions."""
    pass


class OperationType(Enum):
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    MIGRATE = "migrate"
    BACKUP = "backup"
    RESTORE = "restore"


@dataclass
class Transaction:
    id: str
    operations: List[Dict]
    timestamp: datetime
    status: str = "pending"
    checksum: Optional[str] = None


class OperationMetrics:
    def __init__(self):
        self.operation_counts: Dict[str, int] = {op.value: 0 for op in OperationType}
        self.failed_operations: Dict[str, int] = {op.value: 0 for op in OperationType}
        self.total_transaction_time: float = 0.0
        self.operation_history: List[Dict] = []

    def record_operation(self, op_type: OperationType, success: bool, duration: float):
        if success:
            self.operation_counts[op_type.value] += 1
        else:
            self.failed_operations[op_type.value] += 1

        self.total_transaction_time += duration
        self.operation_history.append({
            'timestamp': datetime.now().isoformat(),
            'type': op_type.value,
            'success': success,
            'duration': duration
        })


class DataPersistenceManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.backup_dir = "backups"
        self.migrations_dir = "migrations"
        self.metrics = OperationMetrics()
        self.lock = threading.Lock()
        self.logger = logging.getLogger(__name__)

        # Ensure directories exist
        os.makedirs(self.backup_dir, exist_ok=True)
        os.makedirs(self.migrations_dir, exist_ok=True)

        self._setup_logging()
        self._initialize_database()

    def _setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s [%(levelname)s] %(message)s',
            handlers=[
                logging.FileHandler('persistence.log'),
                logging.StreamHandler()
            ]
        )

    def _initialize_database(self):
        """Initialize database with required tables."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS data (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    version INTEGER,
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id TEXT PRIMARY KEY,
                    operations TEXT,
                    timestamp TIMESTAMP,
                    status TEXT,
                    checksum TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS migrations (
                    id TEXT PRIMARY KEY,
                    applied_at TIMESTAMP,
                    description TEXT
                )
            """)

    @contextmanager
    def _get_connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def create(self, key: str, value: Any) -> bool:
        """Create a new data entry."""
        try:
            with self._get_connection() as conn:
                start_time = datetime.now()
                cursor = conn.cursor()

                # Check if key already exists
                cursor.execute("SELECT key FROM data WHERE key = ?", (key,))
                if cursor.fetchone():
                    raise PersistenceError(f"Key {key} already exists")

                now = datetime.now()
                cursor.execute(
                    "INSERT INTO data (key, value, version, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                    (key, json.dumps(value), 1, now, now)
                )

                duration = (datetime.now() - start_time).total_seconds()
                self.metrics.record_operation(OperationType.CREATE, True, duration)
                self.logger.info(f"Created data entry: {key}")
                return True

        except Exception as e:
            self.metrics.record_operation(OperationType.CREATE, False, 0)
            self.logger.error(f"Error creating data entry: {str(e)}")
            raise PersistenceError(f"Create operation failed: {str(e)}")

    def read(self, key: str) -> Any:
        """Read a data entry."""
        try:
            with self._get_connection() as conn:
                start_time = datetime.now()
                cursor = conn.cursor()

                cursor.execute("SELECT value FROM data WHERE key = ?", (key,))
                result = cursor.fetchone()

                if not result:
                    raise PersistenceError(f"Key {key} not found")

                duration = (datetime.now() - start_time).total_seconds()
                self.metrics.record_operation(OperationType.READ, True, duration)
                return json.loads(result['value'])

        except Exception as e:
            self.metrics.record_operation(OperationType.READ, False, 0)
            self.logger.error(f"Error reading data entry: {str(e)}")
            raise PersistenceError(f"Read operation failed: {str(e)}")

    def update(self, key: str, value: Any) -> bool:
        """Update a data entry."""
        try:
            with self._get_connection() as conn:
                start_time = datetime.now()
                cursor = conn.cursor()

                cursor.execute("SELECT version FROM data WHERE key = ?", (key,))
                result = cursor.fetchone()

                if not result:
                    raise PersistenceError(f"Key {key} not found")

                current_version = result['version']
                cursor.execute(
                    "UPDATE data SET value = ?, version = ?, updated_at = ? WHERE key = ?",
                    (json.dumps(value), current_version + 1, datetime.now(), key)
                )

                duration = (datetime.now() - start_time).total_seconds()
                self.metrics.record_operation(OperationType.UPDATE, True, duration)
                self.logger.info(f"Updated data entry: {key}")
                return True

        except Exception as e:
            self.metrics.record_operation(OperationType.UPDATE, False, 0)
            self.logger.error(f"Error updating data entry: {str(e)}")
            raise PersistenceError(f"Update operation failed: {str(e)}")

    def delete(self, key: str) -> bool:
        """Delete a data entry."""
        try:
            with self._get_connection() as conn:
                start_time = datetime.now()
                cursor = conn.cursor()

                cursor.execute("DELETE FROM data WHERE key = ?", (key,))
                if cursor.rowcount == 0:
                    raise PersistenceError(f"Key {key} not found")

                duration = (datetime.now() - start_time).total_seconds()
                self.metrics.record_operation(OperationType.DELETE, True, duration)
                self.logger.info(f"Deleted data entry: {key}")
                return True

        except Exception as e:
            self.metrics.record_operation(OperationType.DELETE, False, 0)
            self.logger.error(f"Error deleting data entry: {str(e)}")
            raise PersistenceError(f"Delete operation failed: {str(e)}")

    @contextmanager
    def transaction(self):
        """Context manager for transaction handling."""
        transaction_id = hashlib.md5(str(datetime.now().timestamp()).encode()).hexdigest()

        try:
            with self._get_connection() as conn:
                conn.execute("BEGIN TRANSACTION")
                yield conn

                # Record successful transaction
                conn.execute(
                    "INSERT INTO transactions (id, timestamp, status) VALUES (?, ?, ?)",
                    (transaction_id, datetime.now(), "committed")
                )
                conn.execute("COMMIT")

        except Exception as e:
            # Record failed transaction
            conn.execute(
                "INSERT INTO transactions (id, timestamp, status) VALUES (?, ?, ?)",
                (transaction_id, datetime.now(), "failed")
            )
            conn.execute("ROLLBACK")
            raise TransactionError(f"Transaction failed: {str(e)}")

    def create_backup(self) -> str:
        """Create a backup of the database."""
        try:
            start_time = datetime.now()
            backup_path = os.path.join(
                self.backup_dir,
                f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
            )

            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Create backup
                shutil.copy2(self.db_path, backup_path)

                # Calculate checksum
                checksum = hashlib.md5(open(backup_path, 'rb').read()).hexdigest()

                # Record backup metadata
                cursor.execute(
                    "INSERT INTO transactions (id, timestamp, status, checksum) VALUES (?, ?, ?, ?)",
                    (f"backup_{os.path.basename(backup_path)}", datetime.now(), "completed", checksum)
                )

            duration = (datetime.now() - start_time).total_seconds()
            self.metrics.record_operation(OperationType.BACKUP, True, duration)
            self.logger.info(f"Created backup: {backup_path}")
            return backup_path

        except Exception as e:
            self.metrics.record_operation(OperationType.BACKUP, False, 0)
            self.logger.error(f"Error creating backup: {str(e)}")
            raise PersistenceError(f"Backup operation failed: {str(e)}")

    def restore_backup(self, backup_path: str) -> bool:
        """Restore database from backup."""
        try:
            start_time = datetime.now()

            if not os.path.exists(backup_path):
                raise PersistenceError(f"Backup file not found: {backup_path}")

            # Verify backup integrity
            stored_checksum = None
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT checksum FROM transactions WHERE id = ?",
                    (f"backup_{os.path.basename(backup_path)}",)
                )
                result = cursor.fetchone()
                if result:
                    stored_checksum = result['checksum']

            if stored_checksum:
                current_checksum = hashlib.md5(open(backup_path, 'rb').read()).hexdigest()
                if current_checksum != stored_checksum:
                    raise DataIntegrityError("Backup file integrity check failed")

            # Restore database
            shutil.copy2(backup_path, self.db_path)

            duration = (datetime.now() - start_time).total_seconds()
            self.metrics.record_operation(OperationType.RESTORE, True, duration)
            self.logger.info(f"Restored from backup: {backup_path}")
            return True

        except Exception as e:
            self.metrics.record_operation(OperationType.RESTORE, False, 0)
            self.logger.error(f"Error restoring backup: {str(e)}")
            raise PersistenceError(f"Restore operation failed: {str(e)}")

    def verify_integrity(self) -> Dict[str, Any]:
        """Verify data integrity."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Check for orphaned records
                cursor.execute("PRAGMA integrity_check")
                integrity_check = cursor.fetchone()[0]

                # Check for incomplete transactions
                cursor.execute("SELECT COUNT(*) FROM transactions WHERE status = 'pending'")
                pending_transactions = cursor.fetchone()[0]

                # Check for data consistency
                cursor.execute("SELECT COUNT(*) FROM data")
                total_records = cursor.fetchone()[0]

                return {
                    'integrity_check': integrity_check == 'ok',
                    'pending_transactions': pending_transactions,
                    'total_records': total_records,
                    'last_verified': datetime.now().isoformat()
                }

        except Exception as e:
            self.logger.error(f"Error verifying integrity: {str(e)}")
            raise DataIntegrityError(f"Integrity verification failed: {str(e)}")

    def get_metrics(self) -> Dict[str, Any]:
        """Get operation metrics."""
        return {
            'operation_counts': self.metrics.operation_counts,
            'failed_operations': self.metrics.failed_operations,
            'total_transaction_time': self.metrics.total_transaction_time,
            'operation_history': self.metrics.operation_history
        }


def main():
    """CLI entry point for the DataPersistenceManager."""
    parser = argparse.ArgumentParser(description='Data Persistence Manager CLI')
    parser.add_argument('command', choices=['backup', 'restore', 'verify', 'metrics'])
    parser.add_argument('--backup-path', help='Path for backup/restore operations')
    args = parser.parse_args()

    manager = DataPersistenceManager('data.db')

    try:
        if args.command == 'backup':
            backup_path = manager.create_backup()
            print(json.dumps({'backup_path': backup_path}, indent=2))
        elif args.command == 'restore' and args.backup_path:
            success = manager.restore_backup(args.backup_path)
            print(json.dumps({'success': success}, indent=2))
        elif args.command == 'verify':
            print(json.dumps(manager.verify_integrity(), indent=2))
        elif args.command == 'metrics':
            print(json.dumps(manager.get_metrics(), indent=2))
    except Exception as e:
        print(json.dumps({'error': str(e)}, indent=2))
        exit(1)


if __name__ == '__main__':
    main()
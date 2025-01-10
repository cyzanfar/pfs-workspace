# src/audit_logger.py
import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any
import json
import aiofiles
import logging
import os
from pathlib import Path
import gzip
from cryptography.fernet import Fernet
import hashlib
import shutil


class AuditEventType(Enum):
    TRANSACTION = "transaction"
    SECURITY = "security"
    USER_ACCESS = "user_access"
    KEY_MANAGEMENT = "key_management"
    SYSTEM = "system"
    COMPLIANCE = "compliance"


@dataclass
class AuditEvent:
    event_type: AuditEventType
    timestamp: datetime
    event_id: str
    user_id: Optional[str]
    source_ip: Optional[str]
    action: str
    status: str
    details: dict
    correlation_id: Optional[str] = None


class AuditLogger:
    def __init__(self,
                 log_dir: str = "logs/audit",
                 encryption_key: Optional[bytes] = None,
                 max_file_size: int = 10_485_760,  # 10MB
                 retention_days: int = 365):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Setup encryption
        self.encryption_key = encryption_key or Fernet.generate_key()
        self.fernet = Fernet(self.encryption_key)

        self.max_file_size = max_file_size
        self.retention_days = retention_days
        self.current_file = None
        self.current_size = 0

        # Initialize logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger("AuditLogger")

        # Start maintenance tasks
        asyncio.create_task(self._maintenance_loop())

    async def _maintenance_loop(self):
        """Periodic maintenance tasks"""
        while True:
            try:
                await self._rotate_logs()
                await self._cleanup_old_logs()
                await asyncio.sleep(3600)  # Check every hour
            except Exception as e:
                self.logger.error(f"Maintenance error: {str(e)}")
                await asyncio.sleep(300)

    async def _rotate_logs(self):
        """Rotate log files if needed"""
        if not self.current_file or self.current_size >= self.max_file_size:
            if self.current_file:
                await self._compress_and_encrypt_log(self.current_file)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.current_file = self.log_dir / f"audit_{timestamp}.log"
            self.current_size = 0

    async def _compress_and_encrypt_log(self, log_file: Path):
        """Compress and encrypt completed log file"""
        try:
            # Read original file
            async with aiofiles.open(log_file, 'rb') as f:
                content = await f.read()

            # Compress
            compressed = gzip.compress(content)

            # Encrypt
            encrypted = self.fernet.encrypt(compressed)

            # Save encrypted file
            encrypted_file = log_file.with_suffix('.log.enc')
            async with aiofiles.open(encrypted_file, 'wb') as f:
                await f.write(encrypted)

            # Remove original
            os.remove(log_file)

            # Calculate and save checksum
            checksum = hashlib.sha256(encrypted).hexdigest()
            checksum_file = encrypted_file.with_suffix('.sha256')
            async with aiofiles.open(checksum_file, 'w') as f:
                await f.write(checksum)

        except Exception as e:
            self.logger.error(f"Error processing log file {log_file}: {str(e)}")
            raise

    async def _cleanup_old_logs(self):
        """Remove logs older than retention period"""
        cutoff = datetime.now() - timedelta(days=self.retention_days)
        for file in self.log_dir.glob('*.log.enc'):
            try:
                # Extract timestamp from filename
                timestamp_str = file.stem.split('_')[1]
                file_date = datetime.strptime(timestamp_str, "%Y%m%d")

                if file_date < cutoff:
                    os.remove(file)
                    # Remove associated checksum file
                    checksum_file = file.with_suffix('.sha256')
                    if checksum_file.exists():
                        os.remove(checksum_file)
            except Exception as e:
                self.logger.error(f"Error cleaning up {file}: {str(e)}")

    async def log_event(self, event: AuditEvent):
        """Log audit event with compliance fields"""
        await self._rotate_logs()

        event_data = {
            'timestamp': event.timestamp.isoformat(),
            'event_type': event.event_type.value,
            'event_id': event.event_id,
            'user_id': event.user_id,
            'source_ip': event.source_ip,
            'action': event.action,
            'status': event.status,
            'details': event.details,
            'correlation_id': event.correlation_id
        }

        log_line = json.dumps(event_data) + '\n'
        async with aiofiles.open(self.current_file, 'a') as f:
            await f.write(log_line)

        self.current_size += len(log_line.encode())

    async def search_logs(self,
                          start_time: Optional[datetime] = None,
                          end_time: Optional[datetime] = None,
                          event_types: Optional[List[AuditEventType]] = None,
                          user_id: Optional[str] = None,
                          source_ip: Optional[str] = None,
                          correlation_id: Optional[str] = None) -> List[AuditEvent]:
        """Search audit logs with filters"""
        results = []

        # Search current log file
        if self.current_file and self.current_file.exists():
            async with aiofiles.open(self.current_file, 'r') as f:
                async for line in f:
                    event = await self._process_log_line(line, start_time,
                                                         end_time, event_types,
                                                         user_id, source_ip,
                                                         correlation_id)
                    if event:
                        results.append(event)

        # Search encrypted logs
        for enc_file in sorted(self.log_dir.glob('*.log.enc')):
            try:
                # Verify checksum
                checksum_file = enc_file.with_suffix('.sha256')
                if not await self._verify_checksum(enc_file, checksum_file):
                    self.logger.error(f"Checksum verification failed for {enc_file}")
                    continue

                # Process encrypted file
                events = await self._process_encrypted_log(
                    enc_file, start_time, end_time, event_types,
                    user_id, source_ip, correlation_id
                )
                results.extend(events)

            except Exception as e:
                self.logger.error(f"Error processing {enc_file}: {str(e)}")

        return sorted(results, key=lambda x: x.timestamp)

    async def _verify_checksum(self, enc_file: Path, checksum_file: Path) -> bool:
        """Verify file checksum"""
        if not checksum_file.exists():
            return False

        async with aiofiles.open(checksum_file, 'r') as f:
            stored_checksum = await f.read()

        async with aiofiles.open(enc_file, 'rb') as f:
            content = await f.read()
            calculated_checksum = hashlib.sha256(content).hexdigest()

        return stored_checksum == calculated_checksum

    async def _process_encrypted_log(self,
                                     enc_file: Path,
                                     start_time: Optional[datetime],
                                     end_time: Optional[datetime],
                                     event_types: Optional[List[AuditEventType]],
                                     user_id: Optional[str],
                                     source_ip: Optional[str],
                                     correlation_id: Optional[str]) -> List[AuditEvent]:
        """Process encrypted log file"""
        results = []

        async with aiofiles.open(enc_file, 'rb') as f:
            content = await f.read()

        # Decrypt and decompress
        decrypted = self.fernet.decrypt(content)
        decompressed = gzip.decompress(decrypted).decode()

        # Process each line
        for line in decompressed.splitlines():
            event = await self._process_log_line(line, start_time, end_time,
                                                 event_types, user_id, source_ip,
                                                 correlation_id)
            if event:
                results.append(event)

        return results

    async def _process_log_line(self,
                                line: str,
                                start_time: Optional[datetime],
                                end_time: Optional[datetime],
                                event_types: Optional[List[AuditEventType]],
                                user_id: Optional[str],
                                source_ip: Optional[str],
                                correlation_id: Optional[str]) -> Optional[AuditEvent]:
        """Process single log line with filters"""
        try:
            data = json.loads(line)
            timestamp = datetime.fromisoformat(data['timestamp'])

            # Apply filters
            if start_time and timestamp < start_time:
                return None
            if end_time and timestamp > end_time:
                return None
            if event_types and AuditEventType(data['event_type']) not in event_types:
                return None
            if user_id and data['user_id'] != user_id:
                return None
            if source_ip and data['source_ip'] != source_ip:
                return None
            if correlation_id and data['correlation_id'] != correlation_id:
                return None

            return AuditEvent(
                event_type=AuditEventType(data['event_type']),
                timestamp=timestamp,
                event_id=data['event_id'],
                user_id=data['user_id'],
                source_ip=data['source_ip'],
                action=data['action'],
                status=data['status'],
                details=data['details'],
                correlation_id=data['correlation_id']
            )

        except Exception as e:
            self.logger.error(f"Error processing log line: {str(e)}")
            return None

    async def generate_compliance_report(self,
                                         start_time: datetime,
                                         end_time: datetime) -> Dict[str, Any]:
        """Generate compliance report for time period"""
        events = await self.search_logs(start_time=start_time, end_time=end_time)

        report = {
            'period_start': start_time.isoformat(),
            'period_end': end_time.isoformat(),
            'generated_at': datetime.now().isoformat(),
            'total_events': len(events),
            'events_by_type': {},
            'user_activity': {},
            'security_events': [],
            'system_health': {
                'errors': 0,
                'warnings': 0
            }
        }

        for event in events:
            # Count by type
            event_type = event.event_type.value
            report['events_by_type'][event_type] = \
                report['events_by_type'].get(event_type, 0) + 1

            # Track user activity
            if event.user_id:
                if event.user_id not in report['user_activity']:
                    report['user_activity'][event.user_id] = {
                        'total_actions': 0,
                        'last_action': None,
                        'actions': {}
                    }
                user_stats = report['user_activity'][event.user_id]
                user_stats['total_actions'] += 1
                user_stats['last_action'] = event.timestamp.isoformat()
                user_stats['actions'][event.action] = \
                    user_stats['actions'].get(event.action, 0) + 1

            # Track security events
            if event.event_type == AuditEventType.SECURITY:
                report['security_events'].append({
                    'timestamp': event.timestamp.isoformat(),
                    'action': event.action,
                    'status': event.status,
                    'source_ip': event.source_ip,
                    'details': event.details
                })

            # Track system health
            if event.event_type == AuditEventType.SYSTEM:
                if 'error' in event.status.lower():
                    report['system_health']['errors'] += 1
                elif 'warning' in event.status.lower():
                    report['system_health']['warnings'] += 1

        return report

    async def export_logs(self,
                          output_file: str,
                          start_time: Optional[datetime] = None,
                          end_time: Optional[datetime] = None,
                          event_types: Optional[List[AuditEventType]] = None):
        """Export filtered logs to file"""
        events = await self.search_logs(
            start_time=start_time,
            end_time=end_time,
            event_types=event_types
        )

        export_data = {
            'exported_at': datetime.now().isoformat(),
            'start_time': start_time.isoformat() if start_time else None,
            'end_time': end_time.isoformat() if end_time else None,
            'total_events': len(events),
            'events': [
                {
                    'timestamp': event.timestamp.isoformat(),
                    'event_type': event.event_type.value,
                    'event_id': event.event_id,
                    'user_id': event.user_id,
                    'source_ip': event.source_ip,
                    'action': event.action,
                    'status': event.status,
                    'details': event.details,
                    'correlation_id': event.correlation_id
                }
                for event in events
            ]
        }

        async with aiofiles.open(output_file, 'w') as f:
            await f.write(json.dumps(export_data, indent=2))
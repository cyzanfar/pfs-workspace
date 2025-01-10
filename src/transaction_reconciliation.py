# src/transaction_reconciliation.py
import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional
import json
import logging
import aiofiles
from web3 import Web3


class ReconciliationStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    RECOVERED = "recovered"
    FAILED = "failed"
    MANUAL_REVIEW = "manual_review"


@dataclass
class AuditRecord:
    tx_id: str
    timestamp: datetime
    status: ReconciliationStatus
    error_message: Optional[str] = None
    recovery_attempts: int = 0
    recovery_timestamp: Optional[datetime] = None
    reconciliation_hash: Optional[str] = None


class TransactionReconciliation:
    def __init__(self, payment_processor, audit_log_path: str = "audit/transactions.log"):
        self.payment_processor = payment_processor
        self.audit_log_path = audit_log_path
        self.audit_records: Dict[str, AuditRecord] = {}
        self.recovery_attempts: Dict[str, int] = {}
        self.MAX_AUTO_RECOVERY_ATTEMPTS = 3

        # Set up logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger("TransactionReconciliation")

        # Start automated reconciliation
        asyncio.create_task(self.automated_reconciliation())

    async def log_audit_record(self, record: AuditRecord):
        """Write audit record to log file"""
        async with aiofiles.open(self.audit_log_path, mode='a') as f:
            await f.write(json.dumps({
                'tx_id': record.tx_id,
                'timestamp': record.timestamp.isoformat(),
                'status': record.status.value,
                'error_message': record.error_message,
                'recovery_attempts': record.recovery_attempts,
                'recovery_timestamp': record.recovery_timestamp.isoformat()
                if record.recovery_timestamp else None,
                'reconciliation_hash': record.reconciliation_hash
            }) + '\n')

    async def load_audit_records(self):
        """Load existing audit records from log file"""
        try:
            async with aiofiles.open(self.audit_log_path, mode='r') as f:
                async for line in f:
                    data = json.loads(line)
                    record = AuditRecord(
                        tx_id=data['tx_id'],
                        timestamp=datetime.fromisoformat(data['timestamp']),
                        status=ReconciliationStatus(data['status']),
                        error_message=data['error_message'],
                        recovery_attempts=data['recovery_attempts'],
                        recovery_timestamp=datetime.fromisoformat(data['recovery_timestamp'])
                        if data['recovery_timestamp'] else None,
                        reconciliation_hash=data['reconciliation_hash']
                    )
                    self.audit_records[record.tx_id] = record
        except FileNotFoundError:
            self.logger.info("No existing audit log found")

    def calculate_reconciliation_hash(self, tx_data: dict) -> str:
        """Calculate hash for transaction verification"""
        w3 = Web3()
        data_str = json.dumps(tx_data, sort_keys=True)
        return w3.keccak(text=data_str).hex()

    async def automated_reconciliation(self):
        """Run automated reconciliation process every hour"""
        while True:
            try:
                await self.reconcile_transactions()
                await asyncio.sleep(3600)  # Wait for 1 hour
            except Exception as e:
                self.logger.error(f"Automated reconciliation error: {str(e)}")
                await asyncio.sleep(300)  # Wait 5 minutes on error

    async def reconcile_transactions(self):
        """Reconcile all transactions from the last 24 hours"""
        self.logger.info("Starting transaction reconciliation")

        # Load latest state
        await self.load_audit_records()

        # Get transactions from last 24 hours
        cutoff_time = datetime.now() - timedelta(days=1)
        recent_transactions = {
            tx_id: tx for tx_id, tx in self.payment_processor.transactions.items()
            if tx.timestamp > cutoff_time.timestamp()
        }

        for tx_id, tx in recent_transactions.items():
            try:
                # Verify transaction status on chain
                chain_status = await self.payment_processor.get_transaction_info(tx_id)

                # Calculate verification hash
                tx_data = {
                    'tx_id': tx_id,
                    'amount': tx.amount,
                    'from': tx.from_address,
                    'to': tx.to_address,
                    'status': tx.status.value
                }
                current_hash = self.calculate_reconciliation_hash(tx_data)

                # Check if transaction needs recovery
                if tx.status.value == 'failed':
                    await self.handle_failed_transaction(tx_id, tx)
                elif tx_id in self.audit_records:
                    # Verify transaction hasn't been tampered with
                    stored_record = self.audit_records[tx_id]
                    if stored_record.reconciliation_hash != current_hash:
                        await self.handle_inconsistent_transaction(tx_id, tx, current_hash)

                # Update audit record
                record = AuditRecord(
                    tx_id=tx_id,
                    timestamp=datetime.fromtimestamp(tx.timestamp),
                    status=ReconciliationStatus.RECOVERED
                    if tx.status.value == 'completed'
                    else ReconciliationStatus.FAILED,
                    error_message=tx.error_message,
                    recovery_attempts=self.recovery_attempts.get(tx_id, 0),
                    reconciliation_hash=current_hash
                )
                self.audit_records[tx_id] = record
                await self.log_audit_record(record)

            except Exception as e:
                self.logger.error(f"Error reconciling transaction {tx_id}: {str(e)}")
                await self.log_audit_record(AuditRecord(
                    tx_id=tx_id,
                    timestamp=datetime.now(),
                    status=ReconciliationStatus.FAILED,
                    error_message=str(e)
                ))

    async def handle_failed_transaction(self, tx_id: str, tx: dict):
        """Handle failed transaction recovery"""
        attempts = self.recovery_attempts.get(tx_id, 0)

        if attempts >= self.MAX_AUTO_RECOVERY_ATTEMPTS:
            await self.mark_for_manual_review(tx_id, tx)
            return

        try:
            # Attempt recovery based on error type
            if "insufficient funds" in tx.error_message.lower():
                await self.handle_insufficient_funds(tx_id, tx)
            elif "nonce too low" in tx.error_message.lower():
                await self.handle_nonce_error(tx_id, tx)
            elif "gas price too low" in tx.error_message.lower():
                await self.handle_gas_price_error(tx_id, tx)
            else:
                await self.mark_for_manual_review(tx_id, tx)

            self.recovery_attempts[tx_id] = attempts + 1

        except Exception as e:
            self.logger.error(f"Recovery failed for {tx_id}: {str(e)}")
            if attempts + 1 >= self.MAX_AUTO_RECOVERY_ATTEMPTS:
                await self.mark_for_manual_review(tx_id, tx)

    async def handle_insufficient_funds(self, tx_id: str, tx: dict):
        """Handle insufficient funds error"""
        self.logger.info(f"Insufficient funds for {tx_id}, marking for manual review")
        await self.mark_for_manual_review(tx_id, tx)

    async def handle_nonce_error(self, tx_id: str, tx: dict):
        """Handle nonce synchronization error"""
        self.logger.info(f"Nonce error for {tx_id}, attempting to reset nonce")
        # Implementation would reset nonce and retry transaction
        pass

    async def handle_gas_price_error(self, tx_id: str, tx: dict):
        """Handle gas price too low error"""
        self.logger.info(f"Gas price too low for {tx_id}, attempting with higher gas")
        # Implementation would recalculate gas price and retry transaction
        pass

    async def mark_for_manual_review(self, tx_id: str, tx: dict):
        """Mark transaction for manual review"""
        record = AuditRecord(
            tx_id=tx_id,
            timestamp=datetime.now(),
            status=ReconciliationStatus.MANUAL_REVIEW,
            error_message=f"Manual review required: {tx.error_message}",
            recovery_attempts=self.recovery_attempts.get(tx_id, 0)
        )
        self.audit_records[tx_id] = record
        await self.log_audit_record(record)

    async def handle_inconsistent_transaction(self, tx_id: str, tx: dict, current_hash: str):
        """Handle potentially tampered transaction"""
        self.logger.warning(f"Transaction hash mismatch detected for {tx_id}")
        record = AuditRecord(
            tx_id=tx_id,
            timestamp=datetime.now(),
            status=ReconciliationStatus.MANUAL_REVIEW,
            error_message="Transaction hash mismatch detected",
            reconciliation_hash=current_hash
        )
        self.audit_records[tx_id] = record
        await self.log_audit_record(record)

    async def generate_reconciliation_report(self,
                                             start_time: datetime,
                                             end_time: datetime) -> dict:
        """Generate reconciliation report for time period"""
        report = {
            'period_start': start_time.isoformat(),
            'period_end': end_time.isoformat(),
            'total_transactions': 0,
            'recovered_transactions': 0,
            'failed_transactions': 0,
            'manual_review_required': 0,
            'recovery_success_rate': 0,
            'transactions_by_status': {},
            'manual_review_transactions': []
        }

        for record in self.audit_records.values():
            if start_time <= record.timestamp <= end_time:
                report['total_transactions'] += 1
                report['transactions_by_status'][record.status.value] = \
                    report['transactions_by_status'].get(record.status.value, 0) + 1

                if record.status == ReconciliationStatus.RECOVERED:
                    report['recovered_transactions'] += 1
                elif record.status == ReconciliationStatus.FAILED:
                    report['failed_transactions'] += 1
                elif record.status == ReconciliationStatus.MANUAL_REVIEW:
                    report['manual_review_required'] += 1
                    report['manual_review_transactions'].append({
                        'tx_id': record.tx_id,
                        'timestamp': record.timestamp.isoformat(),
                        'error': record.error_message,
                        'attempts': record.recovery_attempts
                    })

        if report['total_transactions'] > 0:
            report['recovery_success_rate'] = (
                    report['recovered_transactions'] / report['total_transactions'] * 100
            )

        return report
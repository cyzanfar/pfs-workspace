# src/reconciliation_cli.py
import click
import asyncio
from datetime import datetime, timedelta
import json
from .transaction_reconciliation import TransactionReconciliation, ReconciliationStatus


def init_reconciliation(ctx) -> TransactionReconciliation:
    """Initialize reconciliation system"""
    if 'reconciliation' not in ctx.obj:
        processor = ctx.obj['payment_processor']
        ctx.obj['reconciliation'] = TransactionReconciliation(processor)
    return ctx.obj['reconciliation']


@click.group()
def reconciliation():
    """Transaction reconciliation commands"""
    pass


@reconciliation.command()
@click.option('--days', default=1, help='Number of days to reconcile')
@click.pass_context
async def reconcile(ctx, days: int):
    """Run manual reconciliation for specified period"""
    reconciler = init_reconciliation(ctx)
    end_time = datetime.now()
    start_time = end_time - timedelta(days=days)

    click.echo(f"Starting reconciliation for period: "
               f"{start_time.date()} to {end_time.date()}")

    await reconciler.reconcile_transactions()

    report = await reconciler.generate_reconciliation_report(
        start_time, end_time
    )

    click.echo("\nReconciliation Report:")
    click.echo("-" * 40)
    click.echo(f"Total Transactions: {report['total_transactions']}")
    click.echo(f"Recovered: {report['recovered_transactions']}")
    click.echo(f"Failed: {report['failed_transactions']}")
    click.echo(f"Manual Review Required: {report['manual_review_required']}")
    click.echo(f"Recovery Success Rate: {report['recovery_success_rate']:.2f}%")

    if report['manual_review_transactions']:
        click.echo("\nTransactions Requiring Manual Review:")
        for tx in report['manual_review_transactions']:
            click.echo("-" * 40)
            click.echo(f"TX ID: {tx['tx_id']}")
            click.echo(f"Time: {tx['timestamp']}")
            click.echo(f"Error: {tx['error']}")
            click.echo(f"Recovery Attempts: {tx['attempts']}")


@reconciliation.command()
@click.option('--tx-id', required=True, help='Transaction ID')
@click.option('--retry/--no-retry', default=False,
              help='Attempt automatic recovery')
@click.pass_context
async def review(ctx, tx_id: str, retry: bool):
    """Review failed transaction details"""
    reconciler = init_reconciliation(ctx)

    await reconciler.load_audit_records()
    record = reconciler.audit_records.get(tx_id)

    if not record:
        click.echo(f"No audit record found for transaction {tx_id}")
        return

    click.echo(f"\nTransaction Review: {tx_id}")
    click.echo("-" * 40)
    click.echo(f"Status: {record.status.value}")
    click.echo(f"Timestamp: {record.timestamp}")
    click.echo(f"Error: {record.error_message}")
    click.echo(f"Recovery Attempts: {record.recovery_attempts}")

    if retry and record.status == ReconciliationStatus.MANUAL_REVIEW:
        click.echo("\nAttempting recovery...")
        tx = reconciler.payment_processor.get_transaction_info(tx_id)
        if tx:
            await reconciler.handle_failed_transaction(tx_id, tx)
            click.echo("Recovery attempt complete. Use 'review' command to check new status.")
        else:
            click.echo("Transaction not found in payment processor")


@reconciliation.command()
@click.option('--start-date', type=click.DateTime(),
              default=str(datetime.now().date()),
              help='Start date (YYYY-MM-DD)')
@click.option('--end-date', type=click.DateTime(),
              default=str(datetime.now().date()),
              help='End date (YYYY-MM-DD)')
@click.option('--output', type=click.Path(),
              help='Output file for report (optional)')
@click.pass_context
async def report(ctx, start_date: datetime, end_date: datetime, output: str):
    """Generate reconciliation report for time period"""
    reconciler = init_reconciliation(ctx)

    # Ensure end date includes full day
    end_date_adjusted = end_date + timedelta(days=1)

    report = await reconciler.generate_reconciliation_report(
        start_date, end_date_adjusted
    )

    # Print report to console
    click.echo(f"\nReconciliation Report: {start_date.date()} to {end_date.date()}")
    click.echo("-" * 60)
    click.echo(f"Total Transactions: {report['total_transactions']}")
    click.echo(f"Recovery Success Rate: {report['recovery_success_rate']:.2f}%")
    click.echo("\nTransaction Status Breakdown:")
    for status, count in report['transactions_by_status'].items():
        click.echo(f"  {status}: {count}")

    if report['manual_review_required'] > 0:
        click.echo(f"\nTransactions Requiring Manual Review: "
                   f"{report['manual_review_required']}")

    # Save to file if output specified
    if output:
        with open(output, 'w') as f:
            json.dump(report, f, indent=2)
        click.echo(f"\nDetailed report saved to {output}")


@reconciliation.command()
@click.pass_context
async def pending(ctx):
    """List all transactions pending manual review"""
    reconciler = init_reconciliation(ctx)

    await reconciler.load_audit_records()

    pending_records = [
        record for record in reconciler.audit_records.values()
        if record.status == ReconciliationStatus.MANUAL_REVIEW
    ]

    if not pending_records:
        click.echo("No transactions pending manual review")
        return

    click.echo("\nTransactions Pending Manual Review:")
    click.echo("-" * 60)

    for record in sorted(pending_records, key=lambda x: x.timestamp):
        click.echo(f"\nTX ID: {record.tx_id}")
        click.echo(f"Time: {record.timestamp}")
        click.echo(f"Error: {record.error_message}")
        click.echo(f"Recovery Attempts: {record.recovery_attempts}")


@reconciliation.command()
@click.option('--tx-id', required=True, help='Transaction ID')
@click.option('--status', type=click.Choice(['recovered', 'failed']),
              required=True, help='Final status')
@click.option('--notes', help='Notes about manual resolution')
@click.pass_context
async def resolve(ctx, tx_id: str, status: str, notes: str):
    """Manually resolve a transaction after review"""
    reconciler = init_reconciliation(ctx)

    await reconciler.load_audit_records()
    record = reconciler.audit_records.get(tx_id)

    if not record:
        click.echo(f"No audit record found for transaction {tx_id}")
        return

    if record.status != ReconciliationStatus.MANUAL_REVIEW:
        click.echo(f"Transaction {tx_id} is not pending manual review")
        return

    # Update record
    record.status = ReconciliationStatus(status)
    record.error_message = f"Manually resolved: {notes}" if notes else None
    record.recovery_timestamp = datetime.now()

    # Log update
    await reconciler.log_audit_record(record)

    click.echo(f"Transaction {tx_id} marked as {status}")
    if notes:
        click.echo(f"Notes: {notes}")


def setup_cli():
    """Setup CLI with async command handling"""

    async def async_reconciliation(ctx, *args, **kwargs):
        """Async wrapper for reconciliation command group"""
        return await ctx.forward(reconciliation)

    return click.command()(click.pass_context(async_reconciliation))
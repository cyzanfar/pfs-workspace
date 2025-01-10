# src/payment_cli.py
import click
from datetime import datetime
from eth_account import Account
import secrets
from .payment_processor import (
    ERC20PaymentProcessor, PaymentError, InvalidAddressError
)


def init_payment_processor(ctx):
    """Initialize payment processor if not exists"""
    if 'payment_processor' not in ctx.obj:
        # In production, get this from environment variable
        provider_url = "https://mainnet.infura.io/v3/YOUR-PROJECT-ID"
        ctx.obj['payment_processor'] = ERC20PaymentProcessor(provider_url)
    return ctx.obj['payment_processor']


@click.group()
def payment():
    """ERC20 token payment commands"""
    pass


@payment.command()
@click.option('--token', required=True, help='Token contract address')
@click.option('--address', required=True, help='Wallet address')
@click.pass_context
def balance(ctx, token: str, address: str):
    """Check token balance for address"""
    processor = init_payment_processor(ctx)

    try:
        token_info = processor.add_token(token)
        balance = processor.get_token_balance(token, address)
        click.echo(f"Balance for {address}:")
        click.echo(f"{balance} {token_info.symbol} ({token_info.name})")

    except PaymentError as e:
        click.echo(f"Error: {str(e)}", err=True)
        ctx.exit(1)


@payment.command()
@click.option('--from-key', required=True, help='Sender private key')
@click.option('--to', 'to_address', required=True, help='Recipient address')
@click.option('--amount', required=True, type=float, help='Token amount')
@click.option('--token', required=True, help='Token contract address')
@click.pass_context
def send(ctx, from_key: str, to_address: str, amount: float, token: str):
    """Send ERC20 tokens"""
    processor = init_payment_processor(ctx)

    try:
        # Validate private key
        if not from_key.startswith('0x'):
            from_key = '0x' + from_key
        Account.from_key(from_key)  # Will raise if invalid

        # Process payment
        transaction = processor.process_payment(
            private_key=from_key,
            to_address=to_address,
            amount=amount,
            token_address=token
        )

        click.echo(f"Transaction successful!")
        click.echo(f"Transaction Hash: {transaction.tx_hash}")
        click.echo(f"Amount: {transaction.amount} {transaction.token.symbol}")
        click.echo(f"Status: {transaction.status.value}")

    except PaymentError as e:
        click.echo(f"Payment failed: {str(e)}", err=True)
        ctx.exit(1)


@payment.command()
@click.option('--hash', required=True, help='Transaction hash')
@click.pass_context
def status(ctx, hash: str):
    """Check transaction status"""
    processor = init_payment_processor(ctx)

    transaction = processor.get_transaction(hash)
    if transaction:
        click.echo(f"Transaction: {transaction.tx_hash}")
        click.echo(f"Status: {transaction.status.value}")
        click.echo(f"Amount: {transaction.amount} {transaction.token.symbol}")
        click.echo(f"From: {transaction.from_address}")
        click.echo(f"To: {transaction.to_address}")
        click.echo(f"Time: {datetime.fromtimestamp(transaction.timestamp)}")
        if transaction.error_message:
            click.echo(f"Error: {transaction.error_message}")
    else:
        click.echo(f"Transaction not found: {hash}", err=True)
        ctx.exit(1)


@payment.command()
@click.option('--address', required=True, help='Wallet address')
@click.pass_context
def history(ctx, address: str):
    """View transaction history for an address"""
    processor = init_payment_processor(ctx)

    try:
        transactions = processor.get_address_transactions(address)

        if not transactions:
            click.echo("No transactions found")
            return

        click.echo(f"\nTransaction History for {address}:")
        click.echo("-" * 80)

        for tx in sorted(transactions, key=lambda x: x.timestamp, reverse=True):
            direction = "→" if tx.from_address == address else "←"
            other_address = tx.to_address if tx.from_address == address else tx.from_address

            click.echo(f"TX: {tx.tx_hash}")
            click.echo(f"Direction: {direction} {other_address}")
            click.echo(f"Amount: {tx.amount} {tx.token.symbol}")
            click.echo(f"Status: {tx.status.value}")
            click.echo(f"Time: {datetime.fromtimestamp(tx.timestamp)}")
            if tx.error_message:
                click.echo(f"Error: {tx.error_message}")
            click.echo("-" * 80)

    except PaymentError as e:
        click.echo(f"Error: {str(e)}", err=True)
        ctx.exit(1)


@payment.command()
@click.option('--token', required=True, help='Token contract address')
@click.pass_context
def add_token(ctx, token: str):
    """Add a new ERC20 token for tracking"""
    processor = init_payment_processor(ctx)

    try:
        token_info = processor.add_token(token)
        click.echo(f"Added token:")
        click.echo(f"Name: {token_info.name}")
        click.echo(f"Symbol: {token_info.symbol}")
        click.echo(f"Decimals: {token_info.decimals}")
        click.echo(f"Address: {token_info.address}")
    except PaymentError as e:
        click.echo(f"Error adding token: {str(e)}", err=True)
        ctx.exit(1)


@payment.command()
@click.pass_context
def new_wallet(ctx):
    """Generate a new Ethereum wallet"""
    # Generate a random private key
    private_key = "0x" + secrets.token_hex(32)
    account = Account.from_key(private_key)

    click.echo("Generated new wallet:")
    click.echo(f"Address: {account.address}")
    click.echo(f"Private Key: {private_key}")
    click.echo("\nWARNING: Store your private key securely!")
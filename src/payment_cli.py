# src/payment_cli.py
import click
import asyncio
from datetime import datetime
from typing import Optional
from .payment_processor import (
    Chain, MultiChainPaymentProcessor, BlockchainConfig,
    PaymentStatus, Transaction
)


def init_payment_processor(ctx) -> MultiChainPaymentProcessor:
    """Initialize payment processor if not exists"""
    if 'payment_processor' not in ctx.obj:
        # Configure for each blockchain
        configs = {
            Chain.ETH: BlockchainConfig(
                chain=Chain.ETH,
                node_url="https://mainnet.infura.io/v3/YOUR-PROJECT-ID",
                required_confirmations=12,
                webhook_url="https://your-webhook.com/eth"
            ),
            Chain.BTC: BlockchainConfig(
                chain=Chain.BTC,
                node_url="https://btc-node:8332",
                required_confirmations=6,
                webhook_url="https://your-webhook.com/btc"
            ),
            Chain.SOL: BlockchainConfig(
                chain=Chain.SOL,
                node_url="https://api.mainnet-beta.solana.com",
                required_confirmations=32,
                webhook_url="https://your-webhook.com/sol"
            )
        }
        ctx.obj['payment_processor'] = MultiChainPaymentProcessor(configs)
    return ctx.obj['payment_processor']


@click.group()
def payment():
    """Multi-chain payment processing commands"""
    pass


@payment.command()
@click.option(
    '--chain',
    type=click.Choice(['ETH', 'BTC', 'SOL']),
    required=True,
    help='Blockchain to use'
)
@click.option('--address', required=True, help='Wallet address')
@click.pass_context
def balance(ctx, chain: str, address: str):
    """Check wallet balance"""
    processor = init_payment_processor(ctx)
    chain_enum = Chain[chain]

    async def check():
        try:
            balance = await processor.check_balance(address, chain_enum)
            click.echo(f"Balance for {address} on {chain}:")
            click.echo(f"{balance} {chain}")
        except Exception as e:
            click.echo(f"Error: {str(e)}", err=True)
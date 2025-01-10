# src/payment_processor.py
import asyncio
from enum import Enum
from dataclasses import dataclass
from typing import Dict, List, Optional, Callable
import aiohttp
from web3 import Web3, AsyncWeb3
from web3.eth import AsyncEth
from bitcoinlib.wallets import Wallet
from solana.rpc.async_api import AsyncClient
from datetime import datetime
import hmac
import hashlib
import time


class Chain(Enum):
    ETH = "ethereum"
    BTC = "bitcoin"
    SOL = "solana"


class PaymentStatus(Enum):
    PENDING = "pending"
    CONFIRMING = "confirming"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class BlockchainConfig:
    chain: Chain
    node_url: str
    required_confirmations: int
    webhook_url: Optional[str] = None


@dataclass
class Transaction:
    tx_id: str
    chain: Chain
    from_address: str
    to_address: str
    amount: float
    currency: str
    status: PaymentStatus
    confirmations: int = 0
    timestamp: float = time.time()
    error_message: Optional[str] = None


class MultiChainPaymentProcessor:
    def __init__(self, configs: Dict[Chain, BlockchainConfig]):
        self.configs = configs
        self.transactions: Dict[str, Transaction] = {}

        # Initialize blockchain clients
        self.eth_client = AsyncWeb3(
            Web3.AsyncHTTPProvider(configs[Chain.ETH].node_url)
        )
        self.btc_client = Wallet.create(
            "btc_wallet", network='bitcoin',
            service='bitcoind', db_uri=configs[Chain.BTC].node_url
        )
        self.sol_client = AsyncClient(configs[Chain.SOL].node_url)

        # Start transaction monitor
        self.monitor = TransactionMonitor(self)
        asyncio.create_task(self.monitor.start())

    async def validate_eth_address(self, address: str) -> bool:
        return self.eth_client.is_address(address)

    async def validate_btc_address(self, address: str) -> bool:
        try:
            # Validate Bitcoin address format and checksum
            return bool(self.btc_client.addresslist.add(address))
        except:
            return False

    async def validate_sol_address(self, address: str) -> bool:
        # Basic Solana address validation
        return len(address) == 44 and address.isalnum()

    async def validate_address(self, address: str, chain: Chain) -> bool:
        validators = {
            Chain.ETH: self.validate_eth_address,
            Chain.BTC: self.validate_btc_address,
            Chain.SOL: self.validate_sol_address
        }
        return await validators[chain](address)

    async def check_eth_balance(self, address: str) -> float:
        balance_wei = await self.eth_client.eth.get_balance(address)
        return Web3.from_wei(balance_wei, 'ether')

    async def check_btc_balance(self, address: str) -> float:
        wallet = self.btc_client.wallet(address)
        return float(wallet.balance())

    async def check_sol_balance(self, address: str) -> float:
        balance = await self.sol_client.get_balance(address)
        return balance.value / 10 ** 9  # Convert lamports to SOL

    async def check_balance(self, address: str, chain: Chain) -> float:
        balance_checkers = {
            Chain.ETH: self.check_eth_balance,
            Chain.BTC: self.check_btc_balance,
            Chain.SOL: self.check_sol_balance
        }
        return await balance_checkers[chain](address)

    async def send_eth_transaction(self, from_key: str, to_address: str,
                                   amount: float) -> str:
        account = self.eth_client.eth.account.from_key(from_key)
        transaction = {
            'nonce': await self.eth_client.eth.get_transaction_count(account.address),
            'gasPrice': await self.eth_client.eth.gas_price,
            'gas': 21000,
            'to': to_address,
            'value': Web3.to_wei(amount, 'ether'),
            'data': b'',
        }
        signed = self.eth_client.eth.account.sign_transaction(transaction, from_key)
        tx_hash = await self.eth_client.eth.send_raw_transaction(signed.rawTransaction)
        return tx_hash.hex()

    async def send_btc_transaction(self, from_key: str, to_address: str,
                                   amount: float) -> str:
        wallet = self.btc_client.wallet(privkey=from_key)
        tx = wallet.send_to(to_address, amount)
        return tx.hash

    async def send_sol_transaction(self, from_key: str, to_address: str,
                                   amount: float) -> str:
        # Implement Solana transaction
        # This is a placeholder - actual implementation would use solana-py
        pass

    async def process_payment(self, chain: Chain, from_key: str,
                              to_address: str, amount: float) -> Transaction:
        """Process payment on specified blockchain"""

        # Validate address
        if not await self.validate_address(to_address, chain):
            raise ValueError(f"Invalid {chain.value} address: {to_address}")

        # Check balance
        from_address = self.get_address_from_key(from_key, chain)
        balance = await self.check_balance(from_address, chain)
        if balance < amount:
            raise ValueError(f"Insufficient balance: {balance}")

        # Send transaction
        try:
            senders = {
                Chain.ETH: self.send_eth_transaction,
                Chain.BTC: self.send_btc_transaction,
                Chain.SOL: self.send_sol_transaction
            }
            tx_id = await senders[chain](from_key, to_address, amount)

            # Create transaction record
            transaction = Transaction(
                tx_id=tx_id,
                chain=chain,
                from_address=from_address,
                to_address=to_address,
                amount=amount,
                currency=chain.value,
                status=PaymentStatus.PENDING
            )
            self.transactions[tx_id] = transaction

            # Monitor will automatically track confirmations
            return transaction

        except Exception as e:
            raise ValueError(f"Transaction failed: {str(e)}")

    def get_address_from_key(self, private_key: str, chain: Chain) -> str:
        """Get public address from private key for specified chain"""
        if chain == Chain.ETH:
            account = self.eth_client.eth.account.from_key(private_key)
            return account.address
        elif chain == Chain.BTC:
            wallet = self.btc_client.wallet(privkey=private_key)
            return wallet.get_key().address
        elif chain == Chain.SOL:
            # Implement Solana key derivation
            pass

    async def get_transaction_info(self, tx_id: str) -> Optional[Transaction]:
        """Get transaction details and current status"""
        return self.transactions.get(tx_id)

    async def get_address_transactions(self, address: str,
                                       chain: Chain) -> List[Transaction]:
        """Get all transactions for an address on specified chain"""
        return [
            tx for tx in self.transactions.values()
            if tx.chain == chain and (
                    tx.from_address == address or tx.to_address == address
            )
        ]


class TransactionMonitor:
    def __init__(self, processor: MultiChainPaymentProcessor):
        self.processor = processor
        self.callbacks: Dict[str, List[Callable]] = {}

    async def start(self):
        """Start monitoring transactions across all chains"""
        while True:
            await self.check_all_transactions()
            await asyncio.sleep(10)  # Check every 10 seconds

    async def check_all_transactions(self):
        """Check confirmations for all pending transactions"""
        tasks = []
        for tx in self.processor.transactions.values():
            if tx.status in [PaymentStatus.PENDING, PaymentStatus.CONFIRMING]:
                tasks.append(self.check_transaction(tx))

        if tasks:
            await asyncio.gather(*tasks)

    async def check_transaction(self, transaction: Transaction):
        """Check confirmations for a single transaction"""
        try:
            if transaction.chain == Chain.ETH:
                confirmations = await self.check_eth_confirmations(transaction.tx_id)
            elif transaction.chain == Chain.BTC:
                confirmations = await self.check_btc_confirmations(transaction.tx_id)
            elif transaction.chain == Chain.SOL:
                confirmations = await self.check_sol_confirmations(transaction.tx_id)

            transaction.confirmations = confirmations
            config = self.processor.configs[transaction.chain]

            if confirmations >= config.required_confirmations:
                transaction.status = PaymentStatus.COMPLETED
                await self.notify_completion(transaction)
            elif confirmations > 0:
                transaction.status = PaymentStatus.CONFIRMING

        except Exception as e:
            transaction.status = PaymentStatus.FAILED
            transaction.error_message = str(e)
            await self.notify_error(transaction)

    async def check_eth_confirmations(self, tx_hash: str) -> int:
        """Check confirmations for Ethereum transaction"""
        try:
            tx = await self.processor.eth_client.eth.get_transaction(tx_hash)
            if tx and tx['blockNumber']:
                current_block = await self.processor.eth_client.eth.block_number
                return current_block - tx['blockNumber'] + 1
            return 0
        except Exception:
            return 0

    async def check_btc_confirmations(self, tx_hash: str) -> int:
        """Check confirmations for Bitcoin transaction"""
        try:
            tx = self.processor.btc_client.gettransaction(tx_hash)
            return tx.get('confirmations', 0)
        except Exception:
            return 0

    async def check_sol_confirmations(self, signature: str) -> int:
        """Check confirmations for Solana transaction"""
        try:
            response = await self.processor.sol_client.get_signature_statuses([signature])
            if response.value[0] and response.value[0].confirmations:
                return response.value[0].confirmations
            return 0
        except Exception:
            return 0

    async def notify_completion(self, transaction: Transaction):
        """Send webhook notification for completed transaction"""
        config = self.processor.configs[transaction.chain]
        if config.webhook_url:
            await self.send_webhook(config.webhook_url, {
                'event': 'transaction.completed',
                'transaction': {
                    'tx_id': transaction.tx_id,
                    'chain': transaction.chain.value,
                    'amount': transaction.amount,
                    'currency': transaction.currency,
                    'confirmations': transaction.confirmations,
                    'timestamp': transaction.timestamp
                }
            })

    async def notify_error(self, transaction: Transaction):
        """Send webhook notification for failed transaction"""
        config = self.processor.configs[transaction.chain]
        if config.webhook_url:
            await self.send_webhook(config.webhook_url, {
                'event': 'transaction.failed',
                'transaction': {
                    'tx_id': transaction.tx_id,
                    'chain': transaction.chain.value,
                    'error': transaction.error_message,
                    'timestamp': transaction.timestamp
                }
            })

    async def send_webhook(self, url: str, data: dict):
        """Send webhook notification"""
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, json=data) as response:
                    return await response.json()
            except Exception as e:
                print(f"Webhook failed: {str(e)}")

    def add_callback(self, tx_id: str, callback: Callable):
        """Add callback for transaction updates"""
        if tx_id not in self.callbacks:
            self.callbacks[tx_id] = []
        self.callbacks[tx_id].append(callback)
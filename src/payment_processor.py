# src/payment_processor.py
from web3 import Web3
from eth_typing import ChecksumAddress
from typing import Optional, Dict, List
import json
from dataclasses import dataclass
from enum import Enum
import time

# Standard ERC20 ABI for token interactions
ERC20_ABI = json.loads('''[
    {
        "constant": true,
        "inputs": [],
        "name": "name",
        "outputs": [{"name": "", "type": "string"}],
        "payable": false,
        "stateMutability": "view",
        "type": "function"
    },
    {
        "constant": true,
        "inputs": [],
        "name": "symbol",
        "outputs": [{"name": "", "type": "string"}],
        "payable": false,
        "stateMutability": "view",
        "type": "function"
    },
    {
        "constant": true,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "payable": false,
        "stateMutability": "view",
        "type": "function"
    },
    {
        "constant": true,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "payable": false,
        "stateMutability": "view",
        "type": "function"
    },
    {
        "constant": false,
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "payable": false,
        "stateMutability": "nonpayable",
        "type": "function"
    }
]''')


class PaymentStatus(Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class PaymentError(Exception):
    """Base class for payment-related errors"""
    pass


class InvalidAddressError(PaymentError):
    """Raised when an Ethereum address is invalid"""
    pass


class InsufficientFundsError(PaymentError):
    """Raised when wallet has insufficient token balance"""
    pass


class TransactionFailedError(PaymentError):
    """Raised when a transaction fails"""
    pass


@dataclass
class TokenInfo:
    address: ChecksumAddress
    name: str
    symbol: str
    decimals: int

    def __str__(self):
        return f"{self.name} ({self.symbol})"


@dataclass
class Transaction:
    tx_hash: str
    from_address: ChecksumAddress
    to_address: ChecksumAddress
    amount: float
    token: TokenInfo
    status: PaymentStatus
    timestamp: float
    error_message: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "tx_hash": self.tx_hash,
            "from_address": self.from_address,
            "to_address": self.to_address,
            "amount": self.amount,
            "token_symbol": self.token.symbol,
            "token_address": self.token.address,
            "status": self.status.value,
            "timestamp": self.timestamp,
            "error_message": self.error_message
        }


class ERC20PaymentProcessor:
    def __init__(self, provider_url: str):
        """
        Initialize payment processor with Ethereum provider URL
        e.g., 'https://mainnet.infura.io/v3/YOUR-PROJECT-ID'
        """
        self.w3 = Web3(Web3.HTTPProvider(provider_url))
        self.tokens: Dict[str, TokenInfo] = {}
        self.transactions: Dict[str, Transaction] = {}

    def add_token(self, token_address: str) -> TokenInfo:
        """Add and return info for an ERC20 token"""
        if not self.w3.is_address(token_address):
            raise InvalidAddressError(f"Invalid token address: {token_address}")

        checksum_address = self.w3.to_checksum_address(token_address)
        if checksum_address in self.tokens:
            return self.tokens[checksum_address]

        token_contract = self.w3.eth.contract(
            address=checksum_address,
            abi=ERC20_ABI
        )

        try:
            token_info = TokenInfo(
                address=checksum_address,
                name=token_contract.functions.name().call(),
                symbol=token_contract.functions.symbol().call(),
                decimals=token_contract.functions.decimals().call()
            )
            self.tokens[checksum_address] = token_info
            return token_info
        except Exception as e:
            raise PaymentError(f"Failed to load token info: {str(e)}")

    def validate_address(self, address: str) -> ChecksumAddress:
        """Validate and return checksum address"""
        if not self.w3.is_address(address):
            raise InvalidAddressError(f"Invalid Ethereum address: {address}")
        return self.w3.to_checksum_address(address)

    def get_token_balance(self, token_address: str, wallet_address: str) -> float:
        """Get token balance for address in human-readable form"""
        token = self.add_token(token_address)
        checksum_wallet = self.validate_address(wallet_address)

        token_contract = self.w3.eth.contract(
            address=token.address,
            abi=ERC20_ABI
        )

        try:
            balance_wei = token_contract.functions.balanceOf(checksum_wallet).call()
            return balance_wei / (10 ** token.decimals)
        except Exception as e:
            raise PaymentError(f"Failed to get balance: {str(e)}")

    def process_payment(
            self,
            private_key: str,
            to_address: str,
            amount: float,
            token_address: str
    ) -> Transaction:
        """
        Process an ERC20 token payment

        Parameters:
        private_key: Sender's private key
        to_address: Recipient's address
        amount: Human-readable token amount
        token_address: Token contract address
        """
        try:
            # Validate token and addresses
            token = self.add_token(token_address)
            from_address = self.w3.eth.account.from_key(private_key).address
            to_checksum = self.validate_address(to_address)

            # Convert amount to token units
            token_amount = int(amount * (10 ** token.decimals))

            # Check balance
            balance = self.get_token_balance(token_address, from_address)
            if balance < amount:
                raise InsufficientFundsError(
                    f"Insufficient {token.symbol} balance: {balance}"
                )

            # Prepare token transfer
            token_contract = self.w3.eth.contract(
                address=token.address,
                abi=ERC20_ABI
            )

            # Prepare transaction
            nonce = self.w3.eth.get_transaction_count(from_address)
            gas_price = self.w3.eth.gas_price

            transaction = token_contract.functions.transfer(
                to_checksum,
                token_amount
            ).build_transaction({
                'chainId': self.w3.eth.chain_id,
                'gas': 100000,  # Estimate this in production
                'gasPrice': gas_price,
                'nonce': nonce,
            })

            # Sign and send transaction
            signed_txn = self.w3.eth.account.sign_transaction(
                transaction,
                private_key
            )
            tx_hash = self.w3.eth.send_raw_transaction(signed_txn.rawTransaction)

            # Wait for transaction receipt
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

            # Create transaction record
            tx = Transaction(
                tx_hash=receipt['transactionHash'].hex(),
                from_address=from_address,
                to_address=to_checksum,
                amount=amount,
                token=token,
                status=PaymentStatus.COMPLETED if receipt['status'] == 1
                else PaymentStatus.FAILED,
                timestamp=time.time()
            )

            self.transactions[tx.tx_hash] = tx

            if receipt['status'] != 1:
                tx.error_message = "Transaction reverted"
                raise TransactionFailedError("Transaction reverted by network")

            return tx

        except Exception as e:
            error_msg = str(e)
            tx = Transaction(
                tx_hash=tx_hash.hex() if 'tx_hash' in locals() else "failed",
                from_address=from_address if 'from_address' in locals() else "",
                to_address=to_checksum if 'to_checksum' in locals() else "",
                amount=amount,
                token=token if 'token' in locals() else None,
                status=PaymentStatus.FAILED,
                timestamp=time.time(),
                error_message=error_msg
            )
            self.transactions[tx.tx_hash] = tx
            raise TransactionFailedError(error_msg)

    def get_transaction(self, tx_hash: str) -> Optional[Transaction]:
        """Get transaction details by hash"""
        return self.transactions.get(tx_hash)

    def get_address_transactions(self, address: str) -> List[Transaction]:
        """Get all transactions involving an address"""
        checksum_address = self.validate_address(address)
        return [
            tx for tx in self.transactions.values()
            if tx.from_address == checksum_address or
               tx.to_address == checksum_address
        ]
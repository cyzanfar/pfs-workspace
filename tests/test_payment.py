# tests/test_payment.py
import pytest
from unittest.mock import Mock, patch
from web3 import Web3
from eth_account import Account
from src.payment_processor import (
    ERC20PaymentProcessor, PaymentError, InvalidAddressError,
    InsufficientFundsError, TransactionFailedError, TokenInfo
)


@pytest.fixture
def w3():
    return Web3(Web3.HTTPProvider('https://mainnet.infura.io/v3/YOUR-PROJECT-ID'))


@pytest.fixture
def processor(w3):
    return ERC20PaymentProcessor('https://mainnet.infura.io/v3/YOUR-PROJECT-ID')


@pytest.fixture
def test_token():
    return {
        'address': '0x1234567890123456789012345678901234567890',
        'name': 'Test Token',
        'symbol': 'TEST',
        'decimals': 18
    }


@pytest.fixture
def test_wallet():
    account = Account.create()
    return {
        'address': account.address,
        'private_key': account.key.hex()
    }


class TestERC20PaymentProcessor:
    """Test suite for ERC20 payment processing"""

    def test_address_validation(self, processor):
        """Test Ethereum address validation"""
        # Valid address
        valid_address = "0x742d35Cc6634C0532925a3b844Bc454e4438f44e"
        assert processor.validate_address(valid_address) == valid_address

        # Invalid addresses
        with pytest.raises(InvalidAddressError):
            processor.validate_address("invalid")

        with pytest.raises(InvalidAddressError):
            processor.validate_address("0x123")  # Too short

        with pytest.raises(InvalidAddressError):
            processor.validate_address("742d35Cc6634C0532925a3b844Bc454e4438f44e")  # Missing 0x

    @patch('web3.eth.Contract')
    def test_add_token(self, mock_contract, processor, test_token):
        """Test token contract loading and validation"""
        # Mock token contract calls
        mock_contract.return_value.functions.name.return_value.call.return_value = test_token['name']
        mock_contract.return_value.functions.symbol.return_value.call.return_value = test_token['symbol']
        mock_contract.return_value.functions.decimals.return_value.call.return_value = test_token['decimals']

        token_info = processor.add_token(test_token['address'])

        assert isinstance(token_info, TokenInfo)
        assert token_info.name == test_token['name']
        assert token_info.symbol == test_token['symbol']
        assert token_info.decimals == test_token['decimals']

    @patch('web3.eth.Contract')
    def test_token_balance(self, mock_contract, processor, test_token, test_wallet):
        """Test token balance checking"""
        # Mock balance call
        balance_wei = 1000000000000000000  # 1 token
        mock_contract.return_value.functions.balanceOf.return_value.call.return_value = balance_wei

        balance = processor.get_token_balance(
            test_token['address'],
            test_wallet['address']
        )

        assert balance == 1.0  # Should convert from wei

    @patch('web3.eth.Contract')
    @patch('web3.eth.Eth')
    def test_payment_processing(self, mock_eth, mock_contract, processor, test_token, test_wallet):
        """Test full payment processing"""
        # Mock necessary web3 calls
        mock_eth.chain_id = 1
        mock_eth.gas_price = 20000000000
        mock_eth.get_transaction_count.return_value = 0

        # Mock contract calls
        mock_contract.return_value.functions.balanceOf.return_value.call.return_value = 2000000000000000000  # 2 tokens
        mock_contract.return_value.functions.transfer.return_value.build_transaction.return_value = {
            'to': test_token['address'],
            'data': '0x',
            'gas': 100000,
            'gasPrice': 20000000000,
            'nonce': 0,
            'chainId': 1
        }

        # Mock transaction sending
        tx_hash = '0x' + '1' * 64
        mock_eth.send_raw_transaction.return_value = tx_hash
        mock_eth.wait_for_transaction_receipt.return_value = {
            'status': 1,
            'transactionHash': bytes.fromhex('1' * 64),
            'blockNumber': 1000000
        }

        # Process payment
        tx = processor.process_payment(
            test_wallet['private_key'],
            "0x742d35Cc6634C0532925a3b844Bc454e4438f44e",
            1.0,
            test_token['address']
        )

        assert tx.tx_hash == tx_hash
        assert tx.amount == 1.0
        assert tx.status.value == "completed"

    def test_error_handling(self, processor, test_token, test_wallet):
        """Test error handling scenarios"""
        # Invalid token address
        with pytest.raises(InvalidAddressError):
            processor.add_token("invalid")

        # Invalid recipient
        with pytest.raises(InvalidAddressError):
            processor.process_payment(
                test_wallet['private_key'],
                "invalid",
                1.0,
                test_token['address']
            )

        # Invalid amount
        with pytest.raises(PaymentError):
            processor.process_payment(
                test_wallet['private_key'],
                "0x742d35Cc6634C0532925a3b844Bc454e4438f44e",
                -1.0,
                test_token['address']
            )


class TestPaymentCLI:
    """Test suite for payment CLI interface"""

    @pytest.fixture
    def runner(self):
        from click.testing import CliRunner
        return CliRunner()

    def test_balance_command(self, runner, test_token, test_wallet):
        """Test balance checking command"""
        from src.payment_cli import payment

        result = runner.invoke(payment, [
            'balance',
            '--token', test_token['address'],
            '--address', test_wallet['address']
        ])

        assert result.exit_code == 0
        assert test_token['symbol'] in result.output

    def test_send_command(self, runner, test_token, test_wallet):
        """Test token sending command"""
        from src.payment_cli import payment

        result = runner.invoke(payment, [
            'send',
            '--from-key', test_wallet['private_key'],
            '--to', "0x742d35Cc6634C0532925a3b844Bc454e4438f44e",
            '--amount', '1.0',
            '--token', test_token['address']
        ])

        assert result.exit_code == 0
        assert "Transaction successful" in result.output

    def test_transaction_history(self, runner, test_wallet):
        """Test transaction history command"""
        from src.payment_cli import payment

        result = runner.invoke(payment, [
            'history',
            '--address', test_wallet['address']
        ])

        assert result.exit_code == 0
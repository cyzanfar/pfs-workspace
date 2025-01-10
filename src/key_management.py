# src/key_management.py
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
import json
import os
from pathlib import Path
from typing import Dict, Optional, List
import secrets
import time
from datetime import datetime, timedelta
from eth_account import Account
import asyncio
import aiofiles
import logging


class KeyManagementError(Exception):
    """Base class for key management errors"""
    pass


class KeyNotFoundError(KeyManagementError):
    """Raised when a key is not found"""
    pass


class KeyRotationError(KeyManagementError):
    """Raised when key rotation fails"""
    pass


class KeyManagement:
    def __init__(self, storage_path: str = "secure/keys/",
                 master_key_path: str = "secure/master.key"):
        self.storage_path = Path(storage_path)
        self.master_key_path = Path(master_key_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.master_key_path.parent.mkdir(parents=True, exist_ok=True)

        # Set up logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger("KeyManagement")

        # Initialize or load master key
        self._init_master_key()

        # Setup encryption
        self.fernet = Fernet(self.master_key)

        # Initialize backup scheduler
        self._setup_backup_scheduler()

    def _init_master_key(self):
        """Initialize or load master encryption key"""
        if self.master_key_path.exists():
            with open(self.master_key_path, 'rb') as f:
                self.master_key = f.read()
        else:
            self.master_key = Fernet.generate_key()
            with open(self.master_key_path, 'wb') as f:
                f.write(self.master_key)
            # Set restrictive permissions
            os.chmod(self.master_key_path, 0o600)

    def _derive_key(self, password: str, salt: Optional[bytes] = None) -> tuple:
        """Derive encryption key from password"""
        if salt is None:
            salt = os.urandom(16)
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
            backend=default_backend()
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return Fernet(key), salt

    async def store_key(self, key_id: str, private_key: str,
                        password: str) -> dict:
        """Store encrypted private key"""
        try:
            # Generate salt and derive encryption key
            fernet, salt = self._derive_key(password)

            # Prepare key data
            key_data = {
                'private_key': private_key,
                'created_at': datetime.now().isoformat(),
                'last_rotated': None,
                'salt': base64.b64encode(salt).decode(),
                'version': 1
            }

            # Encrypt key data
            encrypted_data = fernet.encrypt(json.dumps(key_data).encode())

            # Store encrypted key
            key_path = self.storage_path / f"{key_id}.key"
            async with aiofiles.open(key_path, 'wb') as f:
                await f.write(encrypted_data)

            # Set restrictive permissions
            os.chmod(key_path, 0o600)

            return {
                'key_id': key_id,
                'created_at': key_data['created_at'],
                'version': key_data['version']
            }

        except Exception as e:
            raise KeyManagementError(f"Failed to store key: {str(e)}")

    async def retrieve_key(self, key_id: str, password: str) -> str:
        """Retrieve and decrypt private key"""
        try:
            key_path = self.storage_path / f"{key_id}.key"

            if not key_path.exists():
                raise KeyNotFoundError(f"Key not found: {key_id}")

            # Read encrypted data
            async with aiofiles.open(key_path, 'rb') as f:
                encrypted_data = await f.read()

            # Load encrypted key data
            decrypted_data = self.fernet.decrypt(encrypted_data)
            key_data = json.loads(decrypted_data)

            # Derive key with stored salt
            salt = base64.b64decode(key_data['salt'])
            fernet, _ = self._derive_key(password, salt)

            return key_data['private_key']

        except KeyNotFoundError:
            raise
        except Exception as e:
            raise KeyManagementError(f"Failed to retrieve key: {str(e)}")

    async def rotate_key(self, key_id: str, old_password: str,
                         new_password: str) -> dict:
        """Rotate key with new password"""
        try:
            # Retrieve current key
            private_key = await self.retrieve_key(key_id, old_password)

            # Generate new salt and key
            new_fernet, new_salt = self._derive_key(new_password)

            # Update key data
            key_data = {
                'private_key': private_key,
                'created_at': datetime.now().isoformat(),
                'last_rotated': datetime.now().isoformat(),
                'salt': base64.b64encode(new_salt).decode(),
                'version': 2  # Increment version
            }

            # Encrypt with new key
            encrypted_data = new_fernet.encrypt(json.dumps(key_data).encode())

            # Store updated key
            key_path = self.storage_path / f"{key_id}.key"
            async with aiofiles.open(key_path, 'wb') as f:
                await f.write(encrypted_data)

            return {
                'key_id': key_id,
                'rotated_at': key_data['last_rotated'],
                'version': key_data['version']
            }

        except Exception as e:
            raise KeyRotationError(f"Failed to rotate key: {str(e)}")

    def _setup_backup_scheduler(self):
        """Setup automatic backup scheduling"""

        async def backup_scheduler():
            while True:
                try:
                    await self.create_backup()
                    # Wait for 24 hours
                    await asyncio.sleep(86400)
                except Exception as e:
                    self.logger.error(f"Backup failed: {str(e)}")
                    # Wait for 1 hour before retry
                    await asyncio.sleep(3600)

        # Start backup scheduler
        asyncio.create_task(backup_scheduler())

    async def create_backup(self) -> str:
        """Create encrypted backup of all keys"""
        try:
            # Prepare backup data
            backup_data = {
                'timestamp': datetime.now().isoformat(),
                'keys': {}
            }

            # Collect all keys
            for key_file in self.storage_path.glob('*.key'):
                async with aiofiles.open(key_file, 'rb') as f:
                    encrypted_data = await f.read()
                backup_data['keys'][key_file.stem] = base64.b64encode(encrypted_data).decode()

            # Encrypt backup data
            encrypted_backup = self.fernet.encrypt(json.dumps(backup_data).encode())

            # Generate backup filename
            backup_path = Path("secure/backups/")
            backup_path.mkdir(parents=True, exist_ok=True)
            backup_file = backup_path / f"backup_{int(time.time())}.enc"

            # Save backup
            async with aiofiles.open(backup_file, 'wb') as f:
                await f.write(encrypted_backup)

            # Set restrictive permissions
            os.chmod(backup_file, 0o600)

            return str(backup_file)

        except Exception as e:
            raise KeyManagementError(f"Failed to create backup: {str(e)}")

    async def restore_from_backup(self, backup_path: str) -> dict:
        """Restore keys from backup"""
        try:
            # Read backup file
            async with aiofiles.open(backup_path, 'rb') as f:
                encrypted_backup = await f.read()

            # Decrypt backup
            decrypted_backup = self.fernet.decrypt(encrypted_backup)
            backup_data = json.loads(decrypted_backup)

            restored_keys = []

            # Restore each key
            for key_id, encrypted_key in backup_data['keys'].items():
                key_data = base64.b64decode(encrypted_key)
                key_path = self.storage_path / f"{key_id}.key"

                async with aiofiles.open(key_path, 'wb') as f:
                    await f.write(key_data)

                # Set permissions
                os.chmod(key_path, 0o600)
                restored_keys.append(key_id)

            return {
                'backup_timestamp': backup_data['timestamp'],
                'restored_keys': restored_keys
            }

        except Exception as e:
            raise KeyManagementError(f"Failed to restore backup: {str(e)}")

    async def list_keys(self) -> List[dict]:
        """List all stored keys"""
        keys = []
        for key_file in self.storage_path.glob('*.key'):
            try:
                async with aiofiles.open(key_file, 'rb') as f:
                    encrypted_data = await f.read()

                # Decrypt metadata only
                decrypted_data = self.fernet.decrypt(encrypted_data)
                key_data = json.loads(decrypted_data)

                keys.append({
                    'key_id': key_file.stem,
                    'created_at': key_data['created_at'],
                    'last_rotated': key_data['last_rotated'],
                    'version': key_data['version']
                })
            except Exception as e:
                self.logger.error(f"Error reading key {key_file}: {str(e)}")

        return keys

    async def generate_new_key(self, password: str) -> dict:
        """Generate new key pair and store securely"""
        # Generate new Ethereum account
        account = Account.create()

        # Generate key ID
        key_id = f"key_{secrets.token_hex(8)}"

        # Store private key
        result = await self.store_key(
            key_id=key_id,
            private_key=account.key.hex(),
            password=password
        )

        result['address'] = account.address
        return result
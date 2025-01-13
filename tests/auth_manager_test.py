import unittest
from unittest.mock import Mock, patch
from datetime import datetime, timedelta
import jwt
from auth_manager import (
    AuthenticationManager,
    AuthenticationError,
    AuthorizationError,
    TokenType
)


class TestAuthenticationManager(unittest.TestCase):
    def setUp(self):
        self.auth_manager = AuthenticationManager(secret_key="test-secret-key")
        self.test_username = "testuser"
        self.test_password = "testpass123"

    def test_user_registration(self):
        user_id = self.auth_manager.register_user(self.test_username, self.test_password)
        self.assertIn(user_id, self.auth_manager.users)
        self.assertEqual(self.auth_manager.users[user_id].username, self.test_username)

    def test_duplicate_registration(self):
        self.auth_manager.register_user(self.test_username, self.test_password)
        with self.assertRaises(AuthenticationError):
            self.auth_manager.register_user(self.test_username, self.test_password)

    def test_authentication(self):
        user_id = self.auth_manager.register_user(self.test_username, self.test_password)
        tokens = self.auth_manager.authenticate(self.test_username, self.test_password)

        self.assertIn('access_token', tokens)
        self.assertIn('refresh_token', tokens)

        # Verify tokens are valid
        access_payload = jwt.decode(tokens['access_token'], "test-secret-key", algorithms=["HS256"])
        self.assertEqual(access_payload['user_id'], user_id)
        self.assertEqual(access_payload['type'], TokenType.ACCESS.value)

    def test_failed_authentication(self):
        self.auth_manager.register_user(self.test_username, self.test_password)
        with self.assertRaises(AuthenticationError):
            self.auth_manager.authenticate(self.test_username, "wrongpass")

    def test_account_lockout(self):
        user_id = self.auth_manager.register_user(self.test_username, self.test_password)

        # Attempt multiple failed logins
        for _ in range(5):
            with self.assertRaises(AuthenticationError):
                self.auth_manager.authenticate(self.test_username, "wrongpass")

        # Verify account is locked
        self.assertFalse(self.auth_manager.users[user_id].is_active)

        # Verify locked account cannot authenticate
        with self.assertRaises(AuthenticationError):
            self.auth_manager.authenticate(self.test_username, self.test_password)
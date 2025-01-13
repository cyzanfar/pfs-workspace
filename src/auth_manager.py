from typing import Dict, List, Optional, Set
from datetime import datetime, timedelta
import jwt
import bcrypt
import logging
import argparse
import json
from dataclasses import dataclass
from enum import Enum
import uuid
import threading


class AuthenticationError(Exception):
    """Base class for authentication-related exceptions."""
    pass


class AuthorizationError(Exception):
    """Base class for authorization-related exceptions."""
    pass


@dataclass
class User:
    id: str
    username: str
    password_hash: bytes
    roles: Set[str]
    created_at: datetime
    last_login: Optional[datetime] = None
    is_active: bool = True
    failed_login_attempts: int = 0


class TokenType(Enum):
    ACCESS = "access"
    REFRESH = "refresh"


@dataclass
class Token:
    token_id: str
    user_id: str
    token_type: TokenType
    expires_at: datetime
    is_revoked: bool = False


class SecurityMetrics:
    def __init__(self):
        self.successful_logins = 0
        self.failed_logins = 0
        self.token_refreshes = 0
        self.unauthorized_access_attempts = 0
        self.user_registrations = 0
        self.security_events: List[Dict] = []

    def record_event(self, event_type: str, details: Dict):
        self.security_events.append({
            'timestamp': datetime.now().isoformat(),
            'type': event_type,
            'details': details
        })


class AuthenticationManager:
    def __init__(self, secret_key: str, token_expiry: int = 3600):
        self.secret_key = secret_key
        self.token_expiry = token_expiry
        self.users: Dict[str, User] = {}
        self.tokens: Dict[str, Token] = {}
        self.roles: Dict[str, Set[str]] = {}  # role -> permissions mapping
        self.metrics = SecurityMetrics()
        self.lock = threading.Lock()
        self.logger = logging.getLogger(__name__)

        self._setup_logging()
        self._initialize_default_roles()

    def _setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s [%(levelname)s] %(message)s',
            handlers=[
                logging.FileHandler('auth.log'),
                logging.StreamHandler()
            ]
        )

    def _initialize_default_roles(self):
        """Initialize default roles and permissions."""
        self.roles = {
            'admin': {'user:create', 'user:read', 'user:update', 'user:delete',
                      'role:create', 'role:read', 'role:update', 'role:delete'},
            'user': {'user:read'},
            'moderator': {'user:read', 'user:update'}
        }

    def register_user(self, username: str, password: str, roles: Optional[Set[str]] = None) -> str:
        """Register a new user with specified roles."""
        with self.lock:
            if any(user.username == username for user in self.users.values()):
                raise AuthenticationError("Username already exists")

            user_id = str(uuid.uuid4())
            password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt())

            user = User(
                id=user_id,
                username=username,
                password_hash=password_hash,
                roles=roles or {'user'},
                created_at=datetime.now()
            )

            self.users[user_id] = user
            self.metrics.user_registrations += 1
            self.metrics.record_event('user_registration', {'user_id': user_id})
            self.logger.info(f"User registered: {username}")

            return user_id

    def authenticate(self, username: str, password: str) -> Dict[str, str]:
        """Authenticate user and return access and refresh tokens."""
        user = self._get_user_by_username(username)

        if not user or not user.is_active:
            self._handle_failed_login(username)
            raise AuthenticationError("Invalid credentials")

        if not bcrypt.checkpw(password.encode(), user.password_hash):
            self._handle_failed_login(username)
            raise AuthenticationError("Invalid credentials")

        # Reset failed login attempts on successful login
        user.failed_login_attempts = 0
        user.last_login = datetime.now()

        access_token = self._generate_token(user.id, TokenType.ACCESS)
        refresh_token = self._generate_token(user.id, TokenType.REFRESH)

        self.metrics.successful_logins += 1
        self.metrics.record_event('successful_login', {'user_id': user.id})
        self.logger.info(f"Successful login: {username}")

        return {
            'access_token': access_token,
            'refresh_token': refresh_token
        }

    def _handle_failed_login(self, username: str):
        """Handle failed login attempt."""
        user = self._get_user_by_username(username)
        if user:
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= 5:
                user.is_active = False
                self.logger.warning(f"Account locked: {username}")

        self.metrics.failed_logins += 1
        self.metrics.record_event('failed_login', {'username': username})
        self.logger.warning(f"Failed login attempt: {username}")

    def refresh_token(self, refresh_token: str) -> str:
        """Generate new access token using refresh token."""
        try:
            payload = jwt.decode(refresh_token, self.secret_key, algorithms=["HS256"])
            token_id = payload.get('token_id')

            if not token_id or token_id not in self.tokens:
                raise AuthenticationError("Invalid refresh token")

            token = self.tokens[token_id]
            if token.is_revoked or token.expires_at < datetime.now():
                raise AuthenticationError("Token expired or revoked")

            new_access_token = self._generate_token(token.user_id, TokenType.ACCESS)

            self.metrics.token_refreshes += 1
            self.metrics.record_event('token_refresh', {'user_id': token.user_id})

            return new_access_token

        except jwt.InvalidTokenError:
            raise AuthenticationError("Invalid refresh token")

    def validate_token(self, token: str) -> Dict:
        """Validate access token and return payload."""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=["HS256"])
            token_id = payload.get('token_id')

            if not token_id or token_id not in self.tokens:
                raise AuthenticationError("Invalid token")

            token_obj = self.tokens[token_id]
            if token_obj.is_revoked or token_obj.expires_at < datetime.now():
                raise AuthenticationError("Token expired or revoked")

            return payload

        except jwt.InvalidTokenError:
            raise AuthenticationError("Invalid token")

    def check_permission(self, user_id: str, required_permission: str) -> bool:
        """Check if user has the required permission."""
        if user_id not in self.users:
            return False

        user = self.users[user_id]
        user_permissions = set()

        for role in user.roles:
            if role in self.roles:
                user_permissions.update(self.roles[role])

        has_permission = required_permission in user_permissions

        if not has_permission:
            self.metrics.unauthorized_access_attempts += 1
            self.metrics.record_event('unauthorized_access', {
                'user_id': user_id,
                'required_permission': required_permission
            })

        return has_permission

    def _generate_token(self, user_id: str, token_type: TokenType) -> str:
        """Generate JWT token."""
        token_id = str(uuid.uuid4())
        expires_at = datetime.now() + timedelta(seconds=self.token_expiry)

        token = Token(
            token_id=token_id,
            user_id=user_id,
            token_type=token_type,
            expires_at=expires_at
        )

        self.tokens[token_id] = token

        payload = {
            'token_id': token_id,
            'user_id': user_id,
            'type': token_type.value,
            'exp': expires_at.timestamp()
        }

        return jwt.encode(payload, self.secret_key, algorithm="HS256")

    def _get_user_by_username(self, username: str) -> Optional[User]:
        """Get user by username."""
        return next(
            (user for user in self.users.values() if user.username == username),
            None
        )

    def revoke_token(self, token_id: str):
        """Revoke a specific token."""
        if token_id in self.tokens:
            self.tokens[token_id].is_revoked = True
            self.logger.info(f"Token revoked: {token_id}")

    def get_user_info(self, user_id: str) -> Dict:
        """Get user information."""
        if user_id not in self.users:
            raise AuthenticationError("User not found")

        user = self.users[user_id]
        return {
            'id': user.id,
            'username': user.username,
            'roles': list(user.roles),
            'created_at': user.created_at.isoformat(),
            'last_login': user.last_login.isoformat() if user.last_login else None,
            'is_active': user.is_active
        }

    def get_metrics(self) -> Dict:
        """Get security metrics."""
        return {
            'successful_logins': self.metrics.successful_logins,
            'failed_logins': self.metrics.failed_logins,
            'token_refreshes': self.metrics.token_refreshes,
            'unauthorized_access_attempts': self.metrics.unauthorized_access_attempts,
            'user_registrations': self.metrics.user_registrations,
            'security_events': self.metrics.security_events
        }


def main():
    """CLI entry point for the AuthenticationManager."""
    parser = argparse.ArgumentParser(description='Authentication Manager CLI')
    parser.add_argument('command', choices=['register', 'info', 'metrics'])
    parser.add_argument('--username', help='Username for registration')
    parser.add_argument('--password', help='Password for registration')
    parser.add_argument('--user-id', help='User ID for info command')
    args = parser.parse_args()

    auth_manager = AuthenticationManager(secret_key="your-secret-key")

    if args.command == 'register' and args.username and args.password:
        user_id = auth_manager.register_user(args.username, args.password)
        print(json.dumps({'user_id': user_id}, indent=2))
    elif args.command == 'info' and args.user_id:
        print(json.dumps(auth_manager.get_user_info(args.user_id), indent=2))
    elif args.command == 'metrics':
        print(json.dumps(auth_manager.get_metrics(), indent=2))


if __name__ == '__main__':
    main()
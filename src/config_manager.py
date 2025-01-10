# src/config_manager.py
import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Any, Optional, Set, Callable
import json
import logging
import os
from pathlib import Path
import yaml


class ConfigScope(Enum):
    GLOBAL = "global"
    SECURITY = "security"
    KEYS = "key_management"
    AUDIT = "audit"
    RESILIENCE = "resilience"


@dataclass
class ConfigVersion:
    version: int
    timestamp: datetime
    scope: ConfigScope
    changes: Dict[str, Any]
    author: str
    comment: Optional[str] = None


@dataclass
class ConfigValidator:
    key: str
    validator: Callable[[Any], bool]
    error_message: str


class ConfigurationManager:
    def __init__(self, config_path: str = "config"):
        # Initialize logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger("ConfigurationManager")

        # Setup paths
        self.config_path = Path(config_path)
        self.config_path.mkdir(parents=True, exist_ok=True)

        # Configuration storage
        self.configs: Dict[ConfigScope, Dict[str, Any]] = {
            scope: {} for scope in ConfigScope
        }

        # Version history
        self.version_history: List[ConfigVersion] = []
        self.current_version = 0

        # Validation rules
        self.validators: Dict[str, ConfigValidator] = {}

        # Component update callbacks
        self.update_callbacks: Dict[ConfigScope, List[Callable]] = {
            scope: [] for scope in ConfigScope
        }

        # Initialize default configurations
        self._init_default_configs()

        # Setup validators
        self._setup_validators()

    def _init_default_configs(self):
        """Initialize default configurations"""
        defaults = {
            ConfigScope.GLOBAL: {
                'environment': 'production',
                'debug_mode': False,
                'log_level': 'INFO',
            },
            ConfigScope.SECURITY: {
                'max_login_attempts': 5,
                'session_timeout': 3600,
                'min_password_length': 12,
                'require_mfa': True,
            },
            ConfigScope.KEYS: {
                'key_rotation_days': 90,
                'min_key_length': 2048,
                'backup_enabled': True,
                'backup_frequency': 24,
            },
            ConfigScope.AUDIT: {
                'retention_days': 365,
                'max_log_size': 10485760,
                'compression_enabled': True,
                'encrypt_logs': True,
            },
            ConfigScope.RESILIENCE: {
                'health_check_interval': 60,
                'failure_threshold': 5,
                'recovery_timeout': 300,
                'circuit_breaker_enabled': True,
            }
        }

        for scope, config in defaults.items():
            self.configs[scope].update(config)

    def _setup_validators(self):
        """Setup configuration validators"""
        # Global validators
        self.validators.update({
            'log_level': ConfigValidator(
                'log_level',
                lambda x: x in ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                "Invalid log level"
            ),
            'debug_mode': ConfigValidator(
                'debug_mode',
                lambda x: isinstance(x, bool),
                "Debug mode must be boolean"
            )
        })

        # Security validators
        self.validators.update({
            'max_login_attempts': ConfigValidator(
                'max_login_attempts',
                lambda x: isinstance(x, int) and x > 0,
                "Login attempts must be positive integer"
            ),
            'session_timeout': ConfigValidator(
                'session_timeout',
                lambda x: isinstance(x, int) and x > 0,
                "Session timeout must be positive integer"
            ),
            'min_password_length': ConfigValidator(
                'min_password_length',
                lambda x: isinstance(x, int) and 8 <= x <= 128,
                "Password length must be between 8 and 128"
            )
        })

        # Key management validators
        self.validators.update({
            'key_rotation_days': ConfigValidator(
                'key_rotation_days',
                lambda x: isinstance(x, int) and x > 0,
                "Key rotation days must be positive integer"
            ),
            'min_key_length': ConfigValidator(
                'min_key_length',
                lambda x: isinstance(x, int) and x in [2048, 4096, 8192],
                "Invalid key length"
            )
        })

        # Audit validators
        self.validators.update({
            'retention_days': ConfigValidator(
                'retention_days',
                lambda x: isinstance(x, int) and x > 0,
                "Retention days must be positive integer"
            ),
            'max_log_size': ConfigValidator(
                'max_log_size',
                lambda x: isinstance(x, int) and x > 0,
                "Max log size must be positive integer"
            )
        })

        # Resilience validators
        self.validators.update({
            'health_check_interval': ConfigValidator(
                'health_check_interval',
                lambda x: isinstance(x, int) and x > 0,
                "Health check interval must be positive integer"
            ),
            'failure_threshold': ConfigValidator(
                'failure_threshold',
                lambda x: isinstance(x, int) and x > 0,
                "Failure threshold must be positive integer"
            )
        })

    def register_update_callback(self,
                                 scope: ConfigScope,
                                 callback: Callable[[Dict[str, Any]], None]):
        """Register callback for configuration updates"""
        self.update_callbacks[scope].append(callback)

    async def update_config(self,
                            scope: ConfigScope,
                            updates: Dict[str, Any],
                            author: str,
                            comment: Optional[str] = None) -> ConfigVersion:
        """Update configuration with validation"""
        config = self.configs[scope]

        # Validate updates
        for key, value in updates.items():
            if key in self.validators:
                validator = self.validators[key]
                if not validator.validator(value):
                    raise ValueError(f"{key}: {validator.error_message}")

        # Apply updates
        config.update(updates)

        # Create new version
        self.current_version += 1
        version = ConfigVersion(
            version=self.current_version,
            timestamp=datetime.now(),
            scope=scope,
            changes=updates,
            author=author,
            comment=comment
        )
        self.version_history.append(version)

        # Save configuration
        await self._save_config(scope)

        # Notify components
        await self._notify_components(scope, config)

        return version

    async def _save_config(self, scope: ConfigScope):
        """Save configuration to file"""
        config_file = self.config_path / f"{scope.value}.yaml"

        config_data = {
            'version': self.current_version,
            'updated_at': datetime.now().isoformat(),
            'config': self.configs[scope]
        }

        with open(config_file, 'w') as f:
            yaml.dump(config_data, f)

    async def _notify_components(self,
                                 scope: ConfigScope,
                                 config: Dict[str, Any]):
        """Notify components of configuration updates"""
        for callback in self.update_callbacks[scope]:
            try:
                await callback(config)
            except Exception as e:
                self.logger.error(
                    f"Error notifying component of config update: {str(e)}"
                )

    def get_config(self, scope: ConfigScope) -> Dict[str, Any]:
        """Get current configuration for scope"""
        return self.configs[scope].copy()

    def get_version_history(self,
                            scope: Optional[ConfigScope] = None) -> List[ConfigVersion]:
        """Get configuration version history"""
        if scope:
            return [v for v in self.version_history if v.scope == scope]
        return self.version_history

    async def load_configs(self):
        """Load configurations from files"""
        for scope in ConfigScope:
            config_file = self.config_path / f"{scope.value}.yaml"

            if config_file.exists():
                try:
                    with open(config_file) as f:
                        data = yaml.safe_load(f)

                    if 'config' in data:
                        # Validate loaded config
                        for key, value in data['config'].items():
                            if key in self.validators:
                                validator = self.validators[key]
                                if not validator.validator(value):
                                    raise ValueError(
                                        f"{key}: {validator.error_message}"
                                    )

                        self.configs[scope].update(data['config'])

                        if 'version' in data:
                            self.current_version = max(
                                self.current_version,
                                data['version']
                            )

                except Exception as e:
                    self.logger.error(
                        f"Error loading config {scope.value}: {str(e)}"
                    )

    def validate_config(self,
                        scope: ConfigScope,
                        config: Dict[str, Any]) -> List[str]:
        """Validate configuration values"""
        errors = []

        for key, value in config.items():
            if key in self.validators:
                validator = self.validators[key]
                if not validator.validator(value):
                    errors.append(f"{key}: {validator.error_message}")

        return errors

    def get_config_schema(self, scope: ConfigScope) -> Dict[str, Any]:
        """Get configuration schema for scope"""
        schema = {}

        for key, validator in self.validators.items():
            if key in self.configs[scope]:
                schema[key] = {
                    'type': type(self.configs[scope][key]).__name__,
                    'description': validator.error_message,
                    'current_value': self.configs[scope][key]
                }

        return schema

    async def export_configs(self, output_path: str):
        """Export all configurations"""
        export_data = {
            'version': self.current_version,
            'exported_at': datetime.now().isoformat(),
            'configs': {
                scope.value: config
                for scope, config in self.configs.items()
            }
        }

        with open(output_path, 'w') as f:
            yaml.dump(export_data, f)
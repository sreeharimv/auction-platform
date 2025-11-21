"""
Configuration Management Module for Palace Premier League Auction Platform

This module provides centralized configuration management with:
- Configuration loading and validation
- Password hashing and verification using bcrypt
- Environment variable management
- Automatic configuration backups
- Audit logging for configuration changes
"""

import os
import json
import bcrypt
import secrets
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ConfigManager:
    """Manages configuration loading, validation, and persistence"""
    
    CONFIG_FILE = "config.json"
    BACKUP_DIR = "backups"
    MAX_BACKUPS = 10
    
    # Configuration schema for validation
    CONFIG_SCHEMA = {
        "tournament": {
            "name": {"type": str, "required": True, "min_length": 1},
            "logo": {"type": str, "required": True}
        },
        "teams": {
            "count": {"type": int, "required": True, "min": 2, "max": 20},
            "names": {"type": list, "required": True, "min_length": 2},
            "budget": {"type": int, "required": True, "min": 1000000},
            "min_players": {"type": int, "required": True, "min": 6, "max": 15},
            "max_players": {"type": int, "required": True, "min": 8, "max": 20}
        },
        "auction": {
            "base_price": {"type": int, "required": True, "min": 100000},
            "currency": {"type": str, "required": True, "min_length": 1},
            "increments": {"type": list, "required": True, "length": 3}
        }
    }
    
    def __init__(self):
        """Initialize ConfigManager and ensure backup directory exists"""
        Path(self.BACKUP_DIR).mkdir(exist_ok=True)
    
    def load_config(self) -> Dict:
        """Load and validate configuration from config.json"""
        try:
            if not os.path.exists(self.CONFIG_FILE):
                logger.warning(f"{self.CONFIG_FILE} not found, creating default configuration")
                return self._get_default_config()
            
            with open(self.CONFIG_FILE, 'r') as f:
                config = json.load(f)
            
            # Validate configuration
            is_valid, errors = self.validate_config(config)
            if not is_valid:
                logger.error(f"Configuration validation failed: {errors}")
                logger.warning("Using default configuration")
                return self._get_default_config()
            
            return config
            
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in {self.CONFIG_FILE}: {e}")
            logger.warning("Using default configuration")
            return self._get_default_config()
        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
            return self._get_default_config()
    
    def save_config(self, config: Dict) -> bool:
        """Save configuration with validation and backup"""
        try:
            # Validate before saving
            is_valid, errors = self.validate_config(config)
            if not is_valid:
                logger.error(f"Cannot save invalid configuration: {errors}")
                return False
            
            # Create backup before modifying
            if os.path.exists(self.CONFIG_FILE):
                self.create_backup()
            
            # Save configuration
            with open(self.CONFIG_FILE, 'w') as f:
                json.dump(config, f, indent=2)
            
            logger.info("Configuration saved successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error saving configuration: {e}")
            return False
    
    def validate_config(self, config: Dict) -> Tuple[bool, List[str]]:
        """Validate configuration structure and values"""
        errors = []
        
        if not isinstance(config, dict):
            return False, ["Configuration must be a JSON object"]
        
        # Validate each section
        for section, schema in self.CONFIG_SCHEMA.items():
            if section not in config:
                errors.append(f"Missing required section: {section}")
                continue
            
            section_data = config[section]
            if not isinstance(section_data, dict):
                errors.append(f"Section '{section}' must be an object")
                continue
            
            # Validate fields in section
            for field, rules in schema.items():
                field_path = f"{section}.{field}"
                
                # Check if required field exists
                if rules.get("required") and field not in section_data:
                    errors.append(f"Missing required field: {field_path}")
                    continue
                
                if field not in section_data:
                    continue
                
                value = section_data[field]
                expected_type = rules["type"]
                
                # Type validation
                if not isinstance(value, expected_type):
                    errors.append(
                        f"Field '{field_path}' must be type {expected_type.__name__}, "
                        f"got {type(value).__name__}"
                    )
                    continue
                
                # String length validation
                if expected_type == str and "min_length" in rules:
                    if len(value) < rules["min_length"]:
                        errors.append(
                            f"Field '{field_path}' must have at least "
                            f"{rules['min_length']} characters"
                        )
                
                # Numeric range validation
                if expected_type == int:
                    if "min" in rules and value < rules["min"]:
                        errors.append(
                            f"Field '{field_path}' must be at least {rules['min']}, "
                            f"got {value}"
                        )
                    if "max" in rules and value > rules["max"]:
                        errors.append(
                            f"Field '{field_path}' must be at most {rules['max']}, "
                            f"got {value}"
                        )
                
                # List length validation
                if expected_type == list:
                    if "min_length" in rules and len(value) < rules["min_length"]:
                        errors.append(
                            f"Field '{field_path}' must have at least "
                            f"{rules['min_length']} items"
                        )
                    if "length" in rules and len(value) != rules["length"]:
                        errors.append(
                            f"Field '{field_path}' must have exactly "
                            f"{rules['length']} items, got {len(value)}"
                        )
        
        # Additional validation: teams.count should match teams.names length
        if "teams" in config:
            teams = config["teams"]
            if "count" in teams and "names" in teams:
                if isinstance(teams["names"], list) and teams["count"] != len(teams["names"]):
                    errors.append(
                        f"teams.count ({teams['count']}) must match number of team names "
                        f"({len(teams['names'])})"
                    )
            
            # Validate min_players <= max_players
            if "min_players" in teams and "max_players" in teams:
                if teams["min_players"] > teams["max_players"]:
                    errors.append(
                        f"teams.min_players ({teams['min_players']}) cannot be greater than "
                        f"teams.max_players ({teams['max_players']})"
                    )
        
        # Validate auction increments are positive integers
        if "auction" in config and "increments" in config["auction"]:
            increments = config["auction"]["increments"]
            if isinstance(increments, list):
                for i, inc in enumerate(increments):
                    if not isinstance(inc, int) or inc <= 0:
                        errors.append(
                            f"auction.increments[{i}] must be a positive integer, got {inc}"
                        )
        
        return len(errors) == 0, errors
    
    def create_backup(self) -> Optional[str]:
        """Create timestamped backup of current configuration"""
        try:
            if not os.path.exists(self.CONFIG_FILE):
                logger.warning("No configuration file to backup")
                return None
            
            # Generate timestamped filename
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            backup_filename = f"config_backup_{timestamp}.json"
            backup_path = os.path.join(self.BACKUP_DIR, backup_filename)
            
            # Copy current config to backup
            with open(self.CONFIG_FILE, 'r') as src:
                config = json.load(src)
            with open(backup_path, 'w') as dst:
                json.dump(config, dst, indent=2)
            
            logger.info(f"Backup created: {backup_path}")
            
            # Cleanup old backups
            self._cleanup_old_backups()
            
            return backup_path
            
        except Exception as e:
            logger.error(f"Error creating backup: {e}")
            return None
    
    def _cleanup_old_backups(self):
        """Maintain only the last MAX_BACKUPS backups"""
        try:
            backup_files = []
            for filename in os.listdir(self.BACKUP_DIR):
                if filename.startswith("config_backup_") and filename.endswith(".json"):
                    filepath = os.path.join(self.BACKUP_DIR, filename)
                    backup_files.append((filepath, os.path.getmtime(filepath)))
            
            # Sort by modification time (newest first)
            backup_files.sort(key=lambda x: x[1], reverse=True)
            
            # Delete old backups beyond MAX_BACKUPS
            for filepath, _ in backup_files[self.MAX_BACKUPS:]:
                os.remove(filepath)
                logger.info(f"Deleted old backup: {filepath}")
                
        except Exception as e:
            logger.error(f"Error cleaning up old backups: {e}")
    
    def list_backups(self) -> List[Dict]:
        """List available configuration backups"""
        try:
            backups = []
            for filename in os.listdir(self.BACKUP_DIR):
                if filename.startswith("config_backup_") and filename.endswith(".json"):
                    filepath = os.path.join(self.BACKUP_DIR, filename)
                    stat = os.stat(filepath)
                    backups.append({
                        "filename": filename,
                        "path": filepath,
                        "timestamp": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        "size": stat.st_size
                    })
            
            # Sort by timestamp (newest first)
            backups.sort(key=lambda x: x["timestamp"], reverse=True)
            return backups
            
        except Exception as e:
            logger.error(f"Error listing backups: {e}")
            return []
    
    def restore_backup(self, backup_filename: str) -> bool:
        """Restore configuration from backup"""
        try:
            backup_path = os.path.join(self.BACKUP_DIR, backup_filename)
            
            if not os.path.exists(backup_path):
                logger.error(f"Backup file not found: {backup_path}")
                return False
            
            # Load and validate backup
            with open(backup_path, 'r') as f:
                config = json.load(f)
            
            is_valid, errors = self.validate_config(config)
            if not is_valid:
                logger.error(f"Backup configuration is invalid: {errors}")
                return False
            
            # Create backup of current config before restoring
            if os.path.exists(self.CONFIG_FILE):
                self.create_backup()
            
            # Restore backup
            with open(self.CONFIG_FILE, 'w') as f:
                json.dump(config, f, indent=2)
            
            logger.info(f"Configuration restored from: {backup_filename}")
            return True
            
        except Exception as e:
            logger.error(f"Error restoring backup: {e}")
            return False
    
    def _get_default_config(self) -> Dict:
        """Return default configuration"""
        return {
            "tournament": {
                "name": "Palace Premier League",
                "logo": "logo.png"
            },
            "teams": {
                "count": 3,
                "names": ["Palace Tuskers", "Palace Titans", "Palace Warriors"],
                "budget": 25000000,
                "min_players": 8,
                "max_players": 9
            },
            "auction": {
                "base_price": 5000000,
                "currency": "₹",
                "increments": [1000000, 2500000, 5000000]
            }
        }


class PasswordManager:
    """Manages password hashing and verification using bcrypt"""
    
    BCRYPT_ROUNDS = 12  # Work factor for bcrypt
    
    def hash_password(self, password: str) -> str:
        """Hash password using bcrypt with 12 rounds"""
        if isinstance(password, str):
            password = password.encode('utf-8')
        
        salt = bcrypt.gensalt(rounds=self.BCRYPT_ROUNDS)
        hashed = bcrypt.hashpw(password, salt)
        return hashed.decode('utf-8')
    
    def verify_password(self, password: str, hashed: str) -> bool:
        """Verify password against bcrypt hash"""
        try:
            if isinstance(password, str):
                password = password.encode('utf-8')
            if isinstance(hashed, str):
                hashed = hashed.encode('utf-8')
            
            return bcrypt.checkpw(password, hashed)
        except Exception as e:
            logger.error(f"Error verifying password: {e}")
            return False
    
    def get_admin_password_hash(self) -> str:
        """Get admin password hash from environment or generate default"""
        from dotenv import load_dotenv
        load_dotenv()
        
        password_hash = os.getenv('ADMIN_PASSWORD_HASH')
        
        if password_hash:
            return password_hash
        
        # No environment variable set, use default password
        logger.warning(
            "ADMIN_PASSWORD_HASH not set in environment! "
            "Using default password 'admin123'. "
            "Please set ADMIN_PASSWORD_HASH in .env file for production!"
        )
        
        # Default hash for "admin123"
        return "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYIvApKSRCy"


class EnvironmentManager:
    """Manages environment variable loading with secure defaults"""
    
    def __init__(self):
        """Initialize and load environment variables"""
        from dotenv import load_dotenv
        load_dotenv()
    
    def get_secret_key(self) -> str:
        """Get Flask secret key from environment or generate random"""
        secret_key = os.getenv('FLASK_SECRET_KEY')
        
        if secret_key:
            return secret_key
        
        # Generate random secret key
        generated_key = secrets.token_hex(32)
        logger.warning(
            "FLASK_SECRET_KEY not set in environment! "
            "Generated random key for this session. "
            "Sessions will be invalidated on restart. "
            "Please set FLASK_SECRET_KEY in .env file for production!"
        )
        
        return generated_key
    
    def get_admin_password(self) -> str:
        """Get admin password from environment (for initial setup)"""
        password = os.getenv('ADMIN_PASSWORD')
        
        if password:
            return password
        
        logger.warning(
            "ADMIN_PASSWORD not set in environment. "
            "Using default password 'admin123'. "
            "Please change this immediately!"
        )
        
        return "admin123"


class AuditLogger:
    """Logs configuration changes for audit trail"""
    
    AUDIT_LOG_FILE = "audit.log"
    MAX_LOG_ENTRIES = 50
    
    def log_change(self, field: str, old_value: Any, new_value: Any, 
                   session_id: str = "unknown") -> None:
        """Log a configuration change"""
        try:
            timestamp = datetime.now().isoformat()
            log_entry = {
                "timestamp": timestamp,
                "session_id": session_id,
                "field": field,
                "old_value": str(old_value) if old_value is not None else None,
                "new_value": str(new_value) if new_value is not None else None,
                "action": "update"
            }
            
            # Append to log file
            with open(self.AUDIT_LOG_FILE, 'a') as f:
                f.write(json.dumps(log_entry) + '\n')
            
            logger.info(f"Audit log: {field} changed by {session_id}")
            
        except Exception as e:
            logger.error(f"Error writing audit log: {e}")
            # Fallback to console logging
            print(f"AUDIT: {timestamp} | {session_id} | {field} | {old_value} -> {new_value}")
    
    def get_recent_changes(self, limit: int = 50) -> List[Dict]:
        """Get recent configuration changes"""
        try:
            if not os.path.exists(self.AUDIT_LOG_FILE):
                return []
            
            changes = []
            with open(self.AUDIT_LOG_FILE, 'r') as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                        changes.append(entry)
                    except json.JSONDecodeError:
                        continue
            
            # Return most recent entries (reverse chronological order)
            changes.reverse()
            return changes[:limit]
            
        except Exception as e:
            logger.error(f"Error reading audit log: {e}")
            return []

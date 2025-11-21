# Design Document

## Overview

This design addresses critical configuration and security improvements for the Palace Premier League Auction Platform. The implementation will replace hardcoded values with configurable settings, implement secure password storage, and enhance configuration management capabilities.

The design follows a phased approach:
1. Replace hardcoded currency symbols with CONFIG references
2. Implement secure password and secret key management using environment variables and bcrypt
3. Add UI for password management
4. Enhance configuration management with validation, backups, and audit logging

## Architecture

### Configuration Layer
- **Config Loader**: Centralized configuration loading with validation
- **Environment Manager**: Handles environment variable reading with fallbacks
- **Password Manager**: Manages password hashing and verification using bcrypt
- **Backup Manager**: Handles automatic configuration backups

### Security Layer
- **Password Hashing**: bcrypt with configurable work factor (default: 12 rounds)
- **Environment Variables**: Sensitive data stored outside source code
- **Session Management**: Flask sessions secured with environment-based secret key

### Storage Layer
- **config.json**: Main configuration file (non-sensitive settings)
- **.env**: Environment variables for sensitive data (not committed to git)
- **backups/**: Directory for automatic configuration backups
- **audit.log**: Configuration change audit trail

## Components and Interfaces

### 1. Environment Configuration Module

```python
# config_manager.py

import os
import json
import bcrypt
from datetime import datetime
from pathlib import Path

class ConfigManager:
    """Manages configuration loading, validation, and persistence"""
    
    def load_config(self) -> dict:
        """Load and validate configuration from config.json"""
        
    def save_config(self, config: dict) -> None:
        """Save configuration with validation and backup"""
        
    def validate_config(self, config: dict) -> tuple[bool, list[str]]:
        """Validate configuration structure and values"""
        
    def create_backup(self) -> str:
        """Create timestamped backup of current configuration"""
        
    def list_backups(self) -> list[dict]:
        """List available configuration backups"""
        
    def restore_backup(self, backup_filename: str) -> None:
        """Restore configuration from backup"""

class PasswordManager:
    """Manages password hashing and verification"""
    
    def hash_password(self, password: str) -> str:
        """Hash password using bcrypt"""
        
    def verify_password(self, password: str, hashed: str) -> bool:
        """Verify password against hash"""
        
    def get_admin_password_hash(self) -> str:
        """Get admin password hash from environment or default"""

class EnvironmentManager:
    """Manages environment variable loading"""
    
    def get_secret_key(self) -> str:
        """Get Flask secret key from environment or generate"""
        
    def get_admin_password(self) -> str:
        """Get admin password from environment"""
```

### 2. Template Updates

All templates will be updated to use `{{ CONFIG.auction.currency }}` instead of hardcoded `₹` symbols.

Pattern to replace:
- `₹{{ format_currency(value) }}` → `{{ CONFIG.auction.currency }}{{ format_currency(value) }}`
- JavaScript: `'₹' + formatCurrency(value)` → `CONFIG.auction.currency + formatCurrency(value)`

### 3. Password Change UI Component

New section in `tournament_settings.html`:

```html
<div class="card">
  <h3>Admin Password</h3>
  <form method="post" action="{{ url_for('change_admin_password') }}">
    <div>
      <label>Current Password:</label>
      <input type="password" name="current_password" required>
    </div>
    <div>
      <label>New Password:</label>
      <input type="password" name="new_password" required minlength="8">
    </div>
    <div>
      <label>Confirm New Password:</label>
      <input type="password" name="confirm_password" required>
    </div>
    <button type="submit">Change Password</button>
  </form>
</div>
```

### 4. Configuration Validation Schema

```python
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
```

### 5. Audit Logging

```python
class AuditLogger:
    """Logs configuration changes for audit trail"""
    
    def log_change(self, field: str, old_value: any, new_value: any, user_id: str) -> None:
        """Log a configuration change"""
        
    def get_recent_changes(self, limit: int = 50) -> list[dict]:
        """Get recent configuration changes"""
```

## Data Models

### Configuration Backup Entry
```python
{
    "filename": "config_backup_2024-11-21_14-30-00.json",
    "timestamp": "2024-11-21T14:30:00",
    "size": 1024,
    "path": "backups/config_backup_2024-11-21_14-30-00.json"
}
```

### Audit Log Entry
```python
{
    "timestamp": "2024-11-21T14:30:00",
    "session_id": "abc123",
    "field": "tournament.name",
    "old_value": "Palace Premier League",
    "new_value": "Champions League",
    "action": "update"
}
```

### Environment Variables
```
ADMIN_PASSWORD_HASH=<bcrypt_hash>
FLASK_SECRET_KEY=<random_secret>
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*


### Property 1: Currency symbol loaded from configuration
*For any* configuration load operation, the currency symbol should be read from config.json and not from hardcoded values
**Validates: Requirements 1.1**

### Property 2: Templates use configured currency
*For any* template rendering monetary values, the currency symbol should come from CONFIG.auction.currency
**Validates: Requirements 1.2**

### Property 3: Currency updates apply globally
*For any* currency symbol update in configuration, all subsequent page renders should use the new currency symbol
**Validates: Requirements 1.3**

### Property 4: JavaScript uses configured currency
*For any* JavaScript code rendering currency, it should use CONFIG.auction.currency from the global object
**Validates: Requirements 1.4**

### Property 5: Admin password loaded from environment
*For any* system startup, the admin password hash should be read from the ADMIN_PASSWORD_HASH environment variable
**Validates: Requirements 2.1**

### Property 6: Passwords hashed with bcrypt
*For any* password storage operation, the password should be hashed using bcrypt with at least 12 rounds
**Validates: Requirements 2.2**

### Property 7: Login uses bcrypt verification
*For any* login attempt, the provided password should be verified against the stored hash using bcrypt.checkpw
**Validates: Requirements 2.3**

### Property 8: Failed authentication blocks access
*For any* failed password verification, access to administrative routes should be denied
**Validates: Requirements 2.5**

### Property 9: Secret key loaded from environment
*For any* system startup, the Flask secret key should be read from the FLASK_SECRET_KEY environment variable
**Validates: Requirements 3.1**

### Property 10: Secret key used by Flask
*For any* Flask application instance, app.secret_key should match the loaded secret key value
**Validates: Requirements 3.3**

### Property 11: Password change requires current password
*For any* password change request, the current password must be verified before allowing the change
**Validates: Requirements 4.2**

### Property 12: New passwords are hashed
*For any* successful password change, the new password should be stored as a bcrypt hash
**Validates: Requirements 4.3**

### Property 13: Increment display uses configuration
*For any* increment slab display, the values should match the increments array in config.json
**Validates: Requirements 5.1**

### Property 14: Increment descriptions use configured currency
*For any* increment slab description, the currency symbol should be CONFIG.auction.currency
**Validates: Requirements 5.2**

### Property 15: Increment updates apply immediately
*For any* increment configuration change, subsequent displays should show the new increment values
**Validates: Requirements 5.3**

### Property 16: Export filename contains timestamp
*For any* configuration export, the filename should contain a timestamp in YYYY-MM-DD_HH-MM-SS format
**Validates: Requirements 6.1**

### Property 17: Export contains all configuration
*For any* configuration export, the exported JSON should contain all fields from config.json
**Validates: Requirements 6.2**

### Property 18: Timestamp format is sortable
*For any* generated timestamp, it should match the pattern YYYY-MM-DD_HH-MM-SS and be lexicographically sortable
**Validates: Requirements 6.4**

### Property 19: Invalid JSON rejected
*For any* configuration import with invalid JSON, the import should be rejected with an error message
**Validates: Requirements 7.1**

### Property 20: Missing required fields rejected
*For any* configuration import missing required fields, the import should be rejected with specific field errors
**Validates: Requirements 7.2**

### Property 21: Wrong data types rejected
*For any* configuration import with incorrect data types, the import should be rejected with type error messages
**Validates: Requirements 7.3**

### Property 22: Out-of-range values rejected
*For any* configuration import with values outside acceptable ranges, the import should be rejected with range errors
**Validates: Requirements 7.4**

### Property 23: Validation errors are specific
*For any* failed configuration validation, the error messages should identify the specific fields and problems
**Validates: Requirements 7.5**

### Property 24: Backup created before modification
*For any* configuration modification, a backup file should be created before applying changes
**Validates: Requirements 8.1**

### Property 25: Backup filename contains timestamp
*For any* backup creation, the filename should contain a timestamp in YYYY-MM-DD_HH-MM-SS format
**Validates: Requirements 8.2**

### Property 26: Backup retention limit enforced
*For any* backup directory, only the 10 most recent backups should be retained
**Validates: Requirements 8.3**

### Property 27: Backups stored in dedicated directory
*For any* backup creation, the file should be stored in the backups/ directory
**Validates: Requirements 8.4**

### Property 28: Configuration changes logged
*For any* configuration modification, an audit log entry should be created with timestamp and session ID
**Validates: Requirements 9.1**

### Property 29: Log records modified fields
*For any* configuration change, the audit log should record which specific fields were modified
**Validates: Requirements 9.2**

### Property 30: Log records old and new values
*For any* configuration change, the audit log should contain both the previous and new values
**Validates: Requirements 9.3**

### Property 31: Audit log ordered by recency
*For any* audit log display, entries should be ordered with most recent changes first
**Validates: Requirements 9.4**

### Property 32: Audit log limited to 50 entries
*For any* audit log display, a maximum of 50 most recent entries should be shown
**Validates: Requirements 9.5**

## Error Handling

### Configuration Loading Errors
- **Missing config.json**: Create default configuration and log warning
- **Malformed JSON**: Log error and use default configuration
- **Missing required fields**: Add defaults and log warning

### Environment Variable Errors
- **Missing ADMIN_PASSWORD_HASH**: Use default password "admin123" and log security warning
- **Missing FLASK_SECRET_KEY**: Generate random key and log warning
- **Invalid bcrypt hash**: Regenerate hash and log error

### Password Management Errors
- **Incorrect current password**: Display error message, do not change password
- **Password mismatch**: Display error message when new password and confirmation don't match
- **Weak password**: Enforce minimum 8 characters

### Configuration Import Errors
- **Invalid JSON**: Display "Invalid JSON format" error
- **Missing required fields**: Display list of missing fields
- **Type mismatch**: Display "Field X must be type Y" error
- **Range violation**: Display "Field X must be between A and B" error

### Backup Errors
- **Backup directory missing**: Create directory automatically
- **Backup write failure**: Log error and continue with configuration update
- **Backup deletion failure**: Log warning but continue

### Audit Log Errors
- **Log write failure**: Log to console as fallback
- **Log file corruption**: Create new log file and log warning

## Testing Strategy

### Unit Testing
- Test configuration validation with valid and invalid inputs
- Test password hashing and verification with known values
- Test timestamp generation format
- Test backup retention logic with various backup counts
- Test audit log entry creation and formatting

### Property-Based Testing
Property-based tests will use the `hypothesis` library for Python to generate random test cases.

Each property test should run a minimum of 100 iterations to ensure comprehensive coverage.

Property tests will be tagged with comments referencing the design document properties:
- Format: `# Feature: configuration-improvements, Property X: <property_text>`

Key property tests:
1. Currency symbol consistency across all templates
2. Password hashing produces valid bcrypt hashes
3. Configuration validation rejects all invalid inputs
4. Backup retention maintains exactly 10 most recent files
5. Audit log maintains chronological ordering
6. Timestamp format is always sortable

### Integration Testing
- Test complete password change flow from UI to storage
- Test configuration export and import round-trip
- Test backup creation and restoration
- Test currency symbol update propagation to all pages

### Security Testing
- Verify passwords are never stored in plain text
- Verify secret key is not exposed in logs or responses
- Verify admin routes require authentication
- Verify bcrypt work factor is appropriate (12+ rounds)

## Implementation Notes

### Dependencies
- `bcrypt`: For password hashing (add to requirements.txt)
- `python-dotenv`: For .env file support (add to requirements.txt)

### File Structure
```
.
├── config_manager.py          # New: Configuration management module
├── .env                        # New: Environment variables (not in git)
├── .env.example               # New: Example environment file
├── backups/                   # New: Configuration backups directory
├── audit.log                  # New: Configuration change audit log
├── .gitignore                 # Update: Add .env and backups/
└── app.py                     # Update: Use new config manager
```

### Migration Path
1. Install new dependencies (bcrypt, python-dotenv)
2. Create .env.example with template values
3. Update .gitignore to exclude .env and backups/
4. Implement config_manager.py module
5. Update app.py to use ConfigManager
6. Update all templates to use CONFIG.auction.currency
7. Add password change UI to tournament_settings.html
8. Test all functionality before deployment

### Backward Compatibility
- Existing config.json files will continue to work
- Default password "admin123" used if no environment variable set
- Random secret key generated if not in environment
- System logs warnings when using defaults

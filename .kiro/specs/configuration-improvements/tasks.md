# Implementation Plan

- [x] 1. Set up project dependencies and structure



  - Install bcrypt and python-dotenv packages
  - Create .env.example template file
  - Create backups/ directory
  - Update .gitignore to exclude .env and backups/
  - _Requirements: 2.2, 3.1_

- [ ] 2. Implement configuration management module
  - Create config_manager.py with ConfigManager class
  - Implement load_config() with validation
  - Implement save_config() with backup creation
  - Implement validate_config() with schema checking
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 8.1_

- [ ]* 2.1 Write property test for configuration validation
  - **Property 19: Invalid JSON rejected**
  - **Property 20: Missing required fields rejected**
  - **Property 21: Wrong data types rejected**
  - **Property 22: Out-of-range values rejected**
  - **Validates: Requirements 7.1, 7.2, 7.3, 7.4**

- [ ] 3. Implement password management module
  - Create PasswordManager class in config_manager.py
  - Implement hash_password() using bcrypt with 12 rounds
  - Implement verify_password() using bcrypt.checkpw
  - Implement get_admin_password_hash() with environment variable reading
  - _Requirements: 2.1, 2.2, 2.3_

- [ ]* 3.1 Write property test for password hashing
  - **Property 6: Passwords hashed with bcrypt**
  - **Property 7: Login uses bcrypt verification**
  - **Validates: Requirements 2.2, 2.3**

- [ ] 4. Implement environment variable management
  - Create EnvironmentManager class in config_manager.py
  - Implement get_secret_key() with fallback to random generation
  - Implement get_admin_password() with fallback to default
  - Add logging for missing environment variables
  - _Requirements: 2.4, 3.1, 3.2_

- [ ] 5. Update app.py to use new configuration system
  - Import and initialize ConfigManager, PasswordManager, EnvironmentManager
  - Replace load_config() calls with ConfigManager.load_config()
  - Replace save_config() calls with ConfigManager.save_config()
  - Update app.secret_key to use EnvironmentManager.get_secret_key()
  - Update admin login route to use PasswordManager.verify_password()
  - _Requirements: 2.1, 2.3, 2.5, 3.1, 3.3_

- [ ]* 5.1 Write property test for authentication
  - **Property 8: Failed authentication blocks access**
  - **Validates: Requirements 2.5**

- [ ] 6. Replace hardcoded currency symbols in templates
  - Update templates/teams.html to use {{ CONFIG.auction.currency }}
  - Update templates/players.html to use {{ CONFIG.auction.currency }}
  - Update templates/auction.html to use {{ CONFIG.auction.currency }}
  - Update templates/sequential_auction.html to use {{ CONFIG.auction.currency }}
  - Update templates/live_view.html to use {{ CONFIG.auction.currency }}
  - Update templates/player_management.html to use {{ CONFIG.auction.currency }}
  - _Requirements: 1.2_

- [ ]* 6.1 Write property test for currency symbol usage
  - **Property 2: Templates use configured currency**
  - **Property 3: Currency updates apply globally**
  - **Validates: Requirements 1.2, 1.3**

- [ ] 7. Update JavaScript to use configured currency
  - Update sequential_auction.html JavaScript to use CONFIG.auction.currency
  - Update live_view.html JavaScript to use CONFIG.auction.currency
  - Update auction.html JavaScript to use CONFIG.auction.currency
  - _Requirements: 1.4_

- [ ]* 7.1 Write property test for JavaScript currency usage
  - **Property 4: JavaScript uses configured currency**
  - **Validates: Requirements 1.4**

- [ ] 8. Implement dynamic increment slab display
  - Update auction.html to generate increment slab text from CONFIG
  - Create helper function to format increment slab descriptions
  - Use CONFIG.auction.currency and CONFIG.auction.increments
  - _Requirements: 5.1, 5.2, 5.3, 5.4_

- [ ]* 8.1 Write property test for increment display
  - **Property 13: Increment display uses configuration**
  - **Property 14: Increment descriptions use configured currency**
  - **Validates: Requirements 5.1, 5.2**

- [ ] 9. Add password change UI to tournament settings
  - Add password change form to templates/tournament_settings.html
  - Include current password, new password, and confirm password fields
  - Add password strength requirements (minimum 8 characters)
  - Style form consistently with existing tournament settings
  - _Requirements: 4.1_

- [ ] 10. Implement password change route
  - Create /change-admin-password route in app.py
  - Verify current password using PasswordManager
  - Validate new password matches confirmation
  - Hash new password and update environment/storage
  - Display success or error messages
  - _Requirements: 4.2, 4.3, 4.4, 4.5_

- [ ]* 10.1 Write property test for password change
  - **Property 11: Password change requires current password**
  - **Property 12: New passwords are hashed**
  - **Validates: Requirements 4.2, 4.3**

- [ ] 11. Implement configuration backup system
  - Implement create_backup() in ConfigManager
  - Generate timestamped backup filenames
  - Store backups in backups/ directory
  - Implement backup retention (keep last 10)
  - Call create_backup() before any config modification
  - _Requirements: 8.1, 8.2, 8.3, 8.4_

- [ ]* 11.1 Write property test for backup system
  - **Property 24: Backup created before modification**
  - **Property 25: Backup filename contains timestamp**
  - **Property 26: Backup retention limit enforced**
  - **Property 27: Backups stored in dedicated directory**
  - **Validates: Requirements 8.1, 8.2, 8.3, 8.4**

- [ ] 12. Implement timestamped configuration export
  - Update /export-config route to generate timestamped filename
  - Use format: config_export_YYYY-MM-DD_HH-MM-SS.json
  - Ensure all configuration fields are included
  - Set appropriate download headers
  - _Requirements: 6.1, 6.2, 6.3, 6.4_

- [ ]* 12.1 Write property test for export functionality
  - **Property 16: Export filename contains timestamp**
  - **Property 17: Export contains all configuration**
  - **Property 18: Timestamp format is sortable**
  - **Validates: Requirements 6.1, 6.2, 6.4**

- [ ] 13. Implement configuration import validation
  - Update /import-config route to use ConfigManager.validate_config()
  - Check JSON structure, required fields, data types, and ranges
  - Display specific error messages for validation failures
  - Only apply configuration if validation passes
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

- [ ]* 13.1 Write property test for import validation
  - **Property 23: Validation errors are specific**
  - **Validates: Requirements 7.5**

- [ ] 14. Implement audit logging system
  - Create AuditLogger class in config_manager.py
  - Implement log_change() to record configuration modifications
  - Store timestamp, session ID, field, old value, new value
  - Implement get_recent_changes() to retrieve last 50 entries
  - Integrate logging into all configuration update routes
  - _Requirements: 9.1, 9.2, 9.3_

- [ ]* 14.1 Write property test for audit logging
  - **Property 28: Configuration changes logged**
  - **Property 29: Log records modified fields**
  - **Property 30: Log records old and new values**
  - **Property 31: Audit log ordered by recency**
  - **Property 32: Audit log limited to 50 entries**
  - **Validates: Requirements 9.1, 9.2, 9.3, 9.4, 9.5**

- [ ] 15. Add audit log viewing UI
  - Create /audit-log route to display configuration changes
  - Add audit log section to tournament_settings.html
  - Display timestamp, field, old value, new value for each entry
  - Show last 50 changes in reverse chronological order
  - Style consistently with existing UI
  - _Requirements: 9.4, 9.5_

- [ ] 16. Implement backup restoration UI
  - Implement list_backups() in ConfigManager
  - Create /list-backups route to return available backups
  - Add backup restoration section to tournament_settings.html
  - Display available backups with timestamps
  - Add restore button for each backup
  - Implement /restore-backup route to restore selected backup
  - _Requirements: 8.5_

- [ ] 17. Update Jinja globals on configuration changes
  - Update update_tournament_info() to refresh app.jinja_env.globals
  - Update update_teams() to refresh app.jinja_env.globals
  - Update update_auction_rules() to refresh app.jinja_env.globals
  - Ensure CONFIG is always current in templates
  - _Requirements: 1.3, 5.3_

- [ ]* 17.1 Write property test for global updates
  - **Property 15: Increment updates apply immediately**
  - **Validates: Requirements 5.3**

- [ ] 18. Create .env.example template
  - Document ADMIN_PASSWORD_HASH with example bcrypt hash
  - Document FLASK_SECRET_KEY with example random string
  - Add comments explaining how to generate values
  - Include instructions for first-time setup
  - _Requirements: 2.1, 3.1_

- [ ] 19. Update documentation
  - Update README.md with environment variable setup instructions
  - Document password change process
  - Document configuration backup and restore process
  - Document audit log viewing
  - Add security best practices section
  - _Requirements: All_

- [ ] 20. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

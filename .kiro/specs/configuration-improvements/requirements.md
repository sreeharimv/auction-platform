# Requirements Document

## Introduction

This specification addresses critical configuration and security improvements for the Palace Premier League Auction Platform. The system currently has hardcoded values for currency symbols, admin passwords, and secret keys that need to be made configurable and secure. Additionally, the configuration management system needs enhancements for better usability and security.

## Glossary

- **System**: The Palace Premier League Auction Platform web application
- **Admin User**: A user with administrative privileges who can access auction management features
- **Configuration**: Settings stored in config.json that control tournament behavior
- **Environment Variable**: A system-level variable used to store sensitive configuration outside source code
- **Password Hash**: A one-way cryptographic transformation of a password for secure storage
- **Currency Symbol**: The character or string representing monetary values (e.g., ₹, $, €)
- **Secret Key**: A cryptographic key used by Flask for session management and security
- **Increment Slab**: A tier-based bidding increment rule based on current bid amount

## Requirements

### Requirement 1

**User Story:** As a tournament organizer, I want the currency symbol to be configurable and consistently displayed throughout the application, so that I can run auctions in different currencies without modifying code.

#### Acceptance Criteria

1. WHEN the System loads configuration THEN the System SHALL read the currency symbol from config.json
2. WHEN displaying monetary values in templates THEN the System SHALL use the configured currency symbol instead of hardcoded values
3. WHEN the currency symbol is updated in tournament settings THEN the System SHALL apply the change to all pages immediately
4. WHEN rendering currency in JavaScript THEN the System SHALL use the configured currency symbol from the global CONFIG object

### Requirement 2

**User Story:** As a system administrator, I want the admin password to be stored securely using environment variables and password hashing, so that unauthorized users cannot access administrative functions.

#### Acceptance Criteria

1. WHEN the System starts THEN the System SHALL read the admin password from an environment variable
2. WHEN storing the admin password THEN the System SHALL hash the password using bcrypt with appropriate salt rounds
3. WHEN a user attempts to log in THEN the System SHALL compare the provided password against the hashed password
4. WHEN no environment variable is set THEN the System SHALL use a secure default password and log a warning
5. IF the admin password verification fails THEN the System SHALL prevent access to administrative functions

### Requirement 3

**User Story:** As a system administrator, I want the Flask secret key to be stored in an environment variable, so that session security is maintained and the key is not exposed in source code.

#### Acceptance Criteria

1. WHEN the System starts THEN the System SHALL read the secret key from an environment variable
2. WHEN no environment variable is set THEN the System SHALL generate a random secret key and log a warning
3. WHEN the secret key is loaded THEN the System SHALL use it for Flask session management
4. IF the secret key changes between restarts THEN the System SHALL invalidate existing sessions

### Requirement 4

**User Story:** As a tournament organizer, I want to change the admin password through the tournament settings UI, so that I can maintain security without modifying environment variables or code.

#### Acceptance Criteria

1. WHEN an Admin User accesses tournament settings THEN the System SHALL display a password change form
2. WHEN an Admin User submits a new password THEN the System SHALL require the current password for verification
3. WHEN the new password is submitted THEN the System SHALL hash and store the password securely
4. WHEN the password is successfully changed THEN the System SHALL display a confirmation message
5. IF the current password is incorrect THEN the System SHALL reject the password change and display an error

### Requirement 5

**User Story:** As a tournament organizer, I want the bid increment slabs to be displayed dynamically based on configuration, so that the displayed rules match the actual auction behavior.

#### Acceptance Criteria

1. WHEN the System displays increment information THEN the System SHALL read increment values from config.json
2. WHEN rendering increment slab descriptions THEN the System SHALL format them using the configured currency symbol
3. WHEN increment configuration changes THEN the System SHALL update the displayed information immediately
4. WHEN displaying increment slabs THEN the System SHALL show all three tiers with their respective ranges and increment amounts

### Requirement 6

**User Story:** As a tournament organizer, I want to export configuration with timestamps in the filename, so that I can maintain multiple configuration versions and track when they were created.

#### Acceptance Criteria

1. WHEN an Admin User requests configuration export THEN the System SHALL generate a filename with the current timestamp
2. WHEN exporting configuration THEN the System SHALL include all settings from config.json
3. WHEN the export is complete THEN the System SHALL download the file to the user's device
4. WHEN generating the timestamp THEN the System SHALL use a sortable format (YYYY-MM-DD_HH-MM-SS)

### Requirement 7

**User Story:** As a tournament organizer, I want to validate imported configuration files, so that invalid configurations do not break the application.

#### Acceptance Criteria

1. WHEN an Admin User imports a configuration file THEN the System SHALL validate the JSON structure
2. WHEN validating configuration THEN the System SHALL verify all required fields are present
3. WHEN validating configuration THEN the System SHALL verify data types match expected types
4. WHEN validating configuration THEN the System SHALL verify numeric values are within acceptable ranges
5. IF validation fails THEN the System SHALL reject the import and display specific error messages
6. WHEN validation succeeds THEN the System SHALL apply the configuration and display a success message

### Requirement 8

**User Story:** As a tournament organizer, I want automatic configuration backups before changes, so that I can recover from configuration errors.

#### Acceptance Criteria

1. WHEN configuration is about to be modified THEN the System SHALL create a backup of the current configuration
2. WHEN creating a backup THEN the System SHALL store it with a timestamp in the filename
3. WHEN storing backups THEN the System SHALL maintain the last 10 backups and delete older ones
4. WHEN a backup is created THEN the System SHALL store it in a dedicated backups directory
5. WHEN an Admin User requests backup restoration THEN the System SHALL display available backups with timestamps

### Requirement 9

**User Story:** As a system administrator, I want configuration changes to be logged, so that I can audit who changed what and when.

#### Acceptance Criteria

1. WHEN configuration is modified THEN the System SHALL log the change with timestamp and user session identifier
2. WHEN logging changes THEN the System SHALL record which configuration fields were modified
3. WHEN logging changes THEN the System SHALL record the old and new values
4. WHEN an Admin User views the audit log THEN the System SHALL display changes in reverse chronological order
5. WHEN displaying the audit log THEN the System SHALL show the last 50 configuration changes

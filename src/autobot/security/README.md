# Security Module

This module contains security functionality for the AUTOBOT system.

## Structure

- `auth/`: Authentication and authorization
- `licensing/`: License management

## Usage

The security module provides authentication and licensing functionality:

```python
from autobot.security.auth import verify_token, create_token
from autobot.security.licensing import verify_license, generate_license

# Authentication
token = create_token(user_id="user123", role="admin")
is_valid = verify_token(token)

# Licensing
license_key = generate_license(user_id="user123", features=["trading", "backtest"])
is_licensed = verify_license(license_key)
```

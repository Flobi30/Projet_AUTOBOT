# Core Module

This module contains core functionality for the AUTOBOT system.

## Structure

- `config/`: Configuration management
- `logging/`: Logging functionality
- `monitoring/`: System monitoring and metrics

## Usage

The core module provides essential functionality used throughout the AUTOBOT system:

```python
# Configuration
from autobot.core.config import load_config, save_config

config = load_config("config/app_config.json")
save_config("config/app_config.json", config)

# Logging
from autobot.core.logging import setup_logging

setup_logging(log_level=logging.INFO, log_file="autobot.log")

# Monitoring
from autobot.core.monitoring import get_system_status, get_system_metrics

status = get_system_status()
metrics = get_system_metrics()
```

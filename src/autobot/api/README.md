# API Module

This module contains API routes and schemas for the AUTOBOT system.

## Structure

- `routes/`: API route definitions
- `schemas/`: Pydantic models for request and response validation

## Routes

- `core_routes.py`: Core functionality routes (metrics, logs, health)
- `backtest_routes.py`: Backtesting routes
- `provider_routes.py`: Data provider routes
- `plugin_routes.py`: Plugin routes

## Usage

The API module is automatically loaded by the main application:

```python
from fastapi import FastAPI
from autobot.api.routes import api_router

app = FastAPI()
app.include_router(api_router)
```

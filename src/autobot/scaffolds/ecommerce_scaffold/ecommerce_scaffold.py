Here's a scaffold for an e-commerce module that integrates with Shopify, computes profit margins and sales KPIs, provides a CLI, and includes tests with HTTP mocks.

### Directory Structure
```
src/
└── ecommerce/
    ├── __init__.py
    ├── cli.py
    ├── shopify_integration.py
    ├── sales_metrics.py
    └── config.py
tests/
└── test_ecommerce.py
docs/
└── ecommerce_guide.md
```

### Code Files

#### `src/ecommerce/__init__.py`
```python
# src/ecommerce/__init__.py

__version__ = "0.1.0"
```

#### `src/ecommerce/cli.py`
```python
# src/ecommerce/cli.py

import click
from .shopify_integration import ShopifyIntegration

@click.command()
@click.option('--action', type=click.Choice(['list', 'add', 'remove']), required=True, help='Action to perform on products.')
@click.option('--product_id', type=str, help='ID of the product to remove.')
@click.option('--product_data', type=str, help='JSON string of product data to add.')
def sync(action, product_id, product_data):
    """CLI to sync products with Shopify."""
    shopify = ShopifyIntegration()

    if action == 'list':
        products = shopify.list_products()
        click.echo(products)
    elif action == 'add':
        if product_data:
            shopify.add_product(product_data)
            click.echo("Product added.")
        else:
            click.echo("Product data is required for adding a product.")
    elif action == 'remove':
        if product_id:
            shopify.remove_product(product_id)
            click.echo("Product removed.")
        else:
            click.echo("Product ID is required for removing a product.")

if __name__ == "__main__":
    sync()
```

#### `src/ecommerce/shopify_integration.py`
```python
# src/ecommerce/shopify_integration.py

import requests
import json
from .config import SHOPIFY_API_URL, SHOPIFY_API_KEY, SHOPIFY_API_PASSWORD

class ShopifyIntegration:
    def __init__(self):
        self.base_url = SHOPIFY_API_URL
        self.auth = (SHOPIFY_API_KEY, SHOPIFY_API_PASSWORD)

    def list_products(self):
        response = requests.get(f"{self.base_url}/products.json", auth=self.auth)
        return response.json()

    def add_product(self, product_data):
        response = requests.post(f"{self.base_url}/products.json", auth=self.auth, json=json.loads(product_data))
        return response.json()

    def remove_product(self, product_id):
        response = requests.delete(f"{self.base_url}/products/{product_id}.json", auth=self.auth)
        return response.status_code
```

#### `src/ecommerce/sales_metrics.py`
```python
# src/ecommerce/sales_metrics.py

class SalesMetrics:
    @staticmethod
    def compute_profit_margin(cost_price, selling_price):
        if selling_price == 0:
            return 0
        return (selling_price - cost_price) / selling_price * 100

    @staticmethod
    def compute_kpis(sales_data):
        total_sales = sum(sale['amount'] for sale in sales_data)
        total_units_sold = sum(sale['units'] for sale in sales_data)
        return {
            'total_sales': total_sales,
            'total_units_sold': total_units_sold,
            'average_sale_value': total_sales / total_units_sold if total_units_sold else 0
        }
```

#### `src/ecommerce/config.py`
```python
# src/ecommerce/config.py

SHOPIFY_API_URL = "https://your-shopify-store.myshopify.com/admin/api/2023-01"
SHOPIFY_API_KEY = "your_api_key"
SHOPIFY_API_PASSWORD = "your_api_password"
```

### Test File

#### `tests/test_ecommerce.py`
```python
# tests/test_ecommerce.py

import pytest
from unittest.mock import patch
from ecommerce.shopify_integration import ShopifyIntegration

@pytest.fixture
def shopify_integration():
    return ShopifyIntegration()

@patch('ecommerce.shopify_integration.requests.get')
def test_list_products(mock_get, shopify_integration):
    mock_get.return_value.json.return_value = {'products': []}
    products = shopify_integration.list_products()
    assert products == {'products': []}

@patch('ecommerce.shopify_integration.requests.post')
def test_add_product(mock_post, shopify_integration):
    mock_post.return_value.json.return_value = {'product': {'id': 1}}
    product_data = '{"title": "Test Product", "price": 10.0}'
    response = shopify_integration.add_product(product_data)
    assert response == {'product': {'id': 1}}

@patch('ecommerce.shopify_integration.requests.delete')
def test_remove_product(mock_delete, shopify_integration):
    mock_delete.return_value.status_code = 200
    response_code = shopify_integration.remove_product('1')
    assert response_code == 200
```

### Documentation

#### `docs/ecommerce_guide.md`
```markdown
# E-commerce Module Guide

## Overview
This module integrates with Shopify to manage products and compute sales metrics.

## Installation
To install the required packages, run:
```bash
pip install requests click
```

## Usage
### CLI Commands
- **List Products**
  ```bash
  python -m ecommerce.sync --action list
  ```

- **Add Product**
  ```bash
  python -m ecommerce.sync --action add --product_data '{"title": "New Product", "price": 20.0}'
  ```

- **Remove Product**
  ```bash
  python -m ecommerce.sync --action remove --product_id 1
  ```

## Testing
To run the tests, use:
```bash
pytest tests/
```

## Profit Margin Calculation
To compute profit margins, use the `SalesMetrics` class:
```python
from ecommerce.sales_metrics import SalesMetrics
margin = SalesMetrics.compute_profit_margin(cost_price, selling_price)
```

## KPIs Calculation
To compute sales KPIs, use:
```python
from ecommerce.sales_metrics import SalesMetrics
kpis = SalesMetrics.compute_kpis(sales_data)
```
```

### Summary
This scaffold provides a basic structure for an e-commerce module that integrates with Shopify, computes sales metrics, and includes a command-line interface and tests. You can expand upon this foundation by adding more features and improving error handling as needed.


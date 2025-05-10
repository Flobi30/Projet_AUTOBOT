
import pytest
import responses
import json
from autobot.ecommerce.shopify.shopify_client import list_products, add_product, remove_product

@responses.activate

def test_list_products():
    responses.add(
        responses.GET,
        'https://your-shopify-store.myshopify.com/admin/api/2023-04/products.json',
        json={'products': []},
        status=200
    )
    products = list_products()
    assert isinstance(products, list)

@responses.activate

def test_add_product():
    responses.add(
        responses.POST,
        'https://your-shopify-store.myshopify.com/admin/api/2023-04/products.json',
        json={'product': {'id': 1}},
        status=201
    )
    product = add_product({'title': 'Test Product'})
    assert product['id'] == 1

@responses.activate

def test_remove_product():
    responses.add(
        responses.DELETE,
        'https://your-shopify-store.myshopify.com/admin/api/2023-04/products/1.json',
        status=404
    )
    result = remove_product(1)
    assert result == True


"""
API routes for e-commerce functionality.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import uuid
import time

from autobot.ecommerce.inventory_manager import InventoryManager, Product, Order, create_inventory_manager

router = APIRouter(prefix="/ecommerce", tags=["ecommerce"])

inventory_manager = create_inventory_manager()

class ProductCreate(BaseModel):
    name: str
    sku: str
    description: str
    price: float
    cost: float
    quantity: int
    category: str
    platform: str
    listing_url: Optional[str] = ""
    image_urls: Optional[List[str]] = []
    attributes: Optional[Dict[str, Any]] = {}

class ProductResponse(BaseModel):
    product_id: str
    name: str
    sku: str
    description: str
    price: float
    cost: float
    quantity: int
    category: str
    platform: str
    listing_url: str
    image_urls: List[str]
    attributes: Dict[str, Any]
    created_at: int
    updated_at: int
    margin: float
    days_in_inventory: int
    sales_velocity: float
    is_unsold: bool
    discount_price: Optional[float] = None
    competitive_price: Optional[float] = None

class OrderCreate(BaseModel):
    user_id: str
    product_ids: List[str]
    quantities: List[int]
    shipping_address: Dict[str, str]
    payment_method: Dict[str, Any]

class OrderResponse(BaseModel):
    order_id: str
    user_id: str
    products: List[Dict[str, Any]]
    total_amount: float
    shipping_address: Dict[str, str]
    payment_method: Dict[str, Any]
    status: str
    created_at: int
    updated_at: int
    tracking_number: Optional[str] = None
    estimated_delivery: Optional[int] = None

class InventoryReport(BaseModel):
    total_products: int
    unsold_products: int
    unsold_percentage: float
    total_value: float
    unsold_value: float
    unsold_value_percentage: float
    categories: Dict[str, Dict[str, Any]]
    platforms: Dict[str, Dict[str, Any]]
    generated_at: int

@router.get("/products", response_model=List[ProductResponse])
async def get_products(
    category: Optional[str] = None,
    platform: Optional[str] = None,
    unsold_only: bool = False,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0)
):
    """Get products with optional filtering."""
    products = list(inventory_manager.products.values())
    
    if category:
        products = [p for p in products if p.category == category]
    
    if platform:
        products = [p for p in products if p.platform == platform]
    
    if unsold_only:
        products = [p for p in products if p.is_unsold]
    
    products = products[offset:offset + limit]
    
    return [p.to_dict() for p in products]

@router.get("/products/{product_id}", response_model=ProductResponse)
async def get_product(product_id: str):
    """Get a product by ID."""
    product = inventory_manager.get_product(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    return product.to_dict()

@router.post("/products", response_model=ProductResponse)
async def create_product(product: ProductCreate):
    """Create a new product."""
    product_id = str(uuid.uuid4())
    current_time = int(time.time())
    
    new_product = Product(
        product_id=product_id,
        name=product.name,
        sku=product.sku,
        description=product.description,
        price=product.price,
        cost=product.cost,
        quantity=product.quantity,
        category=product.category,
        platform=product.platform,
        listing_url=product.listing_url,
        image_urls=product.image_urls,
        attributes=product.attributes,
        created_at=current_time,
        updated_at=current_time
    )
    
    inventory_manager.products[product_id] = new_product
    inventory_manager._save_data()
    
    return new_product.to_dict()

@router.get("/unsold", response_model=List[ProductResponse])
async def get_unsold_products():
    """Get all unsold products."""
    unsold_products = inventory_manager.get_unsold_products()
    return [p.to_dict() for p in unsold_products]

@router.post("/identify-unsold", response_model=List[ProductResponse])
async def identify_unsold_inventory():
    """Identify unsold inventory."""
    unsold_products = inventory_manager.identify_unsold_inventory()
    return [p.to_dict() for p in unsold_products]

@router.post("/calculate-discounts", response_model=Dict[str, float])
async def calculate_discount_prices():
    """Calculate discount prices for unsold products."""
    return inventory_manager.calculate_discount_prices()

@router.post("/calculate-competitive-prices", response_model=Dict[str, float])
async def calculate_competitive_prices():
    """Calculate competitive prices for products."""
    return inventory_manager.calculate_competitive_prices()

@router.post("/orders", response_model=OrderResponse)
async def create_order(order: OrderCreate):
    """Create a new order."""
    new_order = inventory_manager.create_order(
        user_id=order.user_id,
        product_ids=order.product_ids,
        quantities=order.quantities,
        shipping_address=order.shipping_address,
        payment_method=order.payment_method
    )
    
    if not new_order:
        raise HTTPException(status_code=400, detail="Failed to create order")
    
    return new_order.to_dict()

@router.get("/orders", response_model=List[OrderResponse])
async def get_orders(user_id: Optional[str] = None):
    """Get orders with optional filtering by user ID."""
    if user_id:
        orders = inventory_manager.get_user_orders(user_id)
    else:
        orders = list(inventory_manager.orders.values())
    
    return [o.to_dict() for o in orders]

@router.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(order_id: str):
    """Get an order by ID."""
    order = inventory_manager.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    return order.to_dict()

@router.put("/orders/{order_id}/status", response_model=OrderResponse)
async def update_order_status(order_id: str, status: str):
    """Update the status of an order."""
    success = inventory_manager.update_order_status(order_id, status)
    if not success:
        raise HTTPException(status_code=404, detail="Order not found")
    
    order = inventory_manager.get_order(order_id)
    return order.to_dict()

@router.put("/orders/{order_id}/tracking", response_model=OrderResponse)
async def add_tracking_number(
    order_id: str, 
    tracking_number: str, 
    estimated_delivery: Optional[int] = None
):
    """Add a tracking number to an order."""
    success = inventory_manager.add_tracking_number(order_id, tracking_number, estimated_delivery)
    if not success:
        raise HTTPException(status_code=404, detail="Order not found")
    
    order = inventory_manager.get_order(order_id)
    return order.to_dict()

@router.get("/report", response_model=InventoryReport)
async def get_inventory_report():
    """Get inventory report."""
    return inventory_manager.generate_inventory_report()

@router.post("/sync", response_model=Dict[str, int])
async def sync_inventory(platform: Optional[str] = None):
    """Synchronize inventory with e-commerce platforms."""
    count = inventory_manager.sync_inventory(platform)
    return {"synchronized_products": count}

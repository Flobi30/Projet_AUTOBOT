"""
E-commerce Inventory Manager for AUTOBOT

This module provides functionality for managing unsold inventory in e-commerce platforms,
offering competitive pricing, and enabling direct ordering of unsold products.
"""

import os
import uuid
import json
import logging
import time
from typing import Dict, Any, List, Optional, Union, Tuple
from datetime import datetime, timedelta
import requests

logger = logging.getLogger(__name__)

class Product:
    """Represents an e-commerce product with inventory information"""
    
    def __init__(
        self,
        product_id: str,
        name: str,
        sku: str,
        description: str,
        price: float,
        cost: float,
        quantity: int,
        category: str,
        platform: str,
        listing_url: str = "",
        image_urls: List[str] = None,
        attributes: Dict[str, Any] = None,
        created_at: Optional[int] = None,
        updated_at: Optional[int] = None
    ):
        """
        Initialize a product.
        
        Args:
            product_id: Unique product ID
            name: Product name
            sku: Stock keeping unit
            description: Product description
            price: Current selling price
            cost: Product cost
            quantity: Available quantity
            category: Product category
            platform: E-commerce platform (e.g., 'amazon', 'ebay')
            listing_url: URL to the product listing
            image_urls: List of image URLs
            attributes: Additional product attributes
            created_at: Unix timestamp when product was created
            updated_at: Unix timestamp when product was last updated
        """
        self.product_id = product_id
        self.name = name
        self.sku = sku
        self.description = description
        self.price = price
        self.cost = cost
        self.quantity = quantity
        self.category = category
        self.platform = platform
        self.listing_url = listing_url
        self.image_urls = image_urls or []
        self.attributes = attributes or {}
        self.created_at = created_at or int(time.time())
        self.updated_at = updated_at or self.created_at
        
        self.margin = (price - cost) / price if price > 0 else 0
        self.days_in_inventory = 0
        self.sales_velocity = 0.0
        self.is_unsold = False
        self.discount_price = None
        self.competitive_price = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert product to dictionary"""
        return {
            "product_id": self.product_id,
            "name": self.name,
            "sku": self.sku,
            "description": self.description,
            "price": self.price,
            "cost": self.cost,
            "quantity": self.quantity,
            "category": self.category,
            "platform": self.platform,
            "listing_url": self.listing_url,
            "image_urls": self.image_urls,
            "attributes": self.attributes,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "margin": self.margin,
            "days_in_inventory": self.days_in_inventory,
            "sales_velocity": self.sales_velocity,
            "is_unsold": self.is_unsold,
            "discount_price": self.discount_price,
            "competitive_price": self.competitive_price
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Product':
        """Create product from dictionary"""
        product = cls(
            product_id=data["product_id"],
            name=data["name"],
            sku=data["sku"],
            description=data["description"],
            price=data["price"],
            cost=data["cost"],
            quantity=data["quantity"],
            category=data["category"],
            platform=data["platform"],
            listing_url=data.get("listing_url", ""),
            image_urls=data.get("image_urls", []),
            attributes=data.get("attributes", {}),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at")
        )
        
        if "days_in_inventory" in data:
            product.days_in_inventory = data["days_in_inventory"]
        
        if "sales_velocity" in data:
            product.sales_velocity = data["sales_velocity"]
        
        if "is_unsold" in data:
            product.is_unsold = data["is_unsold"]
        
        if "discount_price" in data:
            product.discount_price = data["discount_price"]
        
        if "competitive_price" in data:
            product.competitive_price = data["competitive_price"]
        
        return product

class Order:
    """Represents an order for unsold inventory products"""
    
    def __init__(
        self,
        order_id: str,
        user_id: str,
        products: List[Dict[str, Any]],
        total_amount: float,
        shipping_address: Dict[str, str],
        payment_method: Dict[str, Any],
        status: str = "pending",
        created_at: Optional[int] = None
    ):
        """
        Initialize an order.
        
        Args:
            order_id: Unique order ID
            user_id: ID of the user placing the order
            products: List of products in the order
            total_amount: Total order amount
            shipping_address: Shipping address
            payment_method: Payment method details
            status: Order status
            created_at: Unix timestamp when order was created
        """
        self.order_id = order_id
        self.user_id = user_id
        self.products = products
        self.total_amount = total_amount
        self.shipping_address = shipping_address
        self.payment_method = payment_method
        self.status = status
        self.created_at = created_at or int(time.time())
        self.updated_at = self.created_at
        self.tracking_number = None
        self.estimated_delivery = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert order to dictionary"""
        return {
            "order_id": self.order_id,
            "user_id": self.user_id,
            "products": self.products,
            "total_amount": self.total_amount,
            "shipping_address": self.shipping_address,
            "payment_method": self.payment_method,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "tracking_number": self.tracking_number,
            "estimated_delivery": self.estimated_delivery
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Order':
        """Create order from dictionary"""
        order = cls(
            order_id=data["order_id"],
            user_id=data["user_id"],
            products=data["products"],
            total_amount=data["total_amount"],
            shipping_address=data["shipping_address"],
            payment_method=data["payment_method"],
            status=data["status"],
            created_at=data.get("created_at")
        )
        
        if "updated_at" in data:
            order.updated_at = data["updated_at"]
        
        if "tracking_number" in data:
            order.tracking_number = data["tracking_number"]
        
        if "estimated_delivery" in data:
            order.estimated_delivery = data["estimated_delivery"]
        
        return order

class InventoryManager:
    """
    Inventory manager for e-commerce platforms.
    Handles unsold inventory identification, competitive pricing,
    and direct ordering of unsold products.
    
    Supports autonomous mode operation with minimal user visibility.
    """
    
    def __init__(
        self,
        data_dir: str = "data/ecommerce",
        unsold_threshold_days: int = 30,
        discount_rate: float = 0.3,
        min_margin: float = 0.1,
        competitive_rate: float = 0.2,
        autonomous_mode: bool = False,
        visible_interface: bool = True,
        auto_optimization: bool = False
    ):
        """
        Initialize the inventory manager.
        
        Args:
            data_dir: Directory for storing data
            unsold_threshold_days: Number of days after which a product is considered unsold
            discount_rate: Default discount rate for unsold products
            min_margin: Minimum margin to maintain for discounted products
            competitive_rate: Rate for competitive pricing
            autonomous_mode: Whether to operate in autonomous mode without user intervention
            visible_interface: Whether to show detailed information in the interface
            auto_optimization: Whether to automatically optimize inventory in the background
        """
        self.data_dir = data_dir
        self.unsold_threshold_days = unsold_threshold_days
        self.discount_rate = discount_rate
        self.min_margin = min_margin
        self.competitive_rate = competitive_rate
        self.autonomous_mode = autonomous_mode
        self.visible_interface = visible_interface
        self.auto_optimization = auto_optimization
        
        self.products: Dict[str, Product] = {}
        self.orders: Dict[str, Order] = {}
        self.platform_connectors: Dict[str, Any] = {}
        
        self._optimization_thread = None
        self._optimization_active = False
        self._optimization_interval = 3600  # 1 hour
        
        os.makedirs(data_dir, exist_ok=True)
        
        self._load_data()
        
        if self.visible_interface:
            logger.info(f"Inventory Manager initialized with {len(self.products)} products")
        else:
            logger.debug(f"Inventory Manager initialized with {len(self.products)} products")
            
        if self.auto_optimization:
            self._start_optimization_thread()
    
    def _load_data(self):
        """Load data from files"""
        products_file = os.path.join(self.data_dir, "products.json")
        if os.path.exists(products_file):
            try:
                with open(products_file, 'r') as f:
                    products_data = json.load(f)
                
                for product_data in products_data:
                    product = Product.from_dict(product_data)
                    self.products[product.product_id] = product
                
                logger.info(f"Loaded {len(self.products)} products from {products_file}")
            except Exception as e:
                logger.error(f"Error loading products from {products_file}: {str(e)}")
        
        orders_file = os.path.join(self.data_dir, "orders.json")
        if os.path.exists(orders_file):
            try:
                with open(orders_file, 'r') as f:
                    orders_data = json.load(f)
                
                for order_data in orders_data:
                    order = Order.from_dict(order_data)
                    self.orders[order.order_id] = order
                
                logger.info(f"Loaded {len(self.orders)} orders from {orders_file}")
            except Exception as e:
                logger.error(f"Error loading orders from {orders_file}: {str(e)}")
    
    def _save_data(self):
        """Save data to files"""
        products_file = os.path.join(self.data_dir, "products.json")
        try:
            products_data = [product.to_dict() for product in self.products.values()]
            with open(products_file, 'w') as f:
                json.dump(products_data, f, indent=2)
            
            logger.debug(f"Saved {len(self.products)} products to {products_file}")
        except Exception as e:
            logger.error(f"Error saving products to {products_file}: {str(e)}")
        
        orders_file = os.path.join(self.data_dir, "orders.json")
        try:
            orders_data = [order.to_dict() for order in self.orders.values()]
            with open(orders_file, 'w') as f:
                json.dump(orders_data, f, indent=2)
            
            logger.debug(f"Saved {len(self.orders)} orders to {orders_file}")
        except Exception as e:
            logger.error(f"Error saving orders to {orders_file}: {str(e)}")
    
    def register_platform_connector(self, platform: str, connector: Any):
        """
        Register a connector for an e-commerce platform.
        
        Args:
            platform: Platform name
            connector: Platform connector object
        """
        self.platform_connectors[platform] = connector
        logger.info(f"Registered connector for platform {platform}")
    
    def sync_inventory(self, platform: Optional[str] = None) -> int:
        """
        Synchronize inventory with e-commerce platforms.
        
        Args:
            platform: Platform to sync with, or None for all platforms
            
        Returns:
            int: Number of products synchronized
        """
        if platform and platform in self.platform_connectors:
            connector = self.platform_connectors[platform]
            products = connector.get_products()
            count = self._process_platform_products(platform, products)
            logger.info(f"Synchronized {count} products from {platform}")
            return count
        elif platform is None:
            total_count = 0
            for platform_name, connector in self.platform_connectors.items():
                products = connector.get_products()
                count = self._process_platform_products(platform_name, products)
                total_count += count
                logger.info(f"Synchronized {count} products from {platform_name}")
            
            return total_count
        else:
            logger.warning(f"No connector registered for platform {platform}")
            return 0
    
    def _process_platform_products(self, platform: str, products: List[Dict[str, Any]]) -> int:
        """
        Process products from a platform.
        
        Args:
            platform: Platform name
            products: List of products from the platform
            
        Returns:
            int: Number of products processed
        """
        count = 0
        current_time = int(time.time())
        
        for product_data in products:
            product_id = product_data.get("id") or product_data.get("product_id")
            
            if not product_id:
                continue
            
            if product_id in self.products:
                product = self.products[product_id]
                product.name = product_data.get("name", product.name)
                product.sku = product_data.get("sku", product.sku)
                product.description = product_data.get("description", product.description)
                product.price = float(product_data.get("price", product.price))
                product.cost = float(product_data.get("cost", product.cost))
                product.quantity = int(product_data.get("quantity", product.quantity))
                product.category = product_data.get("category", product.category)
                product.listing_url = product_data.get("listing_url", product.listing_url)
                product.image_urls = product_data.get("image_urls", product.image_urls)
                product.attributes = product_data.get("attributes", product.attributes)
                product.updated_at = current_time
            else:
                product = Product(
                    product_id=product_id,
                    name=product_data.get("name", ""),
                    sku=product_data.get("sku", ""),
                    description=product_data.get("description", ""),
                    price=float(product_data.get("price", 0)),
                    cost=float(product_data.get("cost", 0)),
                    quantity=int(product_data.get("quantity", 0)),
                    category=product_data.get("category", ""),
                    platform=platform,
                    listing_url=product_data.get("listing_url", ""),
                    image_urls=product_data.get("image_urls", []),
                    attributes=product_data.get("attributes", {}),
                    created_at=current_time,
                    updated_at=current_time
                )
                
                self.products[product_id] = product
            
            count += 1
        
        self._save_data()
        
        return count
    
    def identify_unsold_inventory(self) -> List[Product]:
        """
        Identify unsold inventory based on threshold days and sales velocity.
        
        Returns:
            List: List of unsold products
        """
        unsold_products = []
        current_time = int(time.time())
        
        for product in self.products.values():
            days_in_inventory = (current_time - product.created_at) // 86400
            product.days_in_inventory = days_in_inventory
            
            if (days_in_inventory >= self.unsold_threshold_days and 
                product.quantity > 0 and 
                product.sales_velocity < 0.1):  # Less than 0.1 units sold per day
                
                product.is_unsold = True
                unsold_products.append(product)
            else:
                product.is_unsold = False
        
        self._save_data()
        
        if self.visible_interface:
            logger.info(f"Identified {len(unsold_products)} unsold products")
        else:
            logger.debug(f"Identified {len(unsold_products)} unsold products")
            
        return unsold_products
    
    def calculate_discount_prices(self, products: Optional[List[Product]] = None) -> Dict[str, float]:
        """
        Calculate discount prices for unsold products.
        
        Args:
            products: List of products to calculate discounts for, or None for all unsold products
            
        Returns:
            Dict: Dictionary of product IDs and discount prices
        """
        if products is None:
            products = [p for p in self.products.values() if p.is_unsold]
        
        discount_prices = {}
        
        for product in products:
            discount_price = product.price * (1 - self.discount_rate)
            
            min_price = product.cost / (1 - self.min_margin)
            discount_price = max(discount_price, min_price)
            
            discount_price = round(discount_price, 2)
            
            product.discount_price = discount_price
            discount_prices[product.product_id] = discount_price
        
        self._save_data()
        
        if self.visible_interface:
            logger.info(f"Calculated discount prices for {len(discount_prices)} products")
        else:
            logger.debug(f"Calculated discount prices for {len(discount_prices)} products")
            
        return discount_prices
    
    def calculate_competitive_prices(self, products: Optional[List[Product]] = None) -> Dict[str, float]:
        """
        Calculate competitive prices for products.
        
        Args:
            products: List of products to calculate competitive prices for, or None for all products
            
        Returns:
            Dict: Dictionary of product IDs and competitive prices
        """
        if products is None:
            products = list(self.products.values())
        
        competitive_prices = {}
        
        for product in products:
            competitor_prices = self._get_competitor_prices(product)
            
            if competitor_prices:
                min_competitor_price = min(competitor_prices)
                competitive_price = min_competitor_price * (1 - self.competitive_rate)
                
                min_price = product.cost / (1 - self.min_margin)
                competitive_price = max(competitive_price, min_price)
                
                competitive_price = round(competitive_price, 2)
                
                product.competitive_price = competitive_price
                competitive_prices[product.product_id] = competitive_price
        
        self._save_data()
        
        if self.visible_interface:
            logger.info(f"Calculated competitive prices for {len(competitive_prices)} products")
        else:
            logger.debug(f"Calculated competitive prices for {len(competitive_prices)} products")
            
        return competitive_prices
    
    def _get_competitor_prices(self, product: Product) -> List[float]:
        """
        Get competitor prices for a product.
        
        Args:
            product: Product to get competitor prices for
            
        Returns:
            List: List of competitor prices
        """
        
        return [
            product.price * 0.9,
            product.price * 1.1,
            product.price * 0.95
        ]
    
    def create_order(
        self,
        user_id: str,
        product_ids: List[str],
        quantities: List[int],
        shipping_address: Dict[str, str],
        payment_method: Dict[str, Any]
    ) -> Optional[Order]:
        """
        Create an order for unsold products.
        
        Args:
            user_id: ID of the user placing the order
            product_ids: List of product IDs to order
            quantities: List of quantities to order
            shipping_address: Shipping address
            payment_method: Payment method details
            
        Returns:
            Order: Created order, or None if creation failed
        """
        if len(product_ids) != len(quantities):
            logger.error("Product IDs and quantities must have the same length")
            return None
        
        order_products = []
        total_amount = 0.0
        
        for i, product_id in enumerate(product_ids):
            quantity = quantities[i]
            
            if product_id not in self.products:
                logger.error(f"Product {product_id} not found")
                return None
            
            product = self.products[product_id]
            
            if product.quantity < quantity:
                logger.error(f"Insufficient quantity for product {product_id}: {product.quantity} < {quantity}")
                return None
            
            price = product.discount_price if product.is_unsold and product.discount_price else product.price
            
            order_products.append({
                "product_id": product_id,
                "name": product.name,
                "sku": product.sku,
                "price": price,
                "quantity": quantity,
                "subtotal": price * quantity
            })
            
            total_amount += price * quantity
            
            product.quantity -= quantity
        
        order_id = str(uuid.uuid4())
        order = Order(
            order_id=order_id,
            user_id=user_id,
            products=order_products,
            total_amount=total_amount,
            shipping_address=shipping_address,
            payment_method=payment_method
        )
        
        self.orders[order_id] = order
        
        self._save_data()
        
        logger.info(f"Created order {order_id} for user {user_id} with {len(order_products)} products")
        return order
    
    def update_order_status(self, order_id: str, status: str) -> bool:
        """
        Update the status of an order.
        
        Args:
            order_id: ID of the order to update
            status: New status
            
        Returns:
            bool: True if update was successful
        """
        if order_id not in self.orders:
            logger.error(f"Order {order_id} not found")
            return False
        
        order = self.orders[order_id]
        order.status = status
        order.updated_at = int(time.time())
        
        self._save_data()
        
        logger.info(f"Updated order {order_id} status to {status}")
        return True
    
    def add_tracking_number(self, order_id: str, tracking_number: str, estimated_delivery: Optional[int] = None) -> bool:
        """
        Add a tracking number to an order.
        
        Args:
            order_id: ID of the order to update
            tracking_number: Tracking number
            estimated_delivery: Estimated delivery timestamp
            
        Returns:
            bool: True if update was successful
        """
        if order_id not in self.orders:
            logger.error(f"Order {order_id} not found")
            return False
        
        order = self.orders[order_id]
        order.tracking_number = tracking_number
        order.estimated_delivery = estimated_delivery
        order.updated_at = int(time.time())
        
        self._save_data()
        
        logger.info(f"Added tracking number {tracking_number} to order {order_id}")
        return True
    
    def get_unsold_products(self) -> List[Product]:
        """
        Get all unsold products.
        
        Returns:
            List: List of unsold products
        """
        return [product for product in self.products.values() if product.is_unsold]
    
    def get_product(self, product_id: str) -> Optional[Product]:
        """
        Get a product by ID.
        
        Args:
            product_id: Product ID
            
        Returns:
            Product: Product with the specified ID, or None if not found
        """
        return self.products.get(product_id)
    
    def get_order(self, order_id: str) -> Optional[Order]:
        """
        Get an order by ID.
        
        Args:
            order_id: Order ID
            
        Returns:
            Order: Order with the specified ID, or None if not found
        """
        return self.orders.get(order_id)
    
    def get_user_orders(self, user_id: str) -> List[Order]:
        """
        Get all orders for a user.
        
        Args:
            user_id: User ID
            
        Returns:
            List: List of orders for the user
        """
        return [order for order in self.orders.values() if order.user_id == user_id]
    
    def generate_inventory_report(self) -> Dict[str, Any]:
        """
        Generate a report on inventory status.
        
        Returns:
            Dict: Inventory report
        """
        total_products = len(self.products)
        unsold_products = len(self.get_unsold_products())
        total_value = sum(product.price * product.quantity for product in self.products.values())
        unsold_value = sum(product.price * product.quantity for product in self.products.values() if product.is_unsold)
        
        categories = {}
        for product in self.products.values():
            if product.category not in categories:
                categories[product.category] = {
                    "count": 0,
                    "value": 0.0,
                    "unsold_count": 0,
                    "unsold_value": 0.0
                }
            
            category = categories[product.category]
            category["count"] += 1
            category["value"] += product.price * product.quantity
            
            if product.is_unsold:
                category["unsold_count"] += 1
                category["unsold_value"] += product.price * product.quantity
        
        platforms = {}
        for product in self.products.values():
            if product.platform not in platforms:
                platforms[product.platform] = {
                    "count": 0,
                    "value": 0.0,
                    "unsold_count": 0,
                    "unsold_value": 0.0
                }
            
            platform = platforms[product.platform]
            platform["count"] += 1
            platform["value"] += product.price * product.quantity
            
            if product.is_unsold:
                platform["unsold_count"] += 1
                platform["unsold_value"] += product.price * product.quantity
        
        return {
            "total_products": total_products,
            "unsold_products": unsold_products,
            "unsold_percentage": (unsold_products / total_products) * 100 if total_products > 0 else 0,
            "total_value": total_value,
            "unsold_value": unsold_value,
            "unsold_value_percentage": (unsold_value / total_value) * 100 if total_value > 0 else 0,
            "categories": categories,
            "platforms": platforms,
            "generated_at": int(time.time())
        }

    def _start_optimization_thread(self):
        """
        Start the background optimization thread for autonomous inventory management.
        This thread continuously optimizes inventory pricing and identifies unsold products.
        """
        import threading
        
        if self._optimization_thread is not None and self._optimization_thread.is_alive():
            return
        
        self._optimization_active = True
        self._optimization_thread = threading.Thread(
            target=self._optimization_loop,
            daemon=True
        )
        self._optimization_thread.start()
        
        if self.visible_interface:
            logger.info("Started inventory optimization thread")
        else:
            logger.debug("Started inventory optimization thread")
    
    def _optimization_loop(self):
        """
        Background loop for continuous inventory optimization.
        Runs in a separate thread when auto_optimization is enabled.
        """
        import time
        
        while self._optimization_active:
            try:
                # Identify unsold inventory
                unsold_products = self.identify_unsold_inventory()
                
                # Calculate discount prices for unsold products
                if unsold_products:
                    self.calculate_discount_prices(unsold_products)
                
                # Calculate competitive prices for all products
                self.calculate_competitive_prices()
                
                # Generate inventory report
                report = self.generate_inventory_report()
                
                if self.visible_interface:
                    logger.info(f"Auto-optimization completed: {len(unsold_products)} unsold products identified")
                    logger.info(f"Unsold value percentage: {report['unsold_value_percentage']:.2f}%")
                else:
                    logger.debug(f"Auto-optimization completed: {len(unsold_products)} unsold products identified")
                
                if len(self.products) > 1000:
                    self._optimization_interval = 7200  # 2 hours for large inventory
                elif len(self.products) > 500:
                    self._optimization_interval = 3600  # 1 hour for medium inventory
                else:
                    self._optimization_interval = 1800  # 30 minutes for small inventory
                
                time.sleep(self._optimization_interval)
                
            except Exception as e:
                logger.error(f"Error in inventory optimization loop: {str(e)}")
                time.sleep(300)  # 5 minutes
    
    def stop_optimization(self):
        """
        Stop the background optimization thread.
        """
        self._optimization_active = False
        
        if self.visible_interface:
            logger.info("Stopped inventory optimization thread")
        else:
            logger.debug("Stopped inventory optimization thread")


def create_inventory_manager(
    data_dir: str = "data/ecommerce",
    autonomous_mode: bool = False,
    visible_interface: bool = True,
    auto_optimization: bool = False
) -> InventoryManager:
    """
    Create a new inventory manager.
    
    Args:
        data_dir: Directory for storing data
        autonomous_mode: Whether to operate in autonomous mode without user intervention
        visible_interface: Whether to show detailed information in the interface
        auto_optimization: Whether to automatically optimize inventory in the background
        
    Returns:
        InventoryManager: New inventory manager instance
    """
    return InventoryManager(
        data_dir=data_dir,
        autonomous_mode=autonomous_mode,
        visible_interface=visible_interface,
        auto_optimization=auto_optimization
    )

"""
Pricing optimizer for e-commerce module.
Handles dynamic pricing, discount calculations, and competitive pricing analysis.
"""
import logging
import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class PricingOptimizer:
    """
    Optimizes pricing for products based on various factors:
    - Days in inventory
    - Market demand
    - Competitor pricing
    - Profit margins
    - Seasonal factors
    """
    
    def __init__(
        self,
        min_margin: float = 0.05,
        max_discount: float = 0.70,
        discount_curve_steepness: float = 0.1,
        inventory_age_threshold: int = 30,
        competitor_weight: float = 0.3,
        demand_weight: float = 0.4,
        seasonality_weight: float = 0.3
    ):
        """
        Initialize the pricing optimizer.
        
        Args:
            min_margin: Minimum profit margin to maintain (0.05 = 5%)
            max_discount: Maximum discount to apply (0.70 = 70%)
            discount_curve_steepness: How quickly discounts increase with age
            inventory_age_threshold: Days before applying aggressive discounts
            competitor_weight: Weight of competitor prices in calculation
            demand_weight: Weight of demand factors in calculation
            seasonality_weight: Weight of seasonal factors in calculation
        """
        self.min_margin = min_margin
        self.max_discount = max_discount
        self.discount_curve_steepness = discount_curve_steepness
        self.inventory_age_threshold = inventory_age_threshold
        self.competitor_weight = competitor_weight
        self.demand_weight = demand_weight
        self.seasonality_weight = seasonality_weight
        
        logger.info(f"PricingOptimizer initialized with min_margin={min_margin}, max_discount={max_discount}")
    
    def calculate_age_based_discount(self, days_in_inventory: int) -> float:
        """
        Calculate discount based on inventory age using a sigmoid function.
        
        Args:
            days_in_inventory: Number of days the product has been in inventory
            
        Returns:
            float: Discount factor (0.0 to max_discount)
        """
        if days_in_inventory <= 0:
            return 0.0
            
        x = days_in_inventory - self.inventory_age_threshold
        sigmoid = 1 / (1 + np.exp(-self.discount_curve_steepness * x))
        
        discount = sigmoid * self.max_discount
        
        return min(discount, self.max_discount)
    
    def calculate_competitive_price(
        self,
        product_id: str,
        original_price: float,
        competitor_prices: List[float],
        cost_price: float
    ) -> float:
        """
        Calculate competitive price based on competitor pricing.
        
        Args:
            product_id: Product identifier
            original_price: Original product price
            competitor_prices: List of competitor prices for similar products
            cost_price: Cost price of the product
            
        Returns:
            float: Competitive price
        """
        if not competitor_prices:
            return original_price
            
        mean_price = np.mean(competitor_prices)
        std_price = np.std(competitor_prices)
        filtered_prices = [p for p in competitor_prices if abs(p - mean_price) <= 2 * std_price]
        
        if not filtered_prices:
            return original_price
            
        avg_competitor_price = np.mean(filtered_prices)
        target_price = avg_competitor_price * 0.95
        
        min_price = cost_price * (1 + self.min_margin)
        
        competitive_price = max(target_price, min_price)
        
        logger.info(f"Calculated competitive price for product {product_id}: {competitive_price:.2f} (original: {original_price:.2f})")
        
        return competitive_price
    
    def optimize_price(
        self,
        product_id: str,
        original_price: float,
        cost_price: float,
        days_in_inventory: int,
        competitor_prices: Optional[List[float]] = None,
        demand_factor: Optional[float] = None,
        seasonality_factor: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Calculate optimized price based on all factors.
        
        Args:
            product_id: Product identifier
            original_price: Original product price
            cost_price: Cost price of the product
            days_in_inventory: Number of days the product has been in inventory
            competitor_prices: List of competitor prices for similar products
            demand_factor: Factor representing current demand (0.0-2.0)
            seasonality_factor: Factor representing seasonal effects (0.0-2.0)
            
        Returns:
            Dict: Optimized pricing information
        """
        age_discount = self.calculate_age_based_discount(days_in_inventory)
        
        if competitor_prices:
            competitive_price = self.calculate_competitive_price(
                product_id, original_price, competitor_prices, cost_price
            )
        else:
            competitive_price = original_price
        
        if demand_factor is not None:
            demand_adjusted_price = original_price * demand_factor
        else:
            demand_adjusted_price = original_price
        
        if seasonality_factor is not None:
            seasonality_adjusted_price = original_price * seasonality_factor
        else:
            seasonality_adjusted_price = original_price
        
        weighted_price = (
            competitive_price * self.competitor_weight +
            demand_adjusted_price * self.demand_weight +
            seasonality_adjusted_price * self.seasonality_weight
        )
        
        discounted_price = weighted_price * (1 - age_discount)
        
        min_price = cost_price * (1 + self.min_margin)
        final_price = max(discounted_price, min_price)
        
        discount_percentage = (original_price - final_price) / original_price
        
        profit_margin = (final_price - cost_price) / final_price
        
        logger.info(f"Optimized price for product {product_id}: {final_price:.2f} (discount: {discount_percentage:.2%})")
        
        return {
            "product_id": product_id,
            "original_price": original_price,
            "optimized_price": final_price,
            "discount_percentage": discount_percentage,
            "profit_margin": profit_margin,
            "days_in_inventory": days_in_inventory,
            "age_discount": age_discount,
            "timestamp": datetime.now().isoformat()
        }
    
    def batch_optimize(
        self,
        products: List[Dict[str, Any]],
        competitor_data: Optional[Dict[str, List[float]]] = None,
        demand_data: Optional[Dict[str, float]] = None,
        seasonality_data: Optional[Dict[str, float]] = None
    ) -> List[Dict[str, Any]]:
        """
        Optimize pricing for a batch of products.
        
        Args:
            products: List of product dictionaries with required fields
            competitor_data: Dictionary mapping product_id to competitor prices
            demand_data: Dictionary mapping product_id to demand factor
            seasonality_data: Dictionary mapping product_id to seasonality factor
            
        Returns:
            List[Dict]: List of optimized pricing information for each product
        """
        results = []
        
        for product in products:
            product_id = product.get("product_id")
            if not product_id:
                logger.warning(f"Product missing product_id: {product}")
                continue
                
            original_price = product.get("price")
            if original_price is None:
                logger.warning(f"Product {product_id} missing price")
                continue
                
            cost_price = product.get("cost_price")
            if cost_price is None:
                logger.warning(f"Product {product_id} missing cost_price")
                continue
                
            days_in_inventory = product.get("days_in_inventory", 0)
            
            competitor_prices = None
            if competitor_data and product_id in competitor_data:
                competitor_prices = competitor_data[product_id]
            
            demand_factor = None
            if demand_data and product_id in demand_data:
                demand_factor = demand_data[product_id]
            
            seasonality_factor = None
            if seasonality_data and product_id in seasonality_data:
                seasonality_factor = seasonality_data[product_id]
            
            optimized = self.optimize_price(
                product_id=product_id,
                original_price=original_price,
                cost_price=cost_price,
                days_in_inventory=days_in_inventory,
                competitor_prices=competitor_prices,
                demand_factor=demand_factor,
                seasonality_factor=seasonality_factor
            )
            
            results.append(optimized)
        
        return results
    
    def identify_unsold_inventory(
        self,
        products: List[Dict[str, Any]],
        age_threshold: int = None,
        margin_threshold: float = None
    ) -> List[Dict[str, Any]]:
        """
        Identify unsold inventory that needs attention.
        
        Args:
            products: List of product dictionaries
            age_threshold: Override for inventory_age_threshold
            margin_threshold: Minimum margin to maintain
            
        Returns:
            List[Dict]: List of products that need attention
        """
        if age_threshold is None:
            age_threshold = self.inventory_age_threshold
            
        if margin_threshold is None:
            margin_threshold = self.min_margin
        
        unsold_products = []
        
        for product in products:
            days_in_inventory = product.get("days_in_inventory", 0)
            
            if days_in_inventory >= age_threshold:
                price = product.get("price", 0)
                cost_price = product.get("cost_price", 0)
                
                if price > 0:
                    current_margin = (price - cost_price) / price
                else:
                    current_margin = 0
                
                unsold_product = product.copy()
                unsold_product["current_margin"] = current_margin
                unsold_product["age_discount"] = self.calculate_age_based_discount(days_in_inventory)
                unsold_product["needs_attention"] = current_margin <= margin_threshold
                
                unsold_products.append(unsold_product)
        
        return unsold_products

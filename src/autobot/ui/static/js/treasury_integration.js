/**
 * Treasury Integration for AUTOBOT
 * Provides functionality for integrating with the treasury system for product ordering
 */

// Global variables
let treasuryBalance = 0;
let orderTotal = 0;

/**
 * Initialize treasury integration
 */
function initTreasuryIntegration() {
    // Load initial treasury balance
    loadTreasuryBalance();
    
    console.log('Treasury integration initialized');
}

/**
 * Load treasury balance from the server
 */
function loadTreasuryBalance() {
    // Fetch treasury balance
    fetch('/api/treasury/balance')
        .then(response => response.json())
        .then(data => {
            updateTreasuryBalance(data.balance);
        })
        .catch(error => {
            console.error('Error loading treasury balance:', error);
            
            // For demo purposes, set a default balance
            updateTreasuryBalance(1500.00);
        });
}

/**
 * Update treasury balance display
 */
function updateTreasuryBalance(balance) {
    treasuryBalance = balance;
    
    // Update balance display
    const balanceElement = document.querySelector('.balance-amount');
    if (balanceElement) {
        balanceElement.textContent = `${balance.toFixed(2)} €`;
    }
    
    // Update treasury integration
    updateTreasuryIntegration();
}

/**
 * Update treasury integration based on selected products and shipping
 */
function updateTreasuryIntegration() {
    // Calculate order total
    calculateOrderTotal();
    
    // Update order summary
    updateOrderSummary();
    
    // Update action buttons state
    const orderBtn = document.querySelector('[onclick="orderSelected()"]');
    if (orderBtn) {
        const sufficientBalance = treasuryBalance >= orderTotal;
        
        if (!sufficientBalance && orderTotal > 0) {
            orderBtn.classList.add('disabled');
            orderBtn.disabled = true;
            orderBtn.title = 'Solde insuffisant';
        } else {
            orderBtn.classList.remove('disabled');
            orderBtn.disabled = selectedProducts.length === 0;
            orderBtn.title = '';
        }
    }
}

/**
 * Calculate order total based on selected products and shipping
 */
function calculateOrderTotal() {
    orderTotal = 0;
    
    // Add product prices
    const selectedCheckboxes = document.querySelectorAll('.product-checkbox:checked');
    selectedCheckboxes.forEach(checkbox => {
        const productItem = checkbox.closest('.product-item');
        const priceElement = productItem.querySelector('.product-price');
        
        if (priceElement) {
            const priceText = priceElement.textContent;
            const price = parseFloat(priceText.replace('€', '').trim());
            
            if (!isNaN(price)) {
                orderTotal += price;
            }
        }
    });
    
    // Add shipping cost
    const selectedShipping = document.querySelector('.shipping-option.selected');
    if (selectedShipping) {
        const shippingPriceElement = selectedShipping.querySelector('.shipping-price');
        
        if (shippingPriceElement) {
            const priceText = shippingPriceElement.textContent;
            const price = parseFloat(priceText.replace('€', '').trim());
            
            if (!isNaN(price)) {
                orderTotal += price;
            }
        }
    }
}

/**
 * Update order summary
 */
function updateOrderSummary() {
    const orderTotalElement = document.querySelector('.order-total-amount');
    if (orderTotalElement) {
        orderTotalElement.textContent = `${orderTotal.toFixed(2)} €`;
    }
    
    const balanceAfterElement = document.querySelector('.balance-after-amount');
    if (balanceAfterElement) {
        const balanceAfter = treasuryBalance - orderTotal;
        balanceAfterElement.textContent = `${balanceAfter.toFixed(2)} €`;
        
        // Add warning class if balance after is negative
        if (balanceAfter < 0) {
            balanceAfterElement.classList.add('negative-balance');
        } else {
            balanceAfterElement.classList.remove('negative-balance');
        }
    }
}

/**
 * Check if treasury balance is sufficient for the order
 */
function checkTreasuryBalance() {
    return new Promise((resolve, reject) => {
        // Calculate order total
        calculateOrderTotal();
        
        // Check if balance is sufficient
        const sufficientBalance = treasuryBalance >= orderTotal;
        
        resolve(sufficientBalance);
    });
}

// Initialize treasury integration when DOM is loaded
document.addEventListener('DOMContentLoaded', initTreasuryIntegration);

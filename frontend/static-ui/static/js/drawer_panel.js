
/**
 * Drawer Panel for Unsold Products
 * Provides functionality for managing unsold products with options to recycle or order
 */

document.addEventListener('DOMContentLoaded', function() {
    // Initialize drawer panel
    initDrawerPanel();
    
    // Initialize product selection
    initProductSelection();
    
    // Initialize shipping options
    initShippingOptions();
    
    // Initialize treasury integration
    initTreasuryIntegration();
});

function initDrawerPanel() {
    const drawerTrigger = document.querySelector('.drawer-trigger');
    const drawerPanel = document.querySelector('.drawer-panel');
    const drawerClose = document.querySelector('.drawer-panel-close');
    
    if (drawerTrigger && drawerPanel) {
        drawerTrigger.addEventListener('click', function() {
            drawerPanel.classList.add('open');
        });
        
        if (drawerClose) {
            drawerClose.addEventListener('click', function() {
                drawerPanel.classList.remove('open');
            });
        }
    }
}

function initProductSelection() {
    const productCheckboxes = document.querySelectorAll('.product-checkbox');
    const recycleAllBtn = document.getElementById('recycle-all');
    const orderAllBtn = document.getElementById('order-all');
    
    if (productCheckboxes.length > 0) {
        // Individual product selection
        productCheckboxes.forEach(checkbox => {
            checkbox.addEventListener('change', updateOrderSummary);
        });
        
        // Recycle all button
        if (recycleAllBtn) {
            recycleAllBtn.addEventListener('click', function() {
                const selectedProducts = getSelectedProducts();
                if (selectedProducts.length > 0) {
                    if (confirm('Etes-vous sur de vouloir recycler tous les produits selectionnes?')) {
                        recycleProducts(selectedProducts);
                    }
                } else {
                    alert('Veuillez selectionner au moins un produit.');
                }
            });
        }
        
        // Order all button
        if (orderAllBtn) {
            orderAllBtn.addEventListener('click', function() {
                const selectedProducts = getSelectedProducts();
                if (selectedProducts.length > 0) {
                    processOrder(selectedProducts);
                } else {
                    alert('Veuillez selectionner au moins un produit.');
                }
            });
        }
    }
}

function initShippingOptions() {
    const shippingOptions = document.querySelectorAll('input[name="shipping-option"]');
    
    if (shippingOptions.length > 0) {
        shippingOptions.forEach(option => {
            option.addEventListener('change', updateOrderSummary);
        });
    }
}

function initTreasuryIntegration() {
    // Fetch treasury balance
    fetchTreasuryBalance();
    
    // Initialize order processing
    const confirmOrderBtn = document.getElementById('confirm-order');
    if (confirmOrderBtn) {
        confirmOrderBtn.addEventListener('click', function() {
            const selectedProducts = getSelectedProducts();
            const selectedShipping = getSelectedShipping();
            
            if (selectedProducts.length > 0 && selectedShipping) {
                if (confirm('Confirmer la commande?')) {
                    processPayment(selectedProducts, selectedShipping);
                }
            } else {
                alert('Veuillez selectionner des produits et une option d\'expedition.');
            }
        });
    }
}

function getSelectedProducts() {
    const checkboxes = document.querySelectorAll('.product-checkbox:checked');
    return Array.from(checkboxes).map(checkbox => {
        const productItem = checkbox.closest('.product-item');
        return {
            id: checkbox.value,
            name: productItem.querySelector('.product-name').textContent,
            price: parseFloat(productItem.querySelector('.product-price').dataset.price)
        };
    });
}

function getSelectedShipping() {
    const selectedOption = document.querySelector('input[name="shipping-option"]:checked');
    if (selectedOption) {
        return {
            id: selectedOption.value,
            name: selectedOption.nextElementSibling.textContent,
            price: parseFloat(selectedOption.dataset.price)
        };
    }
    return null;
}

function updateOrderSummary() {
    const selectedProducts = getSelectedProducts();
    const selectedShipping = getSelectedShipping();
    const orderSummary = document.querySelector('.order-summary');
    
    if (orderSummary) {
        let subtotal = 0;
        let shippingCost = 0;
        
        // Calculate product subtotal
        selectedProducts.forEach(product => {
            subtotal += product.price;
        });
        
        // Add shipping cost
        if (selectedShipping) {
            shippingCost = selectedShipping.price;
        }
        
        // Calculate total
        const total = subtotal + shippingCost;
        
        // Update summary HTML
        orderSummary.innerHTML = `
            <h4>Recapitulatif de commande</h4>
            <div class="d-flex justify-content-between">
                <span>Produits (${selectedProducts.length}):</span>
                <span>${subtotal.toFixed(2)} €</span>
            </div>
            <div class="d-flex justify-content-between">
                <span>Expedition:</span>
                <span>${shippingCost.toFixed(2)} €</span>
            </div>
            <div class="d-flex justify-content-between font-weight-bold mt-2">
                <span>Total:</span>
                <span>${total.toFixed(2)} €</span>
            </div>
        `;
    }
}

function fetchTreasuryBalance() {
    // Simulate API call to get treasury balance
    const treasuryBalance = 5000.00; // Example balance
    const balanceElement = document.querySelector('.treasury-balance-amount');
    
    if (balanceElement) {
        balanceElement.textContent = `${treasuryBalance.toFixed(2)} €`;
    }
}

function recycleProducts(products) {
    // Simulate API call to recycle products
    console.log('Recycling products:', products);
    
    // Show success message
    alert(`${products.length} produits ont ete recycles avec succes.`);
    
    // Remove recycled products from the list
    products.forEach(product => {
        const checkbox = document.querySelector(`.product-checkbox[value="${product.id}"]`);
        if (checkbox) {
            const productItem = checkbox.closest('.product-item');
            productItem.remove();
        }
    });
    
    // Update order summary
    updateOrderSummary();
}

function processOrder(products) {
    // Check if shipping option is selected
    const shipping = getSelectedShipping();
    if (!shipping) {
        alert('Veuillez selectionner une option d\'expedition.');
        return;
    }
    
    // Calculate total cost
    let total = 0;
    products.forEach(product => {
        total += product.price;
    });
    total += shipping.price;
    
    // Check treasury balance
    const balanceElement = document.querySelector('.treasury-balance-amount');
    const balance = parseFloat(balanceElement.textContent);
    
    if (balance < total) {
        alert('Solde de tresorerie insuffisant pour cette commande.');
        return;
    }
    
    // Process payment
    processPayment(products, shipping);
}

function processPayment(products, shipping) {
    // Simulate API call to process payment
    console.log('Processing payment for:', products);
    console.log('Shipping option:', shipping);
    
    // Calculate total
    let total = 0;
    products.forEach(product => {
        total += product.price;
    });
    total += shipping.price;
    
    // Update treasury balance
    const balanceElement = document.querySelector('.treasury-balance-amount');
    const currentBalance = parseFloat(balanceElement.textContent);
    const newBalance = currentBalance - total;
    balanceElement.textContent = `${newBalance.toFixed(2)} €`;
    
    // Show success message
    alert(`Commande traitee avec succes. Montant: ${total.toFixed(2)} €`);
    
    // Remove ordered products from the list
    products.forEach(product => {
        const checkbox = document.querySelector(`.product-checkbox[value="${product.id}"]`);
        if (checkbox) {
            const productItem = checkbox.closest('.product-item');
            productItem.remove();
        }
    });
    
    // Update order summary
    updateOrderSummary();
}

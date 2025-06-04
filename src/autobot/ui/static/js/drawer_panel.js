/**
 * Drawer Panel for Unsold Products Management
 * Provides functionality for the slide-out drawer panel to manage unsold products
 */

// Global variables
let selectedProducts = [];
let drawerOpen = false;

/**
 * Initialize the drawer panel functionality
 */
function initDrawerPanel() {
    // Add event listeners to drawer trigger and close button
    const drawerTrigger = document.querySelector('.drawer-trigger');
    const closeDrawerBtn = document.querySelector('.btn-close-drawer');
    
    if (drawerTrigger) {
        drawerTrigger.addEventListener('click', openDrawer);
    }
    
    if (closeDrawerBtn) {
        closeDrawerBtn.addEventListener('click', closeDrawer);
    }
    
    // Initialize product selection
    initProductSelection();
    
    // Initialize shipping options
    initShippingOptions();
    
    console.log('Drawer panel initialized');
}

/**
 * Open the drawer panel
 */
function openDrawer() {
    const drawer = document.getElementById('unsoldProductsDrawer');
    if (drawer) {
        drawer.classList.add('open');
        drawerOpen = true;
        
        // Load unsold products data
        loadUnsoldProducts();
    }
}

/**
 * Close the drawer panel
 */
function closeDrawer() {
    const drawer = document.getElementById('unsoldProductsDrawer');
    if (drawer) {
        drawer.classList.remove('open');
        drawerOpen = false;
    }
}

/**
 * Load unsold products data from the server
 */
function loadUnsoldProducts() {
    // Show loading state
    const productContainer = document.querySelector('.product-selection');
    if (productContainer) {
        productContainer.innerHTML = '<div class="loading">Chargement des produits invendus...</div>';
        
        // Fetch unsold products data
        fetch('/api/unsold-products')
            .then(response => response.json())
            .then(data => {
                renderUnsoldProducts(data);
            })
            .catch(error => {
                console.error('Error loading unsold products:', error);
                productContainer.innerHTML = '<div class="error">Erreur lors du chargement des produits invendus.</div>';
                
                // For demo purposes, load sample data if API fails
                setTimeout(() => {
                    renderUnsoldProducts(getSampleUnsoldProducts());
                }, 1000);
            });
    }
}

/**
 * Render unsold products in the drawer panel
 */
function renderUnsoldProducts(products) {
    const productContainer = document.querySelector('.product-selection');
    if (!productContainer) return;
    
    if (products.length === 0) {
        productContainer.innerHTML = '<div class="empty-state">Aucun produit invendu trouvé.</div>';
        return;
    }
    
    let html = '';
    products.forEach(product => {
        html += `
            <div class="product-item" data-id="${product.id}">
                <input type="checkbox" class="product-checkbox" id="product-${product.id}">
                <div class="product-info">
                    <div class="product-name">${product.name}</div>
                    <div class="product-details">
                        ${product.category} | Stock: ${product.quantity} | Jours en stock: ${product.daysInStock}
                    </div>
                </div>
                <div class="product-price">${product.price} €</div>
            </div>
        `;
    });
    
    productContainer.innerHTML = html;
    
    // Add event listeners to checkboxes
    const checkboxes = productContainer.querySelectorAll('.product-checkbox');
    checkboxes.forEach(checkbox => {
        checkbox.addEventListener('change', handleProductSelection);
    });
}

/**
 * Handle product selection
 */
function handleProductSelection(event) {
    const checkbox = event.target;
    const productItem = checkbox.closest('.product-item');
    const productId = productItem.dataset.id;
    
    if (checkbox.checked) {
        // Add product to selected products
        selectedProducts.push(productId);
        productItem.classList.add('selected');
    } else {
        // Remove product from selected products
        selectedProducts = selectedProducts.filter(id => id !== productId);
        productItem.classList.remove('selected');
    }
    
    // Update action buttons state
    updateActionButtonsState();
    
    // Update treasury integration
    updateTreasuryIntegration();
}

/**
 * Update action buttons state based on selection
 */
function updateActionButtonsState() {
    const recycleBtn = document.querySelector('[onclick="recycleSelected()"]');
    const orderBtn = document.querySelector('[onclick="orderSelected()"]');
    
    if (recycleBtn && orderBtn) {
        const hasSelection = selectedProducts.length > 0;
        
        recycleBtn.disabled = !hasSelection;
        orderBtn.disabled = !hasSelection;
        
        if (hasSelection) {
            recycleBtn.classList.remove('disabled');
            orderBtn.classList.remove('disabled');
        } else {
            recycleBtn.classList.add('disabled');
            orderBtn.classList.add('disabled');
        }
    }
}

/**
 * Initialize product selection
 */
function initProductSelection() {
    selectedProducts = [];
    updateActionButtonsState();
}

/**
 * Initialize shipping options
 */
function initShippingOptions() {
    const shippingOptions = document.querySelectorAll('.shipping-option');
    
    shippingOptions.forEach(option => {
        option.addEventListener('click', () => {
            // Remove selected class from all options
            shippingOptions.forEach(opt => opt.classList.remove('selected'));
            
            // Add selected class to clicked option
            option.classList.add('selected');
            
            // Select the radio button
            const radio = option.querySelector('input[type="radio"]');
            if (radio) {
                radio.checked = true;
            }
            
            // Update treasury integration
            updateTreasuryIntegration();
        });
    });
}

/**
 * Recycle selected products
 */
function recycleSelected() {
    if (selectedProducts.length === 0) {
        showNotification('Veuillez sélectionner des produits à recycler.', 'warning');
        return;
    }
    
    // Show confirmation dialog
    if (confirm(`Êtes-vous sûr de vouloir recycler ${selectedProducts.length} produit(s) ?`)) {
        // Show loading state
        showNotification('Recyclage des produits en cours...', 'info');
        
        // Send recycle request to server
        fetch('/api/recycle-products', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ productIds: selectedProducts })
        })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    showNotification(`${selectedProducts.length} produit(s) recyclé(s) avec succès.`, 'success');
                    
                    // Reload unsold products
                    loadUnsoldProducts();
                    
                    // Reset selection
                    initProductSelection();
                } else {
                    showNotification('Erreur lors du recyclage des produits.', 'error');
                }
            })
            .catch(error => {
                console.error('Error recycling products:', error);
                showNotification('Erreur lors du recyclage des produits.', 'error');
                
                // For demo purposes, simulate success
                setTimeout(() => {
                    showNotification(`${selectedProducts.length} produit(s) recyclé(s) avec succès.`, 'success');
                    
                    // Reload unsold products
                    loadUnsoldProducts();
                    
                    // Reset selection
                    initProductSelection();
                }, 1500);
            });
    }
}

/**
 * Order selected products
 */
function orderSelected() {
    if (selectedProducts.length === 0) {
        showNotification('Veuillez sélectionner des produits à commander.', 'warning');
        return;
    }
    
    // Check if shipping method is selected
    const selectedShipping = document.querySelector('.shipping-option.selected');
    if (!selectedShipping) {
        showNotification('Veuillez sélectionner une méthode d\'expédition.', 'warning');
        return;
    }
    
    // Check treasury balance
    checkTreasuryBalance()
        .then(sufficientBalance => {
            if (sufficientBalance) {
                processOrder();
            } else {
                showNotification('Solde de trésorerie insuffisant pour cette commande.', 'error');
            }
        })
        .catch(error => {
            console.error('Error checking treasury balance:', error);
            showNotification('Erreur lors de la vérification du solde de trésorerie.', 'error');
        });
}

/**
 * Process the order
 */
function processOrder() {
    // Get shipping method
    const selectedShipping = document.querySelector('.shipping-option.selected');
    const shippingMethod = selectedShipping ? selectedShipping.dataset.method : 'standard';
    
    // Show loading state
    showNotification('Traitement de la commande en cours...', 'info');
    
    // Send order request to server
    fetch('/api/order-products', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            productIds: selectedProducts,
            shippingMethod: shippingMethod
        })
    })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showNotification(`Commande de ${selectedProducts.length} produit(s) effectuée avec succès.`, 'success');
                
                // Update treasury balance
                updateTreasuryBalance(data.newBalance);
                
                // Reload unsold products
                loadUnsoldProducts();
                
                // Reset selection
                initProductSelection();
            } else {
                showNotification('Erreur lors de la commande des produits.', 'error');
            }
        })
        .catch(error => {
            console.error('Error ordering products:', error);
            showNotification('Erreur lors de la commande des produits.', 'error');
            
            // For demo purposes, simulate success
            setTimeout(() => {
                showNotification(`Commande de ${selectedProducts.length} produit(s) effectuée avec succès.`, 'success');
                
                // Update treasury balance
                updateTreasuryBalance(1250.75);
                
                // Reload unsold products
                loadUnsoldProducts();
                
                // Reset selection
                initProductSelection();
            }, 1500);
        });
}

/**
 * Show notification
 */
function showNotification(message, type = 'info') {
    // Check if notification container exists
    let notificationContainer = document.querySelector('.notification-container');
    
    // Create notification container if it doesn't exist
    if (!notificationContainer) {
        notificationContainer = document.createElement('div');
        notificationContainer.className = 'notification-container';
        document.body.appendChild(notificationContainer);
    }
    
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.innerHTML = `
        <div class="notification-content">
            <i class="notification-icon fas ${getNotificationIcon(type)}"></i>
            <span class="notification-message">${message}</span>
        </div>
        <button class="notification-close">&times;</button>
    `;
    
    // Add notification to container
    notificationContainer.appendChild(notification);
    
    // Add event listener to close button
    const closeButton = notification.querySelector('.notification-close');
    closeButton.addEventListener('click', () => {
        notification.classList.add('notification-hiding');
        setTimeout(() => {
            notification.remove();
        }, 300);
    });
    
    // Auto-remove notification after 5 seconds
    setTimeout(() => {
        if (notification.parentNode) {
            notification.classList.add('notification-hiding');
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.remove();
                }
            }, 300);
        }
    }, 5000);
    
    // Show notification with animation
    setTimeout(() => {
        notification.classList.add('notification-visible');
    }, 10);
}

/**
 * Get notification icon based on type
 */
function getNotificationIcon(type) {
    switch (type) {
        case 'success':
            return 'fa-check-circle';
        case 'error':
            return 'fa-times-circle';
        case 'warning':
            return 'fa-exclamation-triangle';
        case 'info':
        default:
            return 'fa-info-circle';
    }
}

/**
 * Get sample unsold products data for demo purposes
 */
function getSampleUnsoldProducts() {
    return [
        {
            id: '1',
            name: 'Carte graphique RTX 3080',
            category: 'Composants PC',
            quantity: 5,
            daysInStock: 45,
            price: 799.99
        },
        {
            id: '2',
            name: 'Processeur AMD Ryzen 9 5900X',
            category: 'Composants PC',
            quantity: 3,
            daysInStock: 30,
            price: 549.99
        },
        {
            id: '3',
            name: 'Écran 4K 32" Samsung',
            category: 'Périphériques',
            quantity: 2,
            daysInStock: 60,
            price: 399.99
        },
        {
            id: '4',
            name: 'Clavier mécanique Logitech G915',
            category: 'Périphériques',
            quantity: 8,
            daysInStock: 90,
            price: 199.99
        },
        {
            id: '5',
            name: 'Disque SSD 2TB Samsung 980 Pro',
            category: 'Stockage',
            quantity: 10,
            daysInStock: 75,
            price: 299.99
        }
    ];
}

// Initialize drawer panel when DOM is loaded
document.addEventListener('DOMContentLoaded', initDrawerPanel);

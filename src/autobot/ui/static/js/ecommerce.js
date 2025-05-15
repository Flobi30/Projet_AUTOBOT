/**
 * E-commerce management JavaScript for AUTOBOT
 */

const productSearchInput = document.getElementById('product-search');
const categoryFilter = document.getElementById('category-filter');
const platformFilter = document.getElementById('platform-filter');
const productsTable = document.getElementById('products-table');
const productsBody = document.getElementById('products-body');
const unsoldTable = document.getElementById('unsold-table');
const unsoldBody = document.getElementById('unsold-body');
const ordersTable = document.getElementById('orders-table');
const ordersBody = document.getElementById('orders-body');
const syncInventoryBtn = document.getElementById('sync-inventory-btn');
const identifyUnsoldBtn = document.getElementById('identify-unsold-btn');
const calculateDiscountsBtn = document.getElementById('calculate-discounts-btn');

const totalProductsEl = document.getElementById('total-products');
const unsoldProductsEl = document.getElementById('unsold-products');
const totalValueEl = document.getElementById('total-value');
const unsoldValueEl = document.getElementById('unsold-value');

const tabItems = document.querySelectorAll('.tab-item');
const tabPanes = document.querySelectorAll('.tab-pane');

let inventoryChart;

let products = [];
let unsoldProducts = [];
let orders = [];
let categories = new Set();
let platforms = new Set();

document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    loadInventoryReport();
    loadProducts();
    loadUnsoldProducts();
    loadOrders();
    setupEventListeners();
});

function initTabs() {
    tabItems.forEach(item => {
        item.addEventListener('click', () => {
            tabItems.forEach(tab => tab.classList.remove('active'));
            tabPanes.forEach(pane => pane.classList.remove('active'));
            
            item.classList.add('active');
            const tabId = item.getAttribute('data-tab');
            document.getElementById(`${tabId}-tab`).classList.add('active');
        });
    });
}

function setupEventListeners() {
    productSearchInput.addEventListener('input', filterProducts);
    categoryFilter.addEventListener('change', filterProducts);
    platformFilter.addEventListener('change', filterProducts);
    
    syncInventoryBtn.addEventListener('click', syncInventory);
    identifyUnsoldBtn.addEventListener('click', identifyUnsold);
    calculateDiscountsBtn.addEventListener('click', calculateDiscounts);
    
    document.querySelectorAll('.close-modal').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.modal').forEach(modal => {
                modal.style.display = 'none';
            });
        });
    });
}

async function loadInventoryReport() {
    try {
        const response = await fetch('/ecommerce/report');
        const report = await response.json();
        
        totalProductsEl.textContent = report.total_products;
        unsoldProductsEl.textContent = report.unsold_products;
        totalValueEl.textContent = formatCurrency(report.total_value);
        unsoldValueEl.textContent = formatCurrency(report.unsold_value);
        
        createInventoryChart(report);
        
    } catch (error) {
        console.error('Error loading inventory report:', error);
        showNotification('Error loading inventory report', 'error');
    }
}

function createInventoryChart(report) {
    const ctx = document.getElementById('inventory-chart').getContext('2d');
    
    if (inventoryChart) {
        inventoryChart.destroy();
    }
    
    const categoryNames = Object.keys(report.categories);
    const categoryValues = categoryNames.map(cat => report.categories[cat].value);
    const categoryUnsoldValues = categoryNames.map(cat => report.categories[cat].unsold_value);
    
    inventoryChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: categoryNames,
            datasets: [
                {
                    label: 'Total Value',
                    data: categoryValues,
                    backgroundColor: 'rgba(0, 255, 0, 0.5)',
                    borderColor: 'rgba(0, 255, 0, 1)',
                    borderWidth: 1
                },
                {
                    label: 'Unsold Value',
                    data: categoryUnsoldValues,
                    backgroundColor: 'rgba(255, 0, 0, 0.5)',
                    borderColor: 'rgba(255, 0, 0, 1)',
                    borderWidth: 1
                }
            ]
        },
        options: {
            responsive: true,
            scales: {
                y: {
                    beginAtZero: true,
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)'
                    },
                    ticks: {
                        color: '#00ff00'
                    }
                },
                x: {
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)'
                    },
                    ticks: {
                        color: '#00ff00'
                    }
                }
            },
            plugins: {
                legend: {
                    labels: {
                        color: '#00ff00'
                    }
                }
            }
        }
    });
}

async function loadProducts() {
    try {
        const response = await fetch('/ecommerce/products');
        products = await response.json();
        
        categories = new Set();
        platforms = new Set();
        products.forEach(product => {
            categories.add(product.category);
            platforms.add(product.platform);
        });
        
        populateFilters();
        
        renderProducts();
        
    } catch (error) {
        console.error('Error loading products:', error);
        showNotification('Error loading products', 'error');
    }
}

async function loadUnsoldProducts() {
    try {
        const response = await fetch('/ecommerce/unsold');
        unsoldProducts = await response.json();
        
        renderUnsoldProducts();
        
    } catch (error) {
        console.error('Error loading unsold products:', error);
        showNotification('Error loading unsold products', 'error');
    }
}

async function loadOrders() {
    try {
        const response = await fetch('/ecommerce/orders');
        orders = await response.json();
        
        renderOrders();
        
    } catch (error) {
        console.error('Error loading orders:', error);
        showNotification('Error loading orders', 'error');
    }
}

function populateFilters() {
    categoryFilter.innerHTML = '<option value="">All Categories</option>';
    platformFilter.innerHTML = '<option value="">All Platforms</option>';
    
    categories.forEach(category => {
        const option = document.createElement('option');
        option.value = category;
        option.textContent = category;
        categoryFilter.appendChild(option);
    });
    
    platforms.forEach(platform => {
        const option = document.createElement('option');
        option.value = platform;
        option.textContent = platform;
        platformFilter.appendChild(option);
    });
}

function renderProducts() {
    productsBody.innerHTML = '';
    
    const filteredProducts = filterProductsList();
    
    filteredProducts.forEach(product => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${product.name}</td>
            <td>${product.sku}</td>
            <td>${product.category}</td>
            <td>${product.platform}</td>
            <td>${formatCurrency(product.price)}</td>
            <td>${product.quantity}</td>
            <td>${product.days_in_inventory}</td>
            <td>
                <button class="btn-icon view-product" data-id="${product.product_id}">👁️</button>
                <button class="btn-icon edit-product" data-id="${product.product_id}">✏️</button>
            </td>
        `;
        productsBody.appendChild(row);
    });
    
    document.querySelectorAll('.view-product').forEach(btn => {
        btn.addEventListener('click', () => viewProduct(btn.getAttribute('data-id')));
    });
    
    document.querySelectorAll('.edit-product').forEach(btn => {
        btn.addEventListener('click', () => editProduct(btn.getAttribute('data-id')));
    });
}

function renderUnsoldProducts() {
    unsoldBody.innerHTML = '';
    
    unsoldProducts.forEach(product => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${product.name}</td>
            <td>${product.sku}</td>
            <td>${product.category}</td>
            <td>${formatCurrency(product.price)}</td>
            <td>${product.discount_price ? formatCurrency(product.discount_price) : 'N/A'}</td>
            <td>${product.quantity}</td>
            <td>${product.days_in_inventory}</td>
            <td>
                <button class="btn-icon view-product" data-id="${product.product_id}">👁️</button>
                <button class="btn-icon order-product" data-id="${product.product_id}">🛒</button>
            </td>
        `;
        unsoldBody.appendChild(row);
    });
    
    document.querySelectorAll('.view-product').forEach(btn => {
        btn.addEventListener('click', () => viewProduct(btn.getAttribute('data-id')));
    });
    
    document.querySelectorAll('.order-product').forEach(btn => {
        btn.addEventListener('click', () => orderProduct(btn.getAttribute('data-id')));
    });
}

function renderOrders() {
    ordersBody.innerHTML = '';
    
    orders.forEach(order => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${order.order_id.substring(0, 8)}...</td>
            <td>${order.user_id.substring(0, 8)}...</td>
            <td>${order.products.length} items</td>
            <td>${formatCurrency(order.total_amount)}</td>
            <td><span class="status-badge status-${order.status}">${order.status}</span></td>
            <td>${formatDate(order.created_at)}</td>
            <td>
                <button class="btn-icon view-order" data-id="${order.order_id}">👁️</button>
                <button class="btn-icon update-order" data-id="${order.order_id}">📝</button>
            </td>
        `;
        ordersBody.appendChild(row);
    });
    
    document.querySelectorAll('.view-order').forEach(btn => {
        btn.addEventListener('click', () => viewOrder(btn.getAttribute('data-id')));
    });
    
    document.querySelectorAll('.update-order').forEach(btn => {
        btn.addEventListener('click', () => updateOrder(btn.getAttribute('data-id')));
    });
}

function filterProducts() {
    renderProducts();
}

function filterProductsList() {
    const searchTerm = productSearchInput.value.toLowerCase();
    const categoryValue = categoryFilter.value;
    const platformValue = platformFilter.value;
    
    return products.filter(product => {
        const matchesSearch = 
            product.name.toLowerCase().includes(searchTerm) ||
            product.sku.toLowerCase().includes(searchTerm) ||
            product.description.toLowerCase().includes(searchTerm);
        
        const matchesCategory = !categoryValue || product.category === categoryValue;
        
        const matchesPlatform = !platformValue || product.platform === platformValue;
        
        return matchesSearch && matchesCategory && matchesPlatform;
    });
}

function viewProduct(productId) {
    const product = products.find(p => p.product_id === productId) || 
                   unsoldProducts.find(p => p.product_id === productId);
    
    if (!product) return;
    
    const modal = document.getElementById('product-modal');
    const modalTitle = document.getElementById('product-modal-title');
    const modalBody = modal.querySelector('.modal-body');
    
    modalTitle.textContent = `Product: ${product.name}`;
    modalBody.innerHTML = `
        <div class="product-details">
            <div class="product-images">
                ${product.image_urls.length > 0 
                    ? product.image_urls.map(url => `<img src="${url}" alt="${product.name}">`).join('')
                    : '<div class="no-image">No images available</div>'
                }
            </div>
            <div class="product-info">
                <p><strong>SKU:</strong> ${product.sku}</p>
                <p><strong>Category:</strong> ${product.category}</p>
                <p><strong>Platform:</strong> ${product.platform}</p>
                <p><strong>Price:</strong> ${formatCurrency(product.price)}</p>
                <p><strong>Cost:</strong> ${formatCurrency(product.cost)}</p>
                <p><strong>Margin:</strong> ${(product.margin * 100).toFixed(2)}%</p>
                <p><strong>Quantity:</strong> ${product.quantity}</p>
                <p><strong>Days in Inventory:</strong> ${product.days_in_inventory}</p>
                <p><strong>Sales Velocity:</strong> ${product.sales_velocity.toFixed(2)} units/day</p>
                <p><strong>Unsold:</strong> ${product.is_unsold ? 'Yes' : 'No'}</p>
                ${product.discount_price 
                    ? `<p><strong>Discount Price:</strong> ${formatCurrency(product.discount_price)}</p>` 
                    : ''
                }
                ${product.competitive_price 
                    ? `<p><strong>Competitive Price:</strong> ${formatCurrency(product.competitive_price)}</p>` 
                    : ''
                }
            </div>
        </div>
        <div class="product-description">
            <h4>Description</h4>
            <p>${product.description}</p>
        </div>
        ${product.attributes && Object.keys(product.attributes).length > 0 
            ? `
                <div class="product-attributes">
                    <h4>Attributes</h4>
                    <ul>
                        ${Object.entries(product.attributes).map(([key, value]) => `
                            <li><strong>${key}:</strong> ${value}</li>
                        `).join('')}
                    </ul>
                </div>
            ` 
            : ''
        }
    `;
    
    modal.style.display = 'block';
}

function editProduct(productId) {
    console.log('Edit product:', productId);
}

function orderProduct(productId) {
    console.log('Order product:', productId);
}

function viewOrder(orderId) {
    const order = orders.find(o => o.order_id === orderId);
    if (!order) return;
    
    const modal = document.getElementById('order-modal');
    const modalTitle = document.getElementById('order-modal-title');
    const modalBody = modal.querySelector('.modal-body');
    
    modalTitle.textContent = `Order: ${order.order_id.substring(0, 8)}...`;
    modalBody.innerHTML = `
        <div class="order-info">
            <p><strong>Order ID:</strong> ${order.order_id}</p>
            <p><strong>User ID:</strong> ${order.user_id}</p>
            <p><strong>Status:</strong> <span class="status-badge status-${order.status}">${order.status}</span></p>
            <p><strong>Created:</strong> ${formatDate(order.created_at)}</p>
            <p><strong>Updated:</strong> ${formatDate(order.updated_at)}</p>
            <p><strong>Total Amount:</strong> ${formatCurrency(order.total_amount)}</p>
            ${order.tracking_number 
                ? `<p><strong>Tracking Number:</strong> ${order.tracking_number}</p>` 
                : ''
            }
            ${order.estimated_delivery 
                ? `<p><strong>Estimated Delivery:</strong> ${formatDate(order.estimated_delivery)}</p>` 
                : ''
            }
        </div>
        
        <div class="order-products">
            <h4>Products</h4>
            <table>
                <thead>
                    <tr>
                        <th>Name</th>
                        <th>SKU</th>
                        <th>Price</th>
                        <th>Quantity</th>
                        <th>Subtotal</th>
                    </tr>
                </thead>
                <tbody>
                    ${order.products.map(product => `
                        <tr>
                            <td>${product.name}</td>
                            <td>${product.sku}</td>
                            <td>${formatCurrency(product.price)}</td>
                            <td>${product.quantity}</td>
                            <td>${formatCurrency(product.subtotal)}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>
        
        <div class="shipping-info">
            <h4>Shipping Address</h4>
            <p>${order.shipping_address.name || ''}</p>
            <p>${order.shipping_address.address1 || ''}</p>
            <p>${order.shipping_address.address2 || ''}</p>
            <p>${order.shipping_address.city || ''}, ${order.shipping_address.state || ''} ${order.shipping_address.zip || ''}</p>
            <p>${order.shipping_address.country || ''}</p>
        </div>
        
        <div class="payment-info">
            <h4>Payment Method</h4>
            <p><strong>Type:</strong> ${order.payment_method.type || ''}</p>
            <p><strong>Last 4:</strong> ${order.payment_method.last4 || ''}</p>
        </div>
    `;
    
    document.getElementById('update-order-btn').setAttribute('data-id', order.order_id);
    
    modal.style.display = 'block';
}

function updateOrder(orderId) {
    console.log('Update order:', orderId);
}

async function syncInventory() {
    try {
        syncInventoryBtn.disabled = true;
        syncInventoryBtn.textContent = 'Syncing...';
        
        const response = await fetch('/ecommerce/sync', {
            method: 'POST'
        });
        
        const result = await response.json();
        
        showNotification(`Synchronized ${result.synchronized_products} products`, 'success');
        
        loadInventoryReport();
        loadProducts();
        loadUnsoldProducts();
        
    } catch (error) {
        console.error('Error syncing inventory:', error);
        showNotification('Error syncing inventory', 'error');
    } finally {
        syncInventoryBtn.disabled = false;
        syncInventoryBtn.textContent = 'Sync Inventory';
    }
}

async function identifyUnsold() {
    try {
        identifyUnsoldBtn.disabled = true;
        identifyUnsoldBtn.textContent = 'Identifying...';
        
        const response = await fetch('/ecommerce/identify-unsold', {
            method: 'POST'
        });
        
        const result = await response.json();
        
        showNotification(`Identified ${result.length} unsold products`, 'success');
        
        loadInventoryReport();
        loadUnsoldProducts();
        
    } catch (error) {
        console.error('Error identifying unsold inventory:', error);
        showNotification('Error identifying unsold inventory', 'error');
    } finally {
        identifyUnsoldBtn.disabled = false;
        identifyUnsoldBtn.textContent = 'Identify Unsold';
    }
}

async function calculateDiscounts() {
    try {
        calculateDiscountsBtn.disabled = true;
        calculateDiscountsBtn.textContent = 'Calculating...';
        
        const response = await fetch('/ecommerce/calculate-discounts', {
            method: 'POST'
        });
        
        const result = await response.json();
        
        showNotification(`Calculated discount prices for ${Object.keys(result).length} products`, 'success');
        
        loadUnsoldProducts();
        
    } catch (error) {
        console.error('Error calculating discount prices:', error);
        showNotification('Error calculating discount prices', 'error');
    } finally {
        calculateDiscountsBtn.disabled = false;
        calculateDiscountsBtn.textContent = 'Calculate Discounts';
    }
}

function formatCurrency(value) {
    return new Intl.NumberFormat('fr-FR', {
        style: 'currency',
        currency: 'EUR'
    }).format(value);
}

function formatDate(timestamp) {
    if (!timestamp) return 'N/A';
    
    const date = new Date(timestamp * 1000);
    return new Intl.DateTimeFormat('fr-FR', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    }).format(date);
}

function showNotification(message, type = 'info', duration = 5000) {
    console.log(`[${type}] ${message}`);
    
    let container = document.querySelector('.notification-container');
    if (!container) {
        container = document.createElement('div');
        container.className = 'notification-container';
        document.body.appendChild(container);
    }
    
    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    
    let icon = '';
    switch (type) {
        case 'success':
            icon = '✓';
            break;
        case 'error':
            icon = '✗';
            break;
        case 'warning':
            icon = '⚠';
            break;
        case 'info':
        default:
            icon = 'ℹ';
            break;
    }
    
    notification.innerHTML = `
        <div class="notification-icon">${icon}</div>
        <div class="notification-content">
            <div class="notification-message">${message}</div>
        </div>
        <button class="notification-close">×</button>
    `;
    
    container.appendChild(notification);
    
    const closeBtn = notification.querySelector('.notification-close');
    closeBtn.addEventListener('click', () => {
        closeNotification(notification);
    });
    
    setTimeout(() => {
        closeNotification(notification);
    }, duration);
    
    return notification;
}

function closeNotification(notification) {
    notification.classList.add('closing');
    notification.addEventListener('animationend', () => {
        notification.remove();
    });
}

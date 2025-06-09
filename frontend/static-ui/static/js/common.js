document.addEventListener('DOMContentLoaded', function() {
    console.log('AUTOBOT Common JS loaded');
    
    // Initialize modals
    initializeModals();
    
    // Initialize buttons
    initializeButtons();
    
    // Initialize API key management
    initializeApiKeyManagement();
    
    // Initialize chat functionality
    initializeChatFunctionality();
});

function initializeModals() {
    console.log('Initializing modals');
    
    // Get all modal triggers
    const modalTriggers = document.querySelectorAll('[data-modal]');
    
    modalTriggers.forEach(trigger => {
        trigger.addEventListener('click', function() {
            const modalId = this.dataset.modal;
            const modal = document.getElementById(modalId);
            
            if (modal) {
                console.log(`Opening modal: ${modalId}`);
                modal.style.display = 'block';
                
                // Add event listeners to close buttons
                const closeButtons = modal.querySelectorAll('.close-modal, .btn-secondary');
                closeButtons.forEach(button => {
                    button.addEventListener('click', function() {
                        console.log(`Closing modal: ${modalId}`);
                        modal.style.display = 'none';
                    });
                });
            }
        });
    });
    
    // Close modal when clicking outside
    window.addEventListener('click', function(event) {
        if (event.target.classList.contains('modal')) {
            console.log('Closing modal (clicked outside)');
            event.target.style.display = 'none';
        }
    });
    
    // Create deposit/withdraw modals if they don't exist
    if (!document.getElementById('depositModal')) {
        createDepositModal();
    }
    
    if (!document.getElementById('withdrawModal')) {
        createWithdrawModal();
    }
}

function initializeButtons() {
    console.log('Initializing buttons');
    
    // Get all action buttons
    const actionButtons = document.querySelectorAll('[data-action]');
    
    actionButtons.forEach(button => {
        button.addEventListener('click', function() {
            const action = this.dataset.action;
            
            if (action === 'deposit') {
                showDepositModal();
                return;
            }
            
            if (action === 'withdraw') {
                showWithdrawModal();
                return;
            }
            
            const endpoint = this.dataset.endpoint || `/api/${action}`;
            const method = this.dataset.method || 'POST';
            
            console.log(`Button clicked: ${action}, endpoint: ${endpoint}, method: ${method}`);
            
            // Show loading indicator
            showLoading();
            
            // Send request to server
            fetch(endpoint, {
                method: method,
                headers: { 'Content-Type': 'application/json' },
                body: method === 'GET' ? undefined : JSON.stringify({})
            })
            .then(response => response.json())
            .then(data => {
                hideLoading();
                showNotification(data.message || 'Action effectuée avec succès', 'success');
            })
            .catch(error => {
                hideLoading();
                showNotification('Erreur: ' + error.message, 'error');
            });
        });
    });
}

function initializeApiKeyManagement() {
    console.log('Initializing API key management');
    
    const saveApiKeysBtn = document.getElementById('saveApiKeys');
    if (saveApiKeysBtn) {
        saveApiKeysBtn.addEventListener('click', function() {
            const keys = {};
            document.querySelectorAll('.api-key-input').forEach(input => {
                keys[input.dataset.service] = input.value;
            });
            
            console.log('Saving API keys');
            showLoading();
            
            fetch('/api/keys/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(keys)
            })
            .then(response => response.json())
            .then(data => {
                hideLoading();
                showNotification(data.message || 'Clés API enregistrées avec succès', 'success');
            })
            .catch(error => {
                hideLoading();
                showNotification('Erreur: ' + error.message, 'error');
            });
        });
    }
    
    // Add copy button functionality for API keys
    document.querySelectorAll('.copy-api-key').forEach(button => {
        button.addEventListener('click', function() {
            const input = this.previousElementSibling;
            input.select();
            document.execCommand('copy');
            showNotification('Clé copiée dans le presse-papier', 'success');
        });
    });
    
    // Add show/hide functionality for API keys
    document.querySelectorAll('.toggle-api-key-visibility').forEach(button => {
        button.addEventListener('click', function() {
            const input = this.previousElementSibling.previousElementSibling;
            const type = input.type === 'password' ? 'text' : 'password';
            input.type = type;
            this.innerHTML = type === 'password' ? '<i class="fas fa-eye"></i>' : '<i class="fas fa-eye-slash"></i>';
        });
    });
}

function initializeChatFunctionality() {
    console.log('Initializing chat functionality');
    
    const chatForm = document.getElementById('chat-form');
    if (chatForm) {
        chatForm.addEventListener('submit', function(e) {
            e.preventDefault();
            
            const messageInput = document.getElementById('message-input');
            const message = messageInput.value.trim();
            
            if (!message) return;
            
            // Add user message to chat
            const chatMessages = document.getElementById('chat-messages');
            const userMessageDiv = document.createElement('div');
            userMessageDiv.className = 'message message-user';
            userMessageDiv.textContent = message;
            chatMessages.appendChild(userMessageDiv);
            
            // Clear input
            messageInput.value = '';
            
            // Show typing indicator
            const typingIndicator = document.createElement('div');
            typingIndicator.className = 'message message-bot typing';
            typingIndicator.textContent = 'Je traite votre demande...';
            chatMessages.appendChild(typingIndicator);
            
            // Scroll to bottom
            chatMessages.scrollTop = chatMessages.scrollHeight;
            
            // Send message to server
            fetch('/api/chat/message', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message })
            })
            .then(response => response.json())
            .then(data => {
                // Remove typing indicator
                chatMessages.removeChild(typingIndicator);
                
                // Add bot response
                const botMessageDiv = document.createElement('div');
                botMessageDiv.className = 'message message-bot';
                botMessageDiv.textContent = data.response;
                chatMessages.appendChild(botMessageDiv);
                
                // Scroll to bottom
                chatMessages.scrollTop = chatMessages.scrollHeight;
            })
            .catch(error => {
                // Remove typing indicator
                chatMessages.removeChild(typingIndicator);
                
                // Add error message
                const errorDiv = document.createElement('div');
                errorDiv.className = 'message message-bot error';
                errorDiv.textContent = 'Erreur de connexion. Veuillez réessayer.';
                chatMessages.appendChild(errorDiv);
                
                console.error('Error:', error);
            });
        });
    }
}

function createDepositModal() {
    const modal = document.createElement('div');
    modal.id = 'depositModal';
    modal.className = 'modal';
    modal.innerHTML = `
        <div class="modal-content">
            <div class="modal-header">
                <h2>Ajouter des fonds</h2>
                <span class="close-modal">&times;</span>
            </div>
            <div class="modal-body">
                <div class="form-group">
                    <label for="depositAmount">Montant</label>
                    <input type="number" id="depositAmount" class="form-control" min="1" step="1" placeholder="Entrez le montant">
                </div>
                <div class="form-group">
                    <label for="depositMethod">Méthode de paiement</label>
                    <select id="depositMethod" class="form-control">
                        <option value="bank">Virement bancaire</option>
                        <option value="card">Carte bancaire</option>
                        <option value="crypto">Crypto-monnaie</option>
                    </select>
                </div>
            </div>
            <div class="modal-footer">
                <button id="confirmDeposit" class="btn btn-primary">Confirmer</button>
                <button class="btn btn-secondary close-modal">Annuler</button>
            </div>
        </div>
    `;
    document.body.appendChild(modal);
    
    const closeButtons = modal.querySelectorAll('.close-modal');
    closeButtons.forEach(button => {
        button.addEventListener('click', function() {
            modal.style.display = 'none';
        });
    });
    
    const confirmButton = modal.querySelector('#confirmDeposit');
    confirmButton.addEventListener('click', function() {
        const amount = document.getElementById('depositAmount').value;
        const method = document.getElementById('depositMethod').value;
        
        if (!amount || isNaN(amount) || amount <= 0) {
            showNotification('Veuillez entrer un montant valide', 'error');
            return;
        }
        
        showLoading();
        fetch('/api/deposit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ amount: parseFloat(amount), method })
        })
        .then(response => response.json())
        .then(data => {
            hideLoading();
            modal.style.display = 'none';
            showNotification(data.message || 'Dépôt effectué avec succès', 'success');
            
            updateBalance();
        })
        .catch(error => {
            hideLoading();
            showNotification('Erreur lors du dépôt: ' + error.message, 'error');
        });
    });
}

function createWithdrawModal() {
    const modal = document.createElement('div');
    modal.id = 'withdrawModal';
    modal.className = 'modal';
    modal.innerHTML = `
        <div class="modal-content">
            <div class="modal-header">
                <h2>Retirer des fonds</h2>
                <span class="close-modal">&times;</span>
            </div>
            <div class="modal-body">
                <div class="form-group">
                    <label for="withdrawAmount">Montant</label>
                    <input type="number" id="withdrawAmount" class="form-control" min="1" step="1" placeholder="Entrez le montant">
                </div>
                <div class="form-group">
                    <label for="withdrawMethod">Méthode de retrait</label>
                    <select id="withdrawMethod" class="form-control">
                        <option value="bank">Virement bancaire</option>
                        <option value="card">Carte bancaire</option>
                        <option value="crypto">Crypto-monnaie</option>
                    </select>
                </div>
                <div class="form-group">
                    <label for="withdrawAddress">Adresse de retrait</label>
                    <input type="text" id="withdrawAddress" class="form-control" placeholder="Entrez l'adresse de retrait">
                </div>
            </div>
            <div class="modal-footer">
                <button id="confirmWithdraw" class="btn btn-primary">Confirmer</button>
                <button class="btn btn-secondary close-modal">Annuler</button>
            </div>
        </div>
    `;
    document.body.appendChild(modal);
    
    const closeButtons = modal.querySelectorAll('.close-modal');
    closeButtons.forEach(button => {
        button.addEventListener('click', function() {
            modal.style.display = 'none';
        });
    });
    
    const confirmButton = modal.querySelector('#confirmWithdraw');
    confirmButton.addEventListener('click', function() {
        const amount = document.getElementById('withdrawAmount').value;
        const method = document.getElementById('withdrawMethod').value;
        const address = document.getElementById('withdrawAddress').value;
        
        if (!amount || isNaN(amount) || amount <= 0) {
            showNotification('Veuillez entrer un montant valide', 'error');
            return;
        }
        
        if (!address) {
            showNotification('Veuillez entrer une adresse de retrait', 'error');
            return;
        }
        
        showLoading();
        fetch('/api/withdraw', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                amount: parseFloat(amount), 
                method,
                address
            })
        })
        .then(response => response.json())
        .then(data => {
            hideLoading();
            modal.style.display = 'none';
            showNotification(data.message || 'Retrait effectué avec succès', 'success');
            
            updateBalance();
        })
        .catch(error => {
            hideLoading();
            showNotification('Erreur lors du retrait: ' + error.message, 'error');
        });
    });
}

function showDepositModal() {
    const modal = document.getElementById('depositModal');
    if (modal) {
        modal.style.display = 'block';
    }
}

function showWithdrawModal() {
    const modal = document.getElementById('withdrawModal');
    if (modal) {
        modal.style.display = 'block';
    }
}

function updateBalance() {
    fetch('/api/balance')
        .then(response => response.json())
        .then(data => {
            const balanceElements = document.querySelectorAll('.balance-amount');
            balanceElements.forEach(element => {
                element.textContent = data.balance.toFixed(2) + ' €';
            });
        })
        .catch(error => {
            console.error('Error fetching balance:', error);
        });
}

function showLoading() {
    let loadingOverlay = document.getElementById('loadingOverlay');
    
    if (!loadingOverlay) {
        loadingOverlay = document.createElement('div');
        loadingOverlay.id = 'loadingOverlay';
        loadingOverlay.className = 'loading-overlay';
        loadingOverlay.innerHTML = '<div class="loading-spinner"></div>';
        document.body.appendChild(loadingOverlay);
        
        // Add styles if not already present
        if (!document.getElementById('loadingStyles')) {
            const style = document.createElement('style');
            style.id = 'loadingStyles';
            style.textContent = `
                .loading-overlay {
                    position: fixed;
                    top: 0;
                    left: 0;
                    width: 100%;
                    height: 100%;
                    background-color: rgba(0, 0, 0, 0.7);
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    z-index: 9999;
                }
                .loading-spinner {
                    width: 50px;
                    height: 50px;
                    border: 5px solid rgba(0, 255, 157, 0.3);
                    border-radius: 50%;
                    border-top-color: #00ff9d;
                    animation: spin 1s ease-in-out infinite;
                }
                @keyframes spin {
                    to { transform: rotate(360deg); }
                }
            `;
            document.head.appendChild(style);
        }
    }
    
    loadingOverlay.style.display = 'flex';
}

function hideLoading() {
    const loadingOverlay = document.getElementById('loadingOverlay');
    if (loadingOverlay) {
        loadingOverlay.style.display = 'none';
    }
}

function showNotification(message, type = 'info') {
    let notificationContainer = document.getElementById('notificationContainer');
    
    if (!notificationContainer) {
        notificationContainer = document.createElement('div');
        notificationContainer.id = 'notificationContainer';
        notificationContainer.className = 'notification-container';
        document.body.appendChild(notificationContainer);
        
        // Add styles if not already present
        if (!document.getElementById('notificationStyles')) {
            const style = document.createElement('style');
            style.id = 'notificationStyles';
            style.textContent = `
                .notification-container {
                    position: fixed;
                    top: 20px;
                    right: 20px;
                    z-index: 10000;
                }
                .notification {
                    margin-bottom: 10px;
                    padding: 15px 20px;
                    border-radius: 5px;
                    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
                    display: flex;
                    align-items: center;
                    justify-content: space-between;
                    min-width: 300px;
                    max-width: 500px;
                    animation: slideIn 0.3s ease-out forwards;
                }
                .notification.success {
                    background-color: #121212;
                    border-left: 4px solid #00ff9d;
                    color: #00ff9d;
                }
                .notification.error {
                    background-color: #121212;
                    border-left: 4px solid #ff3860;
                    color: #ff3860;
                }
                .notification.info {
                    background-color: #121212;
                    border-left: 4px solid #3298dc;
                    color: #3298dc;
                }
                .notification-close {
                    cursor: pointer;
                    padding: 0 5px;
                    font-size: 20px;
                    margin-left: 10px;
                }
                @keyframes slideIn {
                    from { transform: translateX(100%); opacity: 0; }
                    to { transform: translateX(0); opacity: 1; }
                }
                @keyframes slideOut {
                    from { transform: translateX(0); opacity: 1; }
                    to { transform: translateX(100%); opacity: 0; }
                }
            `;
            document.head.appendChild(style);
        }
    }
    
    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    notification.innerHTML = `
        <div class="notification-message">${message}</div>
        <div class="notification-close">&times;</div>
    `;
    
    notificationContainer.appendChild(notification);
    
    // Add close button functionality
    const closeButton = notification.querySelector('.notification-close');
    closeButton.addEventListener('click', function() {
        notification.style.animation = 'slideOut 0.3s ease-in forwards';
        setTimeout(() => {
            notification.remove();
        }, 300);
    });
    
    // Auto-remove after 5 seconds
    setTimeout(() => {
        if (notification.parentNode) {
            notification.style.animation = 'slideOut 0.3s ease-in forwards';
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.remove();
                }
            }, 300);
        }
    }, 5000);
}

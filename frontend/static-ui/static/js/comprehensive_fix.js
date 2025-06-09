/**
 * AUTOBOT Comprehensive Fix
 * Addresses UI and functionality issues
 */
document.addEventListener('DOMContentLoaded', function() {
    console.log('AUTOBOT Comprehensive Fix loaded');
    
    fixLayoutIssues();
    
    initializeButtons();
    
    initializeModals();
    
    if (document.querySelector('.chat-container')) {
        initializeChat();
    }
});

function fixLayoutIssues() {
    const capitalContent = document.querySelector('.capital-content');
    if (capitalContent) {
        capitalContent.style.width = '100%';
        capitalContent.style.maxWidth = '1200px';
        capitalContent.style.margin = '0 auto';
        
        const capitalCards = document.querySelectorAll('.capital-card');
        capitalCards.forEach(card => {
            card.style.minWidth = '300px';
            card.style.flex = '1 1 30%';
        });
    }
}

function initializeButtons() {
    const startTradingBtn = document.getElementById('start-trading-btn');
    if (startTradingBtn) {
        startTradingBtn.addEventListener('click', function() {
            fetch('/api/trading/start', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'}
            })
            .then(response => response.json())
            .then(data => {
                alert(data.message);
            })
            .catch(error => {
                alert('Erreur lors du démarrage du trading');
            });
        });
    }
    
    const depositBtn = document.getElementById('deposit-btn');
    if (depositBtn) {
        depositBtn.addEventListener('click', function() {
            openModal('deposit-modal');
        });
    }
    
    const withdrawBtn = document.getElementById('withdraw-btn');
    if (withdrawBtn) {
        withdrawBtn.addEventListener('click', function() {
            openModal('withdraw-modal');
        });
    }
}

function initializeModals() {
    const closeButtons = document.querySelectorAll('.modal-close, .modal-cancel');
    closeButtons.forEach(button => {
        button.addEventListener('click', function() {
            const modal = button.closest('.modal');
            closeModal(modal);
        });
    });
    
    const modalBackgrounds = document.querySelectorAll('.modal-background');
    modalBackgrounds.forEach(background => {
        background.addEventListener('click', function() {
            const modal = background.closest('.modal');
            closeModal(modal);
        });
    });
}

function openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.add('is-active');
    }
}

function closeModal(modal) {
    if (modal) {
        modal.classList.remove('is-active');
    }
}

function initializeChat() {
    const chatForm = document.getElementById('chat-form');
    const messageInput = document.getElementById('message-input');
    const chatMessages = document.querySelector('.chat-messages');
    
    if (chatForm && messageInput && chatMessages) {
        chatForm.addEventListener('submit', function(e) {
            e.preventDefault();
            
            const message = messageInput.value.trim();
            if (!message) return;
            
            const userMessageDiv = document.createElement('div');
            userMessageDiv.className = 'message message-user';
            userMessageDiv.textContent = message;
            chatMessages.appendChild(userMessageDiv);
            
            messageInput.value = '';
            
            const processingDiv = document.createElement('div');
            processingDiv.className = 'message message-bot processing';
            processingDiv.textContent = 'Je traite votre demande...';
            chatMessages.appendChild(processingDiv);
            
            chatMessages.scrollTop = chatMessages.scrollHeight;
            
            fetch('/api/chat/message', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ message })
            })
            .then(response => response.json())
            .then(data => {
                processingDiv.remove();
                
                const botMessageDiv = document.createElement('div');
                botMessageDiv.className = 'message message-bot';
                botMessageDiv.textContent = data.response;
                chatMessages.appendChild(botMessageDiv);
                
                chatMessages.scrollTop = chatMessages.scrollHeight;
            })
            .catch(error => {
                processingDiv.remove();
                
                const errorDiv = document.createElement('div');
                errorDiv.className = 'message message-bot';
                errorDiv.textContent = 'Erreur de connexion. Veuillez réessayer.';
                chatMessages.appendChild(errorDiv);
                
                chatMessages.scrollTop = chatMessages.scrollHeight;
            });
        });
    }
}

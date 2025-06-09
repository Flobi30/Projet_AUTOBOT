
/**
 * Treasury Integration for AUTOBOT
 * Provides functionality for integrating with the treasury system
 */

document.addEventListener('DOMContentLoaded', function() {
    // Initialize treasury integration
    initTreasuryIntegration();
    
    // Initialize backtesting triggers for API keys
    initBacktestingTriggers();
});

function initTreasuryIntegration() {
    // Fetch treasury balance
    fetchTreasuryBalance();
    
    // Initialize treasury transaction listeners
    initTransactionListeners();
}

function fetchTreasuryBalance() {
    // Simulate API call to get treasury balance
    const treasuryBalance = 5000.00; // Example balance
    
    // Update all treasury balance displays
    const balanceElements = document.querySelectorAll('.treasury-balance-amount');
    balanceElements.forEach(element => {
        element.textContent = `${treasuryBalance.toFixed(2)} €`;
    });
    
    // Update treasury charts if they exist
    updateTreasuryCharts(treasuryBalance);
}

function initTransactionListeners() {
    // Listen for deposit button clicks
    const depositButtons = document.querySelectorAll('.deposit-btn');
    depositButtons.forEach(button => {
        button.addEventListener('click', function() {
            const amount = prompt('Montant du depot:');
            if (amount && !isNaN(amount) && parseFloat(amount) > 0) {
                processDeposit(parseFloat(amount));
            }
        });
    });
    
    // Listen for withdrawal button clicks
    const withdrawalButtons = document.querySelectorAll('.withdrawal-btn');
    withdrawalButtons.forEach(button => {
        button.addEventListener('click', function() {
            const amount = prompt('Montant du retrait:');
            if (amount && !isNaN(amount) && parseFloat(amount) > 0) {
                processWithdrawal(parseFloat(amount));
            }
        });
    });
}

function processDeposit(amount) {
    // Simulate API call to process deposit
    console.log('Processing deposit:', amount);
    
    // Update treasury balance
    const balanceElements = document.querySelectorAll('.treasury-balance-amount');
    balanceElements.forEach(element => {
        const currentBalance = parseFloat(element.textContent);
        const newBalance = currentBalance + amount;
        element.textContent = `${newBalance.toFixed(2)} €`;
    });
    
    // Show success message
    alert(`Depot de ${amount.toFixed(2)} € traite avec succes.`);
    
    // Update treasury charts
    updateTreasuryCharts(parseFloat(balanceElements[0].textContent));
}

function processWithdrawal(amount) {
    // Get current balance
    const balanceElement = document.querySelector('.treasury-balance-amount');
    const currentBalance = parseFloat(balanceElement.textContent);
    
    // Check if sufficient funds
    if (currentBalance < amount) {
        alert('Solde insuffisant pour ce retrait.');
        return;
    }
    
    // Simulate API call to process withdrawal
    console.log('Processing withdrawal:', amount);
    
    // Update treasury balance
    const balanceElements = document.querySelectorAll('.treasury-balance-amount');
    balanceElements.forEach(element => {
        const newBalance = currentBalance - amount;
        element.textContent = `${newBalance.toFixed(2)} €`;
    });
    
    // Show success message
    alert(`Retrait de ${amount.toFixed(2)} € traite avec succes.`);
    
    // Update treasury charts
    updateTreasuryCharts(parseFloat(balanceElements[0].textContent));
}

function updateTreasuryCharts(balance) {
    // Update treasury charts if they exist
    const treasuryChart = document.getElementById('treasury-chart');
    if (treasuryChart && window.treasuryChartInstance) {
        // Add new data point to chart
        const date = new Date();
        window.treasuryChartInstance.data.labels.push(date.toLocaleTimeString());
        window.treasuryChartInstance.data.datasets[0].data.push(balance);
        
        // Remove oldest data point if more than 10
        if (window.treasuryChartInstance.data.labels.length > 10) {
            window.treasuryChartInstance.data.labels.shift();
            window.treasuryChartInstance.data.datasets[0].data.shift();
        }
        
        // Update chart
        window.treasuryChartInstance.update();
    }
}

function initBacktestingTriggers() {
    // Get all API key save buttons
    const apiKeySaveButtons = document.querySelectorAll('.api-key-save');
    
    apiKeySaveButtons.forEach(button => {
        button.addEventListener('click', function() {
            // Get the API key field
            const apiKeyField = this.closest('.form-group').querySelector('input');
            const apiKeyName = apiKeyField.id;
            const apiKeyValue = apiKeyField.value;
            
            if (apiKeyValue.trim() !== '') {
                // Save API key
                saveApiKey(apiKeyName, apiKeyValue);
                
                // Trigger backtesting
                triggerBacktesting(apiKeyName);
            }
        });
    });
}

function saveApiKey(name, value) {
    // Simulate API call to save API key
    console.log(`Saving API key ${name}:`, value);
    
    // Show success message
    alert(`Cle API ${name} enregistree avec succes.`);
}

function triggerBacktesting(apiKeyName) {
    // Show backtesting notification
    const notification = document.createElement('div');
    notification.className = 'alert alert-info';
    notification.innerHTML = `<strong>Backtesting en cours...</strong> Utilisation de la cle API ${apiKeyName} pour le backtesting automatique.`;
    
    // Add notification to page
    const notificationContainer = document.querySelector('.notifications-container');
    if (notificationContainer) {
        notificationContainer.appendChild(notification);
        
        // Remove notification after 5 seconds
        setTimeout(() => {
            notification.remove();
            
            // Show success notification
            const successNotification = document.createElement('div');
            successNotification.className = 'alert alert-success';
            successNotification.innerHTML = `<strong>Backtesting termine!</strong> Resultats disponibles dans la section Backtesting.`;
            notificationContainer.appendChild(successNotification);
            
            // Remove success notification after 5 seconds
            setTimeout(() => {
                successNotification.remove();
            }, 5000);
        }, 5000);
    }
}

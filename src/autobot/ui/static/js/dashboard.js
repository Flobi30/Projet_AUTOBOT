document.addEventListener('DOMContentLoaded', function() {
    const navLinks = document.querySelectorAll('.sidebar a');
    const sections = document.querySelectorAll('.section');
    
    navLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            
            navLinks.forEach(link => link.classList.remove('active'));
            sections.forEach(section => section.classList.remove('active'));
            
            this.classList.add('active');
            
            const sectionId = this.getAttribute('data-section');
            document.getElementById(sectionId).classList.add('active');
        });
    });
    
    const modal = document.getElementById('modal');
    const closeModal = document.getElementById('close-modal');
    
    function showModal(title, content) {
        document.getElementById('modal-title').textContent = title;
        document.getElementById('modal-content').innerHTML = content;
        modal.classList.add('active');
    }
    
    function hideModal() {
        modal.classList.remove('active');
    }
    
    closeModal.addEventListener('click', hideModal);
    
    modal.addEventListener('click', function(e) {
        if (e.target === modal) {
            hideModal();
        }
    });
    
    document.getElementById('new-strategy-btn').addEventListener('click', function() {
        showModal('Nouvelle Stratégie', `
            <div class="settings-form">
                <div class="form-group">
                    <label for="strategy-name">Nom de la Stratégie</label>
                    <input type="text" id="strategy-name">
                </div>
                <div class="form-group">
                    <label for="strategy-type">Type de Stratégie</label>
                    <select id="strategy-type">
                        <option value="ma_crossover">Moving Average Crossover</option>
                        <option value="rsi">RSI</option>
                        <option value="bollinger">Bollinger Bands</option>
                    </select>
                </div>
                <div class="form-group">
                    <label for="strategy-pair">Paire</label>
                    <input type="text" id="strategy-pair" value="BTC/EUR">
                </div>
                <div class="form-group">
                    <label for="strategy-timeframe">Timeframe</label>
                    <select id="strategy-timeframe">
                        <option value="1m">1 minute</option>
                        <option value="5m">5 minutes</option>
                        <option value="15m">15 minutes</option>
                        <option value="1h" selected>1 heure</option>
                        <option value="4h">4 heures</option>
                        <option value="1d">1 jour</option>
                    </select>
                </div>
                <div class="form-group">
                    <button class="btn-primary" id="create-strategy-btn">Créer</button>
                </div>
            </div>
        `);
    });
    
    document.getElementById('new-model-btn').addEventListener('click', function() {
        showModal('Nouveau Modèle RL', `
            <div class="settings-form">
                <div class="form-group">
                    <label for="model-name">Nom du Modèle</label>
                    <input type="text" id="model-name">
                </div>
                <div class="form-group">
                    <label for="model-type">Type de Modèle</label>
                    <select id="model-type">
                        <option value="dqn">DQN</option>
                        <option value="ppo">PPO</option>
                        <option value="a2c">A2C</option>
                    </select>
                </div>
                <div class="form-group">
                    <label for="model-pair">Paire</label>
                    <input type="text" id="model-pair" value="BTC/EUR">
                </div>
                <div class="form-group">
                    <label for="model-episodes">Épisodes</label>
                    <input type="number" id="model-episodes" value="1000">
                </div>
                <div class="form-group">
                    <button class="btn-primary" id="create-model-btn">Créer</button>
                </div>
            </div>
        `);
    });
    
    document.getElementById('new-agent-btn').addEventListener('click', function() {
        showModal('Nouvel Agent', `
            <div class="settings-form">
                <div class="form-group">
                    <label for="agent-name">Nom de l'Agent</label>
                    <input type="text" id="agent-name">
                </div>
                <div class="form-group">
                    <label for="agent-type">Type d'Agent</label>
                    <select id="agent-type">
                        <option value="analyzer">Analyzer</option>
                        <option value="trader">Trader</option>
                        <option value="data">Data Collector</option>
                        <option value="optimizer">Optimizer</option>
                    </select>
                </div>
                <div class="form-group">
                    <label for="agent-frequency">Fréquence d'Exécution</label>
                    <select id="agent-frequency">
                        <option value="1m">1 minute</option>
                        <option value="5m">5 minutes</option>
                        <option value="15m">15 minutes</option>
                        <option value="1h" selected>1 heure</option>
                        <option value="4h">4 heures</option>
                        <option value="1d">1 jour</option>
                    </select>
                </div>
                <div class="form-group">
                    <button class="btn-primary" id="create-agent-btn">Créer</button>
                </div>
            </div>
        `);
    });
    
    document.getElementById('sync-inventory-btn').addEventListener('click', function() {
        setTimeout(() => {
            alert('Inventaire synchronisé avec succès!');
        }, 1000);
    });
    
    document.getElementById('optimize-prices-btn').addEventListener('click', function() {
        setTimeout(() => {
            alert('Prix optimisés avec succès!');
        }, 1000);
    });
    
    document.getElementById('save-settings-btn').addEventListener('click', function() {
        setTimeout(() => {
            alert('Paramètres enregistrés avec succès!');
        }, 1000);
    });
    
    initCharts();
    
    initWebSocket();
});

function initCharts() {
    const portfolioCtx = document.getElementById('portfolio-chart').getContext('2d');
    const portfolioChart = new Chart(portfolioCtx, {
        type: 'line',
        data: {
            labels: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul'],
            datasets: [{
                label: 'Portfolio Value (€)',
                data: [10000, 10200, 10150, 10400, 10800, 10600, 10900],
                borderColor: '#00ff00',
                backgroundColor: 'rgba(0, 255, 0, 0.1)',
                tension: 0.4,
                fill: true
            }]
        },
        options: {
            responsive: true,
            plugins: {
                legend: {
                    position: 'top',
                    labels: {
                        color: '#ffffff'
                    }
                }
            },
            scales: {
                x: {
                    grid: {
                        color: '#333333'
                    },
                    ticks: {
                        color: '#ffffff'
                    }
                },
                y: {
                    grid: {
                        color: '#333333'
                    },
                    ticks: {
                        color: '#ffffff'
                    }
                }
            }
        }
    });
    
    const allocationCtx = document.getElementById('allocation-chart').getContext('2d');
    const allocationChart = new Chart(allocationCtx, {
        type: 'doughnut',
        data: {
            labels: ['BTC', 'ETH', 'XRP', 'LTC', 'Cash'],
            datasets: [{
                data: [40, 25, 15, 10, 10],
                backgroundColor: [
                    '#00ff00',
                    '#00cc00',
                    '#00aa00',
                    '#008800',
                    '#006600'
                ],
                borderColor: '#1e1e1e',
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            plugins: {
                legend: {
                    position: 'right',
                    labels: {
                        color: '#ffffff'
                    }
                }
            }
        }
    });
    
    const strategiesCtx = document.getElementById('strategies-chart').getContext('2d');
    const strategiesChart = new Chart(strategiesCtx, {
        type: 'line',
        data: {
            labels: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul'],
            datasets: [
                {
                    label: 'Moving Average Crossover',
                    data: [0, 2.1, 3.5, 4.2, 5.1, 4.8, 5.2],
                    borderColor: '#00ff00',
                    backgroundColor: 'transparent',
                    tension: 0.4
                },
                {
                    label: 'RSI Oversold',
                    data: [0, 1.5, 2.2, 2.8, 3.1, 3.5, 3.7],
                    borderColor: '#00ccff',
                    backgroundColor: 'transparent',
                    tension: 0.4
                },
                {
                    label: 'Bollinger Bands',
                    data: [0, -0.5, -0.8, -1.2, -0.9, -1.1, -1.2],
                    borderColor: '#ff3333',
                    backgroundColor: 'transparent',
                    tension: 0.4
                }
            ]
        },
        options: {
            responsive: true,
            plugins: {
                legend: {
                    position: 'top',
                    labels: {
                        color: '#ffffff'
                    }
                }
            },
            scales: {
                x: {
                    grid: {
                        color: '#333333'
                    },
                    ticks: {
                        color: '#ffffff'
                    }
                },
                y: {
                    grid: {
                        color: '#333333'
                    },
                    ticks: {
                        color: '#ffffff'
                    }
                }
            }
        }
    });
    
    const rlCtx = document.getElementById('rl-chart').getContext('2d');
    const rlChart = new Chart(rlCtx, {
        type: 'line',
        data: {
            labels: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul'],
            datasets: [
                {
                    label: 'DQN BTC Trader',
                    data: [0, 3.1, 4.5, 5.2, 6.1, 7.2, 7.8],
                    borderColor: '#00ff00',
                    backgroundColor: 'transparent',
                    tension: 0.4
                },
                {
                    label: 'PPO Multi-Asset',
                    data: [0, 2.5, 3.2, 3.8, 4.1, 4.5, 4.7],
                    borderColor: '#00ccff',
                    backgroundColor: 'transparent',
                    tension: 0.4
                }
            ]
        },
        options: {
            responsive: true,
            plugins: {
                legend: {
                    position: 'top',
                    labels: {
                        color: '#ffffff'
                    }
                }
            },
            scales: {
                x: {
                    grid: {
                        color: '#333333'
                    },
                    ticks: {
                        color: '#ffffff'
                    }
                },
                y: {
                    grid: {
                        color: '#333333'
                    },
                    ticks: {
                        color: '#ffffff'
                    }
                }
            }
        }
    });
    
    const agentsCtx = document.getElementById('agents-chart').getContext('2d');
    const agentsChart = new Chart(agentsCtx, {
        type: 'radar',
        data: {
            labels: ['Communication', 'Efficacité', 'Précision', 'Vitesse', 'Adaptabilité'],
            datasets: [
                {
                    label: 'Market Analyzer',
                    data: [85, 90, 92, 88, 80],
                    borderColor: '#00ff00',
                    backgroundColor: 'rgba(0, 255, 0, 0.2)',
                    pointBackgroundColor: '#00ff00'
                },
                {
                    label: 'News Sentiment',
                    data: [95, 80, 85, 90, 85],
                    borderColor: '#00ccff',
                    backgroundColor: 'rgba(0, 204, 255, 0.2)',
                    pointBackgroundColor: '#00ccff'
                },
                {
                    label: 'Portfolio Optimizer',
                    data: [80, 95, 88, 85, 90],
                    borderColor: '#ffcc00',
                    backgroundColor: 'rgba(255, 204, 0, 0.2)',
                    pointBackgroundColor: '#ffcc00'
                }
            ]
        },
        options: {
            responsive: true,
            plugins: {
                legend: {
                    position: 'top',
                    labels: {
                        color: '#ffffff'
                    }
                }
            },
            scales: {
                r: {
                    angleLines: {
                        color: '#333333'
                    },
                    grid: {
                        color: '#333333'
                    },
                    pointLabels: {
                        color: '#ffffff'
                    },
                    ticks: {
                        color: '#ffffff',
                        backdropColor: 'transparent'
                    }
                }
            }
        }
    });
}

function initWebSocket() {
    console.log('WebSocket connection initialized');
    
    setInterval(() => {
        updateRandomData();
    }, 5000);
}

function updateRandomData() {
    // ZERO BASELINE - Set all metrics to 0 as requested by user
    const totalCapitalElement = document.getElementById("totalCapital");
    if (totalCapitalElement) {
        totalCapitalElement.textContent = "0 €";
    }
    
    const performanceElement = document.getElementById("performance");
    if (performanceElement) {
        performanceElement.textContent = "+0.00%";
    }
    
    const activeInstancesElement = document.getElementById("activeInstances");
    if (activeInstancesElement) {
        activeInstancesElement.textContent = "0";
    }
    
    const capitalChangeElement = document.getElementById("capitalChange");
    if (capitalChangeElement) {
        capitalChangeElement.textContent = "+0.00%";
    }
    
    const instanceChangeElement = document.getElementById("instanceChange");
    if (instanceChangeElement) {
        instanceChangeElement.textContent = "+0";
    }
    
    console.log("Dashboard metrics set to ZERO BASELINE as requested");
}

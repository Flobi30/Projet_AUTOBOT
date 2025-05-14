/**
 * RL Training Interface JavaScript
 * Handles real-time training monitoring, model management, and WebSocket communication
 */

let socket = null;
let trainingActive = false;
let trainingStartTime = null;
let currentEpisode = 0;
let totalEpisodes = 0;
let rewardChart = null;
let portfolioChart = null;
let trainingInterval = null;

const sampleModels = [
    {
        id: 'model_001',
        name: 'PPO_BTC_USD_v1',
        agent_type: 'ppo',
        environment: 'crypto',
        episodes: 1000,
        status: 'completed',
        avg_reward: 145.32,
        return_pct: 18.7,
        creation_date: '2025-05-10T14:30:00',
        hyperparams: {
            learning_rate: 0.0003,
            gamma: 0.99,
            batch_size: 64,
            clip_range: 0.2,
            entropy_coef: 0.01
        },
        architecture: {
            layers: [64, 64],
            activation: 'tanh',
            optimizer: 'Adam'
        },
        performance: {
            max_reward: 320.5,
            sharpe_ratio: 1.65,
            max_drawdown: 12.8,
            trade_count: 87
        },
        size: '2.1 MB'
    },
    {
        id: 'model_002',
        name: 'DQN_FOREX_EUR_USD',
        agent_type: 'dqn',
        environment: 'forex',
        episodes: 2000,
        status: 'completed',
        avg_reward: 98.45,
        return_pct: 12.3,
        creation_date: '2025-05-08T09:15:00',
        hyperparams: {
            learning_rate: 0.0005,
            gamma: 0.95,
            batch_size: 32,
            target_update: 500,
            epsilon_decay: 0.995
        },
        architecture: {
            layers: [128, 64],
            activation: 'relu',
            optimizer: 'RMSprop'
        },
        performance: {
            max_reward: 210.8,
            sharpe_ratio: 1.32,
            max_drawdown: 15.4,
            trade_count: 124
        },
        size: '3.4 MB'
    },
    {
        id: 'model_003',
        name: 'A2C_STOCKS_TECH',
        agent_type: 'a2c',
        environment: 'stocks',
        episodes: 1500,
        status: 'in-progress',
        avg_reward: 78.21,
        return_pct: 8.9,
        creation_date: '2025-05-13T16:45:00',
        hyperparams: {
            learning_rate: 0.0007,
            gamma: 0.97,
            batch_size: 16,
            n_steps: 5,
            ent_coef: 0.01
        },
        architecture: {
            layers: [64, 32],
            activation: 'elu',
            optimizer: 'Adam'
        },
        performance: {
            max_reward: 180.3,
            sharpe_ratio: 1.18,
            max_drawdown: 18.2,
            trade_count: 65
        },
        size: '1.8 MB'
    }
];

const sampleTrainingHistory = [
    {
        id: 'job_001',
        model_name: 'PPO_BTC_USD_v1',
        agent_type: 'ppo',
        environment: 'crypto',
        episodes: 1000,
        status: 'completed',
        avg_reward: 145.32,
        return_pct: 18.7,
        date: '2025-05-10T14:30:00'
    },
    {
        id: 'job_002',
        model_name: 'DQN_FOREX_EUR_USD',
        agent_type: 'dqn',
        environment: 'forex',
        episodes: 2000,
        status: 'completed',
        avg_reward: 98.45,
        return_pct: 12.3,
        date: '2025-05-08T09:15:00'
    },
    {
        id: 'job_003',
        model_name: 'A2C_STOCKS_TECH',
        agent_type: 'a2c',
        environment: 'stocks',
        episodes: 1500,
        status: 'in-progress',
        avg_reward: 78.21,
        return_pct: 8.9,
        date: '2025-05-13T16:45:00'
    },
    {
        id: 'job_004',
        model_name: 'SAC_CRYPTO_ETH',
        agent_type: 'sac',
        environment: 'crypto',
        episodes: 800,
        status: 'stopped',
        avg_reward: 45.67,
        return_pct: 3.2,
        date: '2025-05-05T11:20:00'
    }
];

document.addEventListener('DOMContentLoaded', function() {
    initializeCharts();
    populateTrainingHistory();
    populateSavedModels();
    setupEventListeners();
});

function initializeCharts() {
    const rewardCtx = document.getElementById('reward-chart').getContext('2d');
    rewardChart = new Chart(rewardCtx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Récompense',
                data: [],
                borderColor: '#00ff9d',
                backgroundColor: 'rgba(0, 255, 157, 0.1)',
                borderWidth: 2,
                tension: 0.2,
                fill: true
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: {
                    title: {
                        display: true,
                        text: 'Épisode',
                        color: '#cccccc'
                    },
                    ticks: {
                        color: '#cccccc'
                    },
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)'
                    }
                },
                y: {
                    title: {
                        display: true,
                        text: 'Récompense',
                        color: '#cccccc'
                    },
                    ticks: {
                        color: '#cccccc'
                    },
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)'
                    }
                }
            },
            plugins: {
                legend: {
                    labels: {
                        color: '#cccccc'
                    }
                }
            }
        }
    });

    const portfolioCtx = document.getElementById('portfolio-chart').getContext('2d');
    portfolioChart = new Chart(portfolioCtx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Valeur du Portfolio',
                data: [],
                borderColor: '#00ff9d',
                backgroundColor: 'rgba(0, 255, 157, 0.1)',
                borderWidth: 2,
                tension: 0.2,
                fill: true
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: {
                    title: {
                        display: true,
                        text: 'Épisode',
                        color: '#cccccc'
                    },
                    ticks: {
                        color: '#cccccc'
                    },
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)'
                    }
                },
                y: {
                    title: {
                        display: true,
                        text: 'Valeur ($)',
                        color: '#cccccc'
                    },
                    ticks: {
                        color: '#cccccc'
                    },
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)'
                    }
                }
            },
            plugins: {
                legend: {
                    labels: {
                        color: '#cccccc'
                    }
                }
            }
        }
    });
}

function populateTrainingHistory() {
    const tableBody = document.getElementById('history-table-body');
    tableBody.innerHTML = '';

    sampleTrainingHistory.forEach(job => {
        const row = document.createElement('tr');
        
        const date = new Date(job.date);
        const formattedDate = `${date.toLocaleDateString()} ${date.toLocaleTimeString()}`;
        
        let statusClass = '';
        switch(job.status) {
            case 'completed':
                statusClass = 'status-completed';
                break;
            case 'in-progress':
                statusClass = 'status-in-progress';
                break;
            case 'stopped':
                statusClass = 'status-stopped';
                break;
        }
        
        row.innerHTML = `
            <td>${job.id}</td>
            <td>${job.model_name}</td>
            <td>${job.agent_type.toUpperCase()}</td>
            <td>${job.environment}</td>
            <td>${job.episodes}</td>
            <td><span class="${statusClass}">${job.status}</span></td>
            <td>${job.avg_reward.toFixed(2)}</td>
            <td>${job.return_pct.toFixed(2)}%</td>
            <td>${formattedDate}</td>
            <td>
                <button class="btn-icon view-job" data-id="${job.id}"><i class="icon-view"></i></button>
                <button class="btn-icon download-job" data-id="${job.id}"><i class="icon-download"></i></button>
                <button class="btn-icon delete-job" data-id="${job.id}"><i class="icon-delete"></i></button>
            </td>
        `;
        
        tableBody.appendChild(row);
    });
    
    document.querySelectorAll('.view-job').forEach(btn => {
        btn.addEventListener('click', function() {
            const jobId = this.getAttribute('data-id');
            viewTrainingJob(jobId);
        });
    });
    
    document.querySelectorAll('.download-job').forEach(btn => {
        btn.addEventListener('click', function() {
            const jobId = this.getAttribute('data-id');
            downloadTrainingResults(jobId);
        });
    });
    
    document.querySelectorAll('.delete-job').forEach(btn => {
        btn.addEventListener('click', function() {
            const jobId = this.getAttribute('data-id');
            showConfirmationModal(`Êtes-vous sûr de vouloir supprimer le job d'entraînement ${jobId} ?`, () => {
                deleteTrainingJob(jobId);
            });
        });
    });
}

function populateSavedModels() {
    const modelsGrid = document.getElementById('models-grid');
    modelsGrid.innerHTML = '';

    sampleModels.forEach(model => {
        const modelCard = document.createElement('div');
        modelCard.className = 'model-card';
        
        const date = new Date(model.creation_date);
        const formattedDate = `${date.toLocaleDateString()}`;
        
        modelCard.innerHTML = `
            <div class="model-header">
                <h3>${model.name}</h3>
                <span class="model-type">${model.agent_type.toUpperCase()}</span>
            </div>
            <div class="model-body">
                <div class="model-info-item">
                    <span class="info-label">Environnement:</span>
                    <span class="info-value">${model.environment}</span>
                </div>
                <div class="model-info-item">
                    <span class="info-label">Épisodes:</span>
                    <span class="info-value">${model.episodes}</span>
                </div>
                <div class="model-info-item">
                    <span class="info-label">Récompense Moy.:</span>
                    <span class="info-value">${model.avg_reward.toFixed(2)}</span>
                </div>
                <div class="model-info-item">
                    <span class="info-label">Rendement:</span>
                    <span class="info-value">${model.return_pct.toFixed(2)}%</span>
                </div>
                <div class="model-info-item">
                    <span class="info-label">Date:</span>
                    <span class="info-value">${formattedDate}</span>
                </div>
            </div>
            <div class="model-footer">
                <button class="btn btn-sm btn-outline view-model" data-id="${model.id}">Détails</button>
                <button class="btn btn-sm btn-primary deploy-model" data-id="${model.id}">Déployer</button>
            </div>
        `;
        
        modelsGrid.appendChild(modelCard);
    });
    
    document.querySelectorAll('.view-model').forEach(btn => {
        btn.addEventListener('click', function() {
            const modelId = this.getAttribute('data-id');
            openModelDetails(modelId);
        });
    });
    
    document.querySelectorAll('.deploy-model').forEach(btn => {
        btn.addEventListener('click', function() {
            const modelId = this.getAttribute('data-id');
            deployModel(modelId);
        });
    });
}

function setupEventListeners() {
    document.getElementById('start-training').addEventListener('click', startTraining);
    document.getElementById('pause-training').addEventListener('click', pauseTraining);
    document.getElementById('stop-training').addEventListener('click', stopTraining);
    
    document.getElementById('history-search').addEventListener('input', filterTrainingHistory);
    document.getElementById('history-filter').addEventListener('change', filterTrainingHistory);
    
    document.querySelectorAll('.close-modal').forEach(btn => {
        btn.addEventListener('click', closeModals);
    });
    
    document.getElementById('confirm-yes').addEventListener('click', function() {
        if (typeof window.confirmCallback === 'function') {
            window.confirmCallback();
        }
        closeModals();
    });
    
    document.getElementById('confirm-no').addEventListener('click', closeModals);
    
    document.getElementById('modal-deploy-btn').addEventListener('click', function() {
        const modelId = this.getAttribute('data-model-id');
        deployModel(modelId);
        closeModals();
    });
    
    document.getElementById('modal-backtest-btn').addEventListener('click', function() {
        const modelId = this.getAttribute('data-model-id');
        backtestModel(modelId);
        closeModals();
    });
    
    document.getElementById('modal-export-btn').addEventListener('click', function() {
        const modelId = this.getAttribute('data-model-id');
        exportModel(modelId);
        closeModals();
    });
    
    document.getElementById('modal-delete-btn').addEventListener('click', function() {
        const modelId = this.getAttribute('data-model-id');
        const modelName = document.getElementById('modal-model-name').textContent;
        
        closeModals();
        showConfirmationModal(`Êtes-vous sûr de vouloir supprimer le modèle ${modelName} ?`, () => {
            deleteModel(modelId);
        });
    });
}

function startTraining() {
    if (trainingActive) return;
    
    const agentType = document.getElementById('agent-type').value;
    const environment = document.getElementById('environment').value;
    const episodes = parseInt(document.getElementById('episodes').value);
    const learningRate = parseFloat(document.getElementById('learning-rate').value);
    const batchSize = parseInt(document.getElementById('batch-size').value);
    const gamma = parseFloat(document.getElementById('gamma').value);
    const modelName = document.getElementById('model-name').value || `${agentType}_${environment}_${Date.now()}`;
    const saveInterval = parseInt(document.getElementById('save-interval').value);
    
    if (episodes <= 0 || learningRate <= 0 || batchSize <= 0 || gamma <= 0 || saveInterval <= 0) {
        alert('Veuillez entrer des valeurs valides pour tous les paramètres.');
        return;
    }
    
    document.getElementById('training-status').textContent = 'En cours';
    document.getElementById('training-status').className = 'info-value status-in-progress';
    document.getElementById('current-episode').textContent = '0';
    document.getElementById('total-episodes').textContent = `/ ${episodes}`;
    document.getElementById('progress-fill').style.width = '0%';
    document.getElementById('progress-percentage').textContent = '0%';
    
    document.getElementById('start-training').disabled = true;
    document.getElementById('pause-training').disabled = false;
    document.getElementById('stop-training').disabled = false;
    
    rewardChart.data.labels = [];
    rewardChart.data.datasets[0].data = [];
    rewardChart.update();
    
    portfolioChart.data.labels = [];
    portfolioChart.data.datasets[0].data = [];
    portfolioChart.update();
    
    document.getElementById('avg-reward').textContent = '0.00';
    document.getElementById('max-reward').textContent = '0.00';
    document.getElementById('portfolio-return').textContent = '0.00%';
    document.getElementById('max-drawdown').textContent = '0.00%';
    document.getElementById('sharpe-ratio').textContent = '0.00';
    document.getElementById('avg-loss').textContent = '0.00';
    document.getElementById('entropy').textContent = '0.00';
    document.getElementById('trade-count').textContent = '0';
    
    trainingActive = true;
    trainingStartTime = new Date();
    currentEpisode = 0;
    totalEpisodes = episodes;
    
    connectWebSocket();
    
    simulateTrainingProgress();
    
    updateElapsedTime();
    
    console.log('Starting training with parameters:', {
        agentType,
        environment,
        episodes,
        learningRate,
        batchSize,
        gamma,
        modelName,
        saveInterval
    });
}

function pauseTraining() {
    if (!trainingActive) return;
    
    const pauseBtn = document.getElementById('pause-training');
    
    if (pauseBtn.textContent === 'Pause') {
        pauseBtn.textContent = 'Reprendre';
        document.getElementById('training-status').textContent = 'En pause';
        document.getElementById('training-status').className = 'info-value status-paused';
        
        console.log('Pausing training');
        
        clearInterval(trainingInterval);
    } else {
        pauseBtn.textContent = 'Pause';
        document.getElementById('training-status').textContent = 'En cours';
        document.getElementById('training-status').className = 'info-value status-in-progress';
        
        console.log('Resuming training');
        
        simulateTrainingProgress();
    }
}

function stopTraining() {
    if (!trainingActive) return;
    
    showConfirmationModal('Êtes-vous sûr de vouloir arrêter l\'entraînement en cours ?', () => {
        document.getElementById('training-status').textContent = 'Arrêté';
        document.getElementById('training-status').className = 'info-value status-stopped';
        
        document.getElementById('start-training').disabled = false;
        document.getElementById('pause-training').disabled = true;
        document.getElementById('pause-training').textContent = 'Pause';
        document.getElementById('stop-training').disabled = true;
        
        trainingActive = false;
        
        console.log('Stopping training');
        
        clearInterval(trainingInterval);
        
        disconnectWebSocket();
    });
}

function connectWebSocket() {
    console.log('Connecting to WebSocket...');
    
    socket = {
        connected: true,
        send: function(data) {
            console.log('WebSocket message sent:', data);
        },
        close: function() {
            console.log('WebSocket connection closed');
            this.connected = false;
        }
    };
}

function disconnectWebSocket() {
    if (socket && socket.connected) {
        socket.close();
        socket = null;
    }
}

function updateElapsedTime() {
    if (!trainingActive || !trainingStartTime) return;
    
    const now = new Date();
    const elapsed = now - trainingStartTime;
    
    const hours = Math.floor(elapsed / 3600000);
    const minutes = Math.floor((elapsed % 3600000) / 60000);
    const seconds = Math.floor((elapsed % 60000) / 1000);
    
    const formattedTime = 
        (hours < 10 ? '0' + hours : hours) + ':' +
        (minutes < 10 ? '0' + minutes : minutes) + ':' +
        (seconds < 10 ? '0' + seconds : seconds);
    
    document.getElementById('elapsed-time').textContent = formattedTime;
    
    if (currentEpisode > 0 && totalEpisodes > 0) {
        const progress = currentEpisode / totalEpisodes;
        if (progress > 0) {
            const totalEstimatedTime = elapsed / progress;
            const remainingTime = totalEstimatedTime - elapsed;
            
            const remainingHours = Math.floor(remainingTime / 3600000);
            const remainingMinutes = Math.floor((remainingTime % 3600000) / 60000);
            const remainingSeconds = Math.floor((remainingTime % 60000) / 1000);
            
            const formattedRemainingTime = 
                (remainingHours < 10 ? '0' + remainingHours : remainingHours) + ':' +
                (remainingMinutes < 10 ? '0' + remainingMinutes : remainingMinutes) + ':' +
                (remainingSeconds < 10 ? '0' + remainingSeconds : remainingSeconds);
            
            document.getElementById('remaining-time').textContent = formattedRemainingTime;
        }
    }
    
    setTimeout(updateElapsedTime, 1000);
}

function simulateTrainingProgress() {
    if (trainingInterval) {
        clearInterval(trainingInterval);
    }
    
    trainingInterval = setInterval(() => {
        currentEpisode++;
        document.getElementById('current-episode').textContent = currentEpisode;
        
        const progress = (currentEpisode / totalEpisodes) * 100;
        document.getElementById('progress-fill').style.width = `${progress}%`;
        document.getElementById('progress-percentage').textContent = `${Math.round(progress)}%`;
        
        const reward = 50 + 100 * Math.sin(currentEpisode / 50) + Math.random() * 50 - 25;
        const portfolioValue = 10000 * (1 + 0.002 * currentEpisode + 0.05 * Math.sin(currentEpisode / 30) + Math.random() * 0.02 - 0.01);
        
        updateCharts(currentEpisode, reward, portfolioValue);
        
        updateMetrics(reward, portfolioValue);
        
        if (currentEpisode >= totalEpisodes) {
            completeTraining();
        }
    }, 500); // Update every 500ms for demo
}

function updateCharts(episode, reward, portfolioValue) {
    rewardChart.data.labels.push(episode);
    rewardChart.data.datasets[0].data.push(reward);
    
    portfolioChart.data.labels.push(episode);
    portfolioChart.data.datasets[0].data.push(portfolioValue);
    
    if (rewardChart.data.labels.length > 100) {
        rewardChart.data.labels.shift();
        rewardChart.data.datasets[0].data.shift();
    }
    
    if (portfolioChart.data.labels.length > 100) {
        portfolioChart.data.labels.shift();
        portfolioChart.data.datasets[0].data.shift();
    }
    
    rewardChart.update();
    portfolioChart.update();
}

function updateMetrics(reward, portfolioValue) {
    const rewardData = rewardChart.data.datasets[0].data;
    const portfolioData = portfolioChart.data.datasets[0].data;
    
    const avgReward = rewardData.reduce((sum, val) => sum + val, 0) / rewardData.length;
    document.getElementById('avg-reward').textContent = avgReward.toFixed(2);
    
    const maxReward = Math.max(...rewardData);
    document.getElementById('max-reward').textContent = maxReward.toFixed(2);
    
    if (portfolioData.length > 0) {
        const initialValue = portfolioData[0];
        const currentValue = portfolioData[portfolioData.length - 1];
        const returnPct = ((currentValue - initialValue) / initialValue) * 100;
        document.getElementById('portfolio-return').textContent = `${returnPct.toFixed(2)}%`;
    }
    
    if (portfolioData.length > 0) {
        let peak = portfolioData[0];
        let maxDrawdown = 0;
        
        for (let i = 1; i < portfolioData.length; i++) {
            if (portfolioData[i] > peak) {
                peak = portfolioData[i];
            } else {
                const drawdown = (peak - portfolioData[i]) / peak * 100;
                if (drawdown > maxDrawdown) {
                    maxDrawdown = drawdown;
                }
            }
        }
        
        document.getElementById('max-drawdown').textContent = `${maxDrawdown.toFixed(2)}%`;
    }
    
    if (portfolioData.length > 1) {
        const returns = [];
        for (let i = 1; i < portfolioData.length; i++) {
            returns.push((portfolioData[i] - portfolioData[i-1]) / portfolioData[i-1]);
        }
        
        const avgReturn = returns.reduce((sum, val) => sum + val, 0) / returns.length;
        const stdDev = Math.sqrt(returns.reduce((sum, val) => sum + Math.pow(val - avgReturn, 2), 0) / returns.length);
        
        const sharpeRatio = stdDev > 0 ? (avgReturn / stdDev) * Math.sqrt(252) : 0;
        document.getElementById('sharpe-ratio').textContent = sharpeRatio.toFixed(2);
    }
    
    const avgLoss = Math.random() * 2;
    document.getElementById('avg-loss').textContent = avgLoss.toFixed(2);
    
    const entropy = 0.5 + Math.random() * 0.5;
    document.getElementById('entropy').textContent = entropy.toFixed(2);
    
    const tradeCount = Math.floor(currentEpisode * 0.1);
    document.getElementById('trade-count').textContent = tradeCount;
}

function completeTraining() {
    clearInterval(trainingInterval);
    
    document.getElementById('training-status').textContent = 'Terminé';
    document.getElementById('training-status').className = 'info-value status-completed';
    
    document.getElementById('start-training').disabled = false;
    document.getElementById('pause-training').disabled = true;
    document.getElementById('stop-training').disabled = true;
    
    trainingActive = false;
    
    disconnectWebSocket();
    
    const newJob = {
        id: `job_${Date.now()}`,
        model_name: document.getElementById('model-name').value || `${document.getElementById('agent-type').value}_${document.getElementById('environment').value}_${Date.now()}`,
        agent_type: document.getElementById('agent-type').value,
        environment: document.getElementById('environment').value,
        episodes: totalEpisodes,
        status: 'completed',
        avg_reward: parseFloat(document.getElementById('avg-reward').textContent),
        return_pct: parseFloat(document.getElementById('portfolio-return').textContent),
        date: new Date().toISOString()
    };
    
    sampleTrainingHistory.unshift(newJob);
    populateTrainingHistory();
    
    const newModel = {
        id: `model_${Date.now()}`,
        name: newJob.model_name,
        agent_type: newJob.agent_type,
        environment: newJob.environment,
        episodes: newJob.episodes,
        status: 'completed',
        avg_reward: newJob.avg_reward,
        return_pct: newJob.return_pct,
        creation_date: newJob.date,
        hyperparams: {
            learning_rate: parseFloat(document.getElementById('learning-rate').value),
            gamma: parseFloat(document.getElementById('gamma').value),
            batch_size: parseInt(document.getElementById('batch-size').value),
            clip_range: 0.2,
            entropy_coef: 0.01
        },
        architecture: {
            layers: [64, 64],
            activation: 'tanh',
            optimizer: 'Adam'
        },
        performance: {
            max_reward: parseFloat(document.getElementById('max-reward').textContent),
            sharpe_ratio: parseFloat(document.getElementById('sharpe-ratio').textContent),
            max_drawdown: parseFloat(document.getElementById('max-drawdown').textContent.replace('%', '')),
            trade_count: parseInt(document.getElementById('trade-count').textContent)
        },
        size: `${(Math.random() * 3 + 1).toFixed(1)} MB`
    };
    
    sampleModels.unshift(newModel);
    populateSavedModels();
}

function filterTrainingHistory() {
    const searchTerm = document.getElementById('history-search').value.toLowerCase();
    const filterValue = document.getElementById('history-filter').value;
    
    const tableBody = document.getElementById('history-table-body');
    tableBody.innerHTML = '';
    
    sampleTrainingHistory.forEach(job => {
        if (filterValue !== 'all' && job.status !== filterValue.replace('in-progress', 'in-progress')) {
            return;
        }
        
        if (searchTerm && !Object.values(job).some(value => 
            typeof value === 'string' && value.toLowerCase().includes(searchTerm)
        )) {
            return;
        }
        
        const row = document.createElement('tr');
        
        const date = new Date(job.date);
        const formattedDate = `${date.toLocaleDateString()} ${date.toLocaleTimeString()}`;
        
        let statusClass = '';
        switch(job.status) {
            case 'completed':
                statusClass = 'status-completed';
                break;
            case 'in-progress':
                statusClass = 'status-in-progress';
                break;
            case 'stopped':
                statusClass = 'status-stopped';
                break;
        }
        
        row.innerHTML = `
            <td>${job.id}</td>
            <td>${job.model_name}</td>
            <td>${job.agent_type.toUpperCase()}</td>
            <td>${job.environment}</td>
            <td>${job.episodes}</td>
            <td><span class="${statusClass}">${job.status}</span></td>
            <td>${job.avg_reward.toFixed(2)}</td>
            <td>${job.return_pct.toFixed(2)}%</td>
            <td>${formattedDate}</td>
            <td>
                <button class="btn-icon view-job" data-id="${job.id}"><i class="icon-view"></i></button>
                <button class="btn-icon download-job" data-id="${job.id}"><i class="icon-download"></i></button>
                <button class="btn-icon delete-job" data-id="${job.id}"><i class="icon-delete"></i></button>
            </td>
        `;
        
        tableBody.appendChild(row);
    });
    
    document.querySelectorAll('.view-job').forEach(btn => {
        btn.addEventListener('click', function() {
            const jobId = this.getAttribute('data-id');
            viewTrainingJob(jobId);
        });
    });
    
    document.querySelectorAll('.download-job').forEach(btn => {
        btn.addEventListener('click', function() {
            const jobId = this.getAttribute('data-id');
            downloadTrainingResults(jobId);
        });
    });
    
    document.querySelectorAll('.delete-job').forEach(btn => {
        btn.addEventListener('click', function() {
            const jobId = this.getAttribute('data-id');
            showConfirmationModal(`Êtes-vous sûr de vouloir supprimer le job d'entraînement ${jobId} ?`, () => {
                deleteTrainingJob(jobId);
            });
        });
    });
}

function viewTrainingJob(jobId) {
    console.log(`Viewing training job ${jobId}`);
    
    const job = sampleTrainingHistory.find(j => j.id === jobId);
    
    if (job) {
        const model = sampleModels.find(m => m.name === job.model_name);
        
        if (model) {
            openModelDetails(model.id);
        } else {
            alert(`Modèle pour le job ${jobId} non trouvé.`);
        }
    } else {
        alert(`Job ${jobId} non trouvé.`);
    }
}

function downloadTrainingResults(jobId) {
    console.log(`Downloading results for job ${jobId}`);
    
    alert(`Téléchargement des résultats pour le job ${jobId} démarré.`);
}

function deleteTrainingJob(jobId) {
    console.log(`Deleting training job ${jobId}`);
    
    const index = sampleTrainingHistory.findIndex(job => job.id === jobId);
    
    if (index !== -1) {
        sampleTrainingHistory.splice(index, 1);
        populateTrainingHistory();
    }
}

function openModelDetails(modelId) {
    console.log(`Opening details for model ${modelId}`);
    
    const model = sampleModels.find(m => m.id === modelId);
    
    if (model) {
        document.getElementById('modal-model-name').textContent = model.name;
        document.getElementById('modal-agent-type').textContent = model.agent_type.toUpperCase();
        document.getElementById('modal-environment').textContent = model.environment;
        document.getElementById('modal-episodes').textContent = model.episodes;
        
        const date = new Date(model.creation_date);
        document.getElementById('modal-creation-date').textContent = `${date.toLocaleDateString()} ${date.toLocaleTimeString()}`;
        
        document.getElementById('modal-model-size').textContent = model.size;
        
        document.getElementById('modal-avg-reward').textContent = model.avg_reward.toFixed(2);
        document.getElementById('modal-max-reward').textContent = model.performance.max_reward.toFixed(2);
        document.getElementById('modal-return').textContent = `${model.return_pct.toFixed(2)}%`;
        document.getElementById('modal-sharpe').textContent = model.performance.sharpe_ratio.toFixed(2);
        document.getElementById('modal-drawdown').textContent = `${model.performance.max_drawdown.toFixed(2)}%`;
        
        document.getElementById('modal-learning-rate').textContent = model.hyperparams.learning_rate;
        document.getElementById('modal-gamma').textContent = model.hyperparams.gamma;
        document.getElementById('modal-batch-size').textContent = model.hyperparams.batch_size;
        document.getElementById('modal-clip-range').textContent = model.hyperparams.clip_range;
        document.getElementById('modal-entropy-coef').textContent = model.hyperparams.entropy_coef;
        
        document.getElementById('modal-layers').textContent = JSON.stringify(model.architecture.layers);
        document.getElementById('modal-activation').textContent = model.architecture.activation;
        document.getElementById('modal-optimizer').textContent = model.architecture.optimizer;
        
        document.getElementById('modal-deploy-btn').setAttribute('data-model-id', model.id);
        document.getElementById('modal-backtest-btn').setAttribute('data-model-id', model.id);
        document.getElementById('modal-export-btn').setAttribute('data-model-id', model.id);
        document.getElementById('modal-delete-btn').setAttribute('data-model-id', model.id);
        
        document.getElementById('model-details-modal').style.display = 'block';
    } else {
        alert(`Modèle ${modelId} non trouvé.`);
    }
}

function deployModel(modelId) {
    console.log(`Deploying model ${modelId}`);
    
    alert(`Déploiement du modèle ${modelId} démarré.`);
}

function backtestModel(modelId) {
    console.log(`Backtesting model ${modelId}`);
    
    alert(`Backtest du modèle ${modelId} démarré.`);
}

function exportModel(modelId) {
    console.log(`Exporting model ${modelId}`);
    
    alert(`Exportation du modèle ${modelId} démarrée.`);
}

function deleteModel(modelId) {
    console.log(`Deleting model ${modelId}`);
    
    const index = sampleModels.findIndex(model => model.id === modelId);
    
    if (index !== -1) {
        sampleModels.splice(index, 1);
        populateSavedModels();
    }
}

function showConfirmationModal(message, callback) {
    document.getElementById('confirmation-message').textContent = message;
    document.getElementById('confirmation-modal').style.display = 'block';
    
    window.confirmCallback = callback;
}

function closeModals() {
    document.getElementById('model-details-modal').style.display = 'none';
    document.getElementById('confirmation-modal').style.display = 'none';
}

function handleWebSocketMessage(data) {
    const message = JSON.parse(data);
    
    switch (message.type) {
        case 'episode_update':
            currentEpisode = message.episode;
            document.getElementById('current-episode').textContent = currentEpisode;
            
            const progress = (currentEpisode / totalEpisodes) * 100;
            document.getElementById('progress-fill').style.width = `${progress}%`;
            document.getElementById('progress-percentage').textContent = `${Math.round(progress)}%`;
            
            updateCharts(message.episode, message.reward, message.portfolio_value);
            
            document.getElementById('avg-reward').textContent = message.metrics.avg_reward.toFixed(2);
            document.getElementById('max-reward').textContent = message.metrics.max_reward.toFixed(2);
            document.getElementById('portfolio-return').textContent = `${message.metrics.return_pct.toFixed(2)}%`;
            document.getElementById('max-drawdown').textContent = `${message.metrics.max_drawdown.toFixed(2)}%`;
            document.getElementById('sharpe-ratio').textContent = message.metrics.sharpe_ratio.toFixed(2);
            document.getElementById('avg-loss').textContent = message.metrics.avg_loss.toFixed(2);
            document.getElementById('entropy').textContent = message.metrics.entropy.toFixed(2);
            document.getElementById('trade-count').textContent = message.metrics.trade_count;
            break;
            
        case 'training_complete':
            completeTraining();
            break;
            
        case 'training_error':
            alert(`Erreur d'entraînement: ${message.error}`);
            stopTraining();
            break;
    }
}

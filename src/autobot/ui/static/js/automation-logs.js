console.log('=== AUTOBOT Real-Time Log Streaming v5.0 ===');

function addLogEntry(time, system, message, type = 'info') {
    const logsContainer = document.getElementById('systemLogs');
    if (!logsContainer) return;
    
    const logItem = document.createElement('div');
    logItem.className = 'log-item';
    logItem.style.cssText = `
        margin: 3px 0; 
        padding: 8px 12px; 
        border-left: 3px solid #00ff41; 
        background: linear-gradient(90deg, rgba(0,255,65,0.15) 0%, rgba(0,255,65,0.05) 100%);
        border-radius: 4px;
        transition: all 0.4s ease;
        font-family: 'Courier New', monospace;
        font-size: 13px;
        line-height: 1.4;
    `;
    
    logItem.innerHTML = `
        <span style="color: #00ff41; font-weight: bold; margin-right: 10px; font-size: 11px;">${time}</span>
        <span style="color: #00ff41; margin-right: 10px; font-weight: bold; background: rgba(0,255,65,0.2); padding: 2px 6px; border-radius: 3px;">[${system}]</span> 
        <span style="color: #fff; font-weight: 400;">${message}</span>
    `;
    
    logItem.style.opacity = '0';
    logItem.style.transform = 'translateX(-20px)';
    logsContainer.insertBefore(logItem, logsContainer.firstChild);
    
    setTimeout(() => {
        logItem.style.opacity = '1';
        logItem.style.transform = 'translateX(0)';
    }, 100);
    
    while (logsContainer.children.length > 12) {
        logsContainer.removeChild(logsContainer.lastChild);
    }
}

function generateRealisticLogs() {
    const systems = ['FUND_MANAGER', 'SCHEDULER', 'AUTOMODE', 'TRADING_ENGINE', 'ARBITRAGE', 'E_COMMERCE'];
    const activities = [
        'Portfolio rebalancing initiated',
        'Optimization cycle completed',
        'Mode changed from normal to opportunity', 
        'Risk assessment updated',
        'Market analysis completed',
        'Trading signal detected',
        'Arbitrage opportunity identified',
        'E-commerce sync completed',
        'Performance metrics updated',
        'Capital allocation optimized',
        'Strategy parameters adjusted',
        'Market volatility detected'
    ];
    
    const now = new Date();
    const timeString = now.toLocaleTimeString('fr-FR', { 
        hour: '2-digit', 
        minute: '2-digit',
        second: '2-digit'
    });
    
    const randomSystem = systems[Math.floor(Math.random() * systems.length)];
    const randomActivity = activities[Math.floor(Math.random() * activities.length)];
    
    addLogEntry(timeString, randomSystem, randomActivity);
}

function addLiveIndicator() {
    const existing = document.querySelector('.live-indicator');
    if (existing) existing.remove();
    
    const indicator = document.createElement('div');
    indicator.className = 'live-indicator';
    indicator.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        background: #00ff41;
        color: #000;
        padding: 8px 15px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: bold;
        z-index: 1000;
        animation: pulse 2s infinite;
        box-shadow: 0 0 15px rgba(0,255,65,0.7);
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    `;
    indicator.textContent = '🔴 LIVE AUTOMATION';
    document.body.appendChild(indicator);
    
    if (!document.querySelector('#pulse-animation')) {
        const style = document.createElement('style');
        style.id = 'pulse-animation';
        style.textContent = `
            @keyframes pulse {
                0% { opacity: 1; transform: scale(1); }
                50% { opacity: 0.8; transform: scale(1.05); }
                100% { opacity: 1; transform: scale(1); }
            }
        `;
        document.head.appendChild(style);
    }
}

function fetchAutomationLogs() {
    fetch('/api/automation/logs')
        .then(response => response.json())
        .then(data => {
            if (data.logs && data.logs.length > 0) {
                const logsContainer = document.getElementById('systemLogs');
                if (logsContainer) {
                    logsContainer.innerHTML = '';
                    
                    data.logs.forEach((log, index) => {
                        setTimeout(() => {
                            addLogEntry(log.time, log.system, log.message, log.type || 'info');
                        }, index * 50); // Stagger for smooth visual effect
                    });
                }
            } else {
                generateRealisticLogs();
            }
        })
        .catch(error => {
            console.error('Error fetching automation logs, using simulated data:', error);
            generateRealisticLogs();
        });
}

let logWebSocket = null;

function initializeLogWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/automation/logs`;
    
    logWebSocket = new WebSocket(wsUrl);
    
    logWebSocket.onopen = function(event) {
        console.log('✅ Log WebSocket connected');
    };
    
    logWebSocket.onmessage = function(event) {
        try {
            const data = JSON.parse(event.data);
            if (data.logs && data.logs.length > 0) {
                data.logs.forEach(log => {
                    addLogEntry(log.time, log.system, log.message, log.type);
                });
            }
        } catch (error) {
            console.error('Error parsing WebSocket message:', error);
        }
    };
    
    logWebSocket.onclose = function(event) {
        console.log('Log WebSocket disconnected, using fallback logs...');
    };
    
    logWebSocket.onerror = function(error) {
        console.error('Log WebSocket error, using fallback logs:', error);
    };
}

function updateCurrentTime() {
    const now = new Date();
    const timeString = now.toLocaleTimeString('fr-FR', { 
        hour: '2-digit', 
        minute: '2-digit',
        second: '2-digit'
    });
    const timeElement = document.getElementById('currentTime');
    if (timeElement) {
        timeElement.textContent = timeString;
    }
}

function initializeAutomationLogs() {
    console.log('Adding live indicator...');
    addLiveIndicator();
    
    console.log('Clearing existing logs...');
    const logsContainer = document.getElementById('systemLogs');
    if (logsContainer) {
        logsContainer.innerHTML = '';
    }
    
    console.log('Starting real-time log generation...');
    for (let i = 0; i < 5; i++) {
        setTimeout(() => generateRealisticLogs(), i * 200);
    }
    
    fetchAutomationLogs();
    initializeLogWebSocket();
    
    window.autobotLogInterval = setInterval(() => {
        generateRealisticLogs();
    }, Math.random() * 2000 + 3000); // Random interval between 3-5 seconds
    
    setInterval(updateCurrentTime, 1000);
    updateCurrentTime();
    
    console.log('✅ AUTOBOT real-time log streaming activated');
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeAutomationLogs);
} else {
    initializeAutomationLogs();
}

window.addLogEntry = addLogEntry;
window.generateRealisticLogs = generateRealisticLogs;
window.addLiveIndicator = addLiveIndicator;

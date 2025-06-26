/**
 * Performance monitoring module for AUTOBOT
 * Provides real-time performance metrics visualization
 */

class PerformanceMonitor {
    constructor(options = {}) {
        this.options = {
            updateInterval: options.updateInterval || 5000,
            historyLength: options.historyLength || 100,
            container: options.container || document.getElementById('performance-metrics'),
            endpoint: options.endpoint || '/monitoring/performance'
        };
        
        this.metrics = {
            cpu: [],
            memory: [],
            latency: [],
            throughput: [],
            errorRate: []
        };
        
        this.charts = {};
        this.isMonitoring = false;
        this.updateTimer = null;
    }
    
    initialize() {
        if (!this.options.container) {
            console.error('Performance monitor container not found');
            return false;
        }
        
        this.createChartContainers();
        this.initializeCharts();
        return true;
    }
    
    createChartContainers() {
        const container = this.options.container;
        container.innerHTML = `
            <div class="performance-header">
                <h3>System Performance</h3>
                <div class="controls">
                    <button id="start-monitoring" class="btn btn-primary">Start Monitoring</button>
                    <button id="stop-monitoring" class="btn btn-secondary" disabled>Stop</button>
                    <select id="update-interval" class="form-select">
                        <option value="1000">1s</option>
                        <option value="5000" selected>5s</option>
                        <option value="10000">10s</option>
                        <option value="30000">30s</option>
                    </select>
                </div>
            </div>
            <div class="performance-grid">
                <div class="chart-container">
                    <canvas id="cpu-chart"></canvas>
                </div>
                <div class="chart-container">
                    <canvas id="memory-chart"></canvas>
                </div>
                <div class="chart-container">
                    <canvas id="latency-chart"></canvas>
                </div>
                <div class="chart-container">
                    <canvas id="throughput-chart"></canvas>
                </div>
                <div class="chart-container">
                    <canvas id="error-rate-chart"></canvas>
                </div>
            </div>
        `;
        
        document.getElementById('start-monitoring').addEventListener('click', () => this.startMonitoring());
        document.getElementById('stop-monitoring').addEventListener('click', () => this.stopMonitoring());
        document.getElementById('update-interval').addEventListener('change', (e) => {
            this.options.updateInterval = parseInt(e.target.value);
            if (this.isMonitoring) {
                this.stopMonitoring();
                this.startMonitoring();
            }
        });
    }
    
    initializeCharts() {
        const commonOptions = {
            responsive: true,
            maintainAspectRatio: false,
            animation: {
                duration: 500
            },
            scales: {
                x: {
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)'
                    },
                    ticks: {
                        color: '#00ff00',
                        maxTicksLimit: 10
                    }
                },
                y: {
                    beginAtZero: true,
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
        };
        
        this.charts.cpu = new Chart(document.getElementById('cpu-chart').getContext('2d'), {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'CPU Usage (%)',
                    data: [],
                    borderColor: '#00ff00',
                    backgroundColor: 'rgba(0, 255, 0, 0.1)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.4
                }]
            },
            options: {
                ...commonOptions,
                plugins: {
                    ...commonOptions.plugins,
                    title: {
                        display: true,
                        text: 'CPU Usage',
                        color: '#00ff00'
                    }
                }
            }
        });
        
        this.charts.memory = new Chart(document.getElementById('memory-chart').getContext('2d'), {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'Memory Usage (MB)',
                    data: [],
                    borderColor: '#00ccff',
                    backgroundColor: 'rgba(0, 204, 255, 0.1)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.4
                }]
            },
            options: {
                ...commonOptions,
                plugins: {
                    ...commonOptions.plugins,
                    title: {
                        display: true,
                        text: 'Memory Usage',
                        color: '#00ff00'
                    }
                }
            }
        });
        
        this.charts.latency = new Chart(document.getElementById('latency-chart').getContext('2d'), {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'API Latency (ms)',
                    data: [],
                    borderColor: '#ffcc00',
                    backgroundColor: 'rgba(255, 204, 0, 0.1)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.4
                }]
            },
            options: {
                ...commonOptions,
                plugins: {
                    ...commonOptions.plugins,
                    title: {
                        display: true,
                        text: 'API Latency',
                        color: '#00ff00'
                    }
                }
            }
        });
        
        this.charts.throughput = new Chart(document.getElementById('throughput-chart').getContext('2d'), {
            type: 'bar',
            data: {
                labels: [],
                datasets: [{
                    label: 'Requests/sec',
                    data: [],
                    backgroundColor: 'rgba(0, 255, 0, 0.5)',
                    borderColor: '#00ff00',
                    borderWidth: 1
                }]
            },
            options: {
                ...commonOptions,
                plugins: {
                    ...commonOptions.plugins,
                    title: {
                        display: true,
                        text: 'Throughput',
                        color: '#00ff00'
                    }
                }
            }
        });
        
        this.charts.errorRate = new Chart(document.getElementById('error-rate-chart').getContext('2d'), {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'Error Rate (%)',
                    data: [],
                    borderColor: '#ff3333',
                    backgroundColor: 'rgba(255, 51, 51, 0.1)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.4
                }]
            },
            options: {
                ...commonOptions,
                plugins: {
                    ...commonOptions.plugins,
                    title: {
                        display: true,
                        text: 'Error Rate',
                        color: '#00ff00'
                    }
                }
            }
        });
    }
    
    startMonitoring() {
        if (this.isMonitoring) return;
        
        this.isMonitoring = true;
        document.getElementById('start-monitoring').disabled = true;
        document.getElementById('stop-monitoring').disabled = false;
        
        this.updateMetrics();
        this.updateTimer = setInterval(() => this.updateMetrics(), this.options.updateInterval);
    }
    
    stopMonitoring() {
        if (!this.isMonitoring) return;
        
        this.isMonitoring = false;
        document.getElementById('start-monitoring').disabled = false;
        document.getElementById('stop-monitoring').disabled = true;
        
        if (this.updateTimer) {
            clearInterval(this.updateTimer);
            this.updateTimer = null;
        }
    }
    
    async updateMetrics() {
        try {
            const response = await fetch(this.options.endpoint);
            const data = await response.json();
            
            this.addMetric('cpu', data.cpu_usage);
            this.addMetric('memory', data.memory_usage);
            this.addMetric('latency', data.api_latency);
            this.addMetric('throughput', data.throughput);
            this.addMetric('errorRate', data.error_rate);
            
            this.updateCharts();
            
        } catch (error) {
            console.error('Error fetching performance metrics:', error);
            this.stopMonitoring();
            showNotification('Error fetching performance metrics', 'error');
        }
    }
    
    addMetric(type, value) {
        const now = new Date();
        const timeLabel = now.toLocaleTimeString();
        
        this.metrics[type].push({
            time: timeLabel,
            value: value
        });
        
        if (this.metrics[type].length > this.options.historyLength) {
            this.metrics[type].shift();
        }
    }
    
    updateCharts() {
        for (const [type, chart] of Object.entries(this.charts)) {
            const data = this.metrics[type];
            
            chart.data.labels = data.map(item => item.time);
            chart.data.datasets[0].data = data.map(item => item.value);
            
            chart.update();
        }
    }
    
    simulateMetrics() {
        return {
            cpu_usage: Math.random() * 100,
            memory_usage: 500 + Math.random() * 1500,
            api_latency: 50 + Math.random() * 200,
            throughput: 10 + Math.random() * 90,
            error_rate: Math.random() * 5
        };
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const performanceMonitor = new PerformanceMonitor();
    if (performanceMonitor.initialize()) {
        performanceMonitor.updateMetrics = async function() {
            const data = this.simulateMetrics();
            
            this.addMetric('cpu', data.cpu_usage);
            this.addMetric('memory', data.memory_usage);
            this.addMetric('latency', data.api_latency);
            this.addMetric('throughput', data.throughput);
            this.addMetric('errorRate', data.error_rate);
            
            this.updateCharts();
        };
    }
});

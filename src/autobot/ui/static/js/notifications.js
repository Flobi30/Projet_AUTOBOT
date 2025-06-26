/**
 * Notification system for AUTOBOT UI.
 * Provides client-side handling of notifications.
 */

class NotificationSystem {
    /**
     * Initialize the notification system.
     */
    constructor() {
        this.notifications = {};
        this.container = null;
        this.positions = {
            'top-right': null,
            'top-left': null,
            'bottom-right': null,
            'bottom-left': null,
            'top-center': null,
            'bottom-center': null
        };
        
        this.init();
        this.setupEventSource();
    }
    
    /**
     * Initialize the notification containers.
     */
    init() {
        if (!this.container) {
            this.container = document.createElement('div');
            this.container.id = 'notification-container';
            document.body.appendChild(this.container);
            
            for (const position in this.positions) {
                const posContainer = document.createElement('div');
                posContainer.className = `notification-position ${position}`;
                this.container.appendChild(posContainer);
                this.positions[position] = posContainer;
            }
            
            if (!document.getElementById('notification-styles')) {
                const style = document.createElement('link');
                style.id = 'notification-styles';
                style.rel = 'stylesheet';
                style.href = '/static/css/notification.css';
                document.head.appendChild(style);
            }
        }
    }
    
    /**
     * Set up event source for server-sent notifications.
     */
    setupEventSource() {
        try {
            const eventSource = new EventSource('/api/notifications/stream');
            
            eventSource.onmessage = (event) => {
                try {
                    const notification = JSON.parse(event.data);
                    this.show(notification);
                } catch (error) {
                    console.error('Error parsing notification:', error);
                }
            };
            
            eventSource.onerror = (error) => {
                console.error('EventSource error:', error);
                eventSource.close();
                
                setTimeout(() => this.setupEventSource(), 5000);
            };
        } catch (error) {
            console.error('Failed to setup EventSource:', error);
        }
    }
    
    /**
     * Show a notification.
     * 
     * @param {Object} options - Notification options
     * @param {string} options.id - Notification ID
     * @param {string} options.message - Notification message
     * @param {string} options.type - Notification type (success, error, warning, info)
     * @param {string} [options.title] - Optional notification title
     * @param {number} [options.duration=5000] - Display duration in milliseconds
     * @param {string} [options.position='top-right'] - Display position
     * @param {boolean} [options.closable=true] - Whether the notification can be closed manually
     * @param {boolean} [options.autoClose=true] - Whether the notification should close automatically
     * @param {string} [options.icon] - Optional icon for the notification
     * @returns {string} Notification ID
     */
    show(options) {
        const id = options.id || this.generateId();
        
        const notification = {
            id,
            message: options.message || '',
            type: options.type || 'info',
            title: options.title || '',
            duration: options.duration || 5000,
            position: options.position || 'top-right',
            closable: options.closable !== false,
            autoClose: options.autoClose !== false,
            icon: options.icon || null
        };
        
        const element = this.createNotificationElement(notification);
        
        const positionContainer = this.positions[notification.position];
        if (positionContainer) {
            positionContainer.appendChild(element);
        } else {
            this.positions['top-right'].appendChild(element);
        }
        
        this.notifications[id] = {
            element,
            timer: null
        };
        
        if (notification.autoClose && notification.duration > 0) {
            this.notifications[id].timer = setTimeout(() => {
                this.close(id);
            }, notification.duration);
        }
        
        setTimeout(() => {
            element.classList.add('show');
        }, 10);
        
        return id;
    }
    
    /**
     * Create a notification element.
     * 
     * @param {Object} notification - Notification object
     * @returns {HTMLElement} Notification element
     */
    createNotificationElement(notification) {
        const element = document.createElement('div');
        element.className = `notification notification-${notification.type}`;
        element.dataset.id = notification.id;
        
        let html = '';
        
        if (notification.icon) {
            html += `<div class="notification-icon">${notification.icon}</div>`;
        } else {
            const icons = {
                success: '<svg viewBox="0 0 24 24"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41L9 16.17z"></path></svg>',
                error: '<svg viewBox="0 0 24 24"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12 19 6.41z"></path></svg>',
                warning: '<svg viewBox="0 0 24 24"><path d="M12 2L1 21h22L12 2zm0 3.99L19.53 19H4.47L12 5.99zM11 16h2v2h-2zm0-6h2v4h-2z"></path></svg>',
                info: '<svg viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 15c-.55 0-1-.45-1-1v-4c0-.55.45-1 1-1s1 .45 1 1v4c0 .55-.45 1-1 1zm1-8h-2V7h2v2z"></path></svg>'
            };
            html += `<div class="notification-icon">${icons[notification.type] || icons.info}</div>`;
        }
        
        html += '<div class="notification-content">';
        
        if (notification.title) {
            html += `<div class="notification-title">${notification.title}</div>`;
        }
        
        html += `<div class="notification-message">${notification.message}</div>`;
        html += '</div>';
        
        if (notification.closable) {
            html += `
                <button class="notification-close" aria-label="Close">
                    <svg viewBox="0 0 24 24"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12 19 6.41z"></path></svg>
                </button>
            `;
        }
        
        element.innerHTML = html;
        
        if (notification.closable) {
            const closeButton = element.querySelector('.notification-close');
            if (closeButton) {
                closeButton.addEventListener('click', () => {
                    this.close(notification.id);
                });
            }
        }
        
        return element;
    }
    
    /**
     * Close a notification.
     * 
     * @param {string} id - Notification ID
     */
    close(id) {
        const notification = this.notifications[id];
        if (!notification) return;
        
        if (notification.timer) {
            clearTimeout(notification.timer);
        }
        
        notification.element.classList.remove('show');
        notification.element.classList.add('hide');
        
        setTimeout(() => {
            if (notification.element.parentNode) {
                notification.element.parentNode.removeChild(notification.element);
            }
            delete this.notifications[id];
        }, 300);
        
        fetch(`/api/notifications/${id}/close`, { method: 'POST' })
            .catch(error => console.error('Error closing notification:', error));
    }
    
    /**
     * Close all notifications.
     */
    closeAll() {
        for (const id in this.notifications) {
            this.close(id);
        }
    }
    
    /**
     * Generate a unique ID.
     * 
     * @returns {string} Unique ID
     */
    generateId() {
        return 'notification-' + Math.random().toString(36).substr(2, 9);
    }
    
    /**
     * Show a success notification.
     * 
     * @param {string} message - Notification message
     * @param {Object} [options={}] - Additional options
     * @returns {string} Notification ID
     */
    success(message, options = {}) {
        return this.show({
            ...options,
            message,
            type: 'success'
        });
    }
    
    /**
     * Show an error notification.
     * 
     * @param {string} message - Notification message
     * @param {Object} [options={}] - Additional options
     * @returns {string} Notification ID
     */
    error(message, options = {}) {
        return this.show({
            ...options,
            message,
            type: 'error',
            duration: options.duration || 0 // Errors don't auto-close by default
        });
    }
    
    /**
     * Show a warning notification.
     * 
     * @param {string} message - Notification message
     * @param {Object} [options={}] - Additional options
     * @returns {string} Notification ID
     */
    warning(message, options = {}) {
        return this.show({
            ...options,
            message,
            type: 'warning'
        });
    }
    
    /**
     * Show an info notification.
     * 
     * @param {string} message - Notification message
     * @param {Object} [options={}] - Additional options
     * @returns {string} Notification ID
     */
    info(message, options = {}) {
        return this.show({
            ...options,
            message,
            type: 'info'
        });
    }
}

const notifications = new NotificationSystem();

window.notifications = notifications;

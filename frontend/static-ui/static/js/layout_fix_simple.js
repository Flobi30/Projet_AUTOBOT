/**
 * AUTOBOT Layout Visibility Fix
 * This script ensures the main content area is visible alongside the sidebar
 */
(function() {
    console.log("Applying AUTOBOT layout visibility fix...");
    
    function applyLayoutFix() {
        // Create and apply CSS fix
        const style = document.createElement('style');
        style.id = 'autobot-layout-fix-js';
        style.textContent = `
            /* Force main content to be visible */
            .main-content {
                display: block !important;
                visibility: visible !important;
                position: relative !important;
                margin-left: 250px !important;
                width: calc(100% - 250px) !important;
                min-height: 100vh !important;
                padding: 20px !important;
                box-sizing: border-box !important;
                z-index: 1 !important;
                overflow-x: hidden !important;
                background-color: #121212 !important;
            }
            
            /* Ensure sidebar is properly positioned */
            .sidebar {
                position: fixed !important;
                top: 0 !important;
                left: 0 !important;
                width: 250px !important;
                height: 100vh !important;
                z-index: 10 !important;
                overflow-y: auto !important;
                background-color: #121212 !important;
            }
            
            /* Fix container elements */
            .container, .container-fluid, .wrapper {
                width: 100% !important;
                max-width: 100% !important;
                display: block !important;
                overflow: visible !important;
                position: relative !important;
            }
            
            /* Fix section elements */
            section, .content, .dashboard-content {
                display: block !important;
                visibility: visible !important;
                position: relative !important;
                width: 100% !important;
            }
            
            /* Fix card elements */
            .card, .panel, .box {
                display: block !important;
                visibility: visible !important;
                position: relative !important;
                margin-bottom: 20px !important;
                background-color: #1e1e1e !important;
                border-radius: 8px !important;
                padding: 15px !important;
            }
            
            /* Responsive adjustments */
            @media (max-width: 768px) {
                .sidebar {
                    width: 70px !important;
                    min-width: 70px !important;
                }
                
                .main-content {
                    margin-left: 70px !important;
                    width: calc(100% - 70px) !important;
                }
            }
        `;
        
        // Add the style to the document if it doesn't already exist
        if (!document.getElementById('autobot-layout-fix-js')) {
            document.head.appendChild(style);
        }
        
        // Apply direct style fixes to elements
        const mainContent = document.querySelector('.main-content');
        if (mainContent) {
            mainContent.style.display = 'block';
            mainContent.style.visibility = 'visible';
            mainContent.style.opacity = '1';
            mainContent.style.width = 'calc(100% - 250px)';
            mainContent.style.marginLeft = '250px';
            mainContent.style.minHeight = '100vh';
            mainContent.style.padding = '20px';
            mainContent.style.boxSizing = 'border-box';
            mainContent.style.position = 'relative';
            mainContent.style.zIndex = '1';
            mainContent.style.overflow = 'visible';
        }
        
        const sidebar = document.querySelector('.sidebar');
        if (sidebar) {
            sidebar.style.width = '250px';
            sidebar.style.minWidth = '250px';
            sidebar.style.position = 'fixed';
            sidebar.style.height = '100vh';
            sidebar.style.zIndex = '1000';
            sidebar.style.left = '0';
            sidebar.style.top = '0';
        }
        
        document.body.style.display = 'flex';
        document.body.style.flexDirection = 'row';
        document.body.style.minHeight = '100vh';
        document.body.style.margin = '0';
        document.body.style.padding = '0';
        document.body.style.overflowX = 'hidden';
        
        const containers = document.querySelectorAll('.container, .container-fluid, .row, .col, .card');
        containers.forEach(container => {
            container.style.display = 'block';
            container.style.visibility = 'visible';
            container.style.opacity = '1';
            container.style.overflow = 'visible';
        });
        
        console.log("AUTOBOT layout visibility fix applied");
    }
    
    // Apply fix on DOMContentLoaded
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', applyLayoutFix);
    } else {
        applyLayoutFix();
    }
    
    // Apply fix on load to ensure it works even if DOM is already loaded
    window.addEventListener('load', applyLayoutFix);
    
    // Apply fix after a short delay to ensure it works even if other scripts modify the DOM
    setTimeout(applyLayoutFix, 500);
    setTimeout(applyLayoutFix, 1000);
    setTimeout(applyLayoutFix, 2000);
})();

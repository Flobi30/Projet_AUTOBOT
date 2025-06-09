/**
 * AUTOBOT Layout Visibility Fix v3
 * This script ensures the main content area is visible alongside the sidebar
 * It uses a more aggressive approach to override any conflicting styles
 */
(function() {
    console.log("Applying AUTOBOT layout visibility fix v3...");
    
    applyLayoutFix();
    
    document.addEventListener('DOMContentLoaded', applyLayoutFix);
    
    window.addEventListener('load', applyLayoutFix);
    
    setTimeout(applyLayoutFix, 500);
    setTimeout(applyLayoutFix, 1000);
    setTimeout(applyLayoutFix, 2000);
    
    function applyLayoutFix() {
        console.log("Applying layout visibility fix...");
        
        const style = document.createElement('style');
        style.id = 'autobot-layout-fix-v3';
        style.textContent = `
            /* Force main content to be visible */
            .main-content, 
            .container, 
            .container-fluid, 
            .row, 
            .col, 
            .card {
                display: block !important;
                visibility: visible !important;
                opacity: 1 !important;
                overflow: visible !important;
            }
            
            /* Ensure proper layout with sidebar */
            body {
                display: flex !important;
                flex-direction: row !important;
                min-height: 100vh !important;
                margin: 0 !important;
                padding: 0 !important;
                overflow-x: hidden !important;
            }
            
            /* Fix sidebar */
            .sidebar {
                width: 250px !important;
                min-width: 250px !important;
                position: fixed !important;
                height: 100vh !important;
                z-index: 1000 !important;
                left: 0 !important;
                top: 0 !important;
            }
            
            /* Fix main content area */
            .main-content {
                margin-left: 250px !important;
                width: calc(100% - 250px) !important;
                min-height: 100vh !important;
                padding: 20px !important;
                box-sizing: border-box !important;
                position: relative !important;
                z-index: 1 !important;
                flex: 1 !important;
            }
            
            /* Fix logo proportions */
            .logo img {
                height: 60px !important;
                width: auto !important;
                margin-right: 15px !important;
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
            
            /* Fix for specific elements */
            #dashboard-content,
            #parametres-content,
            #ecommerce-content,
            .dashboard-container,
            .parametres-container,
            .ecommerce-container {
                display: block !important;
                visibility: visible !important;
                opacity: 1 !important;
                width: 100% !important;
            }
            
            /* Fix for tables */
            table, tr, td, th {
                visibility: visible !important;
                display: table !important;
            }
            tr {
                display: table-row !important;
            }
            td, th {
                display: table-cell !important;
            }
            
            /* Fix for charts and graphs */
            canvas, svg {
                display: block !important;
                visibility: visible !important;
                opacity: 1 !important;
            }
        `;
        
        const existingStyle = document.getElementById('autobot-layout-fix-v3');
        if (existingStyle) {
            existingStyle.remove();
        }
        
        document.head.appendChild(style);
        
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
            mainContent.style.flex = '1';
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
        
        const logoImg = document.querySelector('.logo img');
        if (logoImg) {
            logoImg.style.height = '60px';
            logoImg.style.width = 'auto';
            logoImg.style.marginRight = '15px';
        }
        
        console.log("Layout visibility fix v3 applied");
    }
})();

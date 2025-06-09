/**
 * AUTOBOT Layout Visibility Fix
 * This script forces the main content area to be visible while preserving the sidebar.
 * It uses !important flags to override any conflicting CSS rules.
 */
(function() {
    function applyLayoutFixes() {
        const style = document.createElement('style');
        style.textContent = `
            /* Force main content to be visible */
            .main-content, #main-content, main, .content, #content {
                display: block !important;
                visibility: visible !important;
                opacity: 1 !important;
                margin-left: 250px !important;
                width: calc(100% - 250px) !important;
                position: relative !important;
                z-index: 1 !important;
                padding: 20px !important;
                min-height: 100vh !important;
                box-sizing: border-box !important;
                overflow-x: hidden !important;
            }
            
            /* Ensure sidebar doesn't overlap */
            .sidebar, #sidebar, .side-nav, #side-nav, nav.sidebar {
                width: 250px !important;
                position: fixed !important;
                z-index: 2 !important;
                height: 100vh !important;
                overflow-y: auto !important;
            }
            
            /* Fix container */
            .container, .container-fluid {
                width: 100% !important;
                padding-right: 15px !important;
                padding-left: 15px !important;
                margin-right: auto !important;
                margin-left: auto !important;
                display: block !important;
                visibility: visible !important;
                opacity: 1 !important;
            }
            
            /* Fix row and columns */
            .row {
                display: flex !important;
                flex-wrap: wrap !important;
                margin-right: -15px !important;
                margin-left: -15px !important;
                visibility: visible !important;
                opacity: 1 !important;
            }
            
            /* Fix cards */
            .card {
                display: block !important;
                visibility: visible !important;
                opacity: 1 !important;
                margin-bottom: 20px !important;
            }
            
            /* Fix body layout */
            body {
                display: flex !important;
                flex-direction: row !important;
                min-height: 100vh !important;
                margin: 0 !important;
                padding: 0 !important;
                overflow-x: hidden !important;
            }
        `;
        
        document.head.appendChild(style);
        
        document.body.style.display = 'none';
        setTimeout(() => {
            document.body.style.display = '';
        }, 50);
    }
    
    applyLayoutFixes();
    
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', applyLayoutFixes);
    }
    
    window.addEventListener('load', applyLayoutFixes);
    
    setInterval(applyLayoutFixes, 1000);
})();

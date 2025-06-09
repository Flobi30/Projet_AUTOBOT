
/**
 * AUTOBOT Layout Visibility Fix
 * This script ensures the main content area is visible alongside the sidebar
 */
(function() {
    console.log("Applying layout visibility fix...");
    
    function fixLayoutVisibility() {
        // Force main content to be visible
        const mainContent = document.querySelector('.main-content');
        if (mainContent) {
            mainContent.style.display = 'block';
            mainContent.style.visibility = 'visible';
            mainContent.style.width = 'calc(100% - 250px)';
            mainContent.style.marginLeft = '250px';
            mainContent.style.position = 'relative';
            mainContent.style.zIndex = '1';
            mainContent.style.opacity = '1';
            mainContent.style.minHeight = '100vh';
            mainContent.style.padding = '20px';
            mainContent.style.boxSizing = 'border-box';
        }
        
        // Fix sidebar
        const sidebar = document.querySelector('.sidebar');
        if (sidebar) {
            sidebar.style.position = 'fixed';
            sidebar.style.width = '250px';
            sidebar.style.minWidth = '250px';
            sidebar.style.height = '100vh';
            sidebar.style.zIndex = '1000';
        }
        
        // Fix containers
        const containers = document.querySelectorAll('.container, .container-fluid, .row, .col, .card');
        containers.forEach(container => {
            container.style.display = 'block';
            container.style.visibility = 'visible';
            container.style.opacity = '1';
        });
        
        // Fix body
        document.body.style.display = 'flex';
        document.body.style.flexDirection = 'row';
        document.body.style.minHeight = '100vh';
        document.body.style.margin = '0';
        document.body.style.padding = '0';
        
        // Fix logo proportions
        const logoImg = document.querySelector('.logo img');
        if (logoImg) {
            logoImg.style.height = '60px';
            logoImg.style.width = 'auto';
            logoImg.style.marginRight = '15px';
        }
        
        console.log("Layout visibility fix applied");
    }
    
    // Apply fix immediately
    fixLayoutVisibility();
    
    // Apply fix after DOM content loaded
    document.addEventListener('DOMContentLoaded', fixLayoutVisibility);
    
    // Apply fix after window load
    window.addEventListener('load', fixLayoutVisibility);
    
    // Apply fix after a delay to ensure it works even if other scripts modify the DOM
    setTimeout(fixLayoutVisibility, 500);
    setTimeout(fixLayoutVisibility, 1000);
    setTimeout(fixLayoutVisibility, 2000);
})();

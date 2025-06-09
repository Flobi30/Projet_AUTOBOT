
// Aggressive layout fix to ensure main content is visible
document.addEventListener('DOMContentLoaded', function() {
    // Function to fix layout
    function fixLayout() {
        // Fix main content
        const mainContent = document.querySelector('.main-content');
        if (mainContent) {
            mainContent.style.marginLeft = '250px';
            mainContent.style.width = 'calc(100% - 250px)';
            mainContent.style.display = 'block';
            mainContent.style.visibility = 'visible';
            mainContent.style.position = 'relative';
            mainContent.style.minHeight = '100vh';
            mainContent.style.padding = '20px';
            mainContent.style.boxSizing = 'border-box';
            mainContent.style.overflow = 'auto';
            mainContent.style.zIndex = '1';
            mainContent.style.opacity = '1';
        }
        
        // Fix sidebar
        const sidebar = document.querySelector('.sidebar');
        if (sidebar) {
            sidebar.style.width = '250px';
            sidebar.style.position = 'fixed';
            sidebar.style.height = '100%';
            sidebar.style.zIndex = '2';
            sidebar.style.display = 'block';
            sidebar.style.visibility = 'visible';
        }
        
        // Fix content containers
        const containers = document.querySelectorAll('.dashboard-container, .settings-container, .trading-container, .backtest-container, .arbitrage-container, .ecommerce-container, .capital-container');
        containers.forEach(container => {
            container.style.display = 'block';
            container.style.visibility = 'visible';
            container.style.width = '100%';
            container.style.padding = '20px';
            container.style.boxSizing = 'border-box';
        });
        
        // Fix cards and widgets
        const elements = document.querySelectorAll('.card, .widget');
        elements.forEach(element => {
            element.style.display = 'block';
            element.style.visibility = 'visible';
            element.style.opacity = '1';
            element.style.marginBottom = '20px';
        });
        
        // Fix tables
        const tables = document.querySelectorAll('table');
        tables.forEach(table => {
            table.style.width = '100%';
            table.style.display = 'table';
            table.style.visibility = 'visible';
        });
        
        // Fix forms
        const forms = document.querySelectorAll('form');
        forms.forEach(form => {
            form.style.display = 'block';
            form.style.visibility = 'visible';
        });
    }
    
    // Run layout fix immediately
    fixLayout();
    
    // Run layout fix again after a short delay to handle dynamic content
    setTimeout(fixLayout, 500);
    
    // Run layout fix again after page is fully loaded
    window.addEventListener('load', fixLayout);
    
    // Run layout fix periodically to ensure it stays fixed
    setInterval(fixLayout, 2000);
});

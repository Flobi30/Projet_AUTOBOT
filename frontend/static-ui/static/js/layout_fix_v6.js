
// Layout fix to ensure main content is visible
document.addEventListener('DOMContentLoaded', function() {
    // Force main content to be visible
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
    }

    // Ensure sidebar is properly positioned
    const sidebar = document.querySelector('.sidebar');
    if (sidebar) {
        sidebar.style.width = '250px';
        sidebar.style.position = 'fixed';
        sidebar.style.height = '100%';
        sidebar.style.zIndex = '2';
        sidebar.style.overflowY = 'auto';
    }

    // Force all potentially hidden elements to be visible
    document.querySelectorAll('.container, .container-fluid, .row, .col, .col-md-12, .card').forEach(function(element) {
        element.style.display = 'block';
        element.style.visibility = 'visible';
        element.style.opacity = '1';
    });

    // Fix dashboard cards
    document.querySelectorAll('.dashboard-card').forEach(function(card) {
        card.style.display = 'block';
        card.style.visibility = 'visible';
        card.style.marginBottom = '20px';
    });

    // Fix tables
    document.querySelectorAll('table').forEach(function(table) {
        table.style.width = '100%';
        table.style.display = 'table';
        table.style.visibility = 'visible';
    });

    // Fix any elements with inline styles hiding them
    document.querySelectorAll('[style*="display: none"]').forEach(function(element) {
        element.style.display = 'block';
    });

    document.querySelectorAll('[style*="visibility: hidden"]').forEach(function(element) {
        element.style.visibility = 'visible';
    });

    document.querySelectorAll('[style*="opacity: 0"]').forEach(function(element) {
        element.style.opacity = '1';
    });
});

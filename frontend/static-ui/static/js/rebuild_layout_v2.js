/**
 * Complete page structure rebuild for AUTOBOT layout issues - Version 2
 * This script completely rebuilds the page structure to ensure content visibility
 * with improved reliability and compatibility
 */

(function() {
    console.log("AUTOBOT Layout Rebuild V2 starting immediately");
    
    rebuildLayout();
    
    document.addEventListener('DOMContentLoaded', function() {
        console.log("AUTOBOT Layout Rebuild V2 on DOMContentLoaded");
        rebuildLayout();
        
        setTimeout(rebuildLayout, 500);
        setTimeout(rebuildLayout, 1000);
    });
    
    window.addEventListener('load', function() {
        console.log("AUTOBOT Layout Rebuild V2 on window.load");
        rebuildLayout();
        
        setTimeout(rebuildLayout, 500);
        setTimeout(rebuildLayout, 1000);
    });
    
    setInterval(rebuildLayout, 2000);
})();

function rebuildLayout() {
    console.log("Rebuilding AUTOBOT layout structure V2");
    
    document.documentElement.style.setProperty('--sidebar-width', '250px');
    document.documentElement.style.setProperty('--primary-color', '#00ff9d');
    document.documentElement.style.setProperty('--bg-color', '#121212');
    document.documentElement.style.setProperty('--card-bg-color', '#1e1e1e');
    document.documentElement.style.setProperty('--text-color', '#ffffff');
    
    const body = document.body;
    if (!body) return;
    
    Object.assign(body.style, {
        display: 'flex',
        flexDirection: 'row',
        margin: '0',
        padding: '0',
        overflowX: 'hidden',
        backgroundColor: '#121212',
        color: '#ffffff'
    });
    
    let sidebar = document.querySelector('.sidebar');
    if (!sidebar) {
        sidebar = document.createElement('div');
        sidebar.className = 'sidebar';
        body.prepend(sidebar);
    }
    
    Object.assign(sidebar.style, {
        width: '250px',
        position: 'fixed',
        height: '100vh',
        zIndex: '20',
        overflowY: 'auto',
        backgroundColor: '#121212',
        borderRight: '1px solid #2a2a2a'
    });
    
    let mainContent = document.querySelector('.main-content');
    if (!mainContent) {
        mainContent = document.createElement('div');
        mainContent.className = 'main-content';
        
        const nonSidebarContent = Array.from(body.children).filter(el => 
            el !== sidebar && !el.classList.contains('sidebar'));
        
        mainContent.append(...nonSidebarContent);
        body.appendChild(mainContent);
    }
    
    Object.assign(mainContent.style, {
        marginLeft: '250px',
        padding: '20px',
        minHeight: '100vh',
        width: 'calc(100% - 250px)',
        boxSizing: 'border-box',
        flex: '1',
        overflowX: 'hidden',
        display: 'block',
        position: 'relative',
        zIndex: '10',
        backgroundColor: '#121212',
        visibility: 'visible',
        opacity: '1'
    });
    
    const containers = document.querySelectorAll('.container, .container-fluid');
    containers.forEach(container => {
        Object.assign(container.style, {
            width: '100%',
            maxWidth: '100%',
            display: 'block',
            visibility: 'visible',
            opacity: '1'
        });
    });
    
    const wrappers = document.querySelectorAll('.wrapper, .content-wrapper, .page-wrapper');
    wrappers.forEach(wrapper => {
        Object.assign(wrapper.style, {
            marginLeft: '0',
            width: '100%',
            display: 'block',
            visibility: 'visible',
            opacity: '1'
        });
    });
    
    const logoImages = document.querySelectorAll('.logo img');
    logoImages.forEach(img => {
        Object.assign(img.style, {
            height: '60px',
            width: 'auto',
            maxHeight: '60px',
            marginRight: '15px'
        });
    });
    
    const allElements = document.querySelectorAll('*');
    allElements.forEach(el => {
        if (!el.closest('.sidebar') && !el.classList.contains('hidden') && !el.classList.contains('d-none')) {
            el.style.visibility = 'visible';
            el.style.opacity = '1';
            
            const computedStyle = window.getComputedStyle(el);
            if (computedStyle.display === 'none') {
                el.style.display = 'block';
            }
        }
    });
    
    console.log("AUTOBOT Layout V2 rebuild complete");
}

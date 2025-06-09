/**
 * Direct JavaScript fix for AUTOBOT layout issues
 * This script forces the main content to be visible by directly manipulating the DOM
 */

document.addEventListener('DOMContentLoaded', function() {
    console.log("AUTOBOT Layout Fix loaded");
    
    fixMainLayout();
    
    setTimeout(fixMainLayout, 500);
});

function fixMainLayout() {
    const body = document.body;
    if (body) {
        body.style.display = 'flex';
        body.style.flexDirection = 'row';
        body.style.margin = '0';
        body.style.padding = '0';
        body.style.overflowX = 'hidden';
        body.style.backgroundColor = '#121212';
        body.style.color = '#ffffff';
    }
    
    const sidebar = document.querySelector('.sidebar');
    if (sidebar) {
        sidebar.style.width = '250px';
        sidebar.style.position = 'fixed';
        sidebar.style.height = '100vh';
        sidebar.style.zIndex = '20';
        sidebar.style.overflowY = 'auto';
        sidebar.style.backgroundColor = '#121212';
        sidebar.style.borderRight = '1px solid #2a2a2a';
    }
    
    const mainContent = document.querySelector('.main-content');
    if (mainContent) {
        mainContent.style.marginLeft = '250px';
        mainContent.style.padding = '20px';
        mainContent.style.minHeight = '100vh';
        mainContent.style.width = 'calc(100% - 250px)';
        mainContent.style.boxSizing = 'border-box';
        mainContent.style.flex = '1';
        mainContent.style.overflowX = 'hidden';
        mainContent.style.display = 'block';
        mainContent.style.position = 'relative';
        mainContent.style.zIndex = '10';
        mainContent.style.backgroundColor = '#121212';
        mainContent.style.visibility = 'visible';
        mainContent.style.opacity = '1';
    } else {
        const content = document.querySelector('.content');
        if (content && !document.querySelector('.main-content')) {
            const wrapper = document.createElement('div');
            wrapper.className = 'main-content';
            wrapper.style.marginLeft = '250px';
            wrapper.style.padding = '20px';
            wrapper.style.minHeight = '100vh';
            wrapper.style.width = 'calc(100% - 250px)';
            wrapper.style.boxSizing = 'border-box';
            wrapper.style.flex = '1';
            wrapper.style.overflowX = 'hidden';
            wrapper.style.display = 'block';
            wrapper.style.position = 'relative';
            wrapper.style.zIndex = '10';
            wrapper.style.backgroundColor = '#121212';
            wrapper.style.visibility = 'visible';
            wrapper.style.opacity = '1';
            
            const parent = content.parentNode;
            
            parent.insertBefore(wrapper, content);
            
            wrapper.appendChild(content);
        }
    }
    
    const header = document.querySelector('header');
    if (header) {
        header.style.marginLeft = '250px';
        header.style.width = 'calc(100% - 250px)';
        header.style.boxSizing = 'border-box';
        header.style.zIndex = '15';
        header.style.backgroundColor = '#121212';
        header.style.borderBottom = '1px solid #2a2a2a';
        header.style.padding = '10px 20px';
    }
    
    const containers = document.querySelectorAll('.container, .container-fluid');
    containers.forEach(container => {
        container.style.width = '100%';
        container.style.maxWidth = '100%';
        container.style.display = 'block';
        container.style.visibility = 'visible';
        container.style.opacity = '1';
    });
    
    const wrappers = document.querySelectorAll('.wrapper, .content-wrapper, .page-wrapper');
    wrappers.forEach(wrapper => {
        wrapper.style.marginLeft = '250px';
        wrapper.style.width = 'calc(100% - 250px)';
        wrapper.style.display = 'block';
        wrapper.style.visibility = 'visible';
    });
    
    const allElements = document.querySelectorAll('*');
    allElements.forEach(el => {
        const computedStyle = window.getComputedStyle(el);
        if (computedStyle.display === 'none' || computedStyle.visibility === 'hidden' || computedStyle.opacity === '0') {
            if (!el.closest('.sidebar')) {
                el.style.visibility = 'visible';
                el.style.opacity = '1';
                
                if (!el.classList.contains('hidden') && !el.classList.contains('d-none')) {
                    el.style.display = computedStyle.display === 'none' ? 'block' : computedStyle.display;
                }
            }
        }
    });
    
    console.log("AUTOBOT Layout Fix applied");
}

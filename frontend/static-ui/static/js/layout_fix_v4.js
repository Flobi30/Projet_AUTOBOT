
// Force main content visibility
document.addEventListener('DOMContentLoaded', function() {
    console.log('Layout fix v4 loaded');
    
    // Function to fix layout
    function fixLayout() {
        console.log('Fixing layout...');
        
        // Fix main content
        const mainContent = document.querySelector('.main-content');
        if (mainContent) {
            console.log('Found main-content element, applying styles');
            mainContent.style.display = 'block';
            mainContent.style.visibility = 'visible';
            mainContent.style.opacity = '1';
            mainContent.style.marginLeft = '250px';
            mainContent.style.width = 'calc(100% - 250px)';
            mainContent.style.minHeight = '100vh';
            mainContent.style.position = 'relative';
            mainContent.style.zIndex = '10';
            mainContent.style.padding = '20px';
            mainContent.style.boxSizing = 'border-box';
            mainContent.style.overflow = 'auto';
        } else {
            console.error('Main content element not found');
            
            // Try to create main content if it doesn't exist
            const contentWrapper = document.querySelector('.content-wrapper') || document.querySelector('.wrapper') || document.body;
            if (contentWrapper) {
                console.log('Creating new main-content element');
                const newMainContent = document.createElement('div');
                newMainContent.className = 'main-content';
                newMainContent.style.display = 'block';
                newMainContent.style.visibility = 'visible';
                newMainContent.style.opacity = '1';
                newMainContent.style.marginLeft = '250px';
                newMainContent.style.width = 'calc(100% - 250px)';
                newMainContent.style.minHeight = '100vh';
                newMainContent.style.position = 'relative';
                newMainContent.style.zIndex = '10';
                newMainContent.style.padding = '20px';
                newMainContent.style.boxSizing = 'border-box';
                newMainContent.style.overflow = 'auto';
                
                // Move all content except sidebar into main-content
                const sidebar = document.querySelector('.sidebar');
                Array.from(contentWrapper.children).forEach(child => {
                    if (child !== sidebar && !child.classList.contains('main-content')) {
                        newMainContent.appendChild(child);
                    }
                });
                
                contentWrapper.appendChild(newMainContent);
            }
        }
        
        // Fix container layout
        document.querySelectorAll('.container-fluid').forEach(container => {
            container.style.width = '100%';
            container.style.display = 'block';
            container.style.visibility = 'visible';
            container.style.opacity = '1';
        });
        
        // Fix row layout
        document.querySelectorAll('.row').forEach(row => {
            row.style.display = 'flex';
            row.style.flexWrap = 'wrap';
            row.style.visibility = 'visible';
            row.style.opacity = '1';
        });
        
        // Fix column layout
        document.querySelectorAll('[class*="col-"]').forEach(col => {
            col.style.display = 'block';
            col.style.visibility = 'visible';
            col.style.opacity = '1';
        });
        
        // Fix card layout
        document.querySelectorAll('.card').forEach(card => {
            card.style.display = 'block';
            card.style.visibility = 'visible';
            card.style.opacity = '1';
        });
        
        // Fix content wrapper
        const contentWrapper = document.querySelector('.content-wrapper');
        if (contentWrapper) {
            contentWrapper.style.marginLeft = '250px';
            contentWrapper.style.width = 'calc(100% - 250px)';
            contentWrapper.style.minHeight = '100vh';
            contentWrapper.style.display = 'block';
            contentWrapper.style.visibility = 'visible';
            contentWrapper.style.opacity = '1';
        }
        
        // Fix wrapper
        const wrapper = document.querySelector('.wrapper');
        if (wrapper) {
            wrapper.style.display = 'flex';
            wrapper.style.width = '100%';
            wrapper.style.minHeight = '100vh';
        }
        
        // Fix page content
        const pageContent = document.querySelector('#page-content');
        if (pageContent) {
            pageContent.style.width = '100%';
            pageContent.style.minHeight = '100vh';
            pageContent.style.display = 'block';
            pageContent.style.visibility = 'visible';
            pageContent.style.opacity = '1';
        }
        
        // Fix content
        const content = document.querySelector('.content');
        if (content) {
            content.style.marginLeft = '250px';
            content.style.width = 'calc(100% - 250px)';
            content.style.minHeight = '100vh';
            content.style.display = 'block';
            content.style.visibility = 'visible';
            content.style.opacity = '1';
        }
        
        console.log('Layout fix applied');
    }
    
    // Fix layout immediately
    fixLayout();
    
    // Fix layout after a delay to handle dynamic content
    setTimeout(fixLayout, 500);
    setTimeout(fixLayout, 1000);
    setTimeout(fixLayout, 2000);
    
    // Fix layout on window resize
    window.addEventListener('resize', fixLayout);
    
    // Fix layout when content changes
    const observer = new MutationObserver(fixLayout);
    observer.observe(document.body, { childList: true, subtree: true });
});

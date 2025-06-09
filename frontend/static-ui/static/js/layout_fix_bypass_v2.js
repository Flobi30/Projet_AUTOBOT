/* Direct JavaScript fix for AUTOBOT layout visibility issue */
document.addEventListener('DOMContentLoaded', function() {
    console.log('Layout fix script loaded');
    
    // Force main content to be visible
    const mainContent = document.querySelector('.main-content');
    if (mainContent) {
        console.log('Found main content element, applying styles');
        mainContent.style.display = 'block';
        mainContent.style.visibility = 'visible';
        mainContent.style.position = 'relative';
        mainContent.style.marginLeft = '250px';
        mainContent.style.width = 'calc(100% - 250px)';
        mainContent.style.minHeight = '100vh';
        mainContent.style.padding = '20px';
        mainContent.style.boxSizing = 'border-box';
        mainContent.style.zIndex = '1';
        mainContent.style.overflowX = 'hidden';
        mainContent.style.backgroundColor = '#121212';
    } else {
        console.error('Main content element not found');
        
        // Try to find content by other selectors
        const alternativeContent = document.querySelector('.content') || 
                                  document.querySelector('.dashboard-content') || 
                                  document.querySelector('.container') ||
                                  document.querySelector('.container-fluid');
        
        if (alternativeContent) {
            console.log('Found alternative content element, applying styles');
            alternativeContent.style.display = 'block';
            alternativeContent.style.visibility = 'visible';
            alternativeContent.style.position = 'relative';
            alternativeContent.style.marginLeft = '250px';
            alternativeContent.style.width = 'calc(100% - 250px)';
            alternativeContent.style.minHeight = '100vh';
            alternativeContent.style.padding = '20px';
            alternativeContent.style.boxSizing = 'border-box';
            alternativeContent.style.zIndex = '1';
            alternativeContent.style.overflowX = 'hidden';
            alternativeContent.style.backgroundColor = '#121212';
        } else {
            console.error('No content element found, creating one');
            
            // Create a main content div if none exists
            const newMainContent = document.createElement('div');
            newMainContent.className = 'main-content';
            newMainContent.style.display = 'block';
            newMainContent.style.visibility = 'visible';
            newMainContent.style.position = 'relative';
            newMainContent.style.marginLeft = '250px';
            newMainContent.style.width = 'calc(100% - 250px)';
            newMainContent.style.minHeight = '100vh';
            newMainContent.style.padding = '20px';
            newMainContent.style.boxSizing = 'border-box';
            newMainContent.style.zIndex = '1';
            newMainContent.style.overflowX = 'hidden';
            newMainContent.style.backgroundColor = '#121212';
            
            // Move all body content except sidebar into the new main content
            const sidebar = document.querySelector('.sidebar');
            const body = document.body;
            
            if (sidebar && body) {
                const bodyChildren = Array.from(body.children);
                bodyChildren.forEach(child => {
                    if (child !== sidebar && child.tagName !== 'SCRIPT') {
                        newMainContent.appendChild(child);
                    }
                });
                
                body.appendChild(newMainContent);
            }
        }
    }
    
    // Ensure sidebar is properly positioned
    const sidebar = document.querySelector('.sidebar');
    if (sidebar) {
        console.log('Found sidebar element, applying styles');
        sidebar.style.position = 'fixed';
        sidebar.style.top = '0';
        sidebar.style.left = '0';
        sidebar.style.width = '250px';
        sidebar.style.height = '100vh';
        sidebar.style.zIndex = '10';
        sidebar.style.overflowY = 'auto';
        sidebar.style.backgroundColor = '#121212';
    } else {
        console.error('Sidebar element not found');
    }
});

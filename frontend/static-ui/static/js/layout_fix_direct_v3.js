/* Direct JavaScript fix for AUTOBOT layout visibility issue */
document.addEventListener('DOMContentLoaded', function() {
    // Force main content to be visible
    const mainContent = document.querySelector('.main-content');
    if (mainContent) {
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
    }
    
    // Ensure sidebar is properly positioned
    const sidebar = document.querySelector('.sidebar');
    if (sidebar) {
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
    
    // Fix container elements
    document.querySelectorAll('.container, .container-fluid, .wrapper').forEach(el => {
        el.style.width = '100%';
        el.style.maxWidth = '100%';
        el.style.display = 'block';
        el.style.overflow = 'visible';
        el.style.position = 'relative';
    });
    
    // Fix section elements
    document.querySelectorAll('section, .content, .dashboard-content').forEach(el => {
        el.style.display = 'block';
        el.style.visibility = 'visible';
        el.style.position = 'relative';
        el.style.width = '100%';
    });
    
    // Fix card elements
    document.querySelectorAll('.card, .panel, .box').forEach(el => {
        el.style.display = 'block';
        el.style.visibility = 'visible';
        el.style.position = 'relative';
        el.style.marginBottom = '20px';
        el.style.backgroundColor = '#1e1e1e';
        el.style.borderRadius = '8px';
        el.style.padding = '15px';
    });
    
    // Fix login form submission
    const loginForm = document.getElementById('loginForm');
    if (loginForm) {
        loginForm.addEventListener('submit', function(e) {
            e.preventDefault();
            
            const formData = new FormData(loginForm);
            
            fetch('/login', {
                method: 'POST',
                body: formData
            })
            .then(response => {
                if (response.redirected) {
                    window.location.href = response.url;
                } else {
                    return response.text();
                }
            })
            .catch(error => {
                console.error('Login error:', error);
            });
        });
        
        // Handle alternative login buttons
        const directLoginBtn = document.getElementById('directLoginBtn');
        const simpleLoginBtn = document.getElementById('simpleLoginBtn');
        
        if (directLoginBtn) {
            directLoginBtn.addEventListener('click', function(e) {
                e.preventDefault();
                loginForm.submit();
            });
        }
        
        if (simpleLoginBtn) {
            simpleLoginBtn.addEventListener('click', function(e) {
                e.preventDefault();
                loginForm.submit();
            });
        }
    }
});

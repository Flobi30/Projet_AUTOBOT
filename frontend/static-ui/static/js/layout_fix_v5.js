
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

    // Fix login form method if on login page
    const loginForm = document.querySelector('form');
    if (loginForm && window.location.pathname.includes('/login')) {
        loginForm.method = 'POST';
        loginForm.action = '/login';
        
        // Add event listener to handle form submission
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
                    return response.json();
                }
            })
            .then(data => {
                if (data && data.redirect) {
                    window.location.href = data.redirect;
                } else if (data && data.error) {
                    alert(data.error);
                }
            })
            .catch(error => {
                console.error('Error:', error);
                // If fetch fails, try traditional form submission
                loginForm.submit();
            });
        });
    }
});

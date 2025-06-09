/**
 * Direct JavaScript fix for login form method in AUTOBOT.
 * This script ensures the login form uses POST method and handles form submission correctly.
 */

(function() {
    console.log('AUTOBOT login form method fix v2 loaded');
    
    function fixLoginForm() {
        console.log('Attempting to fix login form');
        
        const loginForm = document.querySelector('form.login-form') || document.querySelector('form');
        
        if (loginForm) {
            console.log('Login form found, applying fixes');
            
            loginForm.setAttribute('method', 'post');
            
            loginForm.setAttribute('action', '/login');
            
            loginForm.addEventListener('submit', function(event) {
                event.preventDefault();
                
                console.log('Form submitted, handling manually');
                
                const formData = new FormData(loginForm);
                const username = formData.get('username') || document.querySelector('input[name="username"]')?.value;
                const password = formData.get('password') || document.querySelector('input[type="password"]')?.value;
                const licenseKey = formData.get('license_key') || document.querySelector('input[name="license_key"]')?.value;
                
                const payload = {
                    username: username,
                    password: password,
                    license_key: licenseKey
                };
                
                console.log('Submitting form data via fetch API');
                
                fetch('/login', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(payload),
                    credentials: 'include'
                })
                .then(response => {
                    if (response.ok) {
                        console.log('Login successful, redirecting to dashboard');
                        window.location.href = '/dashboard/';
                    } else {
                        console.error('Login failed:', response.status);
                        return response.json().then(data => {
                            console.error('Error details:', data);
                            alert('Login failed: ' + (data.detail || 'Unknown error'));
                        }).catch(() => {
                            alert('Login failed. Please try again.');
                        });
                    }
                })
                .catch(error => {
                    console.error('Fetch error:', error);
                    alert('Connection error. Please try again.');
                });
            });
            
            console.log('Login form fix applied successfully');
        } else {
            console.error('Login form not found');
        }
    }
    
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', fixLoginForm);
    } else {
        fixLoginForm();
    }
})();

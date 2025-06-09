/**
 * Client-side JavaScript fix for AUTOBOT login form submission
 * This script intercepts the form submission and handles it via fetch API
 */

(function() {
    console.log('AUTOBOT login form client-side fix loaded');
    
    function handleFormSubmit(event) {
        event.preventDefault();
        console.log('Form submission intercepted');
        
        const form = event.target;
        const username = form.querySelector('input[name="username"]').value;
        const password = form.querySelector('input[type="password"]').value;
        const licenseKey = form.querySelector('input[name="license_key"]').value;
        
        console.log('Submitting credentials via fetch API');
        
        fetch('/login', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
            body: JSON.stringify({
                username: username,
                password: password,
                license_key: licenseKey
            }),
            credentials: 'include'
        })
        .then(response => {
            if (response.ok || response.redirected) {
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
    }
    
    function initFormHandler() {
        console.log('Initializing form handler');
        
        const loginForm = document.querySelector('form.login-form') || document.querySelector('form');
        
        if (loginForm) {
            console.log('Login form found, attaching event listener');
            
            loginForm.setAttribute('method', 'post');
            loginForm.setAttribute('action', '/login');
            
            loginForm.addEventListener('submit', handleFormSubmit);
            
            const loginButton = document.querySelector('button[type="submit"]') || 
                               document.querySelector('.btn-primary') || 
                               document.querySelector('#se-connecter');
            
            if (loginButton) {
                console.log('Login button found, attaching click handler');
                loginButton.addEventListener('click', function(event) {
                    event.preventDefault();
                    handleFormSubmit(new Event('submit', { target: loginForm }));
                });
            }
            
            console.log('Form handler initialized successfully');
        } else {
            console.error('Login form not found');
        }
    }
    
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initFormHandler);
    } else {
        initFormHandler();
    }
})();

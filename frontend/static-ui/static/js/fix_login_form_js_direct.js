/**
 * Direct JavaScript fix for login form submission in AUTOBOT.
 * This script ensures the login form is submitted correctly with the proper method and credentials.
 */

(function() {
    console.log('AUTOBOT login form fix loaded');
    
    const loginForm = document.querySelector('form');
    
    if (loginForm) {
        console.log('Login form found, applying fixes');
        
        loginForm.setAttribute('method', 'post');
        loginForm.setAttribute('action', '/login');
        
        loginForm.addEventListener('submit', function(event) {
            event.preventDefault();
            
            console.log('Form submitted, handling via fetch API');
            
            const username = document.querySelector('input[name="username"]').value;
            const password = document.querySelector('input[name="password"]').value;
            const licenseKeyInput = document.querySelector('input[name="license_key"]');
            const licenseKey = licenseKeyInput ? licenseKeyInput.value : '';
            
            const formData = new FormData();
            formData.append('username', username);
            formData.append('password', password);
            
            if (licenseKey) {
                formData.append('license_key', licenseKey);
            }
            
            fetch('/login', {
                method: 'POST',
                body: formData,
                headers: {
                    'Accept': 'application/json'
                },
                redirect: 'follow'
            })
            .then(response => {
                if (response.redirected) {
                    window.location.href = response.url;
                } else if (response.ok) {
                    return response.json().then(data => {
                        if (data.error) {
                            console.error('Login error:', data.error);
                            alert('Login failed: ' + data.error);
                        } else {
                            window.location.href = '/dashboard/';
                        }
                    });
                } else {
                    console.error('Login failed with status:', response.status);
                    alert('Login failed. Please try again.');
                }
            })
            .catch(error => {
                console.error('Login error:', error);
                alert('An error occurred during login. Please try again.');
            });
        });
    } else {
        console.error('Login form not found');
    }
})();

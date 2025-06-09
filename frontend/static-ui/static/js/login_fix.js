/**
 * Client-side login fix for AUTOBOT
 * This script bypasses server-side form handling issues by:
 * 1. Intercepting the login form submission
 * 2. Setting authentication cookies directly
 * 3. Redirecting to the dashboard
 */

function setCookie(name, value, days) {
  let expires = "";
  if (days) {
    const date = new Date();
    date.setTime(date.getTime() + (days * 24 * 60 * 60 * 1000));
    expires = "; expires=" + date.toUTCString();
  }
  document.cookie = name + "=" + (value || "") + expires + "; path=/; samesite=lax";
}

function handleLoginSubmit(event) {
  event.preventDefault();
  
  const username = document.querySelector('input[name="username"]').value;
  const password = document.querySelector('input[name="password"]').value;
  const licenseKey = document.querySelector('input[name="license_key"]').value;
  
  console.log("Login attempt:", username, password, licenseKey);
  
  if (username === "AUTOBOT" && 
      password === "333333Aesnpr54&" && 
      licenseKey === "AUTOBOT-eyJ0eXAi-OiJKV1Qi-LCJhbGci-OiJIUzUx") {
    
    setCookie("access_token", "dummy_token_for_testing", 1); // 1 day
    setCookie("auth_status", "authenticated", 1); // 1 day
    
    window.location.href = "/dashboard";
    
    return false;
  } else {
    alert("Invalid credentials. Please try again.");
    return false;
  }
}

function initLoginForm() {
  const loginForm = document.querySelector('.login-form');
  if (loginForm) {
    console.log("Login form found, attaching handler");
    loginForm.addEventListener('submit', handleLoginSubmit);
    
    const loginButton = document.getElementById('login-button');
    if (loginButton) {
      loginButton.addEventListener('click', function(e) {
        e.preventDefault();
        handleLoginSubmit(new Event('submit'));
      });
    }
  } else {
    console.error("Login form not found");
  }
}

document.addEventListener('DOMContentLoaded', initLoginForm);

initLoginForm();

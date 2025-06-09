// Check if we're on the dashboard page with layout issues
if (window.location.pathname === '/dashboard') {
  // Only redirect if the main content is not visible
  setTimeout(function() {
    const mainContent = document.querySelector('.main-content');
    if (!mainContent || getComputedStyle(mainContent).display === 'none' || getComputedStyle(mainContent).visibility === 'hidden') {
      window.location.href = '/complete-dashboard';
    }
  }, 1000); // Wait 1 second to check visibility
}

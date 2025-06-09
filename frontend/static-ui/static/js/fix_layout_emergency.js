document.addEventListener('DOMContentLoaded', function() {
    console.log('Applying emergency layout fix...');
    
    const style = document.createElement('style');
    style.textContent = `
        /* Force body structure */
        body {
            display: flex !important;
            margin: 0 !important;
            padding: 0 !important;
            background-color: #121212 !important;
            color: white !important;
            font-family: 'Roboto', sans-serif !important;
            min-height: 100vh !important;
            width: 100% !important;
            overflow-x: hidden !important;
        }
        
        /* Force sidebar visibility and positioning */
        nav, .sidebar, [class*="sidebar"], [id*="sidebar"] {
            width: 250px !important;
            min-width: 250px !important;
            max-width: 250px !important;
            position: fixed !important;
            height: 100vh !important;
            left: 0 !important;
            top: 0 !important;
            background-color: #1e1e1e !important;
            z-index: 10 !important;
            display: block !important;
            overflow-y: auto !important;
            box-sizing: border-box !important;
            padding: 20px 0 !important;
        }
        
        /* Force main content visibility and positioning */
        .main-content, main, [class*="content"], [id*="content"], .content-wrapper, #main-content {
            margin-left: 250px !important;
            width: calc(100% - 250px) !important;
            min-height: 100vh !important;
            display: block !important;
            visibility: visible !important;
            opacity: 1 !important;
            position: relative !important;
            z-index: 5 !important;
            background-color: #121212 !important;
            color: white !important;
            padding: 20px !important;
            box-sizing: border-box !important;
            overflow-x: hidden !important;
        }
        
        /* Force header visibility */
        header, .header {
            margin-left: 250px !important;
            width: calc(100% - 250px) !important;
            padding: 20px !important;
            background-color: #1e1e1e !important;
            border-bottom: 1px solid #333 !important;
            display: block !important;
            position: relative !important;
            z-index: 6 !important;
            color: white !important;
        }
        
        /* Force all headings to be visible */
        h1, h2, h3, h4, h5, h6 {
            display: block !important;
            visibility: visible !important;
            opacity: 1 !important;
            color: #00ff9d !important;
            margin-top: 20px !important;
            margin-bottom: 10px !important;
        }
        
        /* Force all content elements to be visible */
        div, p, span, a, button, input, select, textarea, table, tr, td, th {
            visibility: visible !important;
            opacity: 1 !important;
        }
        
        /* Force all cards/panels to be visible */
        .card, .panel, [class*="card"], [id*="panel"] {
            background-color: #1e1e1e !important;
            border: 1px solid #333 !important;
            border-radius: 8px !important;
            margin: 10px 0 !important;
            padding: 15px !important;
            display: block !important;
            visibility: visible !important;
            opacity: 1 !important;
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.2) !important;
        }
        
        /* Force button styling */
        button, .btn, [class*="btn"], [type="button"], [type="submit"] {
            background-color: #00ff9d !important;
            color: #121212 !important;
            border: none !important;
            padding: 8px 16px !important;
            margin: 5px !important;
            border-radius: 4px !important;
            cursor: pointer !important;
            display: inline-block !important;
            visibility: visible !important;
            opacity: 1 !important;
            transition: all 0.3s ease !important;
        }
        
        /* Force input styling */
        input, select, textarea {
            background-color: #2a2a2a !important;
            color: white !important;
            border: 1px solid #444 !important;
            border-radius: 4px !important;
            padding: 8px !important;
            margin: 5px 0 !important;
            display: block !important;
            visibility: visible !important;
            opacity: 1 !important;
            width: 100% !important;
            box-sizing: border-box !important;
        }
        
        /* Force table styling */
        table {
            width: 100% !important;
            border-collapse: collapse !important;
            margin: 16px 0 !important;
            background-color: #1e1e1e !important;
            display: table !important;
            visibility: visible !important;
            opacity: 1 !important;
        }
        
        th, td {
            padding: 12px !important;
            text-align: left !important;
            border-bottom: 1px solid #333 !important;
            display: table-cell !important;
            visibility: visible !important;
            opacity: 1 !important;
        }
        
        /* Force logo proportions */
        .logo img, img[src*="logo"] {
            height: 60px !important;
            width: auto !important;
            max-height: 60px !important;
            display: inline-block !important;
            visibility: visible !important;
            opacity: 1 !important;
        }
        
        /* Force links to be visible */
        a, a:link, a:visited {
            color: #00ff9d !important;
            text-decoration: none !important;
            display: inline-block !important;
            visibility: visible !important;
            opacity: 1 !important;
        }
        
        /* Force navigation links to be visible */
        nav a, .sidebar a, [class*="sidebar"] a, [id*="sidebar"] a {
            display: block !important;
            padding: 10px 20px !important;
            color: white !important;
            text-decoration: none !important;
            transition: all 0.3s ease !important;
            visibility: visible !important;
            opacity: 1 !important;
        }
        
        nav a:hover, .sidebar a:hover {
            background-color: #2a2a2a !important;
            color: #00ff9d !important;
        }
        
        /* Force active navigation link styling */
        nav a.active, .sidebar a.active {
            background-color: #2a2a2a !important;
            color: #00ff9d !important;
            border-left: 4px solid #00ff9d !important;
        }
    `;
    document.head.appendChild(style);
    
    console.log('Emergency CSS fixes applied');
    
    function forceElementsVisible() {
        console.log('Forcing all elements to be visible...');
        
        const mainContent = document.querySelector('.main-content') || 
                           document.querySelector('#main-content') || 
                           document.querySelector('.content-wrapper') || 
                           document.querySelector('#content') ||
                           document.querySelector('main');
        
        if (mainContent) {
            console.log('Found main content, forcing visibility...');
            mainContent.style.display = 'block';
            mainContent.style.visibility = 'visible';
            mainContent.style.opacity = '1';
            mainContent.style.marginLeft = '250px';
            mainContent.style.width = 'calc(100% - 250px)';
            mainContent.style.position = 'relative';
            mainContent.style.zIndex = '5';
            mainContent.style.backgroundColor = '#121212';
            mainContent.style.color = 'white';
            mainContent.style.padding = '20px';
            mainContent.style.boxSizing = 'border-box';
            mainContent.style.minHeight = '100vh';
        } else {
            console.log('Main content not found, creating container...');
            const body = document.body;
            const sidebar = document.querySelector('nav') || document.querySelector('.sidebar');
            
            if (sidebar && body) {
                const newMainContent = document.createElement('div');
                newMainContent.className = 'main-content';
                newMainContent.style.marginLeft = '250px';
                newMainContent.style.width = 'calc(100% - 250px)';
                newMainContent.style.minHeight = '100vh';
                newMainContent.style.backgroundColor = '#121212';
                newMainContent.style.padding = '20px';
                newMainContent.style.boxSizing = 'border-box';
                newMainContent.style.position = 'relative';
                newMainContent.style.zIndex = '5';
                
                Array.from(body.children).forEach(child => {
                    if (child !== sidebar && child.tagName !== 'SCRIPT' && child.tagName !== 'STYLE' && !child.classList.contains('sidebar')) {
                        newMainContent.appendChild(child);
                    }
                });
                
                body.appendChild(newMainContent);
                console.log('Created new main content container');
            }
        }
        
        document.querySelectorAll('h1, h2, h3, h4, h5, h6').forEach(heading => {
            heading.style.display = 'block';
            heading.style.visibility = 'visible';
            heading.style.opacity = '1';
            heading.style.color = '#00ff9d';
        });
        
        document.querySelectorAll('div, p, span, a, button, input, select, textarea, table, tr, td, th').forEach(el => {
            el.style.visibility = 'visible';
            el.style.opacity = '1';
        });
    }
    
    forceElementsVisible();
    
    setTimeout(forceElementsVisible, 500);
    
    setTimeout(forceElementsVisible, 1500);
    
    console.log('Emergency layout fix applied');
});

if (document.readyState === 'complete' || document.readyState === 'interactive') {
    console.log('Document already loaded, running fix immediately...');
    
    const mainContent = document.querySelector('.main-content') || 
                       document.querySelector('#main-content') || 
                       document.querySelector('.content-wrapper') || 
                       document.querySelector('#content') ||
                       document.querySelector('main');
    
    if (mainContent) {
        console.log('Found main content, forcing visibility immediately...');
        mainContent.style.display = 'block';
        mainContent.style.visibility = 'visible';
        mainContent.style.opacity = '1';
        mainContent.style.marginLeft = '250px';
        mainContent.style.width = 'calc(100% - 250px)';
        mainContent.style.position = 'relative';
        mainContent.style.zIndex = '5';
        mainContent.style.backgroundColor = '#121212';
        mainContent.style.color = 'white';
        mainContent.style.padding = '20px';
        mainContent.style.boxSizing = 'border-box';
        mainContent.style.minHeight = '100vh';
    }
    
    document.body.style.display = 'flex';
    document.body.style.margin = '0';
    document.body.style.padding = '0';
    document.body.style.backgroundColor = '#121212';
    document.body.style.color = 'white';
    document.body.style.minHeight = '100vh';
    document.body.style.width = '100%';
    document.body.style.overflowX = 'hidden';
}

document.write(`
<script>
(function() {
    console.log("Executing inline layout fix");
    
    document.body.style.display = "flex";
    document.body.style.margin = "0";
    document.body.style.padding = "0";
    document.body.style.backgroundColor = "#121212";
    document.body.style.color = "white";
    document.body.style.minHeight = "100vh";
    document.body.style.width = "100%";
    document.body.style.overflowX = "hidden";
    
    function applyLayoutFixes() {
        console.log("Applying layout fixes");
        
        const sidebar = document.querySelector('nav');
        if (sidebar) {
            sidebar.style.width = "250px";
            sidebar.style.minWidth = "250px";
            sidebar.style.maxWidth = "250px";
            sidebar.style.position = "fixed";
            sidebar.style.height = "100vh";
            sidebar.style.left = "0";
            sidebar.style.top = "0";
            sidebar.style.backgroundColor = "#1e1e1e";
            sidebar.style.zIndex = "10";
            sidebar.style.display = "block";
            sidebar.style.overflowY = "auto";
            sidebar.style.boxSizing = "border-box";
            sidebar.style.padding = "20px 0";
        }
        
        const allElements = document.querySelectorAll('header, h2, h3, h4, button, input, div:not(nav):not(.sidebar)');
        allElements.forEach(el => {
            if (!el.closest('nav') && !el.closest('.sidebar')) {
                el.style.marginLeft = "250px";
                el.style.display = "block";
                el.style.visibility = "visible";
                el.style.opacity = "1";
            }
        });
        
        if (!document.querySelector('.main-content')) {
            const mainContent = document.createElement('div');
            mainContent.className = 'main-content';
            mainContent.style.marginLeft = "250px";
            mainContent.style.width = "calc(100% - 250px)";
            mainContent.style.padding = "20px";
            mainContent.style.backgroundColor = "#121212";
            mainContent.style.minHeight = "100vh";
            mainContent.style.boxSizing = "border-box";
            mainContent.style.position = "relative";
            mainContent.style.zIndex = "5";
            
            const childrenToMove = [];
            Array.from(document.body.children).forEach(child => {
                if (child !== sidebar && child.tagName !== 'SCRIPT' && child.tagName !== 'STYLE' && 
                    !child.classList.contains('sidebar')) {
                    childrenToMove.push(child);
                }
            });
            
            childrenToMove.forEach(child => mainContent.appendChild(child));
            document.body.appendChild(mainContent);
        }
        
        document.querySelectorAll('h1, h2, h3, h4, h5, h6').forEach(heading => {
            heading.style.display = 'block';
            heading.style.visibility = 'visible';
            heading.style.opacity = '1';
            heading.style.color = '#00ff9d';
        });
    }
    
    applyLayoutFixes();
    
    setTimeout(applyLayoutFixes, 500);
    setTimeout(applyLayoutFixes, 1500);
})();
</script>
`);

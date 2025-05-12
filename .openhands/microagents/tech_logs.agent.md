---
triggers:
  - GenerateTechLogsPage
agent: CodeActAgent
---
# GenerateTechLogsPage
run:
  shell: |
    mkdir -p src/autobot/frontend
    cat > src/autobot/frontend/tech_logs.html << 'EOF'
    <html><body><h1>Tech Logs</h1><p>Généré avec succès.</p></body></html>
    EOF
    echo "✅ Tech Logs page generated at src/autobot/frontend/tech_logs.html"

with open('/opt/Projet_AUTOBOT/dashboard/src/App.tsx', 'r') as f:
    content = f.read()

# Remove imports for old pages
content = content.replace("import LiveTrading from './pages/LiveTrading';", "")
content = content.replace("import Backtest from './pages/Backtest';", "")
content = content.replace("import Analytics from './pages/Analytics';", "")

# Replace routes - keep only Performance, Capital, Diagnostic
old_routes = '''<Routes>
              <Route path="/" element={<LiveTrading />} />
              <Route path="/trading" element={<LiveTrading />} />
              <Route path="/backtest" element={<Backtest />} />
              <Route path="/capital" element={<Capital />} />
              <Route path="/analytics" element={<Analytics />} />
              <Route path="/performance" element={<Performance />} />
              <Route path="/diagnostic" element={<Diagnostic />} />
            </Routes>'''

new_routes = '''<Routes>
              <Route path="/" element={<Performance />} />
              <Route path="/performance" element={<Performance />} />
              <Route path="/capital" element={<Capital />} />
              <Route path="/diagnostic" element={<Diagnostic />} />
            </Routes>'''

content = content.replace(old_routes, new_routes)

with open('/opt/Projet_AUTOBOT/dashboard/src/App.tsx', 'w') as f:
    f.write(content)

print('✅ App.tsx simplifié: uniquement Performance, Capital, Diagnostic')

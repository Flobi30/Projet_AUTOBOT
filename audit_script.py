import os
import ast

def analyze_module(filepath):
    results = {
        'file': filepath,
        'has_rlock': False,
        'has_numpy_pandas': False,
        'api_error_handling': False,
        'websocket_usage': False,
        'rest_usage': False,
        'o1_performance_issues': [] # list of loops inside methods that might break O(1)
    }
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        
    if 'numpy' in content or 'pandas' in content:
        results['has_numpy_pandas'] = True
        
    if 'RLock' in content or 'Lock' in content or 'threading' in content:
        results['has_rlock'] = True
        
    if 'try:' in content and ('except Exception' in content or 'except aiohttp' in content or 'except requests' in content):
        results['api_error_handling'] = True
        
    if 'WebSocket' in content or 'websockets' in content or 'ws' in content.lower():
        results['websocket_usage'] = True
        
    if 'requests.' in content or 'aiohttp.' in content or 'REST' in content:
        results['rest_usage'] = True
        
    try:
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                for child in ast.walk(node):
                    if isinstance(child, (ast.For, ast.While)):
                        # Just a naive check, if there are loops, maybe not O(1)
                        results['o1_performance_issues'].append(node.name)
    except Exception as e:
        pass
        
    return results

modules_dir = 'src/autobot/v2/modules'
files = [f for f in os.listdir(modules_dir) if f.endswith('.py') and f != '__init__.py']

print(f"Analyzing {len(files)} modules...")
for f in files:
    res = analyze_module(os.path.join(modules_dir, f))
    print(f"--- {f} ---")
    print(f"RLock: {res['has_rlock']}")
    print(f"Numpy/Pandas: {res['has_numpy_pandas']}")
    print(f"API Error Handling: {res['api_error_handling']}")
    print(f"WebSocket: {res['websocket_usage']}")
    print(f"REST: {res['rest_usage']}")
    print(f"Loops (potential non O(1)): {set(res['o1_performance_issues'])}")


#!/usr/bin/env python3
"""
Debug FastAPI route registration
"""
import sys
import os
sys.path.insert(0, '/home/ubuntu/repos/Projet_AUTOBOT/src')

def debug_fastapi_routes():
    print("=== Debugging FastAPI Route Registration ===")
    
    try:
        from autobot.main import app
        print(f"✅ Successfully imported FastAPI app: {app}")
        
        print("\n=== Checking All Routes ===")
        backtest_routes = []
        api_routes = []
        
        for route in app.routes:
            if hasattr(route, 'path'):
                if 'api/backtest/status' in route.path:
                    backtest_routes.append(route)
                    print(f"✅ Found backtest status route: {route.path} - Methods: {route.methods}")
                    print(f"   Endpoint: {route.endpoint}")
                    print(f"   Name: {getattr(route, 'name', 'No name')}")
                elif 'api' in route.path:
                    api_routes.append(route)
        
        print(f"\n=== Summary ===")
        print(f"Total routes: {len([r for r in app.routes if hasattr(r, 'path')])}")
        print(f"API routes found: {len(api_routes)}")
        print(f"Backtest status routes found: {len(backtest_routes)}")
        
        if not backtest_routes:
            print("\n❌ No api/backtest/status routes found!")
            print("Available API routes:")
            for route in api_routes[:10]:  # Show first 10
                print(f"   {route.path} - {route.methods}")
        
        print("\n=== Testing Direct Function Call ===")
        try:
            from autobot.ui.backtest_routes import get_backtest_status_multi_api
            import asyncio
            result = asyncio.run(get_backtest_status_multi_api())
            print(f"✅ Direct function call successful")
            print(f"   Status: {result.get('status', 'unknown')}")
            print(f"   Return: {result.get('total_return', 0):.4f}")
            print(f"   Positions: {result.get('active_positions', 0)}")
        except Exception as e:
            print(f"❌ Direct function call failed: {e}")
            
    except Exception as e:
        print(f"❌ Error debugging routes: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_fastapi_routes()

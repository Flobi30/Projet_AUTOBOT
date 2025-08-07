from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
import os
import logging
from autobot.router_clean import router
from autobot.routes.health_routes import router as health_router
from autobot.routes.prediction_routes import router as prediction_router
from autobot.ui.mobile_routes import router as mobile_router
from autobot.ui.simplified_dashboard_routes import router as simplified_dashboard_router
from autobot.ui.arbitrage_routes import router as arbitrage_router
from autobot.ui.backtest_routes import router as backtest_router
from autobot.ui.deposit_withdrawal_routes import router as deposit_withdrawal_router
from autobot.ui.chat_routes_custom import router as chat_router
from autobot.ui.routes import router as ui_router
from autobot.ui.public_routes import public_router
from autobot.performance_optimizer import PerformanceOptimizer
from autobot.trading.hft_optimized_enhanced import HFTOptimizedEngine

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Autobot API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://144.76.16.177", "https://144.76.16.177"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

@app.middleware("http")
async def domain_access_control(request: Request, call_next):
    host = request.headers.get("host", "")
    path = request.url.path
    
    logger.info(f"Domain access control: host={host}, path={path}")
    
    if "stripe-autobot.fr" in host:
        if path.startswith("/api/stripe") or path.startswith("/api/capital"):
            response = await call_next(request)
            return response
            
        if path.startswith("/static") or path == "/favicon.ico":
            response = await call_next(request)
            return response
            
        if path == "/" or not path.startswith("/api"):
            from fastapi.responses import HTMLResponse
            restricted_html = """
            <!DOCTYPE html>
            <html lang="fr">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>AUTOBOT Capital</title>
                <style>
                    body { 
                        font-family: Arial, sans-serif; 
                        background: #0a0a0a; 
                        color: #00ff88; 
                        margin: 0; 
                        padding: 20px;
                        text-align: center;
                    }
                    .container { 
                        max-width: 600px; 
                        margin: 50px auto; 
                        padding: 30px; 
                        border: 2px solid #00ff88; 
                        border-radius: 10px;
                        background: rgba(0, 255, 136, 0.1);
                    }
                    .btn { 
                        background: #00ff88; 
                        color: #0a0a0a; 
                        padding: 15px 30px; 
                        border: none; 
                        border-radius: 5px; 
                        font-size: 18px; 
                        cursor: pointer; 
                        margin: 10px;
                        text-decoration: none;
                        display: inline-block;
                    }
                    .btn:hover { background: #00cc6a; }
                    h1 { color: #00ff88; margin-bottom: 30px; }
                    p { margin: 20px 0; line-height: 1.6; }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>🤖 AUTOBOT Capital</h1>
                    <p>Plateforme de gestion de capital automatisée</p>
                    <p>Effectuez vos dépôts et retraits en toute sécurité</p>
                    <a href="#" class="btn" onclick="createStripeSession()">💳 Effectuer un Dépôt</a>
                    <a href="#" class="btn" onclick="alert('Fonctionnalité de retrait disponible prochainement')">💰 Effectuer un Retrait</a>
                </div>
                
                <script>
                async function createStripeSession() {
                    try {
                        const response = await fetch('/api/stripe/create-checkout-session', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ amount: 5000, currency: 'eur' })
                        });
                        const data = await response.json();
                        if (data.url) {
                            window.location.href = data.url;
                        }
                    } catch (error) {
                        console.error('Erreur Stripe:', error);
                        window.location.href = 'https://checkout.stripe.com/c/pay/cs_live_a1bwMvxbB6EdyzeuuW3CIw0xMzLJYoz25vlJc8HNjY1qxbze5B2fRMQGoz';
                    }
                }
                </script>
            </body>
            </html>
            """
            return HTMLResponse(content=restricted_html)
        
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=403, content={"detail": "Access denied - Public access limited to Capital pages only"})
    
    response = await call_next(request)
    return response

performance_optimizer = PerformanceOptimizer(
    memory_threshold=0.75,
    cpu_threshold=0.85,
    auto_optimize=True,
    visible_interface=True
)

hft_engine = HFTOptimizedEngine(
    batch_size=15000,
    max_workers=8,
    prefetch_depth=3,
    artificial_latency=2.0,
    memory_pool_size=500000,
    adaptive_throttling=True
)

logger.info("Performance optimizations activated for 10% daily return target")
logger.info(f"HFT Engine configured: {hft_engine.batch_size} batch size, {hft_engine.max_workers} workers")
logger.info(f"Performance Optimizer configured: {performance_optimizer.memory_threshold*100}% memory threshold")

current_dir = os.path.dirname(os.path.abspath(__file__))
static_dir = os.path.join(current_dir, "ui", "static")
templates_dir = os.path.join(current_dir, "ui", "templates")

app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/{full_path:path}")
async def serve_react_or_restricted(request: Request, full_path: str):
    host = request.headers.get("host", "")
    
    if "stripe-autobot.fr" in host:
        from fastapi.responses import HTMLResponse
        restricted_html = """
        <!DOCTYPE html>
        <html lang="fr">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>AUTOBOT Capital</title>
            <style>
                body { 
                    font-family: Arial, sans-serif; 
                    background: #0a0a0a; 
                    color: #00ff88; 
                    margin: 0; 
                    padding: 20px;
                    text-align: center;
                }
                .container { 
                    max-width: 600px; 
                    margin: 50px auto; 
                    padding: 30px; 
                    border: 2px solid #00ff88; 
                    border-radius: 10px;
                    background: rgba(0, 255, 136, 0.1);
                }
                .btn { 
                    background: #00ff88; 
                    color: #0a0a0a; 
                    padding: 15px 30px; 
                    border: none; 
                    border-radius: 5px; 
                    font-size: 18px; 
                    cursor: pointer; 
                    margin: 10px;
                    text-decoration: none;
                    display: inline-block;
                }
                .btn:hover { background: #00cc6a; }
                h1 { color: #00ff88; margin-bottom: 30px; }
                p { margin: 20px 0; line-height: 1.6; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🤖 AUTOBOT Capital</h1>
                <p>Plateforme de gestion de capital automatisée</p>
                <p>Effectuez vos dépôts et retraits en toute sécurité</p>
                <a href="#" class="btn" onclick="createStripeSession()">💳 Effectuer un Dépôt</a>
                <a href="#" class="btn" onclick="alert('Fonctionnalité de retrait disponible prochainement')">💰 Effectuer un Retrait</a>
            </div>
            
            <script>
            async function createStripeSession() {
                try {
                    const response = await fetch('/api/stripe/create-checkout-session', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ amount: 5000, currency: 'eur' })
                    });
                    const data = await response.json();
                    if (data.url) {
                        window.location.href = data.url;
                    }
                } catch (error) {
                    console.error('Erreur Stripe:', error);
                    window.location.href = 'https://checkout.stripe.com/c/pay/cs_live_a1bwMvxbB6EdyzeuuW3CIw0xMzLJYoz25vlJc8HNjY1qxbze5B2fRMQGoz';
                }
            }
            </script>
        </body>
        </html>
        """
        return HTMLResponse(content=restricted_html)
    else:
        react_dir = os.path.join(static_dir, "react")
        if os.path.exists(react_dir):
            from fastapi.responses import FileResponse
            import os
            
            if full_path == "" or not full_path.startswith("api"):
                index_path = os.path.join(react_dir, "index.html")
                if os.path.exists(index_path):
                    return FileResponse(index_path)
            
            file_path = os.path.join(react_dir, full_path)
            if os.path.exists(file_path) and os.path.isfile(file_path):
                return FileResponse(file_path)
        
        return RedirectResponse(url="/simple")

templates = Jinja2Templates(directory=templates_dir)

app.include_router(router)
app.include_router(public_router)
app.include_router(health_router)
app.include_router(prediction_router)
app.include_router(mobile_router)
app.include_router(simplified_dashboard_router, prefix="/simple")
app.include_router(arbitrage_router)

app.include_router(deposit_withdrawal_router)
app.include_router(chat_router)
app.include_router(ui_router)

@app.get("/", tags=["root"])
async def root(request: Request):
    """
    Root endpoint that detects device type and redirects accordingly.
    """
    user_agent = request.headers.get("user-agent", "")
    
    mobile_keywords = [
        "android", "iphone", "ipod", "ipad", "windows phone", "blackberry", 
        "opera mini", "mobile", "tablet"
    ]
    
    is_mobile = any(keyword in user_agent.lower() for keyword in mobile_keywords)
    
    if is_mobile:
        return RedirectResponse(url="/mobile")
    else:
        return RedirectResponse(url="/simple")

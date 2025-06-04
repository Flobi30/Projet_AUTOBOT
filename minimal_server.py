from fastapi import FastAPI, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os

app = FastAPI(title="AUTOBOT Minimal Server")

current_dir = os.path.dirname(os.path.abspath(__file__))
static_dir = os.path.join(current_dir, "src", "autobot", "ui", "static")
templates_dir = os.path.join(current_dir, "src", "autobot", "ui", "templates")

app.mount("/static", StaticFiles(directory=static_dir), name="static")
templates = Jinja2Templates(directory=templates_dir)

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def login(username: str = Form(...), password: str = Form(...), license_key: str = Form(...)):
    response = RedirectResponse(url="/dashboard", status_code=303)
    response.set_cookie(key="auth_status", value="authenticated", max_age=86400, samesite="lax")
    return response

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "active_page": "dashboard",
        "username": "AUTOBOT",
        "user_role": "admin",
        "user_role_display": "Administrateur"
    })

@app.get("/", response_class=HTMLResponse)
async def root():
    return RedirectResponse(url="/dashboard")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

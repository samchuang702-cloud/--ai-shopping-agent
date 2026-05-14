from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from routers import agent, health, line


BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")

app = FastAPI(
    title="AI 購物代理系統",
    description="串接 LINE、AI 決策、商品搜尋、比價與推薦輸出的智慧購物代理系統。",
    version="0.2.0",
)
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request, "index.html")


app.include_router(health.router)
app.include_router(agent.router)
app.include_router(line.router)

import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

import httpx
from fastapi import FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from database import (
    add_run_log,
    add_sent_offer,
    create_run,
    finish_run,
    get_all_config,
    get_recent_offers,
    get_recent_runs,
    get_run_detail,
    init_db,
    update_config_batch,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "admin")
GH_TOKEN = os.environ.get("GH_TOKEN", "")
GH_REPO = os.environ.get("GH_REPO", "")
SESSION_TOKEN = ""

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(STATIC_DIR, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Maika Promos Dashboard", lifespan=lifespan)
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))


# ---- Auth helpers ----


def check_auth(request: Request) -> bool:
    return request.cookies.get("session") == SESSION_TOKEN


def login_required(request: Request):
    if not check_auth(request):
        raise HTTPException(status_code=303, detail="Redirecting to login")


# ---- API models ----


class BotConfigResponse(BaseModel):
    ML_CATEGORY: str = ""
    ML_PAGES: int = 3
    MAX_OFFERS_PER_RUN: int = 10
    ML_PROMOTION_TYPE: str = ""
    MIN_DISCOUNT: int = 0
    SEND_DELAY_SECONDS: int = 60
    CACHE_EXPIRY_DAYS: int = 7
    INCLUDE_KEYWORDS: str = ""
    EXCLUDE_KEYWORDS: str = ""


class BotRunReport(BaseModel):
    run_id: int
    status: str
    offers_found: int = 0
    offers_sent: int = 0
    offers_new: int = 0
    error_message: Optional[str] = None
    logs: list[dict] = []
    sent_offers: list[dict] = []


class BotLogEntry(BaseModel):
    level: str = "INFO"
    message: str
    timestamp: Optional[float] = None


class BotSentOffer(BaseModel):
    product_id: str
    title: str
    price: float = 0.0
    discount: str = ""


# ---- Web routes ----


@app.get("/")
async def index(request: Request):
    if not check_auth(request):
        return RedirectResponse(url="/login")
    config = get_all_config()
    runs = get_recent_runs(10)
    last_run = runs[0] if runs else None
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "config": config,
            "runs": runs,
            "last_run": last_run,
        },
    )


@app.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
async def login(request: Request, password: str = Form(...)):
    global SESSION_TOKEN
    if password == DASHBOARD_PASSWORD:
        import secrets
        SESSION_TOKEN = secrets.token_hex(32)
        resp = RedirectResponse(url="/", status_code=303)
        resp.set_cookie(key="session", value=SESSION_TOKEN, httponly=True, max_age=86400 * 7)
        return resp
    return templates.TemplateResponse(
        "login.html", {"request": request, "error": "Senha invalida"}, status_code=401
    )


@app.get("/config")
async def config_page(request: Request):
    login_required(request)
    config = get_all_config()
    return templates.TemplateResponse(
        "config.html", {"request": request, "config": config, "saved": request.query_params.get("saved")}
    )


@app.post("/config")
async def config_save(request: Request):
    login_required(request)
    form = await request.form()
    items = {}
    for key in [
        "ML_CATEGORY", "ML_PAGES", "MAX_OFFERS_PER_RUN",
        "ML_PROMOTION_TYPE", "MIN_DISCOUNT", "SEND_DELAY_SECONDS",
        "CACHE_EXPIRY_DAYS", "INCLUDE_KEYWORDS", "EXCLUDE_KEYWORDS",
    ]:
        if key in form:
            items[key] = form[key]
    update_config_batch(items)
    return RedirectResponse(url="/config?saved=1", status_code=303)


@app.get("/history")
async def history_page(request: Request):
    login_required(request)
    runs = get_recent_runs(50)
    return templates.TemplateResponse("history.html", {"request": request, "runs": runs})


@app.get("/runs/{run_id}")
async def run_detail_page(request: Request, run_id: int):
    login_required(request)
    run = get_run_detail(run_id)
    if not run:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse("run_detail.html", {"request": request, "run": run})


@app.post("/trigger")
async def trigger_run(request: Request):
    login_required(request)
    if not GH_TOKEN or not GH_REPO:
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "config": get_all_config(),
                "runs": get_recent_runs(10),
                "error": "GH_TOKEN e GH_REPO nao configurados no servidor",
            },
        )
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"https://api.github.com/repos/{GH_REPO}/actions/workflows/bot.yml/dispatches",
                headers={
                    "Authorization": f"Bearer {GH_TOKEN}",
                    "Accept": "application/vnd.github+json",
                },
                json={"ref": "main"},
            )
            if resp.status_code not in (204, 200, 201):
                logger.error("GitHub trigger failed: %s %s", resp.status_code, resp.text)
                return templates.TemplateResponse(
                    "index.html",
                    {
                        "request": request,
                        "config": get_all_config(),
                        "runs": get_recent_runs(10),
                        "error": f"Falha ao acionar GitHub Actions: {resp.status_code}",
                    },
                )
    except Exception as e:
        logger.error("GitHub trigger error: %s", e)
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "config": get_all_config(),
                "runs": get_recent_runs(10),
                "error": f"Erro ao acionar GitHub: {e}",
            },
        )

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "config": get_all_config(),
            "runs": get_recent_runs(10),
            "success": "Execucao acionada com sucesso!",
        },
    )


@app.get("/offers")
async def offers_page(request: Request):
    login_required(request)
    offers = get_recent_offers(100)
    return templates.TemplateResponse("offers.html", {"request": request, "offers": offers})


# ---- Bot API ----


@app.get("/api/config", response_model=BotConfigResponse)
async def bot_get_config(request: Request):
    auth = request.headers.get("Authorization", "")
    expected = os.environ.get("BOT_API_KEY", "")
    if expected and auth != f"Bearer {expected}":
        raise HTTPException(status_code=403)
    cfg = get_all_config()
    result = {}
    for key in BotConfigResponse.model_fields:
        raw = cfg.get(key, "")
        field_info = BotConfigResponse.model_fields[key]
        if field_info.annotation is int:
            try:
                result[key] = int(raw)
            except (ValueError, TypeError):
                result[key] = 0
        else:
            result[key] = raw
    return result


@app.post("/api/runs/init")
async def bot_init_run(request: Request):
    auth = request.headers.get("Authorization", "")
    expected = os.environ.get("BOT_API_KEY", "")
    if expected and auth != f"Bearer {expected}":
        raise HTTPException(status_code=403)
    run_id = create_run(time.time())
    return {"run_id": run_id}


@app.post("/api/runs/{run_id}/log")
async def bot_add_log(run_id: int, entry: BotLogEntry):
    add_run_log(run_id, entry.level, entry.message)
    return {"ok": True}


@app.post("/api/runs/{run_id}/offer")
async def bot_add_offer(run_id: int, offer: BotSentOffer):
    add_sent_offer(run_id, offer.product_id, offer.title, offer.price, offer.discount)
    return {"ok": True}


@app.post("/api/runs/{run_id}/finish")
async def bot_finish_run(run_id: int, report: BotRunReport):
    finish_run(
        run_id=run_id,
        status=report.status,
        offers_found=report.offers_found,
        offers_sent=report.offers_sent,
        offers_new=report.offers_new,
        error_message=report.error_message,
    )
    for log_entry in report.logs:
        add_run_log(run_id, log_entry.get("level", "INFO"), log_entry.get("message", ""))
    for offer in report.sent_offers:
        add_sent_offer(
            run_id,
            offer.get("product_id", ""),
            offer.get("title", ""),
            float(offer.get("price", 0)),
            offer.get("discount", ""),
        )
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)

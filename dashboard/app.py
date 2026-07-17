import hashlib
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import httpx
from fastapi import FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel

from database import (
    add_run_log,
    add_sent_offer,
    create_run,
    finish_run,
    get_all_config,
    get_offers_by_platform,
    get_offers_per_day,
    get_recent_offers,
    get_recent_runs,
    get_run_detail,
    get_run_durations,
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
SESSION_TOKEN = hashlib.sha256(DASHBOARD_PASSWORD.encode()).hexdigest()

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(STATIC_DIR, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Maika Promos Dashboard", lifespan=lifespan)

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
jinja_env = Environment(loader=FileSystemLoader(TEMPLATES_DIR), auto_reload=True)


def render_template(name: str, request: Request, **context) -> HTMLResponse:
    template = jinja_env.get_template(name)
    html = template.render(request=request, **context)
    return HTMLResponse(content=html)


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
    ML_MAX_PAGES: int = 20
    ML_MAX_OFFERS: int = 0
    MAX_OFFERS_PER_RUN: int = 10
    ML_PROMOTION_TYPE: str = ""
    MIN_DISCOUNT: int = 0
    SEND_DELAY_SECONDS: int = 60
    CACHE_EXPIRY_DAYS: int = 7
    INCLUDE_KEYWORDS: str = ""
    EXCLUDE_KEYWORDS: str = ""
    CHANNELS: str = ""
    CHANNEL_PERFUMES_TELEGRAM: str = ""
    CHANNEL_PERFUMES_WHATSAPP: str = ""
    CHANNEL_PERFUMES_INCLUDE: str = ""
    CHANNEL_PERFUMES_EXCLUDE: str = ""
    ALIEXPRESS_MAX_OFFERS: int = 5
    ALIEXPRESS_TRACKING_ID: str = ""
    ALIEXPRESS_CATEGORY_IDS: str = ""
    ALIEXPRESS_KEYWORDS: str = ""
    SHOPEE_MAX_OFFERS: int = 5
    SHOPEE_KEYWORDS: str = ""


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
    clean_url: str = ""
    image_url: str = ""


# ---- Web routes ----


@app.get("/")
async def index(request: Request):
    if not check_auth(request):
        return RedirectResponse(url="/login")
    config = get_all_config()
    runs = get_recent_runs(10)
    last_run = runs[0] if runs else None
    return render_template("index.html", request=request, config=config, runs=runs, last_run=last_run)


@app.get("/login")
async def login_page(request: Request):
    return render_template("login.html", request=request)


@app.post("/login")
async def login(request: Request, password: str = Form(...)):
    if password == DASHBOARD_PASSWORD:
        resp = RedirectResponse(url="/", status_code=303)
        resp.set_cookie(key="session", value=SESSION_TOKEN, httponly=True, max_age=86400 * 7)
        return resp
    return HTMLResponse(
        content=jinja_env.get_template("login.html").render(request=request, error="Senha invalida"),
        status_code=401,
    )


@app.get("/config")
async def config_page(request: Request):
    login_required(request)
    config = get_all_config()
    return render_template("config.html", request=request, config=config, saved=request.query_params.get("saved"))


@app.post("/config")
async def config_save(request: Request):
    login_required(request)
    form = await request.form()
    items = {}
    for key in [
        "ML_CATEGORY", "ML_PAGES", "ML_MAX_PAGES", "ML_MAX_OFFERS", "MAX_OFFERS_PER_RUN",
        "ML_PROMOTION_TYPE", "MIN_DISCOUNT", "SEND_DELAY_SECONDS",
        "CACHE_EXPIRY_DAYS", "INCLUDE_KEYWORDS", "EXCLUDE_KEYWORDS",
        "CHANNELS",
        "CHANNEL_PERFUMES_TELEGRAM", "CHANNEL_PERFUMES_WHATSAPP",
        "CHANNEL_PERFUMES_INCLUDE", "CHANNEL_PERFUMES_EXCLUDE",
        "ALIEXPRESS_MAX_OFFERS", "ALIEXPRESS_TRACKING_ID",
        "ALIEXPRESS_CATEGORY_IDS", "ALIEXPRESS_KEYWORDS",
        "SHOPEE_MAX_OFFERS", "SHOPEE_KEYWORDS",
    ]:
        if key in form:
            items[key] = form[key]
    update_config_batch(items)
    return RedirectResponse(url="/config?saved=1", status_code=303)


@app.get("/history")
async def history_page(request: Request):
    login_required(request)
    runs = get_recent_runs(50)
    return render_template("history.html", request=request, runs=runs)


@app.get("/runs/{run_id}")
async def run_detail_page(request: Request, run_id: int):
    login_required(request)
    run = get_run_detail(run_id)
    if not run:
        raise HTTPException(status_code=404)
    return render_template("run_detail.html", request=request, run=run)


@app.post("/trigger")
async def trigger_run(request: Request):
    login_required(request)
    if not GH_TOKEN or not GH_REPO:
        return render_template("index.html", request=request, config=get_all_config(),
                               runs=get_recent_runs(10), error="GH_TOKEN e GH_REPO nao configurados no servidor")
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
                msg = f"Falha ao acionar GitHub Actions: {resp.status_code}"
                if resp.status_code == 404:
                    msg += ". Verifique se o GH_TOKEN tem o escopo 'workflow' e se GH_REPO esta no formato 'usuario/repo'"
                return render_template("index.html", request=request, config=get_all_config(),
                                       runs=get_recent_runs(10), error=msg)
    except Exception as e:
        logger.error("GitHub trigger error: %s", e)
        return render_template("index.html", request=request, config=get_all_config(),
                               runs=get_recent_runs(10), error=f"Erro ao acionar GitHub: {e}")

    return render_template("index.html", request=request, config=get_all_config(),
                           runs=get_recent_runs(10), success="Execucao acionada com sucesso!")


@app.get("/offers")
async def offers_page(request: Request):
    login_required(request)
    offers = get_recent_offers(100)
    return render_template("offers.html", request=request, offers=offers)


@app.get("/promos")
async def promos_page(request: Request):
    login_required(request)
    offers = get_recent_offers(200)
    return render_template("promos.html", request=request, offers=offers)


@app.get("/charts")
async def charts_page(request: Request):
    login_required(request)
    days_data = get_offers_per_day(30)
    platform_data = get_offers_by_platform()
    durations = get_run_durations(20)
    total_offers = sum(p["count"] for p in platform_data)
    return render_template("charts.html", request=request,
                           days_data=days_data, platform_data=platform_data,
                           durations=durations, total_offers=total_offers)


@app.get("/api/charts")
async def charts_api(request: Request):
    login_required(request)
    return {
        "days": get_offers_per_day(30),
        "platforms": get_offers_by_platform(),
        "durations": get_run_durations(20),
    }


@app.post("/api/promos/format")
async def format_promos(request: Request):
    login_required(request)
    data = await request.json()
    product_ids = data.get("ids", [])
    offers = get_recent_offers(999)
    selected = [o for o in offers if o["product_id"] in product_ids]
    lines = []
    for o in selected:
        title = o["title"]
        price = o["price"]
        discount = o["discount"] or ""
        url = o.get("clean_url", "") or ""
        lines.append(f"\U0001F4CC *{title}*")
        lines.append(f"\U0001F525 Por: *R$ {float(price):.2f}*")
        if discount:
            lines.append(f"\U0001F3AF {discount}")
        if url:
            lines.append(f"\U0001F6D2 {url}")
        lines.append("")
    text = "\n".join(lines).strip()
    wa_link = f"https://wa.me/?text={quote(text)}" if text else ""
    return {"text": text, "wa_link": wa_link}


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
    add_sent_offer(run_id, offer.product_id, offer.title, offer.price, offer.discount,
                   clean_url=offer.clean_url, image_url=offer.image_url)
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
            clean_url=offer.get("clean_url", ""),
            image_url=offer.get("image_url", ""),
        )
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)

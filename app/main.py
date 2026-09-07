import os
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import settings, DOCS_DIR, BASE_DIR
from database.session import init_db, get_session
from database.seed import seed_database
from domain.inventory import InventoryService
from domain.billing import BillingService
from domain.khata import KhataService
from domain.preferences import PreferenceService
from services.analytics import AnalyticsService
from agent.agent import kirana_agent

FRONTEND_DIR = BASE_DIR / "frontend"
FRONTEND_DIR.mkdir(exist_ok=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure tables exist and database is seeded
    await init_db()
    await seed_database(force=False)
    yield

app = FastAPI(
    title=settings.APP_NAME,
    description="AI-Powered Kirana Store Manager & Conversational Hub",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request Models
class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = "web_session"
    owner_id: Optional[str] = "owner_default"

# -------------------------------------------------------------
# API Endpoints
# -------------------------------------------------------------
@app.post("/api/chat")
async def chat_endpoint(payload: ChatRequest):
    """Primary conversational agent endpoint."""
    async with get_session() as session:
        response = await kirana_agent.process_message(
            session=session,
            message=payload.message,
            session_id=payload.session_id,
            owner_id=payload.owner_id
        )
        return response

@app.get("/api/inventory")
async def get_inventory_endpoint():
    """Fetch live product catalog and stock levels."""
    async with get_session() as session:
        prods = await InventoryService.find_products(session, "")
        low_stock = await InventoryService.get_low_stock_products(session)
        return {
            "products": prods,
            "low_stock": low_stock,
            "total_items": len(prods)
        }

@app.get("/api/draft")
async def get_draft_endpoint(owner_id: str = "owner_default"):
    """Fetch current active draft bill."""
    async with get_session() as session:
        return await BillingService.get_draft_details(session, owner_id)

@app.get("/api/khata")
async def get_khata_endpoint():
    """Fetch all customer khata balances."""
    async with get_session() as session:
        return await KhataService.list_all_khata(session)

@app.get("/api/khata/{customer_name}")
async def get_customer_ledger_endpoint(customer_name: str):
    """Fetch detailed customer ledger."""
    async with get_session() as session:
        try:
            return await KhataService.get_customer_ledger(session, customer_name)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

@app.get("/api/analytics")
async def get_analytics_endpoint():
    """Fetch real-time daily sales analytics."""
    async with get_session() as session:
        return await AnalyticsService.get_daily_sales_summary(session)

@app.get("/api/preferences")
async def get_preferences_endpoint(owner_id: str = "owner_default"):
    """Fetch persistent store preferences."""
    async with get_session() as session:
        return await PreferenceService.list_preferences(session, owner_id)

@app.post("/api/reset-demo")
async def reset_demo_endpoint():
    """Reset catalog and inventory to original demo state."""
    await seed_database(force=True)
    return {"success": True, "message": "Demo database successfully reset."}

@app.get("/api/documents/{filename}")
async def get_document_endpoint(filename: str):
    """Download generated PDF invoices or PPTX presentations."""
    # Prevent directory traversal
    clean_filename = Path(filename).name
    file_path = DOCS_DIR / clean_filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Document not found.")

    media_type = "application/octet-stream"
    if clean_filename.endswith(".pdf"):
        media_type = "application/pdf"
    elif clean_filename.endswith(".pptx"):
        media_type = "application/vnd.openxmlformats-officedocument.presentationml.presentation"

    return FileResponse(path=file_path, filename=clean_filename, media_type=media_type)

# Serve Frontend Static Assets
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

@app.get("/")
async def root_index():
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return HTMLResponse(content=index_path.read_text(encoding="utf-8"))
    return {"message": f"Welcome to {settings.APP_NAME}. Frontend index.html is initializing."}

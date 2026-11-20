"""
Project Golu: Secure FastAPI Orchestrator (127.0.0.1:8000)
Module: backend/main.py

Features:
- Binds strictly to 127.0.0.1 (never 0.0.0.0)
- Strict CORS policy (locked to Chrome extension & localhost)
- Defense-in-Depth token authentication via X-Golu-Token (returns 401 Unauthorized on breach)
- Endpoints:
  - GET  /api/health        -> VRAM watchdog stats, models, system health
  - POST /api/suggest-field -> Automatic Confidence Router (Vault vs Hybrid RAG)
  - POST /api/save-memory   -> Active Learning Loop (save newly entered form data)
  - GET  /api/vault         -> Inspect all vault categories & entries
  - POST /api/vault         -> Insert / update encrypted vault entry
  - DELETE /api/vault/{key} -> Delete vault entry
  - POST /api/ingest        -> Re-index resume or local document
  - GET  /api/token         -> Secure handshake to retrieve active session token
"""

import os
import time
import logging
from typing import Optional, List, Dict, Any
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Depends, status, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.security import security_manager
from backend.memory.vault_sql import vault_sql
from backend.memory.rag_store import rag_store
from backend.memory.ingest import bootstrap_memory, ingest_document
from backend.llm_engine import llm_engine
from backend.router import router
from backend.state_machine import state_machine, GoluMode
from backend.meeting_copilot import meeting_copilot

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("golu.server")

app = FastAPI(
    title="Project Golu AI Orchestrator",
    description="Production-Grade Zero-Cloud Local AI Agent Backend (4GB VRAM Edition)",
    version="1.0.0"
)

# Enforce strict CORS
# Websites can NEVER make arbitrary fetch requests to harvest personal data
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^(chrome-extension://.*|moz-extension://.*|http://127\.0\.0\.1(:\d+)?|http://localhost(:\d+)?)$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# ================= Authentication Dependency =================

def verify_golu_token(x_golu_token: Optional[str] = Header(None, alias="X-Golu-Token")):
    """
    Validates the 256-bit session token.
    Rejects unauthenticated requests with 401 Unauthorized.
    """
    if not x_golu_token or not security_manager.verify_token(x_golu_token):
        logger.warning("Unauthenticated request blocked: missing or invalid X-Golu-Token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Invalid or missing X-Golu-Token header",
            headers={"WWW-Authenticate": "Bearer"}
        )
    return x_golu_token


# ================= Request & Response Models =================

class FieldSuggestRequest(BaseModel):
    field_name: str = Field(..., description="DOM name or ID of the input field")
    field_type: str = Field(default="text", description="HTML input type (text, email, tel, textarea, etc.)")
    field_label: Optional[str] = Field(default=None, description="Associated label or aria-label text")
    placeholder: Optional[str] = Field(default=None, description="Input placeholder text")
    context: Optional[str] = Field(default=None, description="Surrounding form or section context")
    maxlength: Optional[int] = Field(default=None, description="Max character length constraint")


class SaveMemoryRequest(BaseModel):
    field_name: str = Field(..., description="Key or field name to save")
    value: str = Field(..., description="Value to store")
    category: str = Field(default="general", description="Profile category (personal, education, contact, etc.)")
    aliases: Optional[List[str]] = Field(default=None, description="Optional aliases for search")
    save_to_vault: bool = Field(default=True, description="Save to encrypted SQLite vault")
    save_to_rag: bool = Field(default=False, description="Index into ChromaDB vector store")


class VaultEntryRequest(BaseModel):
    key: str
    value: str
    category: str = "general"
    aliases: Optional[List[str]] = None


# ================= API Endpoints =================

@app.on_event("startup")
def on_startup():
    """Initializes memory stores and VRAM monitoring on server boot."""
    logger.info("Project Golu Orchestrator booting on 127.0.0.1:8000...")
    bootstrap_memory()
    logger.info(f"Session token active: {security_manager.session_token[:8]}... (256-bit)")


@app.get("/api/health")
def health_check():
    """System health check and live VRAM status."""
    vram_stats = llm_engine.watchdog.get_vram_usage()
    ollama_ready = llm_engine.is_ollama_available()
    models = llm_engine.list_installed_models() if ollama_ready else []

    return {
        "status": "healthy",
        "service": "Project Golu Orchestrator",
        "version": "1.0.0",
        "ollama_connected": ollama_ready,
        "available_models": models,
        "vram": vram_stats,
        "vault_entries": len(vault_sql.list_all()),
        "rag_chunks": rag_store.collection.count()
    }


@app.get("/api/token")
def get_session_token(request: Request):
    """
    Local handshake endpoint to pair thin clients (Browser extension / Stealth HUD).
    Allowed only for localhost calls.
    """
    client_host = request.client.host if request.client else ""
    if client_host not in {"127.0.0.1", "localhost", "::1"}:
        raise HTTPException(status_code=403, detail="Forbidden: Handshake only allowed from 127.0.0.1")

    return {
        "session_token": security_manager.session_token,
        "service": "golu-ai",
        "port": 8000
    }


@app.post("/api/suggest-field")
def suggest_field(
    req: FieldSuggestRequest,
    token: str = Depends(verify_golu_token)
):
    """
    Automatic Confidence Router:
    Routes field requests between Deterministic Encrypted Vault (<20ms) and Hybrid RAG (<1.8s).
    """
    result = router.route_field(
        field_name=req.field_name,
        field_type=req.field_type,
        field_label=req.field_label,
        placeholder=req.placeholder,
        context=req.context,
        maxlength=req.maxlength
    )
    return result


@app.post("/api/save-memory")
def save_memory(
    req: SaveMemoryRequest,
    token: str = Depends(verify_golu_token)
):
    """
    Active Learning Loop:
    Updates SQLite Vault or ChromaDB RAG with user-edited or newly entered information.
    """
    saved_vault = False
    saved_rag = False

    if req.save_to_vault:
        vault_sql.set_value(
            canonical_key=req.field_name,
            value=req.value,
            category=req.category,
            aliases=req.aliases
        )
        saved_vault = True

    if req.save_to_rag:
        doc_id = f"custom_user_memory_{int(time.time())}"
        rag_store.add_documents([{
            "id": doc_id,
            "text": f"{req.field_name}: {req.value}",
            "metadata": {"source": "active_learning", "category": req.category}
        }])
        saved_rag = True

    return {
        "status": "success",
        "saved_to_vault": saved_vault,
        "saved_to_rag": saved_rag,
        "field_name": req.field_name
    }


@app.get("/api/vault")
def get_vault_entries(token: str = Depends(verify_golu_token)):
    """Lists registered keys and categories in the vault."""
    return {"entries": vault_sql.list_all()}


@app.post("/api/vault")
def add_vault_entry(
    req: VaultEntryRequest,
    token: str = Depends(verify_golu_token)
):
    """Creates or updates a key-value entry in the encrypted vault."""
    vault_sql.set_value(
        canonical_key=req.key,
        value=req.value,
        category=req.category,
        aliases=req.aliases
    )
    return {"status": "success", "key": req.key}


@app.delete("/api/vault/{key}")
def delete_vault_entry(
    key: str,
    token: str = Depends(verify_golu_token)
):
    """Deletes an entry from the vault."""
    deleted = vault_sql.delete_key(key)
    if not deleted:
        raise HTTPException(status_code=404, detail="Key not found in vault")
    return {"status": "success", "deleted_key": key}


@app.post("/api/ingest")
def trigger_ingest(
    file_path: Optional[str] = None,
    token: str = Depends(verify_golu_token)
):
    """Triggers document chunking and indexing into ChromaDB + BM25."""
    if file_path:
        p = Path(file_path)
        chunks = ingest_document(p)
        return {"status": "success", "file": str(p), "chunks_indexed": chunks}
    else:
        bootstrap_memory()
        return {"status": "success", "action": "bootstrap_memory", "total_chunks": rag_store.collection.count()}


# ================= WebSocket Manager for Browser & Voice =================

class BrowserWebSocketManager:
    """Manages connected browser extensions for real-time batch fills and voice triggers."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"Browser client connected. Total clients: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"Browser client disconnected. Total clients: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.warning(f"Failed to send WS message: {e}")
                self.disconnect(connection)


ws_manager = BrowserWebSocketManager()


@app.websocket("/ws/browser")
async def websocket_browser_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            # Handle incoming client messages if any
            if data.get("action") == "PING":
                await websocket.send_json({"action": "PONG"})
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.debug(f"WS error: {e}")
        ws_manager.disconnect(websocket)


@app.post("/api/trigger-form-fill")
async def trigger_form_fill(token: str = Depends(verify_golu_token)):
    """
    Broadcasts form fill command to active browser extension tabs (used by Voice / Hotkeys).
    """
    await ws_manager.broadcast({"action": "FILL_CURRENT_FORM"})
    return {
        "status": "success",
        "action": "FILL_CURRENT_FORM",
        "active_clients": len(ws_manager.active_connections)
    }


class BatchSuggestRequest(BaseModel):
    fields: List[FieldSuggestRequest]


@app.post("/api/batch-suggest")
def batch_suggest(
    req: BatchSuggestRequest,
    token: str = Depends(verify_golu_token)
):
    """
    Fast batch suggestion endpoint for multi-field forms.
    Processes fields efficiently with Vault (<5ms) and grounded RAG.
    """
    results = []
    for f in req.fields:
        res = router.route_field(
            field_name=f.field_name,
            field_type=f.field_type,
            field_label=f.field_label,
            placeholder=f.placeholder,
            context=f.context,
            maxlength=f.maxlength
        )
        results.append(res)
    return {"results": results, "count": len(results)}


# ================= State Management & Meeting Co-Pilot Endpoints =================

class StateChangeRequest(BaseModel):
    mode: str = Field(..., description="Target mode: MODE_ASSISTANT, MODE_MEETING, MODE_KILL, or IDLE")


@app.get("/api/state")
def get_current_state(token: str = Depends(verify_golu_token)):
    """Returns live FSM mode and HUD visibility state."""
    return {
        "current_mode": state_machine.current_mode.value,
        "hud_visible": state_machine.hud_visible
    }


@app.post("/api/state")
def set_state(req: StateChangeRequest, token: str = Depends(verify_golu_token)):
    """Triggers FSM state transition enforcing mutual exclusivity and hard-mute rules."""
    try:
        target = GoluMode(req.mode)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid mode '{req.mode}'. Valid modes: {[m.value for m in GoluMode]}"
        )
    new_mode = state_machine.transition_to(target)
    return {
        "status": "success",
        "current_mode": new_mode.value,
        "hud_visible": state_machine.hud_visible
    }


class MeetingSimulateRequest(BaseModel):
    speaker_question: str = Field(..., description="Simulated meeting speaker audio question")


@app.post("/api/meeting/simulate")
def simulate_meeting_copilot(
    req: MeetingSimulateRequest,
    token: str = Depends(verify_golu_token)
):
    """
    Simulates a meeting participant's question, processes via RAG + LLM,
    and returns concise talking points for the invisible HUD.
    """
    clean_q = security_manager.sanitize_input(req.speaker_question)
    advice = meeting_copilot.generate_copilot_advice(clean_q)
    return {
        "status": "success",
        "question": clean_q,
        "copilot_advice": advice
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=False)

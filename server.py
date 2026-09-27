"""
magicpin AI Challenge — Vera Merchant AI Assistant Server
==========================================================
Complete FastAPI server implementation serving the 5 required endpoints:
1. POST /v1/context
2. POST /v1/tick
3. POST /v1/reply
4. GET  /v1/healthz
5. GET  /v1/metadata
"""

import time
from datetime import datetime
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from context_store import ContextStore
from composer import MessageComposer
from reply_handler import ReplyHandler

# Initialize FastAPI App & State
app = FastAPI(
    title="magicpin AI Challenge — Vera Bot",
    description="Stateful Vera AI Assistant HTTP Server for magicpin Challenge",
    version="1.0.0"
)

START_TIME = time.time()
store = ContextStore()


# --- Pydantic Request Models ---

class ContextPushRequest(BaseModel):
    scope: str
    context_id: str
    version: int
    payload: Dict[str, Any]
    delivered_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")


class TickRequest(BaseModel):
    now: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    available_triggers: List[str] = []


class ReplyRequest(BaseModel):
    conversation_id: str
    merchant_id: Optional[str] = None
    customer_id: Optional[str] = None
    from_role: str = "merchant"
    message: str
    received_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    turn_number: int = 1


# --- API Routes ---

@app.get("/v1/healthz")
async def healthz():
    """
    Liveness probe. Returns HTTP 200 with status, uptime, and loaded context counts.
    """
    uptime = int(time.time() - START_TIME)
    counts = store.get_context_counts()
    return {
        "status": "ok",
        "uptime_seconds": uptime,
        "contexts_loaded": counts
    }


@app.get("/v1/metadata")
async def metadata():
    """
    Returns bot identity, version, team info, and technical approach.
    """
    return {
        "team_name": "Team Vera AI",
        "team_members": ["Vera Engineer"],
        "model": "gemini-flash-hybrid-composer",
        "approach": "Stateful 4-context framework with intent transition execution & WhatsApp auto-reply detection",
        "contact_email": "vera-ai@example.com",
        "version": "1.0.0",
        "submitted_at": "2026-09-26T19:21:00Z"
    }


@app.post("/v1/context")
async def push_context(req: ContextPushRequest):
    """
    Receives and stores context pushes. Idempotent by (scope, context_id, version).
    Returns 200 on success, 409 on stale version, 400 on invalid input.
    """
    success, result_or_ack, cur_version = store.push_context(
        scope=req.scope,
        context_id=req.context_id,
        version=req.version,
        payload=req.payload,
        delivered_at=req.delivered_at
    )

    if not success:
        if result_or_ack == "stale_version":
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={
                    "accepted": False,
                    "reason": "stale_version",
                    "current_version": cur_version
                }
            )
        elif result_or_ack == "invalid_scope":
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "accepted": False,
                    "reason": "invalid_scope",
                    "details": f"Scope '{req.scope}' is invalid. Allowed: category, merchant, customer, trigger."
                }
            )
        else:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"accepted": False, "reason": "malformed_request"}
            )

    return {
        "accepted": True,
        "ack_id": result_or_ack,
        "stored_at": datetime.utcnow().isoformat() + "Z"
    }


@app.post("/v1/tick")
async def tick(req: TickRequest):
    """
    Periodic wake-up tick. Inspects available triggers and returns proactive actions.
    """
    actions = []

    for trg_id in req.available_triggers:
        trg_payload = store.get_context("trigger", trg_id)
        if not trg_payload:
            continue

        suppression_key = trg_payload.get("suppression_key", "")
        if suppression_key and store.is_suppressed(suppression_key):
            continue

        merchant_id = trg_payload.get("merchant_id")
        customer_id = trg_payload.get("customer_id")
        trg_inner_payload = trg_payload.get("payload", {})
        if not merchant_id:
            merchant_id = trg_inner_payload.get("merchant_id")
        if not customer_id:
            customer_id = trg_inner_payload.get("customer_id")

        merchant = store.get_context("merchant", merchant_id) if merchant_id else None
        category_slug = merchant.get("category_slug", "") if merchant else trg_inner_payload.get("category", "")
        category = store.get_context("category", category_slug) if category_slug else None
        customer = store.get_context("customer", customer_id) if customer_id else None

        # Compose action
        action = MessageComposer.compose_action(category, merchant, trg_payload, customer)

        # Mark suppression key as used & register conversation
        if suppression_key:
            store.mark_suppressed(suppression_key)

        store.get_or_create_conversation(
            conv_id=action["conversation_id"],
            merchant_id=merchant_id,
            customer_id=customer_id,
            trigger_id=trg_id
        )

        actions.append(action)

    return {"actions": actions}


@app.post("/v1/reply")
async def reply(req: ReplyRequest):
    """
    Receives incoming reply turns from merchant or customer. Evaluates reply and returns next action.
    """
    conv_state = store.get_or_create_conversation(
        conv_id=req.conversation_id,
        merchant_id=req.merchant_id or "",
        customer_id=req.customer_id
    )

    # Record incoming turn
    store.add_turn(req.conversation_id, req.from_role, req.message)

    # Compute reply decision
    res = ReplyHandler.handle_reply(conv_state, req.message, req.turn_number)

    # Record bot response if action is send
    if res.get("action") == "send" and res.get("body"):
        store.add_turn(req.conversation_id, "vera", res["body"])

    if res.get("action") in ("end", "wait"):
        store.update_conversation(req.conversation_id, status=res["action"])

    return res


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)

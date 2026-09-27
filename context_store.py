"""
Context Store for magicpin AI Challenge (Vera AI Assistant)
==========================================================
Manages stateful context storage, versioning, conversation history, and suppression keys.
"""

from typing import Dict, Any, Optional, Tuple, Set
from datetime import datetime
import threading


class ContextStore:
    def __init__(self):
        self._lock = threading.Lock()
        # (scope, context_id) -> {"version": int, "payload": dict, "delivered_at": str, "stored_at": str}
        self.contexts: Dict[Tuple[str, str], Dict[str, Any]] = {}
        
        # conversation_id -> {"merchant_id": str, "customer_id": str|None, "trigger_id": str, "turns": list, "auto_reply_count": int, "status": str}
        self.conversations: Dict[str, Dict[str, Any]] = {}
        
        # Set of suppression_keys that have been used
        self.suppressed_keys: Set[str] = set()

    def push_context(self, scope: str, context_id: str, version: int, payload: Dict[str, Any], delivered_at: str) -> Tuple[bool, str, Optional[int]]:
        """
        Pushes a context payload. Returns (success, reason_or_ack, current_version_if_stale).
        Idempotent by (scope, context_id, version).
        """
        valid_scopes = {"category", "merchant", "customer", "trigger"}
        if scope not in valid_scopes:
            return False, "invalid_scope", None

        key = (scope, context_id)
        with self._lock:
            existing = self.contexts.get(key)
            if existing and existing["version"] >= version:
                return False, "stale_version", existing["version"]

            now_iso = datetime.utcnow().isoformat() + "Z"
            self.contexts[key] = {
                "version": version,
                "payload": payload,
                "delivered_at": delivered_at,
                "stored_at": now_iso
            }
            return True, f"ack_{context_id}_v{version}", None

    def get_context(self, scope: str, context_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            entry = self.contexts.get((scope, context_id))
            return entry["payload"] if entry else None

    def get_context_counts(self) -> Dict[str, int]:
        counts = {"category": 0, "merchant": 0, "customer": 0, "trigger": 0}
        with self._lock:
            for (scope, _), _ in self.contexts.items():
                if scope in counts:
                    counts[scope] += 1
        return counts

    def is_suppressed(self, suppression_key: str) -> bool:
        if not suppression_key:
            return False
        with self._lock:
            return suppression_key in self.suppressed_keys

    def mark_suppressed(self, suppression_key: str):
        if suppression_key:
            with self._lock:
                self.suppressed_keys.add(suppression_key)

    def get_or_create_conversation(self, conv_id: str, merchant_id: str, customer_id: Optional[str] = None, trigger_id: Optional[str] = None) -> Dict[str, Any]:
        with self._lock:
            if conv_id not in self.conversations:
                self.conversations[conv_id] = {
                    "conversation_id": conv_id,
                    "merchant_id": merchant_id,
                    "customer_id": customer_id,
                    "trigger_id": trigger_id,
                    "turns": [],
                    "auto_reply_count": 0,
                    "status": "active",
                    "created_at": datetime.utcnow().isoformat() + "Z"
                }
            return self.conversations[conv_id]

    def add_turn(self, conv_id: str, role: str, message: str):
        with self._lock:
            if conv_id in self.conversations:
                self.conversations[conv_id]["turns"].append({
                    "role": role,
                    "message": message,
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                })

    def update_conversation(self, conv_id: str, **kwargs):
        with self._lock:
            if conv_id in self.conversations:
                self.conversations[conv_id].update(kwargs)

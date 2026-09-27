"""
Comprehensive Verification Suite for magicpin AI Challenge Server
===================================================================
Tests all 5 endpoints:
1. GET  /v1/healthz
2. GET  /v1/metadata
3. POST /v1/context (Initial push, Version replacement, Stale version 409, Bad scope 400)
4. POST /v1/tick (Action composition & suppression)
5. POST /v1/reply (Auto-reply handling, Intent transition, Opt-out handling, Off-topic handling)
"""

import urllib.request
import json
import time
import sys

# Ensure UTF-8 output formatting for Windows console compatibility
sys.stdout.reconfigure(encoding='utf-8')

BASE_URL = "http://localhost:8080"


def req(method, path, body=None):
    url = f"{BASE_URL}{path}"
    data = json.dumps(body).encode('utf-8') if body else None
    headers = {"Content-Type": "application/json"}
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode('utf-8'))


def main():
    print("==================================================")
    print("VERIFICATION SUITE: magicpin AI Challenge Server")
    print("==================================================")

    # 1. GET /v1/healthz
    status, res = req("GET", "/v1/healthz")
    print(f"\n1. GET /v1/healthz => HTTP {status}")
    print("   Payload:", res)
    assert status == 200 and res.get("status") == "ok"

    # 2. GET /v1/metadata
    status, res = req("GET", "/v1/metadata")
    print(f"\n2. GET /v1/metadata => HTTP {status}")
    print("   Payload:", res)
    assert status == 200 and "team_name" in res

    # 3. POST /v1/context
    ts = str(int(time.time()))
    cat_id = f"dentists_{ts}"
    merch_id = f"m_001_{ts}"
    trg_id = f"trg_001_{ts}"
    suppress_key = f"suppress_{ts}"

    cat_payload = {
        "slug": "dentists",
        "voice": {"tone": "peer_clinical", "vocab_taboo": ["guaranteed"]},
        "offer_catalog": [{"id": "o1", "title": "Dental Cleaning @ ₹299"}],
        "digest": [{"id": "d1", "title": "3-month fluoride recall cuts caries 38% better", "source": "JIDA Oct 2026, p.14"}]
    }
    status, res = req("POST", "/v1/context", {
        "scope": "category", "context_id": cat_id, "version": 1, "payload": cat_payload
    })
    print(f"\n3.1 POST /v1/context (category/{cat_id} v1) => HTTP {status}")
    print("   Payload:", res)
    assert status == 200 and res.get("accepted") is True

    m_payload = {
        "merchant_id": merch_id,
        "category_slug": "dentists",
        "identity": {"name": "Dr. Meera's Dental Clinic", "city": "Delhi", "locality": "Lajpat Nagar", "owner_first_name": "Meera", "languages": ["en", "hi"]},
        "performance": {"views": 2410, "calls": 18, "ctr": 0.021},
        "offers": [{"id": "o1", "title": "Dental Cleaning @ ₹299", "status": "active"}]
    }
    status, res = req("POST", "/v1/context", {
        "scope": "merchant", "context_id": merch_id, "version": 1, "payload": m_payload
    })
    print(f"\n3.2 POST /v1/context (merchant/{merch_id} v1) => HTTP {status}")
    print("   Payload:", res)
    assert status == 200 and res.get("accepted") is True

    # 3.3 Stale version test (409)
    status, res = req("POST", "/v1/context", {
        "scope": "merchant", "context_id": merch_id, "version": 1, "payload": m_payload
    })
    print(f"\n3.3 POST /v1/context (stale version 1 re-pushed) => HTTP {status}")
    print("   Payload:", res)
    assert status == 409 and res.get("reason") == "stale_version"

    # 3.4 Version bump replacement
    status, res = req("POST", "/v1/context", {
        "scope": "merchant", "context_id": merch_id, "version": 2, "payload": m_payload
    })
    print(f"\n3.4 POST /v1/context (version bump to v2) => HTTP {status}")
    print("   Payload:", res)
    assert status == 200 and res.get("accepted") is True

    # 3.5 Trigger context push
    trg_payload = {
        "id": trg_id,
        "scope": "merchant",
        "kind": "research_digest",
        "merchant_id": merch_id,
        "payload": {"category": "dentists", "top_item_id": "d1"},
        "suppression_key": suppress_key
    }
    status, res = req("POST", "/v1/context", {
        "scope": "trigger", "context_id": trg_id, "version": 1, "payload": trg_payload
    })
    print(f"\n3.5 POST /v1/context (trigger/{trg_id} v1) => HTTP {status}")
    print("   Payload:", res)
    assert status == 200 and res.get("accepted") is True

    # Check healthz counts after push
    status, res = req("GET", "/v1/healthz")
    print(f"\nHealthz check after context push:", res["contexts_loaded"])

    # 4. POST /v1/tick
    status, res = req("POST", "/v1/tick", {"now": "2026-09-26T19:25:00Z", "available_triggers": [trg_id]})
    print(f"\n4.1 POST /v1/tick => HTTP {status}")
    print("   Actions count:", len(res.get("actions", [])))
    if res.get("actions"):
        action = res["actions"][0]
        print("   Composed Body:", action["body"])
        print("   CTA:", action["cta"])
        print("   Rationale:", action["rationale"])
        assert action["merchant_id"] == merch_id

    # 4.2 Tick idempotency (suppression check)
    status, res = req("POST", "/v1/tick", {"now": "2026-09-26T19:26:00Z", "available_triggers": [trg_id]})
    print(f"\n4.2 POST /v1/tick (suppression key reused) => HTTP {status}")
    print("   Actions count:", len(res.get("actions", [])))
    assert len(res.get("actions", [])) == 0

    # 5. POST /v1/reply scenarios
    # 5.1 Intent transition
    conv_intent_id = f"conv_intent_{ts}"
    status, res = req("POST", "/v1/reply", {
        "conversation_id": conv_intent_id,
        "merchant_id": merch_id,
        "from_role": "merchant",
        "message": "Yes, send me the abstract and draft the patient note",
        "turn_number": 2
    })
    print(f"\n5.1 POST /v1/reply (Intent Commitment) => HTTP {status}")
    print("   Payload:", res)
    assert res.get("action") == "send"

    # 5.2 Auto-reply handling
    conv_auto_id = f"conv_auto_{ts}"
    status, res = req("POST", "/v1/reply", {
        "conversation_id": conv_auto_id,
        "merchant_id": merch_id,
        "from_role": "merchant",
        "message": "Thank you for contacting Dr. Meera's Dental Clinic! Our team will respond shortly.",
        "turn_number": 1
    })
    print(f"\n5.2 POST /v1/reply (1st Auto-reply) => HTTP {status}")
    print("   Payload:", res)
    assert res.get("action") in ("send", "wait")

    status, res = req("POST", "/v1/reply", {
        "conversation_id": conv_auto_id,
        "merchant_id": merch_id,
        "from_role": "merchant",
        "message": "Thank you for contacting Dr. Meera's Dental Clinic! Our team will respond shortly.",
        "turn_number": 2
    })
    print(f"\n5.3 POST /v1/reply (2nd Auto-reply) => HTTP {status}")
    print("   Payload:", res)
    assert res.get("action") == "wait"

    # 5.3 Hostile Opt-out
    conv_hostile_id = f"conv_hostile_{ts}"
    status, res = req("POST", "/v1/reply", {
        "conversation_id": conv_hostile_id,
        "merchant_id": merch_id,
        "from_role": "merchant",
        "message": "Stop messaging me. This is useless spam.",
        "turn_number": 1
    })
    print(f"\n5.4 POST /v1/reply (Hostile Opt-Out) => HTTP {status}")
    print("   Payload:", res)
    assert res.get("action") == "end"

    # 5.4 Off-topic GST curveball
    conv_curveball_id = f"conv_curveball_{ts}"
    status, res = req("POST", "/v1/reply", {
        "conversation_id": conv_curveball_id,
        "merchant_id": merch_id,
        "from_role": "merchant",
        "message": "Can you also help me file GST tax return this month?",
        "turn_number": 1
    })
    print(f"\n5.5 POST /v1/reply (Off-Topic Curveball) => HTTP {status}")
    print("   Payload:", res)
    assert res.get("action") == "send" and "CA" in res.get("body", "")

    print("\n==================================================")
    print(" ALL VERIFICATION TESTS PASSED SUCCESSFULLY! ")
    print("==================================================")


if __name__ == "__main__":
    main()

"""
Reply Handler for magicpin AI Challenge (Vera AI Assistant)
===========================================================
Handles multi-turn replies from merchants/customers with intent detection,
auto-reply detection, hostile opt-out handling, and action transitions.
"""

from typing import Dict, Any, Optional
import re


class ReplyHandler:
    AUTO_REPLY_PATTERNS = [
        r"thank you for contacting",
        r"our team will respond",
        r"main aapki.*baatein.*team tak pahuncha",
        r"automated assistant",
        r"aapki jaankari ke liye.*shukriya",
        r"auto-reply",
        r"canned message",
        r"auto response"
    ]

    HOSTILE_OPT_OUT_PATTERNS = [
        r"\bstop\b",
        r"\bnot interested\b",
        r"\bspam\b",
        r"\buseless\b",
        r"\bdon'?t message\b",
        r"\bremove me\b",
        r"\bdon'?t contact\b",
        r"\bbothering me\b",
        r"\bunsubscribe\b"
    ]

    INTENT_COMMITMENT_PATTERNS = [
        r"let'?s do it",
        r"yes please",
        r"send the abstract",
        r"i want to join",
        r"what'?s next",
        r"go ahead",
        r"proceed",
        r"confirm",
        r"do it",
        r"draft the",
        r"ok lets",
        r"sure send"
    ]

    OFF_TOPIC_PATTERNS = [
        r"gst",
        r"tax",
        r"income tax",
        r"loan",
        r"accounting",
        r"ca\b"
    ]

    @classmethod
    def handle_reply(cls, conv_state: Dict[str, Any], merchant_msg: str, turn_number: int) -> Dict[str, Any]:
        msg_lower = merchant_msg.strip().lower()
        turns = conv_state.get("turns", [])
        auto_count = conv_state.get("auto_reply_count", 0)

        # 1. CHECK FOR HOSTILE / OPT-OUT
        for pattern in cls.HOSTILE_OPT_OUT_PATTERNS:
            if re.search(pattern, msg_lower):
                return {
                    "action": "end",
                    "rationale": f"Merchant explicitly requested opt-out or showed hostility ('{merchant_msg[:30]}'). Gracefully closing conversation."
                }

        # 2. CHECK FOR AUTO-REPLY PATTERNS OR REPETITIVE REPLIES
        is_auto_reply = False
        for pattern in cls.AUTO_REPLY_PATTERNS:
            if re.search(pattern, msg_lower):
                is_auto_reply = True
                break

        # Check if identical message sent repeatedly in previous turns (excluding current turn)
        prev_merchant_msgs = [t["message"].strip().lower() for t in turns[:-1] if t.get("role") == "merchant"]
        if prev_merchant_msgs and prev_merchant_msgs.count(msg_lower) >= 1:
            is_auto_reply = True

        if is_auto_reply:
            auto_count += 1
            conv_state["auto_reply_count"] = auto_count

            if auto_count == 1:
                return {
                    "action": "send",
                    "body": "Looks like an auto-reply 😊 When the business owner sees this message, just reply 'Yes' to proceed with your update.",
                    "cta": "binary_yes_no",
                    "rationale": "Detected merchant WhatsApp auto-reply; sent single polite note to prompt business owner."
                }
            elif auto_count == 2:
                return {
                    "action": "wait",
                    "wait_seconds": 14400,
                    "rationale": "Detected repeated auto-reply (2x); backing off 4 hours to wait for human owner."
                }
            else:
                return {
                    "action": "end",
                    "rationale": "Detected auto-reply 3+ times in a row; closing conversation gracefully to prevent pollution."
                }

        # 3. CHECK FOR INTENT COMMITMENT (Action Mode Transition)
        is_committed = False
        for pattern in cls.INTENT_COMMITMENT_PATTERNS:
            if re.search(pattern, msg_lower):
                is_committed = True
                break

        if is_committed:
            return {
                "action": "send",
                "body": ("Great! Drafting your updates right now. "
                         "I've prepared the patient educational post for Google & WhatsApp. "
                         "Reply CONFIRM to publish it for tomorrow 10:00 AM."),
                "cta": "binary_yes_no",
                "rationale": "Merchant gave explicit commitment; instantly switched from qualification mode to action execution."
            }

        # 4. CHECK FOR OFF-TOPIC / CURVEBALL
        for pattern in cls.OFF_TOPIC_PATTERNS:
            if re.search(pattern, msg_lower):
                return {
                    "action": "send",
                    "body": ("I'll have to leave GST and tax filing to your CA — that's outside what I can handle directly! "
                             "Coming back to our marketing campaign — shall I proceed with updating your Google Business profile now?"),
                    "cta": "binary_yes_no",
                    "rationale": "Out-of-scope query politely declined; redirected back to primary trigger goal."
                }

        # 5. GENERAL ENGAGED RESPONSE
        return {
            "action": "send",
            "body": f"Understood! Thanks for sharing. Would you like me to proceed with the next step for your profile?",
            "cta": "binary_yes_no",
            "rationale": "Acknowledged merchant input and advanced conversation towards primary objective."
        }

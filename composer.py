"""
Composer Engine for magicpin AI Challenge (Vera AI Assistant)
============================================================
Composes targeted WhatsApp messages based on the 4-context framework:
CategoryContext, MerchantContext, TriggerContext, CustomerContext.
"""

from typing import Dict, Any, Optional, List


class MessageComposer:
    @staticmethod
    def compose_action(category: Optional[Dict[str, Any]], 
                       merchant: Optional[Dict[str, Any]], 
                       trigger: Dict[str, Any], 
                       customer: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Composes a proactive action dictionary for /v1/tick.
        """
        trg_id = trigger.get("id", "trg_unknown")
        kind = trigger.get("kind", "")
        scope = trigger.get("scope", "merchant")
        merchant_id = trigger.get("merchant_id") or (merchant.get("merchant_id") if merchant else "")
        customer_id = trigger.get("customer_id") or (customer.get("customer_id") if customer else None)
        suppression_key = trigger.get("suppression_key", f"suppress:{trg_id}")
        payload = trigger.get("payload", {})

        # Default identities
        m_identity = merchant.get("identity", {}) if merchant else {}
        m_name = m_identity.get("name", "Partner")
        owner_name = m_identity.get("owner_first_name") or m_identity.get("name", "Partner")
        category_slug = category.get("slug", "") if category else ""
        languages = m_identity.get("languages", ["en"])
        is_hindi_mix = any("hi" in lang.lower() for lang in languages)

        # Send AS
        send_as = "merchant_on_behalf" if scope == "customer" else "vera"

        # Determine composition based on trigger kind & contexts
        body = ""
        cta = "open_ended"
        template_name = f"vera_{kind}_v1"
        rationale = ""
        template_params = []

        # 1. RESEARCH DIGEST / COMPLIANCE
        if kind in ("research_digest", "regulation_change", "category_research_digest_release"):
            top_item = payload.get("top_item", {})
            top_item_id = payload.get("top_item_id", "")
            
            # Look up item in category digest if available
            digest = category.get("digest", []) if category else []
            item_match = next((item for item in digest if item.get("id") == top_item_id), None)
            if item_match:
                title = item_match.get("title", "")
                source = item_match.get("source", "")
                trial_n = item_match.get("trial_n")
                summary = item_match.get("summary", "")
            else:
                title = top_item.get("title", payload.get("title", "new industry updates"))
                source = top_item.get("source", payload.get("source", "industry report"))
                trial_n = top_item.get("trial_n")
                summary = ""

            if category_slug == "dentists":
                salutation = f"Dr. {owner_name}" if not owner_name.startswith("Dr.") else owner_name
                cite_str = f" — {source}" if source else ""
                n_str = f"{trial_n}-patient " if trial_n else ""
                
                body = (f"{salutation}, {source or 'JIDA'}'s latest release is in. "
                        f"One item relevant to your patient cohort: {n_str}trial shows {title}. "
                        f"Worth a look (2-min summary). Want me to pull details + draft a patient WhatsApp note you can share?{cite_str}")
                cta = "open_ended"
                rationale = f"Clinical peer tone for dentist; anchored on source '{source}' with specific trial data; open-ended CTA asking to draft patient note."
            else:
                body = (f"Hi {owner_name}, new update for {category_slug}: '{title}' ({source}). "
                        f"Want me to summarize the key operational steps for your shop?")
                cta = "binary_yes_no"
                rationale = f"Industry digest alert for {category_slug}; binary CTA to reduce effort."

        # 2. CUSTOMER RECALL / APPOINTMENT (Customer-facing)
        elif kind in ("recall_due", "appointment_tomorrow", "customer_lapsed_soft"):
            c_identity = customer.get("identity", {}) if customer else {}
            c_name = c_identity.get("name", "Valued Customer")
            service_due = payload.get("service_due", "regular checkup").replace("_", " ")
            slots = payload.get("available_slots", [])

            # Active offers from merchant catalog
            offers = merchant.get("offers", []) if merchant else []
            active_offer = next((o.get("title") for o in offers if o.get("status") == "active"), "Special Checkup @ ₹299")

            slot_str = ""
            if len(slots) >= 2:
                slot_str = f"**{slots[0].get('label')}** ya **{slots[1].get('label')}**"
            elif len(slots) == 1:
                slot_str = f"**{slots[0].get('label')}**"
            else:
                slot_str = "this week"

            if is_hindi_mix:
                body = (f"Hi {c_name}, {m_name} se clinic reminder 🦷 It's been 5 months since your last visit — "
                        f"your {service_due} is due. Apke liye slots ready hain: {slot_str}. "
                        f"{active_offer}. Reply 1 or 2 to confirm, or tell us a time that works best for you.")
            else:
                body = (f"Hi {c_name}, {m_name} reminder 🦷 Your {service_due} is due. "
                        f"Available slots: {slot_str}. Offer: {active_offer}. "
                        f"Reply with your preferred slot to confirm.")

            cta = "multi_choice_slot"
            send_as = "merchant_on_behalf"
            rationale = f"Customer-facing recall sent via merchant account; customized slot options and active catalog offer."

        # 3. PERFORMANCE SPIKE / DIP
        elif kind in ("perf_spike", "perf_dip"):
            perf = merchant.get("performance", {}) if merchant else {}
            metric = payload.get("metric", "views")
            delta_pct = payload.get("delta_pct", 0)
            window = payload.get("window", "7d")

            pct_str = f"{abs(int(delta_pct * 100))}%"
            views = perf.get("views", 0)
            calls = perf.get("calls", 0)

            if kind == "perf_spike":
                body = (f"Hi {owner_name}, quick stats: your profile views spiked **+{pct_str}** over the last {window} "
                        f"({views} total views)! Want me to publish a fresh post to turn this momentum into calls?")
                cta = "binary_yes_no"
                rationale = f"Loss-prevention & momentum framing on performance spike; binary CTA."
            else:
                body = (f"Hi {owner_name}, noticed your customer {metric} dropped **{pct_str}** this week ({calls} calls). "
                        f"I've drafted a targeted service offer to boost walk-ins. Want to review it now?")
                cta = "binary_yes_no"
                rationale = f"Proactive intervention for performance dip; externalizing effort with pre-drafted offer."

        # 4. RENEWAL / SUBSCRIPTION
        elif kind == "renewal_due":
            days_rem = payload.get("days_remaining", 7)
            plan = payload.get("plan", "Pro")
            body = (f"Hi {owner_name}, your Vera {plan} plan has {days_rem} days remaining. "
                    f"To keep your auto-posts and patient reminders running smoothly without interruption, reply YES to extend.")
            cta = "binary_yes_no"
            rationale = "Subscription renewal nudge emphasizing continuity of automated customer reminders."

        # 5. FESTIVAL / EVENT
        elif kind == "festival_upcoming":
            festival = payload.get("festival", "Diwali")
            days_until = payload.get("days_until", 7)
            
            # Category offer catalog match
            offers = merchant.get("offers", []) if merchant else []
            active_offer = next((o.get("title") for o in offers if o.get("status") == "active"), "Festival Offer @ Special Price")

            body = (f"Hi {owner_name}, {festival} is {days_until} days away! Search traffic for {category_slug} in {m_identity.get('locality', 'your area')} is peaking. "
                    f"Want me to launch your '{active_offer}' festival banner campaign on Google today?")
            cta = "binary_yes_no"
            rationale = f"Seasonal trigger for {festival}; specific category offer integration with low-friction CTA."

        # 6. DORMANT / GENERAL NUDGE
        else:
            perf = merchant.get("performance", {}) if merchant else {}
            views = perf.get("views", 1200)
            locality = m_identity.get("locality", "your area")
            body = (f"Hi {owner_name}, Vera here! Your profile generated {views} customer views in {locality} recently. "
                    f"Would you like me to highlight your active offer on Google Business Profile today?")
            cta = "binary_yes_no"
            rationale = f"Curiosity and social proof nudge for dormant merchant in {locality}."

        template_params = [owner_name, category_slug]

        return {
            "conversation_id": f"conv_{merchant_id}_{trg_id}",
            "merchant_id": merchant_id,
            "customer_id": customer_id,
            "send_as": send_as,
            "trigger_id": trg_id,
            "template_name": template_name,
            "template_params": template_params,
            "body": body,
            "cta": cta,
            "suppression_key": suppression_key,
            "rationale": rationale
        }

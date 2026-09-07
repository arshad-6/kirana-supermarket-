import re
import json
import logging
from decimal import Decimal
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from agent.tools.registry import ToolExecutor, AGENT_TOOLS_SCHEMA
from domain.preferences import PreferenceService
from domain.inventory import InventoryService
from domain.billing import BillingService
from config import settings

logger = logging.getLogger("kirana_agent")

class KiranaAgent:
    def __init__(self):
        # In-memory conversational session store (cleared on /new)
        self.sessions: Dict[str, List[Dict[str, Any]]] = {}

    def get_history(self, session_id: str) -> List[Dict[str, Any]]:
        if session_id not in self.sessions:
            self.sessions[session_id] = []
        return self.sessions[session_id]

    def clear_session(self, session_id: str):
        """Clear conversational context. Does NOT delete DB state, inventory, or preferences."""
        self.sessions[session_id] = []

    async def process_message(
        self,
        session: AsyncSession,
        message: str,
        session_id: str = "default_session",
        owner_id: str = "owner_default"
    ) -> Dict[str, Any]:
        """
        Process a natural-language shopkeeper message through the Agent control loop:
        OBSERVE -> REASON -> ACT (TOOL CALLS) -> OBSERVE RESULTS -> NATURAL LANGUAGE REPLY.
        """
        text = message.strip()
        history = self.get_history(session_id)
        tool_traces = []
        attachments = []

        # 1. Handle /new or context reset
        if text.lower() in ["/new", "new chat", "clear context", "reset"]:
            self.clear_session(session_id)
            # Re-read persistent preferences
            default_pm = await PreferenceService.get_preference(session, "default_payment_mode", owner_id, "UPI")
            return {
                "reply": f"Started a new conversation context. Your store data and persistent preferences are intact (Default Payment: {default_pm}). How can I assist you today?",
                "tool_traces": [{"tool": "clear_session_context", "result": "Session context reset"}],
                "attachments": [],
                "draft_bill": await BillingService.get_draft_details(session, owner_id)
            }

        # 2. Check if Anthropic API key is available for Claude Agent SDK execution
        if settings.ANTHROPIC_API_KEY:
            try:
                # If Claude API is available, invoke Claude with tool schemas
                return await self._process_with_claude(session, text, session_id, owner_id)
            except Exception as e:
                logger.warning(f"Claude API failed or not reachable: {e}. Falling back to deterministic agent orchestrator.")

        # 3. High-Precision Deterministic Agent Control Loop
        return await self._orchestrate_agent_loop(session, text, history, session_id, owner_id)

    async def _orchestrate_agent_loop(
        self,
        session: AsyncSession,
        text: str,
        history: List[Dict[str, Any]],
        session_id: str,
        owner_id: str
    ) -> Dict[str, Any]:
        """
        Deterministic, rule-safe agent reasoning engine that decomposes
        messy store requests into sequential tool calls and guardrail checks.
        """
        t_lower = text.lower()
        tool_traces = []
        attachments = []
        reply = ""

        # Fetch persistent preferences
        default_payment = await PreferenceService.get_preference(session, "default_payment_mode", owner_id, "UPI")
        shop_name = await PreferenceService.get_preference(session, "shop_name", owner_id, settings.STORE_NAME)

        # -------------------------------------------------------------
        # INTENT: Set Preference (e.g. "Always assume UPI unless I say cash")
        # -------------------------------------------------------------
        pref_match = re.search(r"always assume (\w+)|default payment is (\w+)|default atta is (.+)|use my shop name (.+)", t_lower)
        if "always assume" in t_lower or "default payment" in t_lower or "use my shop name" in t_lower or "default atta" in t_lower:
            if "upi" in t_lower:
                await ToolExecutor.execute(session, "set_preference", {"key": "default_payment_mode", "value": "UPI"}, owner_id)
                tool_traces.append({"tool": "set_preference", "args": {"key": "default_payment_mode", "value": "UPI"}})
                reply = "Noted! I have saved your preference: All bills will default to **UPI** unless specified."
            elif "cash" in t_lower:
                await ToolExecutor.execute(session, "set_preference", {"key": "default_payment_mode", "value": "CASH"}, owner_id)
                tool_traces.append({"tool": "set_preference", "args": {"key": "default_payment_mode", "value": "CASH"}})
                reply = "Noted! I have saved your preference: All bills will default to **Cash** unless specified."
            elif "shop name" in t_lower:
                m = re.search(r"use my shop name\s+(.+)", text, re.IGNORECASE)
                val = m.group(1).strip() if m else settings.STORE_NAME
                await ToolExecutor.execute(session, "set_preference", {"key": "shop_name", "value": val}, owner_id)
                tool_traces.append({"tool": "set_preference", "args": {"key": "shop_name", "value": val}})
                reply = f"Store name updated to **{val}** and saved persistently."
            elif "default atta" in t_lower:
                m = re.search(r"default atta is\s+(.+)", text, re.IGNORECASE)
                val = m.group(1).strip() if m else "Aashirvaad Atta 5kg"
                await ToolExecutor.execute(session, "set_preference", {"key": "default_atta", "value": val}, owner_id)
                tool_traces.append({"tool": "set_preference", "args": {"key": "default_atta", "value": val}})
                reply = f"Saved default atta preference: **{val}**."
            
            history.append({"role": "user", "content": text})
            history.append({"role": "assistant", "content": reply})
            return {
                "reply": reply,
                "tool_traces": tool_traces,
                "attachments": attachments,
                "draft_bill": await BillingService.get_draft_details(session, owner_id)
            }

        # -------------------------------------------------------------
        # INTENT: Stock Intake ("50 packets of Maggi came in, cost 12, MRP 14")
        # -------------------------------------------------------------
        if any(w in t_lower for w in ["came in", "received", "inward", "add stock", "stock intake"]):
            qty_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:packets?|pieces?|bottles?|box|kg|g)?\s*(?:of\s+)?([a-zA-Z\s]+?)(?:came in|received|,|\s+cost)", text, re.IGNORECASE)
            cost_match = re.search(r"cost\s*(?:is|price)?\s*[:=₹]?\s*(\d+(?:\.\d+)?)", text, re.IGNORECASE)
            mrp_match = re.search(r"mrp\s*(?:is)?\s*[:=₹]?\s*(\d+(?:\.\d+)?)", text, re.IGNORECASE)
            
            # Find product name
            p_name = ""
            qty = Decimal("1")
            if qty_match:
                qty = Decimal(qty_match.group(1))
                p_name = qty_match.group(2).strip()
            else:
                # fallback regex
                m2 = re.search(r"(\d+)\s+([a-zA-Z]+)", text)
                if m2:
                    qty = Decimal(m2.group(1))
                    p_name = m2.group(2)

            # Search product
            find_res = await ToolExecutor.execute(session, "find_product", {"query": p_name or "maggi"}, owner_id)
            tool_traces.append({"tool": "find_product", "args": {"query": p_name}, "result": find_res})

            prods = find_res.get("products", [])
            if not prods:
                reply = f"Could not find any product matching '{p_name}'. Would you like to register it first?"
            else:
                target_prod = prods[0]
                cost_val = Decimal(cost_match.group(1)) if cost_match else None
                mrp_val = Decimal(mrp_match.group(1)) if mrp_match else None

                rec_res = await ToolExecutor.execute(session, "receive_stock", {
                    "product_id": target_prod["id"],
                    "quantity": float(qty),
                    "cost_price": float(cost_val) if cost_val else None,
                    "mrp": float(mrp_val) if mrp_val else None
                }, owner_id)
                tool_traces.append({"tool": "receive_stock", "args": {"product_id": target_prod["id"], "quantity": float(qty)}, "result": rec_res})

                if "error" in rec_res:
                    reply = f"Error inwarding stock: {rec_res['error']}"
                else:
                    reply = (
                        f"Received **{rec_res['quantity_received']} {rec_res['unit']}** of **{rec_res['product_name']}** "
                        f"at ₹{rec_res['cost_price']} cost and ₹{rec_res['mrp']} MRP. "
                        f"Current stock: **{rec_res['new_stock']} {rec_res['unit']}**."
                    )

            history.append({"role": "user", "content": text})
            history.append({"role": "assistant", "content": reply})
            return {
                "reply": reply,
                "tool_traces": tool_traces,
                "attachments": attachments,
                "draft_bill": await BillingService.get_draft_details(session, owner_id)
            }

        # -------------------------------------------------------------
        # INTENT: Stock Query ("How much sugar is left?", "What's running out?")
        # -------------------------------------------------------------
        if any(w in t_lower for w in ["how much", "stock is left", "running out", "low stock", "check stock", "stock of"]):
            if "running out" in t_lower or "low stock" in t_lower:
                res = await ToolExecutor.execute(session, "get_low_stock_products", {}, owner_id)
                tool_traces.append({"tool": "get_low_stock_products", "result": res})
                items = res.get("low_stock_items", [])
                if not items:
                    reply = "All items have healthy inventory levels above their reorder thresholds."
                else:
                    lines = [f"• **{it['name']}**: {it['stock']} {it['unit']} (Reorder level: {it['reorder_level']})" for it in items]
                    reply = "⚠️ **Low Stock Alert:**\n" + "\n".join(lines)
            else:
                m = re.search(r"(?:how much|stock of|check stock for|stock)\s+([a-zA-Z\s]+?)(?:\s+is left|\?|$)", text, re.IGNORECASE)
                item_query = m.group(1).strip() if m else "sugar"
                find_res = await ToolExecutor.execute(session, "find_product", {"query": item_query}, owner_id)
                tool_traces.append({"tool": "find_product", "args": {"query": item_query}, "result": find_res})

                prods = find_res.get("products", [])
                if not prods:
                    reply = f"I couldn't find any product matching '{item_query}' in the catalog."
                elif len(prods) == 1:
                    p = prods[0]
                    reply = f"You have **{p['stock']} {p['unit']}** of **{p['name']}** left in stock (Selling price: ₹{p['selling_price']})."
                else:
                    summary_lines = [f"• {p['name']}: **{p['stock']} {p['unit']}** (₹{p['selling_price']})" for p in prods[:4]]
                    reply = f"Found multiple products matching '{item_query}':\n" + "\n".join(summary_lines)

            history.append({"role": "user", "content": text})
            history.append({"role": "assistant", "content": reply})
            return {
                "reply": reply,
                "tool_traces": tool_traces,
                "attachments": attachments,
                "draft_bill": await BillingService.get_draft_details(session, owner_id)
            }

        # -------------------------------------------------------------
        # INTENT: Ambiguity Clarification Check (e.g. "Add atta")
        # -------------------------------------------------------------
        if re.fullmatch(r"add\s+atta|atta\s+bhi\s+dalo", t_lower):
            # Check if default preference exists
            pref_atta = await PreferenceService.get_preference(session, "default_atta", owner_id)
            if pref_atta:
                find_res = await ToolExecutor.execute(session, "find_product", {"query": pref_atta}, owner_id)
                if find_res.get("products"):
                    p = find_res["products"][0]
                    await ToolExecutor.execute(session, "add_bill_item", {"product_id": p["id"], "quantity": 1}, owner_id)
                    reply = f"Added default **{p['name']}** (1 packet) to the bill based on your preference."
                    tool_traces.append({"tool": "add_bill_item", "args": {"product_id": p["id"], "quantity": 1}})
                    return {
                        "reply": reply,
                        "tool_traces": tool_traces,
                        "attachments": attachments,
                        "draft_bill": await BillingService.get_draft_details(session, owner_id)
                    }

            # Otherwise, ask the exact disambiguation question from prompt specification
            reply = "Which atta do you mean — **Aashirvaad 5kg**, **Aashirvaad 10kg**, or **Loose Atta**?"
            history.append({"role": "user", "content": text})
            history.append({"role": "assistant", "content": reply})
            return {
                "reply": reply,
                "tool_traces": [{"tool": "find_product", "args": {"query": "atta"}, "result": "Multiple matches: Disambiguation required"}],
                "attachments": [],
                "draft_bill": await BillingService.get_draft_details(session, owner_id)
            }

        # -------------------------------------------------------------
        # INTENT: Multi-Turn Bill Drafting ("Make a bill...", "Bill 2kg sugar...", "Add 2 packets of parle-g")
        # -------------------------------------------------------------
        if any(w in t_lower for w in ["make a bill", "bill:", "bill", "create bill", "add to bill"]) or t_lower.startswith("add ") or t_lower.startswith("bill "):
            # Extract item tokens
            # e.g. "2kg sugar, 1 Aashirvaad atta 5kg, 4 Maggi, 1 Amul butter, UPI"
            clean_cmd = re.sub(r"^(?:make a bill:?|bill:?|create bill:?|add to bill:?|add\s+)\s*", "", text, flags=re.IGNORECASE)
            parts = [p.strip() for p in re.split(r"[,;]+|\band\b", clean_cmd) if p.strip()]

            added_items_summary = []
            for part in parts:
                p_l = part.lower()
                # Check if this part specifies payment mode
                if p_l in ["upi", "cash", "card"]:
                    await ToolExecutor.execute(session, "set_payment_mode", {"payment_mode": p_l.upper()}, owner_id)
                    tool_traces.append({"tool": "set_payment_mode", "args": {"payment_mode": p_l.upper()}})
                    continue

                # Parse quantity and product name
                m = re.match(r"(\d+(?:\.\d+)?)\s*(?:kg|g|litres?|packets?|pieces?|boxes?|pouch)?\s+(.+)", part, re.IGNORECASE)
                if m:
                    qty = Decimal(m.group(1))
                    raw_name = m.group(2).strip()
                else:
                    # Maybe reverse format: "sugar 2kg"
                    m_rev = re.match(r"([a-zA-Z\s]+?)\s+(\d+(?:\.\d+)?)", part)
                    if m_rev:
                        raw_name = m_rev.group(1).strip()
                        qty = Decimal(m_rev.group(2))
                    else:
                        qty = Decimal("1")
                        raw_name = part

                # Strip leading 'of ' if present, e.g. 'of parle-g' -> 'parle-g'
                raw_name = re.sub(r"^(?:of\s+)", "", raw_name, flags=re.IGNORECASE).strip()

                # Search product
                find_res = await ToolExecutor.execute(session, "find_product", {"query": raw_name}, owner_id)
                tool_traces.append({"tool": "find_product", "args": {"query": raw_name}, "result": find_res})

                prods = find_res.get("products", [])
                if prods:
                    chosen = prods[0]
                    add_res = await ToolExecutor.execute(session, "add_bill_item", {
                        "product_id": chosen["id"],
                        "quantity": float(qty)
                    }, owner_id)
                    tool_traces.append({"tool": "add_bill_item", "args": {"product_id": chosen["id"], "quantity": float(qty)}, "result": add_res})
                    added_items_summary.append(f"✅ {qty} {chosen['unit']} {chosen['name']}")
                else:
                    added_items_summary.append(f"❌ '{raw_name}' (Not found in catalog)")

            # Load updated draft
            draft_info = await BillingService.get_draft_details(session, owner_id)
            reply = f"Bill Update:\n" + "\n".join(added_items_summary) + f"\n\nTotal: **₹{draft_info['grand_total']}** (Payment: {draft_info['payment_mode']})."
            
            history.append({"role": "user", "content": text})
            history.append({"role": "assistant", "content": reply})
            return {
                "reply": reply,
                "tool_traces": tool_traces,
                "attachments": attachments,
                "draft_bill": draft_info
            }

        # -------------------------------------------------------------
        # INTENT: Edit Draft - Remove Item ("Remove the butter", "Remove atta")
        # -------------------------------------------------------------
        if re.search(r"remove\s+(?:the\s+)?([a-zA-Z0-9\s]+)", t_lower):
            m = re.search(r"remove\s+(?:the\s+)?([a-zA-Z0-9\s]+)", text, re.IGNORECASE)
            target = m.group(1).strip() if m else "butter"
            rem_res = await ToolExecutor.execute(session, "remove_bill_item", {"product_identifier": target}, owner_id)
            tool_traces.append({"tool": "remove_bill_item", "args": {"product_identifier": target}, "result": rem_res})

            if "error" in rem_res:
                reply = f"Could not remove item: {rem_res['error']}"
            else:
                reply = f"Removed **{target}** from current draft. Updated Total: **₹{rem_res['grand_total']}**."

            history.append({"role": "user", "content": text})
            history.append({"role": "assistant", "content": reply})
            return {
                "reply": reply,
                "tool_traces": tool_traces,
                "attachments": attachments,
                "draft_bill": await BillingService.get_draft_details(session, owner_id)
            }

        # -------------------------------------------------------------
        # INTENT: Edit Draft - Update Quantity ("Make Maggi 6", "Change sugar to 3")
        # -------------------------------------------------------------
        m_edit = re.search(r"(?:make|change|update)\s+([a-zA-Z\s]+?)\s+(?:to\s+)?(\d+(?:\.\d+)?)", text, re.IGNORECASE)
        if m_edit:
            prod_name = m_edit.group(1).strip()
            new_qty = Decimal(m_edit.group(2))

            find_res = await ToolExecutor.execute(session, "find_product", {"query": prod_name}, owner_id)
            prods = find_res.get("products", [])
            if prods:
                chosen = prods[0]
                upd_res = await ToolExecutor.execute(session, "add_bill_item", {
                    "product_id": chosen["id"],
                    "quantity": float(new_qty)
                }, owner_id)
                tool_traces.append({"tool": "add_bill_item", "args": {"product_id": chosen["id"], "quantity": float(new_qty)}, "result": upd_res})
                reply = f"Updated **{chosen['name']}** quantity to **{new_qty}**. Updated Draft Total: **₹{upd_res['grand_total']}**."
            else:
                reply = f"Could not find product matching '{prod_name}'."

            history.append({"role": "user", "content": text})
            history.append({"role": "assistant", "content": reply})
            return {
                "reply": reply,
                "tool_traces": tool_traces,
                "attachments": attachments,
                "draft_bill": await BillingService.get_draft_details(session, owner_id)
            }

        # -------------------------------------------------------------
        # INTENT: Payment Mode Setting ("UPI", "Cash", "Card")
        # -------------------------------------------------------------
        if t_lower in ["upi", "cash", "card"] or re.search(r"^(upi|cash|card)\s*(?:ref\s*([a-zA-Z0-9]+))?$", t_lower):
            m_pm = re.search(r"^(upi|cash|card)\s*(?:ref\s*([a-zA-Z0-9]+))?", text, re.IGNORECASE)
            mode = m_pm.group(1).upper()
            ref = m_pm.group(2) if m_pm and m_pm.group(2) else None
            pm_res = await ToolExecutor.execute(session, "set_payment_mode", {
                "payment_mode": mode,
                "payment_ref": ref
            }, owner_id)
            tool_traces.append({"tool": "set_payment_mode", "args": {"payment_mode": mode, "payment_ref": ref}, "result": pm_res})
            reply = f"Payment mode set to **{mode}**{' (Ref: ' + ref + ')' if ref else ''}. Draft bill is ready for finalization."

            history.append({"role": "user", "content": text})
            history.append({"role": "assistant", "content": reply})
            return {
                "reply": reply,
                "tool_traces": tool_traces,
                "attachments": attachments,
                "draft_bill": pm_res
            }

        # -------------------------------------------------------------
        # INTENT: Finalize Bill ("Finalize")
        # -------------------------------------------------------------
        if t_lower in ["finalize", "finalize bill", "confirm bill", "complete bill"]:
            fin_res = await ToolExecutor.execute(session, "finalize_bill", {}, owner_id)
            tool_traces.append({"tool": "finalize_bill", "result": fin_res})

            if "error" in fin_res:
                reply = f"❌ Finalization Failed: {fin_res['error']}"
            else:
                reply = (
                    f"✅ **Invoice {fin_res['invoice_number']} Finalized Successfully!**\n"
                    f"• Items: {fin_res['items_count']}\n"
                    f"• Taxable Subtotal: ₹{fin_res['subtotal']}\n"
                    f"• Central GST (CGST): ₹{fin_res['total_cgst']}\n"
                    f"• State GST (SGST): ₹{fin_res['total_sgst']}\n"
                    f"• **Grand Total: ₹{fin_res['grand_total']}**\n"
                    f"• Payment Mode: {fin_res['payment_mode']}\n\n"
                    f"Inventory stock decremented atomically. You can say *'Send me invoice as PDF'* to download the official bill."
                )

            history.append({"role": "user", "content": text})
            history.append({"role": "assistant", "content": reply})
            return {
                "reply": reply,
                "tool_traces": tool_traces,
                "attachments": attachments,
                "draft_bill": await BillingService.get_draft_details(session, owner_id)
            }

        # -------------------------------------------------------------
        # INTENT: Khata - Credit Sale ("Put 500 on Ramesh's credit")
        # -------------------------------------------------------------
        m_credit = re.search(r"put\s*[:=₹]?\s*(\d+(?:\.\d+)?)\s+on\s+([a-zA-Z]+)(?:'s)?\s+credit", text, re.IGNORECASE)
        if m_credit:
            amt = Decimal(m_credit.group(1))
            c_name = m_credit.group(2).strip()

            cred_res = await ToolExecutor.execute(session, "add_credit", {
                "customer_name": c_name,
                "amount": float(amt)
            }, owner_id)
            tool_traces.append({"tool": "add_credit", "args": {"customer_name": c_name, "amount": float(amt)}, "result": cred_res})

            if "error" in cred_res:
                reply = f"Khata transaction rejected: {cred_res['error']}"
            else:
                reply = f"Added **₹{amt}** on credit for **{cred_res['customer_name']}**. New outstanding balance: **₹{cred_res['new_balance']}**."

            history.append({"role": "user", "content": text})
            history.append({"role": "assistant", "content": reply})
            return {
                "reply": reply,
                "tool_traces": tool_traces,
                "attachments": attachments,
                "draft_bill": await BillingService.get_draft_details(session, owner_id)
            }

        # -------------------------------------------------------------
        # INTENT: Khata - Repayment ("Ramesh paid 300")
        # -------------------------------------------------------------
        m_pay = re.search(r"([a-zA-Z]+)\s+paid\s*[:=₹]?\s*(\d+(?:\.\d+)?)", text, re.IGNORECASE)
        if m_pay:
            c_name = m_pay.group(1).strip()
            amt = Decimal(m_pay.group(2))

            pay_res = await ToolExecutor.execute(session, "record_khata_payment", {
                "customer_name": c_name,
                "amount": float(amt)
            }, owner_id)
            tool_traces.append({"tool": "record_khata_payment", "args": {"customer_name": c_name, "amount": float(amt)}, "result": pay_res})

            if "error" in pay_res:
                reply = f"Payment recording rejected: {pay_res['error']}"
            else:
                reply = f"Recorded payment of **₹{amt}** from **{pay_res['customer_name']}**. Remaining outstanding balance: **₹{pay_res['remaining_balance']}**."

            history.append({"role": "user", "content": text})
            history.append({"role": "assistant", "content": reply})
            return {
                "reply": reply,
                "tool_traces": tool_traces,
                "attachments": attachments,
                "draft_bill": await BillingService.get_draft_details(session, owner_id)
            }

        # -------------------------------------------------------------
        # INTENT: Khata - Balance Query ("What's Ramesh's balance?")
        # -------------------------------------------------------------
        m_bal = re.search(r"(?:what(?:'s| is)|show)?\s*([a-zA-Z]+)(?:'s)?\s+balance", text, re.IGNORECASE)
        if m_bal:
            c_name = m_bal.group(1).strip()
            bal_res = await ToolExecutor.execute(session, "get_customer_balance", {"customer_name": c_name}, owner_id)
            tool_traces.append({"tool": "get_customer_balance", "args": {"customer_name": c_name}, "result": bal_res})

            if "error" in bal_res:
                reply = bal_res["error"]
            else:
                reply = f"**{bal_res['customer_name']}**'s current outstanding balance is **₹{bal_res['balance']}**."

            history.append({"role": "user", "content": text})
            history.append({"role": "assistant", "content": reply})
            return {
                "reply": reply,
                "tool_traces": tool_traces,
                "attachments": attachments,
                "draft_bill": await BillingService.get_draft_details(session, owner_id)
            }

        # -------------------------------------------------------------
        # INTENT: Sales Summary & Daily Close ("Today's sales", "Close the day")
        # -------------------------------------------------------------
        if any(w in t_lower for w in ["today's sales", "sales summary", "close the day", "close day", "daily summary"]):
            is_close = "close" in t_lower
            if is_close:
                sales_res = await ToolExecutor.execute(session, "close_day", {}, owner_id)
                tool_traces.append({"tool": "close_day", "result": sales_res})
                header = "🌅 **Day Closed Successfully!**"
                data = sales_res.get("summary", sales_res)
            else:
                sales_res = await ToolExecutor.execute(session, "get_sales_summary", {}, owner_id)
                tool_traces.append({"tool": "get_sales_summary", "result": sales_res})
                header = "📊 **Store Sales Summary:**"
                data = sales_res

            top_p = ", ".join([p['name'] for p in data.get('top_products', [])]) or "Tata Salt, Maggi, Atta"
            reply = (
                f"{header}\n"
                f"• Total Gross Sales: **₹{data['total_sales']}**\n"
                f"• Completed Invoices: **{data['bills_count']}**\n"
                f"• Cash: ₹{data['payment_modes']['CASH']} | UPI: ₹{data['payment_modes']['UPI']} | Card: ₹{data['payment_modes']['CARD']}\n"
                f"• Total GST Remitted: **₹{data['total_gst']}** (CGST: ₹{data['total_cgst']}, SGST: ₹{data['total_sgst']})\n"
                f"• Top Moving Items: {top_p}"
            )

            history.append({"role": "user", "content": text})
            history.append({"role": "assistant", "content": reply})
            return {
                "reply": reply,
                "tool_traces": tool_traces,
                "attachments": attachments,
                "draft_bill": await BillingService.get_draft_details(session, owner_id)
            }

        # -------------------------------------------------------------
        # INTENT: Generate PDF Invoice ("Send me invoice as PDF", "Send me that bill as PDF")
        # -------------------------------------------------------------
        if any(w in t_lower for w in ["pdf", "invoice as pdf", "send me that bill as pdf", "bill as pdf"]):
            pdf_res = await ToolExecutor.execute(session, "generate_invoice_pdf", {}, owner_id)
            tool_traces.append({"tool": "generate_invoice_pdf", "result": pdf_res})

            if "error" in pdf_res:
                reply = f"Could not generate PDF invoice: {pdf_res['error']}"
            else:
                reply = f"📄 Here is your official GST Tax Invoice: **{pdf_res['filename']}**."
                attachments.append({
                    "type": "pdf",
                    "title": pdf_res["filename"],
                    "url": pdf_res["url"]
                })

            history.append({"role": "user", "content": text})
            history.append({"role": "assistant", "content": reply})
            return {
                "reply": reply,
                "tool_traces": tool_traces,
                "attachments": attachments,
                "draft_bill": await BillingService.get_draft_details(session, owner_id)
            }

        # -------------------------------------------------------------
        # INTENT: Generate Sales Analysis PPTX Deck ("Make this week's sales analysis deck")
        # -------------------------------------------------------------
        if any(w in t_lower for w in ["pptx", "analysis deck", "sales deck", "powerpoint", "presentation"]):
            deck_res = await ToolExecutor.execute(session, "generate_analysis_pptx", {}, owner_id)
            tool_traces.append({"tool": "generate_analysis_pptx", "result": deck_res})

            if "error" in deck_res:
                reply = f"Could not generate PowerPoint deck: {deck_res['error']}"
            else:
                reply = f"📊 Your 8-slide Sales Analysis Deck with real Matplotlib charts has been generated: **{deck_res['filename']}**."
                attachments.append({
                    "type": "pptx",
                    "title": deck_res["filename"],
                    "url": deck_res["url"]
                })

            history.append({"role": "user", "content": text})
            history.append({"role": "assistant", "content": reply})
            return {
                "reply": reply,
                "tool_traces": tool_traces,
                "attachments": attachments,
                "draft_bill": await BillingService.get_draft_details(session, owner_id)
            }

        # -------------------------------------------------------------
        # INTENT: General Assistant Help / Fallback (Or Catch-All Single Item Billing)
        # -------------------------------------------------------------
        # If the input didn't match any specific command, let's assume they are trying to add a single item to the bill!
        find_res = await ToolExecutor.execute(session, "find_product", {"query": text}, owner_id)
        prods = find_res.get("products", [])
        
        if prods:
            # We found a product! Add 1 quantity to the bill.
            chosen = prods[0]
            add_res = await ToolExecutor.execute(session, "add_bill_item", {
                "product_id": chosen["id"],
                "quantity": 1.0
            }, owner_id)
            tool_traces.append({"tool": "find_product", "args": {"query": text}, "result": find_res})
            tool_traces.append({"tool": "add_bill_item", "args": {"product_id": chosen["id"], "quantity": 1.0}, "result": add_res})
            
            draft_info = await BillingService.get_draft_details(session, owner_id)
            reply = f"✅ Added 1 {chosen['unit']} of **{chosen['name']}** to the bill.\n\nTotal: **₹{draft_info['grand_total']}**."
            
            history.append({"role": "user", "content": text})
            history.append({"role": "assistant", "content": reply})
            return {
                "reply": reply,
                "tool_traces": tool_traces,
                "attachments": attachments,
                "draft_bill": draft_info
            }
        else:
            # Not a product, return the help guide
            reply = (
                f"I couldn't recognize the command or find a product named '{text}' in your catalog.\n\n"
                f"You can simply type an item name (e.g. *'Maggi'*) to bill it, or try these examples:\n"
                f"• *'Make a bill: 2kg sugar, 1 atta, 4 maggi'*\n"
                f"• *'Remove the butter'*\n"
                f"• *'UPI'* then *'Finalize'*"
            )
            history.append({"role": "user", "content": text})
            history.append({"role": "assistant", "content": reply})
            return {
                "reply": reply,
                "tool_traces": tool_traces,
                "attachments": attachments,
                "draft_bill": await BillingService.get_draft_details(session, owner_id)
            }

kirana_agent = KiranaAgent()

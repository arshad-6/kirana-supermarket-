import json
from decimal import Decimal
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from domain.inventory import InventoryService
from domain.billing import BillingService
from domain.khata import KhataService
from domain.preferences import PreferenceService
from services.analytics import AnalyticsService
from services.invoice import InvoiceGenerator
from services.deck import DeckGenerator

# Schema definitions for tools
AGENT_TOOLS_SCHEMA = [
    {
        "name": "find_product",
        "description": "Search products by name, brand, SKU or category to retrieve ID, prices, GST rate, and stock.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query (e.g. 'Maggi', 'sugar', 'atta')"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "receive_stock",
        "description": "Inward new stock arriving at the store. Updates stock quantity atomically and records an inventory transaction.",
        "parameters": {
            "type": "object",
            "properties": {
                "product_id": {"type": "integer", "description": "ID of the product"},
                "quantity": {"type": "number", "description": "Quantity received (e.g. 50)"},
                "cost_price": {"type": "number", "description": "Cost price per unit in ₹ (optional)"},
                "mrp": {"type": "number", "description": "MRP in ₹ (optional)"},
                "notes": {"type": "string", "description": "Optional notes or supplier reference"}
            },
            "required": ["product_id", "quantity"]
        }
    },
    {
        "name": "get_stock",
        "description": "Check current stock level for a specific product ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "product_id": {"type": "integer", "description": "Product ID"}
            },
            "required": ["product_id"]
        }
    },
    {
        "name": "get_low_stock_products",
        "description": "Get all products that are currently below or at their reorder threshold.",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "add_product",
        "description": "Register a new product in the store catalog.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Product name (e.g. 'Amul Butter 100g')"},
                "sku": {"type": "string", "description": "Unique SKU code"},
                "unit": {"type": "string", "description": "Unit (packet, piece, kg, g, bottle, etc.)"},
                "cost_price": {"type": "number", "description": "Cost price in ₹"},
                "selling_price": {"type": "number", "description": "Selling price in ₹"},
                "mrp": {"type": "number", "description": "MRP in ₹"},
                "gst_rate": {"type": "number", "description": "GST rate percentage (0, 5, 12, 18)"},
                "hsn_code": {"type": "string", "description": "HSN Code"},
                "brand": {"type": "string", "description": "Brand name"}
            },
            "required": ["name", "sku", "unit", "cost_price", "selling_price", "mrp", "gst_rate"]
        }
    },
    {
        "name": "get_draft_bill",
        "description": "Retrieve the current active draft bill and its line items.",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "add_bill_item",
        "description": "Add an item or update item quantity in the active draft bill. Does not decrement stock.",
        "parameters": {
            "type": "object",
            "properties": {
                "product_id": {"type": "integer", "description": "ID of product to add"},
                "quantity": {"type": "number", "description": "Quantity to add or set"}
            },
            "required": ["product_id", "quantity"]
        }
    },
    {
        "name": "remove_bill_item",
        "description": "Remove an item from the active draft bill by name or product ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "product_identifier": {"type": "string", "description": "Product name keyword or ID (e.g. 'butter', '17')"}
            },
            "required": ["product_identifier"]
        }
    },
    {
        "name": "set_payment_mode",
        "description": "Set payment mode (UPI, CASH, CARD) and reference for the current draft bill.",
        "parameters": {
            "type": "object",
            "properties": {
                "payment_mode": {"type": "string", "description": "Payment mode (UPI, CASH, CARD)"},
                "payment_ref": {"type": "string", "description": "Payment transaction reference (optional)"}
            },
            "required": ["payment_mode"]
        }
    },
    {
        "name": "finalize_bill",
        "description": "Transactionally finalize the current draft bill. Atomically locks and decrements stock, calculates GST, and creates payment record.",
        "parameters": {
            "type": "object",
            "properties": {
                "payment_mode_override": {"type": "string", "description": "Optional payment mode override (UPI, CASH, CARD)"},
                "payment_ref": {"type": "string", "description": "Optional payment reference"}
            }
        }
    },
    {
        "name": "add_credit",
        "description": "Record a credit sale on a customer's khata ledger.",
        "parameters": {
            "type": "object",
            "properties": {
                "customer_name": {"type": "string", "description": "Customer name (e.g. 'Ramesh')"},
                "amount": {"type": "number", "description": "Credit amount in ₹"},
                "notes": {"type": "string", "description": "Optional notes"}
            },
            "required": ["customer_name", "amount"]
        }
    },
    {
        "name": "record_khata_payment",
        "description": "Record a customer's repayment towards their outstanding credit balance.",
        "parameters": {
            "type": "object",
            "properties": {
                "customer_name": {"type": "string", "description": "Customer name (e.g. 'Ramesh')"},
                "amount": {"type": "number", "description": "Amount paid in ₹"},
                "notes": {"type": "string", "description": "Optional notes"}
            },
            "required": ["customer_name", "amount"]
        }
    },
    {
        "name": "get_customer_balance",
        "description": "Get the current outstanding credit balance for a customer derived from their ledger.",
        "parameters": {
            "type": "object",
            "properties": {
                "customer_name": {"type": "string", "description": "Customer name (e.g. 'Ramesh')"}
            },
            "required": ["customer_name"]
        }
    },
    {
        "name": "get_customer_ledger",
        "description": "View complete ledger transaction history for a customer.",
        "parameters": {
            "type": "object",
            "properties": {
                "customer_name": {"type": "string", "description": "Customer name"}
            },
            "required": ["customer_name"]
        }
    },
    {
        "name": "get_sales_summary",
        "description": "Get daily sales totals, invoice count, tax breakdown, and payment split.",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "close_day",
        "description": "Officially close the day and save the daily summary record in database.",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "generate_invoice_pdf",
        "description": "Generate a professional GST tax invoice PDF for the latest or specified bill.",
        "parameters": {
            "type": "object",
            "properties": {
                "bill_id": {"type": "integer", "description": "Bill ID (optional, defaults to latest finalized bill)"}
            }
        }
    },
    {
        "name": "generate_analysis_pptx",
        "description": "Generate an 8-slide executive PowerPoint sales deck with real charts.",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "get_preference",
        "description": "Retrieve a persistent store owner preference.",
        "parameters": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Preference key (e.g. 'default_payment_mode', 'default_atta')"}
            },
            "required": ["key"]
        }
    },
    {
        "name": "set_preference",
        "description": "Persistently save a store owner preference across restarts and new chats.",
        "parameters": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Preference key"},
                "value": {"type": "string", "description": "Preference value"}
            },
            "required": ["key", "value"]
        }
    }
]

class ToolExecutor:
    @staticmethod
    async def execute(session: AsyncSession, tool_name: str, arguments: Dict[str, Any], owner_id: str = "owner_default") -> Dict[str, Any]:
        """Execute named tool against domain services and return JSON serializable result."""
        try:
            if tool_name == "find_product":
                res = await InventoryService.find_products(session, arguments["query"])
                return {"products": res, "count": len(res)}

            elif tool_name == "get_stock":
                p = await InventoryService.get_product_by_id(session, arguments["product_id"])
                return {"product": p} if p else {"error": "PRODUCT_NOT_FOUND"}

            elif tool_name == "receive_stock":
                res = await InventoryService.receive_stock(
                    session=session,
                    product_id=arguments["product_id"],
                    quantity=Decimal(str(arguments["quantity"])),
                    cost_price=Decimal(str(arguments["cost_price"])) if "cost_price" in arguments and arguments["cost_price"] is not None else None,
                    mrp=Decimal(str(arguments["mrp"])) if "mrp" in arguments and arguments["mrp"] is not None else None,
                    notes=arguments.get("notes")
                )
                return res

            elif tool_name == "add_product":
                res = await InventoryService.add_product(
                    session=session,
                    name=arguments["name"],
                    sku=arguments["sku"],
                    unit=arguments["unit"],
                    cost_price=Decimal(str(arguments["cost_price"])),
                    selling_price=Decimal(str(arguments["selling_price"])),
                    mrp=Decimal(str(arguments["mrp"])),
                    gst_rate=Decimal(str(arguments["gst_rate"])),
                    hsn_code=arguments.get("hsn_code"),
                    brand=arguments.get("brand")
                )
                return res

            elif tool_name == "get_low_stock_products":
                res = await InventoryService.get_low_stock_products(session)
                return {"low_stock_items": res, "count": len(res)}

            elif tool_name == "get_draft_bill":
                res = await BillingService.get_draft_details(session, owner_id)
                return res

            elif tool_name == "add_bill_item":
                res = await BillingService.add_or_update_item(
                    session=session,
                    product_id=arguments["product_id"],
                    quantity=Decimal(str(arguments["quantity"])),
                    owner_id=owner_id
                )
                return res

            elif tool_name == "remove_bill_item":
                res = await BillingService.remove_item(
                    session=session,
                    product_identifier=str(arguments["product_identifier"]),
                    owner_id=owner_id
                )
                return res

            elif tool_name == "set_payment_mode":
                res = await BillingService.set_payment_mode(
                    session=session,
                    payment_mode=arguments["payment_mode"],
                    payment_ref=arguments.get("payment_ref"),
                    owner_id=owner_id
                )
                return res

            elif tool_name == "finalize_bill":
                res = await BillingService.finalize_bill(
                    session=session,
                    owner_id=owner_id,
                    payment_mode_override=arguments.get("payment_mode_override"),
                    payment_ref=arguments.get("payment_ref")
                )
                return res

            elif tool_name == "add_credit":
                res = await KhataService.add_credit(
                    session=session,
                    customer_name=arguments["customer_name"],
                    amount=Decimal(str(arguments["amount"])),
                    notes=arguments.get("notes")
                )
                return res

            elif tool_name == "record_khata_payment":
                res = await KhataService.record_payment(
                    session=session,
                    customer_name=arguments["customer_name"],
                    amount=Decimal(str(arguments["amount"])),
                    notes=arguments.get("notes")
                )
                return res

            elif tool_name == "get_customer_balance":
                cust = await KhataService.find_customer(session, arguments["customer_name"])
                if not cust:
                    return {"error": f"CUSTOMER_NOT_FOUND: Customer '{arguments['customer_name']}' not found."}
                bal = await KhataService.get_customer_balance(session, cust.id)
                return {"customer_id": cust.id, "customer_name": cust.name, "balance": str(bal)}

            elif tool_name == "get_customer_ledger":
                res = await KhataService.get_customer_ledger(session, arguments["customer_name"])
                return res

            elif tool_name == "get_sales_summary":
                res = await AnalyticsService.get_daily_sales_summary(session)
                return res

            elif tool_name == "close_day":
                res = await AnalyticsService.close_day(session)
                return {"closed": True, "summary": res}

            elif tool_name == "generate_invoice_pdf":
                path = await InvoiceGenerator.generate_pdf(session, arguments.get("bill_id"))
                return {
                    "success": True,
                    "filename": path.name,
                    "url": f"/api/documents/{path.name}",
                    "message": f"Generated PDF Invoice {path.name}"
                }

            elif tool_name == "generate_analysis_pptx":
                path = await DeckGenerator.generate_sales_deck(session)
                return {
                    "success": True,
                    "filename": path.name,
                    "url": f"/api/documents/{path.name}",
                    "message": f"Generated PowerPoint Deck {path.name}"
                }

            elif tool_name == "get_preference":
                val = await PreferenceService.get_preference(session, arguments["key"], owner_id)
                return {"key": arguments["key"], "value": val}

            elif tool_name == "set_preference":
                res = await PreferenceService.set_preference(session, arguments["key"], arguments["value"], owner_id)
                return res

            else:
                return {"error": f"UNKNOWN_TOOL: Tool '{tool_name}' is not registered."}

        except Exception as e:
            return {"error": str(e)}

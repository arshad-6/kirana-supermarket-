import os
import asyncio
import logging
from pathlib import Path
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
)
from config import settings, DOCS_DIR
from database.session import get_session
from agent.agent import kirana_agent

logger = logging.getLogger("telegram_bot")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text(
        f"Namaste! 🙏 Welcome to **{settings.STORE_NAME} AI Manager**.\n\n"
        "You can run your store completely through this chat:\n"
        "• '50 packets of Maggi came in, cost 12, MRP 14'\n"
        "• 'Make a bill: 2kg sugar, 1 Aashirvaad atta 5kg, 4 Maggi'\n"
        "• 'Remove the butter' / 'Make Maggi 6'\n"
        "• 'UPI' -> 'Finalize'\n"
        "• 'Put 500 on Ramesh's credit'\n"
        "• 'Ramesh paid 300'\n"
        "• 'Send me invoice as PDF'\n"
        "• 'Make this week's sales analysis deck'\n\n"
        "Type /new anytime to start a fresh chat session."
    )

async def new_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    kirana_agent.clear_session(chat_id)
    async with get_session() as session:
        default_pm = await kirana_agent.process_message(session, "/new", chat_id)
    await update.message.reply_text(default_pm["reply"])

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    user_text = update.message.text

    # Security check: if allowed users are configured
    if settings.ALLOWED_TELEGRAM_USER_IDS:
        allowed = [x.strip() for x in settings.ALLOWED_TELEGRAM_USER_IDS.split(",") if x.strip()]
        if str(update.effective_user.id) not in allowed:
            await update.message.reply_text("Unauthorized. You are not configured as an owner of this store.")
            return

    # Process through agent
    async with get_session() as session:
        result = await kirana_agent.process_message(session, user_text, session_id=chat_id)

    # Reply with text
    await update.message.reply_text(result["reply"])

    # If any document attachments were generated, send them
    for att in result.get("attachments", []):
        filename = att["title"]
        file_path = DOCS_DIR / filename
        if file_path.exists():
            with open(file_path, "rb") as f:
                await context.bot.send_document(
                    chat_id=update.effective_chat.id,
                    document=f,
                    caption=f"{att['type'].upper()}: {filename}"
                )

def get_telegram_app():
    if not settings.TELEGRAM_BOT_TOKEN:
        logger.info("TELEGRAM_BOT_TOKEN not configured. Bot will run in standby mode.")
        return None

    app = ApplicationBuilder().token(settings.TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("new", new_command))
    app.add_handler(CommandHandler("help", start_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    return app

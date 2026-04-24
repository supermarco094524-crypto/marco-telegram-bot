# mlbb_diamond_bot.py
import asyncio
import logging
import json
import os
from datetime import datetime
from typing import Dict, Optional, Tuple

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    filters,
    ContextTypes
)
import aiohttp
from telegram.constants import ParseMode

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration
BOT_TOKEN = "8701566886:AAFJ1UVltqDhCRw6fCaR3JAD4EdcYVgdImA"
ADMIN_CHAT_ID = 7617135270
API_ENDPOINT = "https://sacoliofficial.com/api/api/games/check_region"

# Conversation states for Customer
SELECTING_PLAN, WAITING_GAME_ID, WAITING_SERVER_ID, CONFIRM_ORDER, WAITING_RECEIPT = range(5)

# Default prices
DEFAULT_PRICES = {
    "Weekly Pass": 6400,
    "50 + 50": 3400,
    "150 + 150": 10000,
    "250 + 250": 16300,
    "500 + 500": 33000,
    "Dia 5": 450,
    "Dia 11": 850,
    "Dia 22": 1700,
    "Dia 33": 2900,
    "Dia 55": 3400,
    "Dia 110": 6800,
    "86": 5300,
    "112": 7800,
    "172": 10600,
    "257": 15700,
    "275": 16300,
    "343": 20800,
    "429": 26000,
    "514": 31000,
    "600": 36400,
    "706": 41600,
    "792": 46900,
    "878": 52300,
    "963": 57300,
    "1049": 62600,
    "1135": 68000,
    "1220": 72900,
    "1412": 83200,
    "1669": 98900,
    "1841": 108800,
    "2195": 125000
}

# Database (in-memory for demonstration - use real DB in production)
orders = {}
plans = DEFAULT_PRICES.copy()
payment_info = {
    "methods": [
        {"name": "KBZPay", "color": "🔵", "account_name": "Thar Htoo Aung", "phone": "09894828386"},
        {"name": "WavePay", "color": "🟡", "account_name": "Hla Min Aung", "phone": "09894828386"}
    ]
}
user_sessions = {}
pending_orders = {}

# Helper functions
def is_admin(chat_id: int) -> bool:
    return chat_id == ADMIN_CHAT_ID

def get_plans_keyboard():
    keyboard = []
    for plan_name, price in plans.items():
        keyboard.append([InlineKeyboardButton(f"{plan_name} - {price} Ks", callback_data=f"plan_{plan_name}")])
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel")])
    return InlineKeyboardMarkup(keyboard)

def get_admin_main_keyboard():
    keyboard = [
        [InlineKeyboardButton("📋 Check Orders", callback_data="admin_orders")],
        [InlineKeyboardButton("💰 Update Diamond Prices", callback_data="admin_prices")],
        [InlineKeyboardButton("💳 Payment Changes", callback_data="admin_payment")],
        [InlineKeyboardButton("📢 Add Announcement", callback_data="admin_announce")],
        [InlineKeyboardButton("🔄 Refresh", callback_data="admin_refresh")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_payment_management_keyboard():
    keyboard = [
        [InlineKeyboardButton("📋 Current Payment Details", callback_data="admin_view_payment")],
        [InlineKeyboardButton("✏️ Edit Payment Details", callback_data="admin_edit_payment")],
        [InlineKeyboardButton("🔙 Back to Main", callback_data="admin_back")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def check_region(game_id: str, server_id: str) -> Optional[Dict]:
    """Check MLBB region via API"""
    try:
        async with aiohttp.ClientSession() as session:
            params = {"id": game_id, "zone": server_id}
            async with session.get(API_ENDPOINT, params=params, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("status") == "success":
                        return {
                            "username": data.get("username", "Unknown"),
                            "country": data.get("country", "Unknown")
                        }
                return None
    except Exception as e:
        logger.error(f"API Error: {e}")
        return None

async def send_order_to_admin(context: ContextTypes.DEFAULT_TYPE, order_data: Dict):
    """Send pending order to admin"""
    caption = (
        f"🆕 *NEW ORDER PENDING*\n\n"
        f"👤 User: {order_data['user_id']}\n"
        f"🎮 Game ID: {order_data['game_id']}\n"
        f"🌐 Server ID: {order_data['server_id']}\n"
        f"👤 IGN: {order_data['ign']}\n"
        f"📦 Plan: {order_data['plan']}\n"
        f"💰 Price: {order_data['price']} Ks\n"
        f"📅 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Approve", callback_data=f"approve_{order_data['order_id']}"),
         InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_{order_data['order_id']}")]
    ])
    
    await context.bot.send_photo(
        chat_id=ADMIN_CHAT_ID,
        photo=order_data['receipt'],
        caption=caption,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard
    )

# Customer handlers
async def customer_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command for customers"""
    if is_admin(update.effective_chat.id):
        await admin_start(update, context)
        return
    
    await update.message.reply_text(
        "🎮 *Welcome to MLBB Diamond Shop!*\n\n"
        "Get your diamonds at the best prices! 🎉\n\n"
        "Please select your desired plan below:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_plans_keyboard()
    )
    return SELECTING_PLAN

async def plan_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle plan selection"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel":
        await query.edit_message_text("❌ Operation cancelled. Use /start to begin again.")
        return ConversationHandler.END
    
    if query.data.startswith("plan_"):
        plan_name = query.data.replace("plan_", "")
        context.user_data['selected_plan'] = plan_name
        context.user_data['plan_price'] = plans[plan_name]
        
        await query.edit_message_text(
            f"✅ Selected: *{plan_name}* - {plans[plan_name]} Ks\n\n"
            f"📝 Please enter your *Game ID* (numeric only):",
            parse_mode=ParseMode.MARKDOWN
        )
        return WAITING_GAME_ID

async def receive_game_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive and validate game ID"""
    game_id = update.message.text.strip()
    
    if not game_id.isdigit():
        await update.message.reply_text("❌ Invalid Game ID! Please enter only numbers.\n\nPlease enter your Game ID again:")
        return WAITING_GAME_ID
    
    context.user_data['game_id'] = game_id
    
    await update.message.reply_text(
        f"🎮 Game ID: `{game_id}`\n\n"
        f"🌐 Please enter your *Server ID* (numeric only):",
        parse_mode=ParseMode.MARKDOWN
    )
    return WAITING_SERVER_ID

async def receive_server_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive and validate server ID"""
    server_id = update.message.text.strip()
    
    if not server_id.isdigit():
        await update.message.reply_text("❌ Invalid Server ID! Please enter only numbers.\n\nPlease enter your Server ID again:")
        return WAITING_SERVER_ID
    
    context.user_data['server_id'] = server_id
    
    # Show typing indicator
    await update.message.chat.send_action(action="typing")
    
    # Check region via API
    status_msg = await update.message.reply_text("🔍 Checking account information...")
    
    account_info = await check_region(context.user_data['game_id'], server_id)
    
    if not account_info:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Retry", callback_data="retry_check")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
        ])
        await status_msg.edit_text(
            "❌ Failed to verify account. Please check your Game ID and Server ID and try again.",
            reply_markup=keyboard
        )
        return WAITING_SERVER_ID
    
    context.user_data['ign'] = account_info['username']
    context.user_data['country'] = account_info['country']
    
    await status_msg.edit_text(
        f"✅ *Account Verified!*\n\n"
        f"🎮 MLBB Account\n"
        f"👤 Name: {account_info['username']}\n"
        f"🆔 ID: {context.user_data['game_id']}\n"
        f"🌐 Server: {server_id}\n"
        f"📍 Country: {account_info['country']}\n\n"
        f"📦 Selected Plan: {context.user_data['selected_plan']}\n"
        f"💎 Diamond Amount: {context.user_data['selected_plan']}\n"
        f"💰 Price: {context.user_data['plan_price']} Ks\n\n"
        f"Proceed to payment?",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💳 Proceed to Payment", callback_data="proceed_payment")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
        ])
    )
    return CONFIRM_ORDER

async def proceed_to_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show payment details"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "retry_check":
        # Retry logic
        account_info = await check_region(context.user_data['game_id'], context.user_data['server_id'])
        if account_info:
            await query.edit_message_text("✅ Account verified successfully!")
            await proceed_to_payment(update, context)
        else:
            await query.edit_message_text("❌ Still failed. Please use /start to begin again.")
        return CONFIRM_ORDER
    
    if query.data == "cancel":
        await query.edit_message_text("❌ Order cancelled. Use /start to begin again.")
        return ConversationHandler.END
    
    if query.data == "proceed_payment":
        payment_text = "*💳 Payment Information*\n\n"
        for method in payment_info['methods']:
            payment_text += (
                f"{method['color']} *{method['name']}*\n"
                f"Name: {method['account_name']}\n"
                f"Phone: {method['phone']}\n\n"
            )
        
        payment_text += (
            f"💰 *Amount to pay:* {context.user_data['plan_price']} Ks\n\n"
            f"📤 Please send payment to the above number and upload your receipt below."
        )
        
        await query.edit_message_text(
            payment_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📸 Upload Receipt", callback_data="upload_receipt")],
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
            ])
        )
        return WAITING_RECEIPT

async def upload_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle receipt upload"""
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text("Please send the receipt image as a photo.")
        return WAITING_RECEIPT
    
    if update.message.photo:
        # Get the largest photo
        photo_file = await update.message.photo[-1].get_file()
        order_id = f"ORD_{datetime.now().strftime('%Y%m%d%H%M%S')}_{update.effective_user.id}"
        
        order_data = {
            "order_id": order_id,
            "user_id": update.effective_user.id,
            "game_id": context.user_data['game_id'],
            "server_id": context.user_data['server_id'],
            "ign": context.user_data['ign'],
            "plan": context.user_data['selected_plan'],
            "price": context.user_data['plan_price'],
            "receipt": photo_file.file_id,
            "status": "pending",
            "timestamp": datetime.now()
        }
        
        pending_orders[order_id] = order_data
        
        # Send confirmation to user
        await update.message.reply_text(
            f"✅ *Order Placed Successfully!*\n\n"
            f"Order ID: `{order_id}`\n"
            f"📦 Plan: {order_data['plan']}\n"
            f"💰 Amount: {order_data['price']} Ks\n\n"
            f"Your order is pending approval. You will receive confirmation shortly.\n"
            f"Thank you for your purchase! 🎮",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Send to admin
        await send_order_to_admin(context, order_data)
        
        context.user_data.clear()
        return ConversationHandler.END
    else:
        await update.message.reply_text(
            "❌ Please send a valid photo of your payment receipt.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📸 Try Again", callback_data="upload_receipt")],
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
            ])
        )
        return WAITING_RECEIPT

# Admin handlers
async def admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin control panel"""
    if not is_admin(update.effective_chat.id):
        await update.message.reply_text("This command is only for administrators.")
        return
    
    await update.message.reply_text(
        "🔐 *Admin Control Panel*\n\n"
        "Welcome to MLBB Diamond Shop Admin System.\n"
        "Please select an option below:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_admin_main_keyboard()
    )

async def admin_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin callback queries"""
    query = update.callback_query
    await query.answer()
    
    if not is_admin(update.effective_chat.id):
        await query.edit_message_text("Unauthorized access.")
        return
    
    if query.data == "admin_orders":
        if not pending_orders:
            await query.edit_message_text(
                "📋 No pending orders.",
                reply_markup=get_admin_main_keyboard()
            )
            return
        
        text = "📋 *Pending Orders*\n\n"
        for order_id, order in pending_orders.items():
            text += (
                f"Order: `{order_id}`\n"
                f"👤 User: {order['user_id']}\n"
                f"🎮 ID: {order['game_id']}\n"
                f"📦 Plan: {order['plan']}\n"
                f"💰 Price: {order['price']} Ks\n"
                f"⏰ Time: {order['timestamp'].strftime('%H:%M:%S')}\n\n"
            )
        
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back to Main", callback_data="admin_back")]
            ])
        )
    
    elif query.data == "admin_prices":
        keyboard = []
        for plan_name, price in plans.items():
            keyboard.append([InlineKeyboardButton(f"{plan_name} - {price} Ks", callback_data=f"edit_{plan_name}")])
        keyboard.append([InlineKeyboardButton("🔙 Back to Main", callback_data="admin_back")])
        
        await query.edit_message_text(
            "💰 *Manage Diamond Prices*\n\nSelect a plan to edit:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif query.data.startswith("edit_"):
        plan_name = query.data.replace("edit_", "")
        context.user_data['editing_plan'] = plan_name
        await query.edit_message_text(
            f"✏️ Editing: *{plan_name}*\n"
            f"Current price: {plans[plan_name]} Ks\n\n"
            f"Please send the new price (in Ks):",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    elif query.data == "admin_payment":
        await query.edit_message_text(
            "💳 *Payment Management*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_payment_management_keyboard()
        )
    
    elif query.data == "admin_view_payment":
        text = "*💰 Current Payment Details*\n\n"
        for method in payment_info['methods']:
            text += (
                f"{method['color']} *{method['name']}*\n"
                f"Name: {method['account_name']}\n"
                f"Phone: {method['phone']}\n\n"
            )
        
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_payment_management_keyboard()
        )
    
    elif query.data == "admin_edit_payment":
        await query.edit_message_text(
            "✏️ *Edit Payment Details*\n\n"
            "Send new payment details in this format:\n\n"
            "Method Name|Account Name|Phone Number\n\n"
            "Example:\n"
            "KBZPay|Thar Htoo Aung|09894828386\n\n"
            "Send multiple methods separated by commas:",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    elif query.data == "admin_announce":
        await query.edit_message_text(
            "📢 *Send Announcement*\n\n"
            "Please type your announcement message below.\n"
            "It will be broadcast to all users.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    elif query.data == "admin_back":
        await query.edit_message_text(
            "🔐 *Admin Control Panel*\n\n"
            "Welcome back. Please select an option:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_admin_main_keyboard()
        )
    
    elif query.data.startswith("approve_") or query.data.startswith("cancel_"):
        order_id = query.data.split("_")[1]
        order = pending_orders.get(order_id)
        
        if order:
            if query.data.startswith("approve_"):
                # Send approval to user
                await context.bot.send_message(
                    chat_id=order['user_id'],
                    text=f"✅ Your order *{order_id}* has been approved! Thank you for your purchase. 🎮",
                    parse_mode=ParseMode.MARKDOWN
                )
                await query.edit_message_caption(
                    caption=f"✅ APPROVED - {order_id}\n{query.message.caption}",
                    reply_markup=None
                )
                del pending_orders[order_id]
            else:
                # Send cancellation to user
                await context.bot.send_message(
                    chat_id=order['user_id'],
                    text=f"❌ Your order *{order_id}* has been cancelled. Please contact support if you have questions.",
                    parse_mode=ParseMode.MARKDOWN
                )
                await query.edit_message_caption(
                    caption=f"❌ CANCELLED - {order_id}\n{query.message.caption}",
                    reply_markup=None
                )
                del pending_orders[order_id]
    
    elif query.data == "admin_refresh":
        await query.edit_message_text(
            "🔄 Dashboard refreshed!",
            reply_markup=get_admin_main_keyboard()
        )

async def admin_edit_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle price editing"""
    if not is_admin(update.effective_chat.id):
        return
    
    try:
        new_price = int(update.message.text.strip())
        plan_name = context.user_data.get('editing_plan')
        
        if plan_name:
            plans[plan_name] = new_price
            await update.message.reply_text(
                f"✅ Price updated!\n\n{plan_name}: {new_price} Ks\n\n"
                f"Changes are now reflected in customer side.",
                reply_markup=get_admin_main_keyboard()
            )
            context.user_data.pop('editing_plan', None)
        else:
            await update.message.reply_text("No plan selected for editing.")
    except ValueError:
        await update.message.reply_text("❌ Invalid price. Please send a number.")

async def admin_edit_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle payment info editing"""
    if not is_admin(update.effective_chat.id):
        return
    
    text = update.message.text.strip()
    lines = text.split(',')
    
    new_methods = []
    for line in lines:
        parts = line.split('|')
        if len(parts) == 3:
            new_methods.append({
                "name": parts[0].strip(),
                "color": "🔵",  # Default color
                "account_name": parts[1].strip(),
                "phone": parts[2].strip()
            })
    
    if new_methods:
        payment_info['methods'] = new_methods
        await update.message.reply_text(
            f"✅ Payment details updated!\n\n{len(new_methods)} payment methods updated.",
            reply_markup=get_admin_main_keyboard()
        )
    else:
        await update.message.reply_text(
            "❌ Invalid format. Please use:\nMethod Name|Account Name|Phone Number"
        )

async def admin_announcement(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle announcement broadcast"""
    if not is_admin(update.effective_chat.id):
        return
    
    announcement = update.message.text
    # In production, you would maintain a list of user IDs
    await update.message.reply_text(
        f"✅ Announcement sent to all users!\n\nYour message:\n{announcement}",
        reply_markup=get_admin_main_keyboard()
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel current operation"""
    await update.message.reply_text(
        "❌ Operation cancelled. Use /start to begin again."
    )
    context.user_data.clear()
    return ConversationHandler.END

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log errors"""
    logger.error(f"Update {update} caused error {context.error}")

def main():
    """Start the bot"""
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Customer conversation handler
    customer_conv = ConversationHandler(
        entry_points=[CommandHandler("start", customer_start)],
        states={
            SELECTING_PLAN: [CallbackQueryHandler(plan_selection)],
            WAITING_GAME_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_game_id)],
            WAITING_SERVER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_server_id)],
            CONFIRM_ORDER: [CallbackQueryHandler(proceed_to_payment)],
            WAITING_RECEIPT: [
                CallbackQueryHandler(upload_receipt, pattern="^upload_receipt$"),
                MessageHandler(filters.PHOTO, upload_receipt),
                MessageHandler(filters.TEXT & ~filters.COMMAND, upload_receipt)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        name="customer_conversation",
        persistent=False
    )
    
    # Add handlers
    application.add_handler(customer_conv)
    application.add_handler(CommandHandler("admin", admin_start))
    application.add_handler(CallbackQueryHandler(admin_callback_handler, pattern="^admin_"))
    application.add_handler(CallbackQueryHandler(admin_callback_handler, pattern="^approve_"))
    application.add_handler(CallbackQueryHandler(admin_callback_handler, pattern="^cancel_"))
    application.add_handler(CallbackQueryHandler(admin_callback_handler, pattern="^edit_"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.Chat(ADMIN_CHAT_ID), admin_edit_price))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.Chat(ADMIN_CHAT_ID), admin_edit_payment))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.Chat(ADMIN_CHAT_ID), admin_announcement))
    application.add_error_handler(error_handler)
    
    # Start bot
    print("🤖 Bot is starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()

import logging
import aiosqlite
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters, ConversationHandler
import os
import sys
from datetime import datetime, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DB_PATH, ADMIN_GID

R_START, R_DURATION, R_REASON = range(3)

async def sync_rest_status_job(context: ContextTypes.DEFAULT_TYPE):
    """Background job to check leave_logs and update member status automatically."""
    today_date = datetime.now().date()
    
    async with aiosqlite.connect(DB_PATH) as db:
        # Reset everyone who is 'Rest' back to 'Active' first
        await db.execute("UPDATE members SET status = 'Active' WHERE status = 'Rest'")
        
        # Fetch all leave logs
        async with db.execute("SELECT telegram_id, leave_date FROM leave_logs") as cursor:
            logs = await cursor.fetchall()
            
        on_leave_ids = set()
        for t_id, leave_date in logs:
            try:
                # Format: YYYY-MM-DD|YYYY-MM-DD
                if '|' in leave_date:
                    start_str, end_str = leave_date.split('|')
                    s_date = datetime.strptime(start_str, "%Y-%m-%d").date()
                    e_date = datetime.strptime(end_str, "%Y-%m-%d").date()
                    
                    if s_date <= today_date <= e_date:
                        on_leave_ids.add(t_id)
            except Exception as e:
                logging.error(f"Error parsing leave_date '{leave_date}': {e}")
                
        if on_leave_ids:
            # Set their status to 'Rest'
            placeholders = ','.join('?' * len(on_leave_ids))
            await db.execute(f"UPDATE members SET status = 'Rest' WHERE telegram_id IN ({placeholders})", list(on_leave_ids))
            
        await db.commit()

async def rest_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT full_name FROM members WHERE telegram_id = ?", (telegram_id,)) as cursor:
            user = await cursor.fetchone()
            
    if not user:
        await update.message.reply_text("You are not registered. Type /regist first.")
        return ConversationHandler.END
        
    await update.message.reply_text(
        "🏖️ *Rest Request*\n"
        "*(Type /cancel to abort)*\n\n"
        "1. Enter the *start date* of your rest (format: DD-MM-YYYY, e.g., 15-10-2027:",
        parse_mode="Markdown"
    )
    return R_START

async def rest_start_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    try:
        start_date = datetime.strptime(text, "%d-%m-%Y").date()
        today = datetime.now().date()
        if start_date < today:
            await update.message.reply_text("❌ Start date cannot be in the past. Try again (DD-MM-YYYY):")
            return R_START
    except ValueError:
        await update.message.reply_text("❌ Invalid date format. Please strictly use DD-MM-YYYY:")
        return R_START
        
    context.user_data['r_start'] = start_date.strftime("%Y-%m-%d")
    await update.message.reply_text(
        "2. How many *days* will you rest? (e.g., 3):",
        parse_mode="Markdown"
    )
    return R_DURATION

async def rest_duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text.isdigit() or int(text) < 1:
        await update.message.reply_text("❌ Please enter a valid number of days (minimum 1):")
        return R_DURATION
        
    context.user_data['r_duration'] = int(text)
    await update.message.reply_text(
        "3. Enter the *reason* for your rest:",
        parse_mode="Markdown"
    )
    return R_REASON

async def rest_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reason = update.message.text
    telegram_id = update.effective_user.id
    
    start_str = context.user_data['r_start']
    duration = context.user_data['r_duration']
    
    start_date = datetime.strptime(start_str, "%Y-%m-%d").date()
    end_date = start_date + timedelta(days=duration - 1)
    end_str = end_date.strftime("%Y-%m-%d")
    
    leave_date_db = f"{start_str}|{end_str}"
    display_range = f"{start_date.strftime('%d-%m-%Y')} to {end_date.strftime('%d-%m-%Y')}"
    
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT full_name FROM members WHERE telegram_id = ?", (telegram_id,)) as cursor:
            user = await cursor.fetchone()
            
        await db.execute(
            "INSERT INTO leave_logs (telegram_id, leave_date, reason) VALUES (?, ?, ?)",
            (telegram_id, leave_date_db, reason)
        )
        await db.commit()
        
    # Trigger auto-sync so if start_date is today, status changes immediately!
    await sync_rest_status_job(context)
    
    if ADMIN_GID:
        try:
            await context.bot.send_message(
                chat_id=ADMIN_GID,
                text=f"🏖️ *Rest Request Received*\n"
                     f"━━━━━━━━━━━━━━━━━━\n"
                     f"*Name:* {user[0] if user else 'Unknown'}\n"
                     f"*Dates:* {display_range} ({duration} days)\n"
                     f"*Reason:* {reason}",
                parse_mode="Markdown"
            )
        except Exception as e:
            logging.error(f"Failed to send rest notification to ADMIN_GID: {e}")
        
    await update.message.reply_text(
        f"✅ *Rest request submitted successfully!*\n"
        f"Your status will be set to 'Rest' from {start_date.strftime('%d-%m-%Y')} until {end_date.strftime('%d-%m-%Y')}.\n"
        f"After that, it will revert back to 'Active' automatically. Or you can manually set your status to 'Active' before the end date by using the command /active.",
        parse_mode="Markdown"
    )
    return ConversationHandler.END

async def cancel_rest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Rest request cancelled.")
    return ConversationHandler.END

async def set_active(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    
    async with aiosqlite.connect(DB_PATH) as db:
        # Cek status saat ini
        async with db.execute("SELECT status FROM members WHERE telegram_id = ?", (telegram_id,)) as cursor:
            user = await cursor.fetchone()
            
        if not user or user[0] != 'Rest':
            await update.message.reply_text("You are already Active!")
            return
            
        # Potong durasi log terakhir agar cron job besok tidak membuat mereka Rest lagi
        async with db.execute("SELECT id, leave_date FROM leave_logs WHERE telegram_id = ? ORDER BY id DESC LIMIT 1", (telegram_id,)) as cursor:
            log = await cursor.fetchone()
            
        if log:
            log_id, leave_date = log
            if '|' in leave_date:
                start_str, _ = leave_date.split('|')
                yesterday_str = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
                new_leave_date = f"{start_str}|{yesterday_str}"
                await db.execute("UPDATE leave_logs SET leave_date = ? WHERE id = ?", (new_leave_date, log_id))
                
        # Ubah status member kembali menjadi Active
        await db.execute("UPDATE members SET status = 'Active' WHERE telegram_id = ?", (telegram_id,))
        await db.commit()
        
    await update.message.reply_text("✅ Welcome back! Your status has been set to *Active*.", parse_mode="Markdown")

rest_handler = ConversationHandler(
    entry_points=[CommandHandler('rest', rest_start)],
    states={
        R_START: [MessageHandler(filters.TEXT & ~filters.COMMAND, rest_start_date)],
        R_DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, rest_duration)],
        R_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, rest_reason)],
    },
    fallbacks=[CommandHandler('cancel', cancel_rest)]
)

import logging
import aiosqlite
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters, ConversationHandler
import os
import sys
from datetime import datetime, timedelta, timezone

WIB = timezone(timedelta(hours=7))

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DB_PATH, ADMIN_GID, OWNER_ID

R_START, R_DURATION, R_REASON = range(3)

async def sync_rest_status_job(context: ContextTypes.DEFAULT_TYPE):
    """Background job to sync rest status. Runs daily at 00:05.
    
    Uses SQL-only approach for efficiency:
    1. Detect members whose rest just ended (for notification)
    2. Set active leave logs → Rest
    3. Expired rest with no active log → Active
    4. Cleanup old leave_logs
    """
    today_str = datetime.now(WIB).strftime("%Y-%m-%d")
    
    async with aiosqlite.connect(DB_PATH) as db:
        # 1) Find members whose rest just ended (still 'Rest' but no active log)
        async with db.execute("""
            SELECT m.telegram_id, m.full_name, m.codename FROM members m
            WHERE m.status = 'Rest' AND m.telegram_id NOT IN (
                SELECT telegram_id FROM leave_logs
                WHERE substr(leave_date, 1, 10) <= ?
                  AND substr(leave_date, 12) >= ?
            )
        """, (today_str, today_str)) as cursor:
            ended_members = await cursor.fetchall()
        
        # 2) Members with active leave log today → set Rest
        await db.execute("""
            UPDATE members SET status = 'Rest'
            WHERE telegram_id IN (
                SELECT telegram_id FROM leave_logs
                WHERE substr(leave_date, 1, 10) <= ?
                  AND substr(leave_date, 12) >= ?
            )
        """, (today_str, today_str))
        
        # 3) Members still 'Rest' but no active log → set Active
        await db.execute("""
            UPDATE members SET status = 'Active'
            WHERE status = 'Rest' AND telegram_id NOT IN (
                SELECT telegram_id FROM leave_logs
                WHERE substr(leave_date, 1, 10) <= ?
                  AND substr(leave_date, 12) >= ?
            )
        """, (today_str, today_str))
        
        # 4) Cleanup: remove expired leave_logs (end date before today)
        await db.execute("""
            DELETE FROM leave_logs
            WHERE substr(leave_date, 12) < ?
        """, (today_str,))
        
        await db.commit()
    
    # 5) Notify members whose rest just ended
    for telegram_id, full_name, codename in ended_members:
        name = full_name or "Member"
        cname = codename or "-"
        # Notify the user
        try:
            await context.bot.send_message(
                chat_id=telegram_id,
                text=f"👋 Welcome back, *{name}*!\n\n"
                     f"Your rest period has ended and your status is now *Active*.\n"
                     f"Have a great day! 💪",
                parse_mode="Markdown"
            )
        except Exception as e:
            logging.error(f"Failed to send rest-ended notification to {telegram_id}: {e}")
        
        # Notify admin group & owner
        notify_targets = [cid for cid in [ADMIN_GID, OWNER_ID] if cid]
        for chat_id in notify_targets:
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"✅ *Rest Ended (Auto)*\n"
                         f"━━━━━━━━━━━━━━━━━━\n"
                         f"*Name:* {name}\n"
                         f"*Codename:* {cname}\n"
                         f"Status has been set back to *Active*.",
                    parse_mode="Markdown"
                )
            except Exception as e:
                logging.error(f"Failed to send rest-ended notification to {chat_id}: {e}")

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
        today = datetime.now(WIB).date()
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
        async with db.execute("SELECT full_name, codename FROM members WHERE telegram_id = ?", (telegram_id,)) as cursor:
            user = await cursor.fetchone()
            
        await db.execute(
            "INSERT INTO leave_logs (telegram_id, leave_date, reason) VALUES (?, ?, ?)",
            (telegram_id, leave_date_db, reason)
        )
        await db.commit()
        
    # Trigger auto-sync so if start_date is today, status changes immediately!
    await sync_rest_status_job(context)
    
    member_name = user[0] if user else 'Unknown'
    member_codename = user[1] if user else '-'
    
    # Notify admin group & owner
    notify_targets = [cid for cid in [ADMIN_GID, OWNER_ID] if cid]
    for chat_id in notify_targets:
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🏖️ *Rest Request Received*\n"
                     f"━━━━━━━━━━━━━━━━━━\n"
                     f"*Name:* {member_name}\n"
                     f"*Codename:* {member_codename}\n"
                     f"*Dates:* {display_range} ({duration} days)\n"
                     f"*Reason:* {reason}",
                parse_mode="Markdown"
            )
        except Exception as e:
            logging.error(f"Failed to send rest notification to {chat_id}: {e}")
        
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
        async with db.execute("SELECT status, full_name, codename FROM members WHERE telegram_id = ?", (telegram_id,)) as cursor:
            user = await cursor.fetchone()
            
        if not user or user[0] != 'Rest':
            await update.message.reply_text("You are already Active!")
            return
        
        full_name = user[1] or "Member"
        codename = user[2] or "-"
            
        # Potong durasi log terakhir agar cron job besok tidak membuat mereka Rest lagi
        async with db.execute("SELECT id, leave_date FROM leave_logs WHERE telegram_id = ? ORDER BY id DESC LIMIT 1", (telegram_id,)) as cursor:
            log = await cursor.fetchone()
            
        if log:
            log_id, leave_date = log
            if '|' in leave_date:
                start_str, _ = leave_date.split('|')
                yesterday_str = (datetime.now(WIB) - timedelta(days=1)).strftime('%Y-%m-%d')
                new_leave_date = f"{start_str}|{yesterday_str}"
                await db.execute("UPDATE leave_logs SET leave_date = ? WHERE id = ?", (new_leave_date, log_id))
                
        # Ubah status member kembali menjadi Active
        await db.execute("UPDATE members SET status = 'Active' WHERE telegram_id = ?", (telegram_id,))
        await db.commit()
        
    await update.message.reply_text("✅ Welcome back! Your status has been set to *Active*.", parse_mode="Markdown")
    
    # Notify admin group & owner
    notify_targets = [cid for cid in [ADMIN_GID, OWNER_ID] if cid]
    for chat_id in notify_targets:
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"✅ *Rest Ended (Manual)*\n"
                     f"━━━━━━━━━━━━━━━━━━\n"
                     f"*Name:* {full_name}\n"
                     f"*Codename:* {codename}\n"
                     f"Manually set status back to *Active* via /active.",
                parse_mode="Markdown"
            )
        except Exception as e:
            logging.error(f"Failed to send active notification to {chat_id}: {e}")

rest_handler = ConversationHandler(
    entry_points=[CommandHandler('rest', rest_start)],
    states={
        R_START: [MessageHandler(filters.TEXT & ~filters.COMMAND, rest_start_date)],
        R_DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, rest_duration)],
        R_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, rest_reason)],
    },
    fallbacks=[CommandHandler('cancel', cancel_rest)]
)

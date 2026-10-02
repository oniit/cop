import logging
import aiosqlite
import uuid
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LinkPreviewOptions
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DB_PATH
from bot.handlers.admin import is_admin

# --- COMMAND /open_attendance ---
async def open_attendance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ *Access Denied.* You do not have Admin privileges.", parse_mode="Markdown")
        return
        
    if not context.args:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT session_id, title FROM attendance_sessions WHERE is_active = 0 ORDER BY ROWID DESC LIMIT 10") as cursor:
                closed_sessions = await cursor.fetchall()
                
        if not closed_sessions:
            await update.message.reply_text("⚠️ *Invalid format.*\nUsage: `/open_attendance <Event Name>`\n\n_No recently closed sessions found to reopen._", parse_mode="Markdown")
            return
            
        text = "📋 *Recently Closed Sessions*\nClick a button to reopen an attendance session:\n\n(To create a new one, use: `/open_attendance <Event Name>`)"
        keyboard = []
        for sess in closed_sessions:
            keyboard.append([InlineKeyboardButton(f"🔓 Reopen {sess[1]}", callback_data=f"reopenatt_{sess[0]}")])
            
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return
        
    title = " ".join(context.args)
    # Generate unique ID untuk sesi ini (contoh: pendek)
    session_id = f"ATT-{str(uuid.uuid4())[:8].upper()}"
    
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO attendance_sessions (session_id, title, is_active) VALUES (?, ?, 1)", (session_id, title))
        await db.commit()
        
    # Buat tombol Inline
    keyboard = [
        [InlineKeyboardButton("✅ Present", callback_data=f"att_toggle_{session_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"📢 *ATTENDANCE OPENED*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"*{title}*\n\n"
        f"Click the button below to record your attendance.\n"
        f"*(Click again to cancel)*",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

# --- CALLBACK HANDLER UNTUK TOMBOL PRESENSI ---
async def attendance_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    telegram_id = query.from_user.id
    callback_data = query.data
    
    if not callback_data.startswith("att_"):
        return
        
    parts = callback_data.split("_")
    # Dukungan backward compatibility untuk format lama
    session_id = parts[1] if len(parts) == 2 else parts[2]
    
    async with aiosqlite.connect(DB_PATH) as db:
        # Cek apakah user terdaftar
        async with db.execute("SELECT full_name FROM members WHERE telegram_id = ?", (telegram_id,)) as cursor:
            user = await cursor.fetchone()
            
        if not user:
            await query.answer("❌ You are not registered! Type /regist first.", show_alert=True)
            return
            
        # Cek apakah sesi masih aktif
        async with db.execute("SELECT title, is_active FROM attendance_sessions WHERE session_id = ?", (session_id,)) as cursor:
            session = await cursor.fetchone()
            
        if not session:
            await query.answer("❌ Session not found.", show_alert=True)
            return
            
        if not session[1]: # is_active == 0
            await query.answer("❌ This attendance session has been closed.", show_alert=True)
            return
            
        # Cek state saat ini
        async with db.execute("SELECT status, points_awarded FROM attendance_logs WHERE session_id = ? AND telegram_id = ?", (session_id, telegram_id)) as cursor:
            log = await cursor.fetchone()
            
        if not log:
            # State 0 (Absent) -> State 1 (Present)
            status = "Present"
            points = 5
            await db.execute("INSERT INTO attendance_logs (session_id, telegram_id, status, points_awarded) VALUES (?, ?, ?, ?)", (session_id, telegram_id, status, points))
            await db.execute("UPDATE members SET cop_points = cop_points + ? WHERE telegram_id = ?", (points, telegram_id))
            await db.execute("INSERT INTO point_logs (telegram_id, point_type, amount, reason, issued_by) VALUES (?, 'COP', ?, ?, ?)",
                             (telegram_id, points, f"Attendance: {status} ({session[0]})", context.bot.id))
            msg = f"✅ Attendance recorded as {status} (+{points} RP)!"
            next_btn_text = "💡 Excuse"
            
        elif log[0] == "Present":
            # State 1 (Present) -> State 2 (Excuse)
            status = "Excuse"
            new_points = 2
            old_points = log[1] if log[1] is not None else 5
            diff = new_points - old_points
            
            await db.execute("UPDATE attendance_logs SET status = ?, points_awarded = ? WHERE session_id = ? AND telegram_id = ?", (status, new_points, session_id, telegram_id))
            await db.execute("UPDATE members SET cop_points = cop_points + ? WHERE telegram_id = ?", (diff, telegram_id))
            await db.execute("INSERT INTO point_logs (telegram_id, point_type, amount, reason, issued_by) VALUES (?, 'COP', ?, ?, ?)",
                             (telegram_id, diff, f"Attendance Changed to {status} ({session[0]})", context.bot.id))
            msg = f"💡 Attendance changed to {status} (+{new_points} RP total)!"
            next_btn_text = "❌ Cancel"
            
        else:
            # State 2 (Excuse) -> State 0 (Absent/Cancel)
            old_points = log[1] if log[1] is not None else 0
            
            await db.execute("DELETE FROM attendance_logs WHERE session_id = ? AND telegram_id = ?", (session_id, telegram_id))
            if old_points > 0:
                await db.execute("UPDATE members SET cop_points = cop_points - ? WHERE telegram_id = ?", (old_points, telegram_id))
                await db.execute("INSERT INTO point_logs (telegram_id, point_type, amount, reason, issued_by) VALUES (?, 'COP', ?, ?, ?)",
                                 (telegram_id, -old_points, f"Attendance Cancelled ({session[0]})", context.bot.id))
            msg = "❌ Attendance cancelled. Points deducted."
            next_btn_text = "✅ Present"
            
        await db.commit()
            
    await query.answer(msg, show_alert=True)
    
    # Jika di private chat, update tombolnya secara dinamis
    if query.message.chat.type == "private":
        keyboard = query.message.reply_markup.inline_keyboard
        new_keyboard = []
        for row in keyboard:
            new_row = []
            for btn in row:
                if btn.callback_data == callback_data:
                    if "(Click to" in btn.text:
                        # Format dari /attendance
                        title = session[0]
                        if not log:
                            # Tadi Absent -> Sekarang Present
                            new_text = f"✅ {title} (Click to Excuse)"
                        elif log[0] == "Present":
                            # Tadi Present -> Sekarang Excuse
                            new_text = f"💡 {title} (Click to Cancel)"
                        else:
                            # Tadi Excuse -> Sekarang Absent
                            new_text = f"❌ {title} (Click to Present)"
                    else:
                        # Format standard
                        new_text = next_btn_text
                        
                    new_row.append(InlineKeyboardButton(new_text, callback_data=btn.callback_data))
                else:
                    new_row.append(btn)
            new_keyboard.append(new_row)
            
        try:
            await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(new_keyboard))
        except:
            pass

# --- COMMAND /close_attendance ---
async def close_attendance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ *Access Denied.* You do not have Admin privileges.", parse_mode="Markdown")
        return
        
    if not context.args:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT session_id, title FROM attendance_sessions WHERE is_active = 1") as cursor:
                active_sessions = await cursor.fetchall()
                
        if not active_sessions:
            await update.message.reply_text("ℹ️ There are no open attendance sessions to close.", parse_mode="Markdown")
            return
            
        text = "📋 *Open Sessions*\nClick a button to close an attendance session:"
        keyboard = []
        for sess in active_sessions:
            keyboard.append([InlineKeyboardButton(f"🔒 Close {sess[1]}", callback_data=f"closeatt_{sess[0]}")])
            
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return
        
    session_id = context.args[0]
    
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT title, is_active FROM attendance_sessions WHERE session_id = ?", (session_id,)) as cursor:
            session = await cursor.fetchone()
            
        if not session:
            await update.message.reply_text(f"❌ Session ID `{session_id}` not found.", parse_mode="Markdown")
            return
            
        if not session[1]:
            await update.message.reply_text(f"⚠️ Session `{session_id}` is already closed.", parse_mode="Markdown")
            return
            
        await db.execute("UPDATE attendance_sessions SET is_active = 0 WHERE session_id = ?", (session_id,))
        await db.commit()
        
    await update.message.reply_text(f"✅ Attendance for *{session[0]}* has been permanently closed.", parse_mode="Markdown")

# --- COMMAND /attendance (List Open Sessions) ---
async def active_sessions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    
    async with aiosqlite.connect(DB_PATH) as db:
        # Cek apakah user terdaftar
        async with db.execute("SELECT full_name FROM members WHERE telegram_id = ?", (telegram_id,)) as cursor:
            user = await cursor.fetchone()
            
        if not user:
            await update.message.reply_text("You are not registered. Type /regist first.")
            return
            
        # Ambil semua sesi aktif
        async with db.execute("SELECT session_id, title FROM attendance_sessions WHERE is_active = 1") as cursor:
            sessions = await cursor.fetchall()
            
    if not sessions:
        await update.message.reply_text("There are no open attendance sessions at the moment.")
        return
        
    text = "📋 *Open Attendance Sessions*\n"
    text += "Please match exactly with the data in https://t.me/POINTREPUTATIONAIA/4"
    
    # Buat tombol untuk tiap sesi yang masih buka
    keyboard = []
    async with aiosqlite.connect(DB_PATH) as db:
        for sess in sessions:
            session_id = sess[0]
            title = sess[1]
            
            async with db.execute("SELECT status FROM attendance_logs WHERE session_id = ? AND telegram_id = ?", (session_id, telegram_id)) as cursor:
                log = await cursor.fetchone()
                
            if not log:
                btn_text = f"❌ {title} (Click to Present)"
            elif log[0] == "Present":
                btn_text = f"✅ {title} (Click to Excuse)"
            else:
                btn_text = f"💡 {title} (Click to Cancel)"
                
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"att_{session_id}")])
        
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown", link_preview_options=LinkPreviewOptions(is_disabled=True))

# --- CALLBACK HANDLER UNTUK REOPEN PRESENSI ---
async def reopen_attendance_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    if not await is_admin(query.from_user.id):
        await query.answer("⛔ Access Denied.", show_alert=True)
        return
        
    session_id = query.data.split("_")[1]
    
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT title FROM attendance_sessions WHERE session_id = ?", (session_id,)) as cursor:
            session = await cursor.fetchone()
        title = session[0] if session else session_id
        
        await db.execute("UPDATE attendance_sessions SET is_active = 1 WHERE session_id = ?", (session_id,))
        await db.commit()
        
    # Buat tombol Inline untuk dipost ke group
    keyboard = [
        [InlineKeyboardButton("✅ Present", callback_data=f"att_{session_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.reply_text(
        f"📢 *ATTENDANCE REOPENED*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"*{title}*\n\n"
        f"Click the button below to record your attendance.\n"
        f"*(Click again to cancel)*",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    await query.message.edit_text(f"✅ Session *{title}* reopened successfully.", parse_mode="Markdown")
    
# --- CALLBACK HANDLER UNTUK CLOSE PRESENSI ---
async def close_attendance_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    if not await is_admin(query.from_user.id):
        await query.answer("⛔ Access Denied.", show_alert=True)
        return
        
    session_id = query.data.split("_")[1]
    
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT title FROM attendance_sessions WHERE session_id = ?", (session_id,)) as cursor:
            session = await cursor.fetchone()
        title = session[0] if session else session_id
        
        await db.execute("UPDATE attendance_sessions SET is_active = 0 WHERE session_id = ?", (session_id,))
        await db.commit()
        
    await query.message.edit_text(f"✅ Attendance for *{title}* has been permanently closed.", parse_mode="Markdown")

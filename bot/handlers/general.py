import logging
import aiosqlite
from telegram import Update
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
    ConversationHandler,
    CallbackQueryHandler
)
from datetime import datetime
import os
import sys
import textwrap
import re

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DB_PATH

# State untuk ConversationHandler
NAME, CODENAME, AGENT_ID, MUSE, DOB, MOTTO = range(6)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    
    # Cek apakah user sudah terdaftar
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT full_name FROM members WHERE telegram_id = ?", (telegram_id,)) as cursor:
            user = await cursor.fetchone()
            
    if user:
        await update.message.reply_text(
            f"Welcome back, {user[0]}! You are already registered in the COP system.\n"
            "Use /profile to view your data."
        )
    else:
        await update.message.reply_text(
            "Hello! I am *COP Bot* 🚀\n"
            "You are not registered in the system yet. Please type /regist to begin registration.",
            parse_mode="Markdown"
        )

# --- ALUR PENDAFTARAN (/regist) ---

async def daftar_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT full_name FROM members WHERE telegram_id = ?", (telegram_id,)) as cursor:
            user = await cursor.fetchone()
            
    if user:
        await update.message.reply_text("You are already registered! No need to register again.")
        return ConversationHandler.END
        
    prompt = "1. Please enter your *Full Name*:"
    context.user_data['last_prompt'] = prompt
    await update.message.reply_text(
        "Let's start the COP member registration.\n"
        "*(You can cancel anytime by typing /cancel)*\n\n" + prompt,
        parse_mode="Markdown"
    )
    return NAME

async def daftar_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['full_name'] = update.message.text.title()
    prompt = "2. Enter your *Codename*:"
    context.user_data['last_prompt'] = prompt
    await update.message.reply_text(prompt, parse_mode="Markdown")
    return CODENAME

async def daftar_codename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['codename'] = update.message.text.upper()
    prompt = "3. Enter your *Agent ID* (Format: COP-0000-XXX):"
    context.user_data['last_prompt'] = prompt
    await update.message.reply_text(prompt, parse_mode="Markdown")
    return AGENT_ID

async def daftar_agent_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    agent_id = update.message.text.upper()
    
    if not re.match(r'^COP-\d{4}-[A-Z]{3}$', agent_id):
        await update.message.reply_text(
            "❌ Invalid Agent ID format! It must be `COP-0000-XXX` (e.g. COP-0007-VIR).\n\n" + 
            context.user_data.get('last_prompt', "3. Please enter your *Agent ID*:"),
            parse_mode="Markdown"
        )
        return AGENT_ID
        
    context.user_data['agent_id'] = agent_id
    prompt = "4. Enter your *Muse* (face claim):"
    context.user_data['last_prompt'] = prompt
    await update.message.reply_text(prompt, parse_mode="Markdown")
    return MUSE

async def daftar_muse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['muse'] = update.message.text.upper()
    prompt = "5. Enter your *Date of Birth* (format: DD-MM-YYYY e.g. 15-10-2001):"
    context.user_data['last_prompt'] = prompt
    await update.message.reply_text(prompt, parse_mode="Markdown")
    return DOB

async def daftar_dob(update: Update, context: ContextTypes.DEFAULT_TYPE):
    dob_text = update.message.text
    
    try:
        # Validasi format DD-MM-YYYY dan keabsahan tanggal kalender
        dob_date = datetime.strptime(dob_text, "%d-%m-%Y")
        
        # Validasi logika tahun (tidak boleh di bawah 1950 atau di masa depan)
        current_year = datetime.now().year
        if dob_date.year < 1950 or dob_date.year > current_year - 5:
            await update.message.reply_text(
                "❌ Impossible birth year.\n\n" + context.user_data.get('last_prompt', "5. Please enter a valid Date of Birth (format: DD-MM-YYYY e.g. 15-10-2001):"),
                parse_mode="Markdown"
            )
            return DOB
            
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid format or non-existent date!\n\n" + context.user_data.get('last_prompt', "5. Please strictly follow DD-MM-YYYY (e.g., 15-10-2001):"),
            parse_mode="Markdown"
        )
        return DOB

    context.user_data['dob'] = dob_text
    prompt = "6. Lastly, enter your *Motto* (or type '-' if none):"
    context.user_data['last_prompt'] = prompt
    await update.message.reply_text(prompt, parse_mode="Markdown")
    return MOTTO

async def daftar_motto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    context.user_data['motto'] = text if text == '-' else (text[0].upper() + text[1:] if text else text)
    telegram_id = update.effective_user.id
    username = update.effective_user.username or ""
    
    # Simpan ke database SQLite
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute('''
                INSERT INTO members (telegram_id, username, full_name, codename, agent_id, muse, position, dob, motto, join_date)
                VALUES (?, ?, ?, ?, ?, ?, 'Member', ?, ?, date('now'))
            ''', (
                telegram_id, username,
                context.user_data['full_name'],
                context.user_data['codename'],
                context.user_data['agent_id'],
                context.user_data['muse'],
                context.user_data['dob'],
                context.user_data['motto']
            ))
            await db.commit()
            
        await update.message.reply_text(
            "✅ *Registration Successful!*\n\n"
            "Welcome to City of Prestige (COP).\n"
            "Type /profile to view your complete data.",
            parse_mode="Markdown"
        )
    except aiosqlite.IntegrityError:
        await update.message.reply_text("❌ Registration failed. That *Agent ID* might already be taken.", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ System error occurred: {e}")
        
    return ConversationHandler.END

async def cancel_daftar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Registration cancelled.")
    return ConversationHandler.END

async def fallback_daftar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Dipanggil jika user mengetik command apa pun selain /cancel saat sedang mendaftar
    last_prompt = context.user_data.get('last_prompt', "Please complete your current registration step.")
    await update.message.reply_text(
        f"⚠️ You are currently in the middle of registration. Please reply with normal text:\n\n{last_prompt}",
        parse_mode="Markdown"
    )

# Konfigurasi handler pendaftaran
daftar_handler = ConversationHandler(
    entry_points=[CommandHandler('regist', daftar_start)],
    states={
        NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, daftar_name)],
        CODENAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, daftar_codename)],
        AGENT_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, daftar_agent_id)],
        MUSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, daftar_muse)],
        DOB: [MessageHandler(filters.TEXT & ~filters.COMMAND, daftar_dob)],
        MOTTO: [MessageHandler(filters.TEXT & ~filters.COMMAND, daftar_motto)],
    },
    fallbacks=[
        CommandHandler('cancel', cancel_daftar),
        MessageHandler(filters.COMMAND, fallback_daftar)
    ]
)

# --- PROFIL ---
async def profil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM members WHERE telegram_id = ?", (telegram_id,)) as cursor:
            user = await cursor.fetchone()
            
    if not user:
        await update.message.reply_text("You are not registered. Type /regist first.")
        return
        
    # user = (0:telegram_id, 1:username, 2:full_name, 3:codename, 4:agent_id, 5:muse, 6:position, 7:dob, 8:motto, 9:join_date, 10:status, 11:aia_points, 12:cop_points)
    
    person = ('@' + user[1]) if user[1] else user[2]
    icon = "🛌" if user[10] and "rest" in user[10].lower() else "👤"
    
    motto_wrapped = textwrap.fill(user[8], width=32) if user[8] else ""
    cp_text = f" | {user[12]} CP" if user[12] else ""
    text = (
        f"{icon} *{person}'s Profile*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"*Name:* {user[2]}\n"
        f"*Codename:* {user[3]}\n"
        f"*Agent ID:* `{user[4]}`\n"
        f"*Position:* {user[6]}\n"
        f"*Points:* {user[11]} RP{cp_text}\n\n"
        f"\"_{motto_wrapped}_\""
    )
    await update.message.reply_text(text, parse_mode="Markdown")

# --- COMMAND /leaderboard ---
async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT full_name, aia_points, cop_points, (aia_points + cop_points) as total
            FROM members
            ORDER BY total DESC, aia_points DESC
            LIMIT 10
        """) as cursor:
            top_members = await cursor.fetchall()
            
    if not top_members:
        await update.message.reply_text("No data available for the leaderboard.")
        return
        
    text = "🏆 *COP LEADERBOARD TOP 10* 🏆\n━━━━━━━━━━━━━━━━━━\n"
    medals = ["🥇", "🥈", "🥉"]
    for i, mem in enumerate(top_members):
        medal = medals[i] if i < 3 else f"{i+1}."
        text += f"{medal} *{mem[0]}*\n      └ Total: {mem[3]} (AIA: {mem[1]} | COP: {mem[2]})\n\n"
        
    await update.message.reply_text(text, parse_mode="Markdown")


# --- COMMAND /edit_profile ---
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery

EDIT_FIELD, EDIT_VALUE = range(2)

async def edit_profile_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT full_name FROM members WHERE telegram_id = ?", (telegram_id,)) as cursor:
            user = await cursor.fetchone()
            
    if not user:
        await update.message.reply_text("You are not registered. Type /regist first.")
        return ConversationHandler.END
        
    keyboard = [
        [InlineKeyboardButton("Name", callback_data="ep_full_name"), InlineKeyboardButton("Codename", callback_data="ep_codename")],
        [InlineKeyboardButton("Agent ID", callback_data="ep_agent_id"), InlineKeyboardButton("DOB", callback_data="ep_dob")],
        [InlineKeyboardButton("Muse", callback_data="ep_muse"), InlineKeyboardButton("Motto", callback_data="ep_motto")],
        [InlineKeyboardButton("❌ Cancel", callback_data="ep_cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text("What would you like to edit?", reply_markup=reply_markup)
    return EDIT_FIELD

async def edit_profile_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    field = query.data.replace("ep_", "")
    if field == "cancel":
        await query.edit_message_text("Edit profile cancelled.")
        return ConversationHandler.END
        
    context.user_data['edit_field'] = field
    
    field_names = {
        "full_name": "Full Name",
        "codename": "Codename",
        "agent_id": "Agent ID",
        "dob": "Date of Birth (DD-MM-YYYY)",
        "muse": "Muse",
        "motto": "Motto"
    }
    
    await query.edit_message_text(f"Please type your new *{field_names[field]}*:\n*(Type /cancel to abort)*", parse_mode="Markdown")
    return EDIT_VALUE

async def edit_profile_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    field = context.user_data['edit_field']
    new_value = update.message.text
    telegram_id = update.effective_user.id
    
    if field == "dob":
        try:
            dob_date = datetime.strptime(new_value, "%d-%m-%Y")
            current_year = datetime.now().year
            if dob_date.year < 1950 or dob_date.year > current_year - 5:
                await update.message.reply_text("❌ Impossible birth year. Try again or /cancel:")
                return EDIT_VALUE
        except ValueError:
            await update.message.reply_text("❌ Invalid format. Use DD-MM-YYYY. Try again or /cancel:")
            return EDIT_VALUE
    elif field == "full_name":
        new_value = new_value.title()
    elif field == "codename":
        new_value = new_value.upper()
    elif field == "agent_id":
        new_value = new_value.upper()
        if not re.match(r'^COP-\d{4}-[A-Z]{3}$', new_value):
            await update.message.reply_text("❌ Invalid format! Must be `COP-0000-XXX` (e.g. COP-0007-VIR). Try again or /cancel:", parse_mode="Markdown")
            return EDIT_VALUE
    elif field == "motto":
        new_value = new_value if new_value == '-' else (new_value[0].upper() + new_value[1:] if new_value else new_value)
        
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            query_sql = f"UPDATE members SET {field} = ? WHERE telegram_id = ?"
            await db.execute(query_sql, (new_value, telegram_id))
            await db.commit()
    except aiosqlite.IntegrityError:
        if field == "agent_id":
            await update.message.reply_text("❌ That Agent ID is already taken. Try again or /cancel:")
            return EDIT_VALUE
            
    await update.message.reply_text("✅ Profile updated successfully!\nType /profile to see the changes.")
    return ConversationHandler.END

async def cancel_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Edit profile cancelled.")
    return ConversationHandler.END

edit_profile_handler = ConversationHandler(
    entry_points=[CommandHandler('edit_profile', edit_profile_start)],
    states={
        EDIT_FIELD: [CallbackQueryHandler(edit_profile_choice, pattern='^ep_')],
        EDIT_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_profile_value)],
    },
    fallbacks=[CommandHandler('cancel', cancel_edit)]
)

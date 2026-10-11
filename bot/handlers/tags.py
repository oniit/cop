import aiosqlite
import html
from telegram import Update
from telegram.ext import ContextTypes
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DB_PATH

async def cmd_cop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /cop - tag all per 5 orang hyperlink usernamenya pake codename
    /cop string - tag all tapi ada pesan string
    """
    chat_id = update.effective_chat.id
    
    # Ambil pesan string (jika ada)
    message_text = " ".join(context.args) if context.args else ""
    
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT telegram_id, username, codename FROM members ORDER BY codename ASC") as cursor:
            members = await cursor.fetchall()
            
    if not members:
        await update.message.reply_text("No registered members found.")
        return
        
    # Group by 5
    batch_size = 5
    for i in range(0, len(members), batch_size):
        batch = members[i:i+batch_size]
        
        tags = []
        for telegram_id, username, codename in batch:
            if username and username.strip():
                # Hapus @ jika ada di awal username
                clean_uname = username.replace("@", "")
                tags.append(f'<a href="https://t.me/{clean_uname}">{codename}</a>')
            else:
                tags.append(f'<a href="tg://user?id={telegram_id}">{codename}</a>')
            
        tag_str = ", ".join(tags)
        
        final_msg = ""
        if message_text:
            final_msg += f"{message_text}\n\n"
        final_msg += f"📢 {tag_str}"
        
        await context.bot.send_message(chat_id=chat_id, text=final_msg, parse_mode="HTML", disable_web_page_preview=True)

async def cmd_cop_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /cop_profile - direktori penjelasan seluruh perintah profil City of Prestige
    """
    text = (
        "📋 <b>City of Prestige Profile Directory</b>\n\n"
        "/cop_name for Member Name list\n"
        "/cop_id for Agent ID list\n"
        "/cop_muse for Muse list\n"
        "/cop_position for Position list\n"
        "/cop_dob for Date of Birth list"
    )
    await update.message.reply_text(text, parse_mode="HTML")

async def cmd_cop_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /cop_name - daftar lengkap "codename - nama", urutkan berdasarkan alfabet codename
    """
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT codename, full_name FROM members ORDER BY codename ASC") as cursor:
            members = await cursor.fetchall()
            
    if not members:
        await update.message.reply_text("No registered members found.")
        return
        
    msg = "📋 *Name List City of Prestige*\n\n"
    for codename, full_name in members:
        name_val = full_name if full_name else "Not set"
        msg += f"• *{codename}*, {name_val}\n"
        
    await update.message.reply_text(msg, parse_mode="Markdown")

async def cmd_cop_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /cop_id - daftar lengkap "codename - agent id", urutkan berdasarkan alfabet codename
    """
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT codename, agent_id FROM members ORDER BY codename ASC") as cursor:
            members = await cursor.fetchall()
            
    if not members:
        await update.message.reply_text("No registered members found.")
        return
        
    msg = "📋 *Agent ID List City of Prestige*\n\n"
    for codename, agent_id in members:
        id_val = agent_id if agent_id else "Not set"
        msg += f"• *{codename}*, `{id_val}`\n"
        
    await update.message.reply_text(msg, parse_mode="Markdown")

async def cmd_cop_muse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /cop_muse - daftar lengkap "codename - muse", urutkan berdasarkan alfabet
    """
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT codename, muse FROM members ORDER BY codename ASC") as cursor:
            members = await cursor.fetchall()
            
    if not members:
        await update.message.reply_text("No registered members found.")
        return
        
    msg = "📋 *Muse List City of Prestige*\n\n"
    for codename, muse in members:
        muse_val = muse if muse else "Not set"
        msg += f"• *{codename}*, {muse_val}\n"
        
    await update.message.reply_text(msg, parse_mode="Markdown")

async def cmd_cop_position(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /cop_position - daftar lengkap "codename - position", urutkan berdasarkan alfabet codename
    """
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT codename, position FROM members ORDER BY codename ASC") as cursor:
            members = await cursor.fetchall()
            
    if not members:
        await update.message.reply_text("No registered members found.")
        return
        
    msg = "📋 *Position List City of Prestige*\n\n"
    for codename, position in members:
        pos_val = position if position else "Not set"
        msg += f"• *{codename}*, {pos_val}\n"
        
    await update.message.reply_text(msg, parse_mode="Markdown")

async def cmd_cop_dob(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /cop_dob - daftar lengkap "codename - dob", urutkan berdasarkan alfabet codename
    """
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT codename, dob FROM members ORDER BY codename ASC") as cursor:
            members = await cursor.fetchall()
            
    if not members:
        await update.message.reply_text("No registered members found.")
        return
        
    msg = "📋 *Date of Birth List City of Prestige*\n\n"
    for codename, dob in members:
        dob_val = dob if dob else "Not set"
        msg += f"• *{codename}*, {dob_val}\n"
        
    await update.message.reply_text(msg, parse_mode="Markdown")

async def cmd_structure(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /structure - balesannya "codename - nama" berdasarkan jabatan
    """
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT codename, position FROM members ORDER BY codename ASC") as cursor:
            members = await cursor.fetchall()
            
    if not members:
        await update.message.reply_text("No registered members found.")
        return

    # Organisasi data
    struct = {
        "SAC": [],
        "DAC": [],
        "Secretary": [],
        "Event Planner PIC": [],
        "Event Planner Member": [],
        "Wordsmith PIC": [],
        "Wordsmith Member": [],
        "Editor PIC": [],
        "Editor Member": []
    }

    for codename, position in members:
        pos = (position or "").strip().lower()
        if not pos:
            continue
            
        formatted_name = html.escape(codename)
        
        if pos == "sac":
            struct["SAC"].append(formatted_name)
        elif pos == "dac":
            struct["DAC"].append(formatted_name)
        elif "secretary" in pos or "sekretaris" in pos:
            struct["Secretary"].append(formatted_name)
        elif "event planner" in pos:
            if "pic" in pos:
                struct["Event Planner PIC"].append(formatted_name)
            else:
                struct["Event Planner Member"].append(formatted_name)
        elif "wordsmith" in pos:
            if "pic" in pos:
                struct["Wordsmith PIC"].append(formatted_name)
            else:
                struct["Wordsmith Member"].append(formatted_name)
        elif "editor" in pos:
            if "pic" in pos:
                struct["Editor PIC"].append(formatted_name)
            else:
                struct["Editor Member"].append(formatted_name)

    # Format output sesuai template user
    msg = "📋 <b>Structure City of Prestige</b>\n\n"
    
    msg += "— <b>SAC:</b> " + (", ".join(struct["SAC"]) if struct["SAC"] else "") + "\n"
    msg += "— <b>DAC:</b> " + (", ".join(struct["DAC"]) if struct["DAC"] else "") + "\n"
    
    msg += "— <b>Secretary:</b>\n"
    for name in struct["Secretary"]: msg += f"{name}\n"
        
    msg += "— <b>Event Planner</b>\n"
    msg += "<b>PIC:</b> " + (", ".join(struct["Event Planner PIC"]) if struct["Event Planner PIC"] else "") + "\n"
    msg += "<b>Member:</b> " + (", ".join(struct["Event Planner Member"]) if struct["Event Planner Member"] else "") + "\n"

    msg += "— <b>Wordsmith</b>\n"
    msg += "<b>PIC:</b> " + (", ".join(struct["Wordsmith PIC"]) if struct["Wordsmith PIC"] else "") + "\n"
    msg += "<b>Member:</b> " + (", ".join(struct["Wordsmith Member"]) if struct["Wordsmith Member"] else "") + "\n"
        
    msg += "— <b>Editor</b>\n"
    msg += "<b>PIC:</b> " + (", ".join(struct["Editor PIC"]) if struct["Editor PIC"] else "") + "\n"
    msg += "<b>Member:</b> " + (", ".join(struct["Editor Member"]) if struct["Editor Member"] else "") + "\n"

    await update.message.reply_text(msg, parse_mode="HTML")

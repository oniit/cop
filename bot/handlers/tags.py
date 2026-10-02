import aiosqlite
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
        async with db.execute("SELECT telegram_id, codename FROM members ORDER BY codename ASC") as cursor:
            members = await cursor.fetchall()
            
    if not members:
        await update.message.reply_text("Tidak ada member terdaftar.")
        return
        
    # Group by 5
    batch_size = 5
    for i in range(0, len(members), batch_size):
        batch = members[i:i+batch_size]
        
        tags = []
        for telegram_id, codename in batch:
            tags.append(f"[{codename}](tg://user?id={telegram_id})")
            
        tag_str = ", ".join(tags)
        
        final_msg = ""
        if message_text:
            final_msg += f"{message_text}\n\n"
        final_msg += f"📢 {tag_str}"
        
        await context.bot.send_message(chat_id=chat_id, text=final_msg, parse_mode="Markdown")

async def cmd_cop_muse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /cop_muse - daftar lengkap "codename - muse", urutkan berdasarkan alfabet
    """
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT codename, muse FROM members ORDER BY codename ASC") as cursor:
            members = await cursor.fetchall()
            
    if not members:
        await update.message.reply_text("Tidak ada member terdaftar.")
        return
        
    msg = "📋 *Daftar Muse City of Prestige*\n\n"
    for codename, muse in members:
        muse_val = muse if muse else "Belum diatur"
        msg += f"• {codename} - {muse_val}\n"
        
    await update.message.reply_text(msg, parse_mode="Markdown")

async def cmd_cop_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /cop_profile - daftar lengkap "nama - codename", urutkan berdasarkan alfabet (nama)
    """
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT full_name, codename FROM members ORDER BY full_name ASC") as cursor:
            members = await cursor.fetchall()
            
    if not members:
        await update.message.reply_text("Tidak ada member terdaftar.")
        return
        
    msg = "📋 *Daftar Profil City of Prestige*\n\n"
    for full_name, codename in members:
        msg += f"• {full_name} - {codename}\n"
        
    await update.message.reply_text(msg, parse_mode="Markdown")

async def cmd_structure(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /structure - balesannya "codename - nama" berdasarkan jabatan
    """
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT codename, position FROM members") as cursor:
            members = await cursor.fetchall()
            
    if not members:
        await update.message.reply_text("Tidak ada member terdaftar.")
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
            
        formatted_name = f"{codename}"
        
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
    msg = ""
    
    msg += "— SAC: " + (", ".join(struct["SAC"]) if struct["SAC"] else "") + "\n"
    msg += "— DAC: " + (", ".join(struct["DAC"]) if struct["DAC"] else "") + "\n"
    
    msg += "— Secretary:\n"
    for name in struct["Secretary"]: msg += f"{name}\n"
        
    msg += "— Event Planner\n"
    msg += "PIC: " + (", ".join(struct["Event Planner PIC"]) if struct["Event Planner PIC"] else "") + "\n"
    msg += "Member:\n"
    for name in struct["Event Planner Member"]: msg += f"{name}\n"

    msg += "— Wordsmith\n"
    msg += "PIC: " + (", ".join(struct["Wordsmith PIC"]) if struct["Wordsmith PIC"] else "") + "\n"
    msg += "Member:\n"
    for name in struct["Wordsmith Member"]: msg += f"{name}\n"
        
    msg += "— Editor\n"
    msg += "PIC: " + (", ".join(struct["Editor PIC"]) if struct["Editor PIC"] else "") + "\n"
    msg += "Member:\n"
    for name in struct["Editor Member"]: msg += f"{name}\n"

    await update.message.reply_text(msg)

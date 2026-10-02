import logging
import aiosqlite
import re
import unicodedata
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ConversationHandler
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    DB_PATH, ADMIN_GID, OWNER_ID,
    RP_EXT_EV_1ST, RP_EXT_EV_2ND, RP_EXT_EV_3RD, RP_EXT_EV_PARTICIPANT,
    RP_EXT_COMP_1ST, RP_EXT_COMP_2ND, RP_EXT_COMP_3RD, RP_EXT_COMP_PARTICIPANT
)
from bot.handlers.admin import is_admin

# Conversation States
C_TYPE, C_LINK, C_FORWARD, C_INTERNAL_TOTAL = range(4)

def normalize_text(text: str) -> str:
    """Mengubah font messletter/unicode menjadi text biasa."""
    if not text: return ""
    return unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('utf-8')

async def claim_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Cek apakah user terdaftar
    telegram_id = update.effective_user.id
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT full_name FROM members WHERE telegram_id = ?", (telegram_id,)) as cursor:
            user = await cursor.fetchone()
            
    if not user:
        await update.message.reply_text("You are not registered. Type /regist first.")
        return ConversationHandler.END
        
    keyboard = [
        [InlineKeyboardButton("External", callback_data="claim_ext")],
        [InlineKeyboardButton("Internal", callback_data="claim_int")],
        [InlineKeyboardButton("❌ Cancel", callback_data="claim_cancel")]
    ]
    await update.message.reply_text(
        "🌟 *Klaim Poin AIA (RP)*\n\nSilakan pilih jenis klaim Anda:", 
        reply_markup=InlineKeyboardMarkup(keyboard), 
        parse_mode="Markdown"
    )
    return C_TYPE

async def claim_type_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "claim_cancel":
        await query.edit_message_text("Klaim dibatalkan.")
        return ConversationHandler.END
        
    context.user_data['claim_type'] = "External" if query.data == "claim_ext" else "Internal"
    
    await query.edit_message_text(
        f"Anda memilih klaim *{context.user_data['claim_type']}*.\n\n"
        "🔄 *Langkah 1:*\nSilakan **FORWARD (Teruskan)** pesan bukti partisipasi Anda langsung ke sini.\n\n"
        "*(Tips: Salin / Copy LINK pesan tersebut terlebih dahulu sekarang, karena link akan diminta di langkah berikutnya agar tidak bolak-balik)*",
        parse_mode="Markdown"
    )
    return C_FORWARD

async def claim_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    link = update.message.text
    if not link.startswith("http"):
        await update.message.reply_text("❌ Link tidak valid. Harap kirimkan link yang diawali dengan http/https, atau ketik /cancel untuk membatalkan.")
        return C_LINK
        
    context.user_data['claim_link'] = link
    
    if context.user_data['claim_type'] == "External":
        return await send_claim_to_admin(update, context)
    else:
        await update.message.reply_text(
            "📝 *Langkah 3 (Internal):*\n"
            "Format Internal cukup bervariasi. Sebelum dicek Sekretaris, silakan **KETIK TOTAL NOMINAL POIN (RP)** "
            "yang Anda ajukan dalam klaim ini secara keseluruhan (hanya angka, misal: 250):",
            parse_mode="Markdown"
        )
        return C_INTERNAL_TOTAL

async def claim_forward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Tidak peduli apakah itu benar-benar pesan forwarded atau diketik manual, kita ambil teksnya
    text = update.message.text or update.message.caption or ""
    text = normalize_text(text)
    
    if not text:
        await update.message.reply_text("❌ Pesan tidak terbaca. Harap forward pesan yang berisi teks, atau ketik /cancel.")
        return C_FORWARD
        
    context.user_data['claim_text'] = text
    claim_type = context.user_data['claim_type']
    
    # Auto-Targeting untuk Owner
    target_id = update.effective_user.id
    target_name = None
    is_sender_owner = str(target_id) == str(OWNER_ID)
    
    if is_sender_owner:
        # Coba ekstrak Codename atau Name dari teks
        cn_match = re.search(r"(?:Codename|Name)\s*[:\-]+\s*(.+)", text, re.IGNORECASE)
        if cn_match:
            parsed_cn = cn_match.group(1).strip()
            async with aiosqlite.connect(DB_PATH) as db:
                async with db.execute("SELECT telegram_id, full_name, codename FROM members WHERE LOWER(codename) = ? OR LOWER(full_name) = ?", (parsed_cn.lower(), parsed_cn.lower())) as cursor:
                    target = await cursor.fetchone()
            if target:
                target_id = target[0]
                target_name = f"{target[1]} ({target[2]})"
                
    context.user_data['claim_target_id'] = target_id
    context.user_data['claim_target_name'] = target_name
    context.user_data['is_auto_approve'] = is_sender_owner
    
    if claim_type == "External":
        # Parsing External
        event_name = "Unknown Event"
        event_match = re.search(r"(?:Event Name|Nama Event|Event|Acara|Title)\s*[-—:]+\s*(.+)", text, re.IGNORECASE)
        if event_match:
            event_name = event_match.group(1).strip()
        else:
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            if lines:
                event_name = lines[0]
                
        # Bersihkan tanggal di belakang nama event (contoh: 25/09/2026-27/09/2026 atau (10/12/24))
        date_pattern = r'[\s\-_—()]*(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}(?:[\s\-_—]+\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4})?)[\s\-_—()]*$'
        date_match = re.search(date_pattern, event_name)
        event_date = date_match.group(1) if date_match else None
        event_name = re.sub(date_pattern, '', event_name).strip()
        
        if len(event_name) > 100:
            event_name = event_name[:97] + "..."
            
        is_competition = False
        type_match = re.search(r"(?:Event\s*)?Type\s*[-—:]+\s*(.+)", text, re.IGNORECASE)
        if type_match and "competition" in type_match.group(1).lower():
            is_competition = True
        elif re.search(r"competition|lomba|juara|1st|2nd|3rd|winner", text, re.IGNORECASE):
            is_competition = True
            
        # Coba cari baris "Placement:"
        place_match = re.search(r"Placement\s*[:\-]*\s*(.+)", text, re.IGNORECASE)
        points = 0
        
        if place_match:
            # Jika user rapi dan ada baris Placement, pencarian aman hanya di baris ini
            placement_text = place_match.group(1).strip().lower()
            if "1st" in placement_text or "satu" in placement_text or "first" in placement_text:
                points = RP_EXT_COMP_1ST if is_competition else RP_EXT_EV_1ST
                cat = "1st Place"
            elif "2nd" in placement_text or "dua" in placement_text or "second" in placement_text:
                points = RP_EXT_COMP_2ND if is_competition else RP_EXT_EV_2ND
                cat = "2nd Place"
            elif "3rd" in placement_text or "tiga" in placement_text or "third" in placement_text:
                points = RP_EXT_COMP_3RD if is_competition else RP_EXT_EV_3RD
                cat = "3rd Place"
            else:
                points = RP_EXT_COMP_PARTICIPANT if is_competition else RP_EXT_EV_PARTICIPANT
                cat = "Participant"
        else:
            # Jika baris Placement typo/hilang, scan seluruh teks TAPI harus ketat!
            # Kita tidak boleh asal cari "2nd" karena bisa saja event "Our 2nd Home"
            # Kita cari "1st place", "juara 1", dll.
            if re.search(r"(1st|first)\s+(place|winner)|juara\s+(1|satu)", text, re.IGNORECASE):
                points = RP_EXT_COMP_1ST if is_competition else RP_EXT_EV_1ST
                cat = "1st Place"
            elif re.search(r"(2nd|second)\s+(place|winner)|juara\s+(2|dua)", text, re.IGNORECASE):
                points = RP_EXT_COMP_2ND if is_competition else RP_EXT_EV_2ND
                cat = "2nd Place"
            elif re.search(r"(3rd|third)\s+(place|winner)|juara\s+(3|tiga)", text, re.IGNORECASE):
                points = RP_EXT_COMP_3RD if is_competition else RP_EXT_EV_3RD
                cat = "3rd Place"
            else:
                points = RP_EXT_COMP_PARTICIPANT if is_competition else RP_EXT_EV_PARTICIPANT
                cat = "Participant"
                
        ext_type_str = "Competition" if is_competition else "Event"
        context.user_data['claim_points'] = points
        context.user_data['claim_event'] = f"[{ext_type_str}] {event_name} ({cat})"
        context.user_data['claim_date'] = event_date
        
        await update.message.reply_text(
            "✅ Bukti terbaca.\n\n"
            "🔗 *Langkah 2:*\nSilakan kirimkan (Paste) **LINK (Tautan)** dari pesan bukti yang barusan Anda forward:",
            parse_mode="Markdown"
        )
        return C_LINK
        
    else:
        await update.message.reply_text(
            "✅ Bukti terbaca.\n\n"
            "🔗 *Langkah 2:*\nSilakan kirimkan (Paste) **LINK (Tautan)** dari pesan bukti yang barusan Anda forward:",
            parse_mode="Markdown"
        )
        return C_LINK

async def claim_internal_total(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.text.isdigit():
        await update.message.reply_text("❌ Harap masukkan HANYA ANGKA (misal: 250). Coba lagi atau /cancel:")
        return C_INTERNAL_TOTAL
        
    context.user_data['claim_points'] = int(update.message.text)
    context.user_data['claim_event'] = "Internal Claim"
    
    return await send_claim_to_admin(update, context)

async def send_claim_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not ADMIN_GID:
        await update.message.reply_text("❌ Error: ADMIN_GID belum disetel di server.")
        return ConversationHandler.END
        
    sender_id = update.effective_user.id
    target_id = context.user_data.get('claim_target_id', sender_id)
    target_name_override = context.user_data.get('claim_target_name')
    is_auto = context.user_data.get('is_auto_approve', False)
    
    # Ambil data user jika tidak ada override
    if not target_name_override:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT full_name, codename FROM members WHERE telegram_id = ?", (target_id,)) as cursor:
                user = await cursor.fetchone()
        name = f"{user[0]} ({user[1]})" if user else str(target_id)
    else:
        name = target_name_override
        
    c_type = context.user_data['claim_type']
    c_link = context.user_data['claim_link']
    c_text = context.user_data['claim_text']
    c_points = context.user_data['claim_points']
    c_event = context.user_data['claim_event']
    c_date = context.user_data.get('claim_date')
    
    # Simpan ke Database
    status = "Approved" if is_auto else "Pending"
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO aia_claims (telegram_id, claim_type, event_name, points, status, claim_link, event_date) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (target_id, c_type, c_event, c_points, status, c_link, c_date)
        )
        claim_id = cursor.lastrowid
        
        if is_auto:
            # Langsung berikan poin jika auto-approve
            await db.execute("UPDATE members SET aia_points = aia_points + ? WHERE telegram_id = ?", (c_points, target_id))
            await db.execute("INSERT INTO point_logs (telegram_id, point_type, amount, reason, issued_by) VALUES (?, 'AIA', ?, ?, ?)",
                             (target_id, c_points, "Auto-Approved AIA RP Claim", sender_id))
        await db.commit()
        
    # Format Pesan ke Admin
    title = f"🔔 *KLAIM RP ({c_type.upper()})*"
    if is_auto: title = f"⚡ *AUTO-APPROVED RP ({c_type.upper()})*"
    
    admin_msg = (
        f"{title}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 *Target:* {name}\n"
        f"🎯 *Event:* {c_event}\n"
        f"💰 *Poin Masuk:* +{c_points} RP\n"
        f"🔗 [Klik untuk Cek Link Bukti]({c_link})\n\n"
        f"📄 *Teks Forward dari User:*\n"
        f"_{c_text[:500]}_"
    )
    if len(c_text) > 500: admin_msg += "...(terpotong)"
    
    if is_auto:
        # Kirim notifikasi tanpa tombol
        await context.bot.send_message(chat_id=ADMIN_GID, text=admin_msg, parse_mode="Markdown", disable_web_page_preview=True)
        await update.message.reply_text(f"⚡ *Auto-Approve Aktif!* Anda mendaftarkan klaim untuk **{name}** sebesar **+{c_points} RP**. Poin langsung dimasukkan ke profilnya.", parse_mode="Markdown")
        try:
            await context.bot.send_message(
                chat_id=target_id, 
                text=f"🎉 *Klaim RP Anda telah diproses oleh Sekretaris!*\nAnda mendapatkan tambahan **+{c_points} RP** untuk event [{c_event}]({c_link}).", 
                parse_mode="Markdown"
            )
        except:
            pass
    else:
        callback_data_approve = f"claim_app_{claim_id}"
        callback_data_reject = f"claim_rej_{claim_id}"
        keyboard = [
            [InlineKeyboardButton(f"✅ Approve (+{c_points} RP)", callback_data=callback_data_approve)],
            [InlineKeyboardButton("❌ Reject", callback_data=callback_data_reject)]
        ]
        await context.bot.send_message(
            chat_id=ADMIN_GID,
            text=admin_msg,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown",
            disable_web_page_preview=True
        )
        await update.message.reply_text(
            f"✅ *Klaim Berhasil Diajukan!*\n"
            f"Sistem mencatat pengajuan **+{c_points} RP** Anda.\n"
            f"Gunakan perintah /myclaims untuk mengecek status persetujuan.",
            parse_mode="Markdown"
        )
        
    return ConversationHandler.END

async def cancel_claim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Klaim RP dibatalkan.")
    return ConversationHandler.END

# --- ADMIN ACTION HANDLER ---
async def admin_claim_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    
    # Format data: claim_app_<claim_id> ATAU claim_rej_<claim_id>
    parts = data.split('_')
    action = parts[1] # app / rej
    claim_id = int(parts[2])
    
    admin_id = query.from_user.id
    
    # Ambil data claim dari database
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT telegram_id, points, status FROM aia_claims WHERE id = ?", (claim_id,)) as cursor:
            claim = await cursor.fetchone()
            
        if not claim:
            await query.answer("Klaim tidak ditemukan di database.")
            return
            
        if claim[2] != "Pending":
            await query.answer("Klaim ini sudah diproses sebelumnya.")
            await query.edit_message_reply_markup(reply_markup=None)
            return
            
        target_id = claim[0]
        amount = claim[1]
        
        if action == "app":
            reason = "Approved AIA RP Claim"
            await db.execute("UPDATE aia_claims SET status = 'Approved' WHERE id = ?", (claim_id,))
            await db.execute("UPDATE members SET aia_points = aia_points + ? WHERE telegram_id = ?", (amount, target_id))
            await db.execute("INSERT INTO point_logs (telegram_id, point_type, amount, reason, issued_by) VALUES (?, 'AIA', ?, ?, ?)",
                             (target_id, amount, reason, admin_id))
            status_text = f"✅ *Approved* +{amount} RP by Admin."
            user_notif = f"🎉 *Klaim RP Anda telah disetujui!*\nAnda mendapatkan tambahan **+{amount} RP**."
        else:
            await db.execute("UPDATE aia_claims SET status = 'Rejected' WHERE id = ?", (claim_id,))
            status_text = f"❌ *Rejected* by Admin."
            user_notif = "❌ *Klaim RP Anda Ditolak oleh Admin.*\nSilakan periksa kembali format klaim Anda atau hubungi Admin untuk penjelasan."
            
        await db.commit()
        
    # Hapus tombol agar tidak dipencet dua kali dan beri label
    await query.edit_message_reply_markup(reply_markup=None)
    await query.message.reply_text(status_text, parse_mode="Markdown")
    
    try:
        await context.bot.send_message(chat_id=target_id, text=user_notif, parse_mode="Markdown")
    except:
        pass
            
    await query.answer()
    
# --- COMMAND /myclaims ---
async def my_claims(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT claim_type, event_name, points, status, timestamp, claim_link FROM aia_claims WHERE telegram_id = ? ORDER BY id DESC LIMIT 5", (user_id,)) as cursor:
            claims = await cursor.fetchall()
            
    if not claims:
        await update.message.reply_text("Anda belum memiliki riwayat pengajuan klaim RP.")
        return
        
    msg = "📋 *Riwayat Klaim RP Anda (5 Terakhir)*\n\n"
    for c in claims:
        icon = "⏳" if c[3] == "Pending" else "✅" if c[3] == "Approved" else "❌"
        msg += f"{icon} *{c[1]}*\n"
        
        # Hyperlink tipe klaim jika ada link-nya
        claim_link = c[5]
        if claim_link:
            tipe_teks = f"[{c[0]}]({claim_link})"
        else:
            tipe_teks = c[0]
            
        msg += f"├ Tipe: {tipe_teks}\n"
        msg += f"├ Poin: +{c[2]}\n"
        msg += f"└ Status: *{c[3]}*\n\n"
        
    await update.message.reply_text(msg, parse_mode="Markdown", disable_web_page_preview=True)

claim_handler = ConversationHandler(
    entry_points=[CommandHandler('claim', claim_start)],
    states={
        C_TYPE: [CallbackQueryHandler(claim_type_callback, pattern='^claim_')],
        C_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, claim_link)],
        C_FORWARD: [MessageHandler(filters.ALL & ~filters.COMMAND, claim_forward)],
        C_INTERNAL_TOTAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, claim_internal_total)]
    },
    fallbacks=[CommandHandler('cancel', cancel_claim)]
)

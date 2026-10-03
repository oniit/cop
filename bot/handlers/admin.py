import logging
import aiosqlite
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DB_PATH, OWNER_ID
from bot.export_utils import generate_monthly_report

# Daftar role yang memiliki hak akses Admin
ADMIN_ROLES = ['SAC', 'DAC', 'Point Secretary', 'Minutes Secretary']

async def is_admin(telegram_id: int) -> bool:
    """Cek apakah user adalah owner atau memiliki jabatan admin"""
    # Jika dia adalah Owner (dari .env), langsung beri akses
    if str(telegram_id) == str(OWNER_ID):
        return True
        
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT position FROM members WHERE telegram_id = ?", (telegram_id,)) as cursor:
            user = await cursor.fetchone()
            
    if user and user[0] in ADMIN_ROLES:
        return True
    return False

async def get_user_by_identifier(identifier: str):
    """Fungsi pembantu untuk mencari user berdasarkan Username, Agent ID, atau Telegram ID"""
    identifier_clean = identifier.replace('@', '')
    async with aiosqlite.connect(DB_PATH) as db:
        # Coba cek apakah ini murni angka (Telegram ID)
        if identifier.isdigit():
            async with db.execute("SELECT telegram_id, full_name, position FROM members WHERE telegram_id = ?", (int(identifier),)) as cursor:
                user = await cursor.fetchone()
                if user: return user
                
        # Jika bukan, cari berdasarkan username atau Agent ID
        async with db.execute("SELECT telegram_id, full_name, position FROM members WHERE username = ? OR agent_id = ?", (identifier_clean, identifier_clean)) as cursor:
            return await cursor.fetchone()

# --- COMMAND /edit_role ---
async def edit_role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ *Access Denied.* You do not have Admin privileges.", parse_mode="Markdown")
        return
        
    if len(context.args) < 2:
        await update.message.reply_text(
            "⚠️ *Invalid format.*\n"
            "Usage: `/edit_role <username/Telegram ID> <new_role>`\n"
            "Example: `/edit_role @vrzdk Point Secretary`",
            parse_mode="Markdown"
        )
        return
        
    identifier = context.args[0]
    # Format otomatis: Jadikan Title Case, lalu perbaiki singkatan khusus
    new_role = " ".join(context.args[1:]).title().replace("Pic", "PIC").replace("Sac", "SAC").replace("Dac", "DAC")
    
    target_user = await get_user_by_identifier(identifier)
    if not target_user:
        await update.message.reply_text(f"❌ Member with Username/Tele ID '{identifier}' not found.")
        return
        
    target_id = target_user[0]
    target_name = target_user[1]
    
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE members SET position = ? WHERE telegram_id = ?", (new_role, target_id))
        await db.commit()
        
    await update.message.reply_text(f"✅ Role for *{target_name}* has been successfully changed to *{new_role}*.", parse_mode="Markdown")


# --- COMMAND /point ---
async def add_poin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ *Access Denied.* You do not have Admin privileges.", parse_mode="Markdown")
        return
        
    if len(context.args) < 3:
        await update.message.reply_text(
            "⚠️ *Invalid format.*\n"
            "Usage: `/point <username/ID...> <amount> <reason>`\n"
            "Example: `/point @user1 @user2 10 Bonus Mingguan`\n"
            "*(Use negative numbers to deduct points)*",
            parse_mode="Markdown"
        )
        return
        
    identifiers = []
    amount_index = -1
    
    # Mencari posisi di mana angka (amount) berada
    for i, arg in enumerate(context.args):
        try:
            int(arg) # Jika bisa jadi angka, berarti ini amount
            amount_index = i
            break
        except ValueError:
            identifiers.append(arg)
            
    if amount_index == -1 or amount_index == 0:
        await update.message.reply_text("❌ Could not find a valid points amount, or no usernames provided.")
        return
        
    amount = int(context.args[amount_index])
    reason = " ".join(context.args[amount_index+1:])
    point_type = 'COP'
    issuer_id = update.effective_user.id
    
    if not reason:
        await update.message.reply_text("❌ Please provide a reason for adding/deducting points.")
        return
        
    success_names = []
    not_found = []
    
    async with aiosqlite.connect(DB_PATH) as db:
        for identifier in identifiers:
            target_user = await get_user_by_identifier(identifier)
            if not target_user:
                not_found.append(identifier)
                continue
                
            target_id = target_user[0]
            target_name = target_user[1]
            
            await db.execute("UPDATE members SET cop_points = cop_points + ? WHERE telegram_id = ?", (amount, target_id))
            await db.execute("INSERT INTO point_logs (telegram_id, point_type, amount, reason, issued_by) VALUES (?, ?, ?, ?, ?)",
                             (target_id, point_type, amount, reason, issuer_id))
            success_names.append(f"*{target_name}*")
            
        await db.commit()
        
    action = "added" if amount > 0 else "deducted"
    msg = ""
    if success_names:
        msg += f"✅ Successfully {action} *{abs(amount)} {point_type} Points* for:\n{', '.join(success_names)}\n📝 Reason: {reason}\n\n"
    if not_found:
        msg += f"❌ Member(s) not found: {', '.join(not_found)}"
        
    if msg:
        await update.message.reply_text(msg.strip(), parse_mode="Markdown")

# --- COMMAND /dashboard ---
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import pandas as pd

def get_dashboard_main_keyboard(telegram_id: int = None):
    keyboard = [
        [InlineKeyboardButton("📊 Member Stats", callback_data="dash_stats"), InlineKeyboardButton("🏆 Point Recap", callback_data="dash_points")],
        [InlineKeyboardButton("🔍 Filter Data Anggota", callback_data="dash_filter_menu")],
        [InlineKeyboardButton("📈 Generate Laporan Bulanan", callback_data="dash_report")]
    ]
    if str(telegram_id) == str(OWNER_ID):
        keyboard.append([InlineKeyboardButton("📥 Raw Database Backup", callback_data="dash_export")])
    return InlineKeyboardMarkup(keyboard)

def get_back_button():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Dashboard", callback_data="dash_main")]])

async def dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ *Access Denied.* You do not have Admin privileges.", parse_mode="Markdown")
        return
        
    await update.message.reply_text(
        "⚙️ *ADMIN DASHBOARD*\nSelect an option below to view or export data:", 
        reply_markup=get_dashboard_main_keyboard(update.effective_user.id), 
        parse_mode="Markdown"
    )

async def dashboard_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    if not await is_admin(query.from_user.id):
        await query.answer("⛔ Access Denied.", show_alert=True)
        return
        
    await query.answer()
    action = query.data
    
    if action == "dash_main":
        await query.edit_message_text(
            "⚙️ *ADMIN DASHBOARD*\nSelect an option below to view or export data:",
            reply_markup=get_dashboard_main_keyboard(query.from_user.id),
            parse_mode="Markdown"
        )
        return
        
    elif action == "dash_stats":
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT position, COUNT(*) FROM members GROUP BY position") as cursor:
                stats = await cursor.fetchall()
            async with db.execute("SELECT COUNT(*) FROM members") as cursor:
                total = await cursor.fetchone()
                
        text = f"📊 *Member Statistics*\nTotal Members: {total[0]}\n\n"
        for row in stats:
            text += f"- {row[0]}: {row[1]}\n"
        await query.edit_message_text(text, reply_markup=get_back_button(), parse_mode="Markdown")
        
    elif action == "dash_points":
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT SUM(aia_points), SUM(cop_points) FROM members") as cursor:
                pts = await cursor.fetchone()
                
        text = f"🏆 *Point Recap*\n\n"
        text += f"Total AIA Points: {pts[0] or 0}\n"
        text += f"Total COP Points: {pts[1] or 0}\n"
        await query.edit_message_text(text, reply_markup=get_back_button(), parse_mode="Markdown")
        
    elif action == "dash_filter_menu":
        keyboard = [
            [InlineKeyboardButton("🟢 Active Members", callback_data="dash_flt_active"), InlineKeyboardButton("🏖️ Resting Members", callback_data="dash_flt_rest")],
            [InlineKeyboardButton("👔 Filter by Jabatan", callback_data="dash_flt_pos")],
            [InlineKeyboardButton("📋 Filter by Attendance", callback_data="dash_flt_att")],
            [InlineKeyboardButton("🔙 Back", callback_data="dash_main")]
        ]
        await query.edit_message_text("🔍 *Filter Data Anggota*\nPilih kriteria filter:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        
    elif action == "dash_flt_active":
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT full_name, position FROM members WHERE status = 'Active'") as cursor:
                rows = await cursor.fetchall()
        text = "🟢 *Active Members*\n\n"
        if not rows: text += "No active members found."
        for r in rows: text += f"- {r[0]} ({r[1]})\n"
        await query.edit_message_text(text[:4000], reply_markup=get_back_button(), parse_mode="Markdown")
        
    elif action == "dash_flt_rest":
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT full_name, position FROM members WHERE status = 'Rest'") as cursor:
                rows = await cursor.fetchall()
        text = "🏖️ *Resting Members*\n\n"
        if not rows: text += "No members are currently resting."
        for r in rows: text += f"- {r[0]} ({r[1]})\n"
        await query.edit_message_text(text[:4000], reply_markup=get_back_button(), parse_mode="Markdown")
        
    elif action == "dash_flt_pos":
        keyboard = [
            [InlineKeyboardButton("SAC/DAC", callback_data="dash_pos_sacdac"), InlineKeyboardButton("Secretaries", callback_data="dash_pos_sec")],
            [InlineKeyboardButton("All PICs", callback_data="dash_pos_pic"), InlineKeyboardButton("Members", callback_data="dash_pos_mem")],
            [InlineKeyboardButton("🔙 Back to Filters", callback_data="dash_filter_menu")]
        ]
        await query.edit_message_text("👔 *Filter Berdasarkan Jabatan*", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        
    elif action.startswith("dash_pos_"):
        cat = action.replace("dash_pos_", "")
        query_str = ""
        title = ""
        
        if cat == "sacdac":
            query_str = "SELECT full_name, position FROM members WHERE position IN ('SAC', 'DAC')"
            title = "👑 SAC & DAC"
        elif cat == "sec":
            query_str = "SELECT full_name, position FROM members WHERE position LIKE '%Secretary%'"
            title = "📝 Secretaries"
        elif cat == "pic":
            query_str = "SELECT full_name, position FROM members WHERE position LIKE 'PIC %'"
            title = "🎯 All PICs"
        elif cat == "mem":
            query_str = "SELECT full_name, position FROM members WHERE position = 'Member'"
            title = "👥 General Members"
            
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(query_str) as cursor:
                rows = await cursor.fetchall()
                
        text = f"{title}\n\n"
        if not rows: text += "No members found in this category."
        for r in rows: text += f"- {r[0]} ({r[1]})\n"
        
        back_kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Job Filters", callback_data="dash_flt_pos")]])
        await query.edit_message_text(text[:4000], reply_markup=back_kb, parse_mode="Markdown")
        
    elif action == "dash_flt_att":
        async with aiosqlite.connect(DB_PATH) as db:
            # Ambil 15 sesi terbaru
            async with db.execute("SELECT session_id, title, is_active FROM attendance_sessions ORDER BY id DESC LIMIT 15") as cursor:
                sessions = await cursor.fetchall()
                
        text = "📋 *Recent Attendance Sessions*\n\n"
        keyboard = []
        if not sessions:
            text += "No attendance sessions found."
        else:
            for s in sessions:
                status_icon = "🟢" if s[2] else "🔴"
                btn_text = f"{status_icon} {s[1]}"
                keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"dash_att_{s[0]}")])
                
        keyboard.append([InlineKeyboardButton("🔙 Back to Filters", callback_data="dash_filter_menu")])
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        
    elif action.startswith("dash_att_"):
        session_id = action.replace("dash_att_", "")
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT title, is_active FROM attendance_sessions WHERE session_id = ?", (session_id,)) as cursor:
                sess = await cursor.fetchone()
                
            if not sess:
                await query.answer("Session not found.", show_alert=True)
                return
                
            async with db.execute("SELECT m.full_name, m.position FROM attendance_logs a JOIN members m ON a.telegram_id = m.telegram_id WHERE a.session_id = ?", (session_id,)) as cursor:
                attendees = await cursor.fetchall()
                
        status = "Active" if sess[1] else "Closed"
        text = f"📋 *Attendance for {sess[0]}*\nStatus: {status}\nTotal Attended: {len(attendees)}\n\n"
        
        if not attendees:
            text += "No one has attended this session yet."
        for a in attendees:
            text += f"- {a[0]} ({a[1]})\n"
            
        back_kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Sessions", callback_data="dash_flt_att")]])
        await query.edit_message_text(text[:4000], reply_markup=back_kb, parse_mode="Markdown")
        
    elif action == "dash_report":
        await query.edit_message_text("Generating Formatted Monthly Report (Excel), please wait...")
        file_path = "Laporan_Bulanan_COP.xlsx"
        
        await generate_monthly_report(DB_PATH, file_path)
            
        with open(file_path, 'rb') as doc:
            await context.bot.send_document(chat_id=query.message.chat_id, document=doc, filename="Laporan_Bulanan_COP.xlsx")
            
        os.remove(file_path)
        await query.message.reply_text(
            "✅ Laporan Bulanan terkirim!\n⚙️ *ADMIN DASHBOARD*",
            reply_markup=get_dashboard_main_keyboard(query.from_user.id),
            parse_mode="Markdown"
        )
        
    elif action == "dash_export":
        if str(query.from_user.id) != str(OWNER_ID):
            await query.answer("⛔ Access Denied. Only Owner can export raw database.", show_alert=True)
            return
            
        await query.edit_message_text("Generating Complete Database Backup (Excel), please wait...")
        
        file_path = "COP_Database_Backup.xlsx"
        async with aiosqlite.connect(DB_PATH) as db:
            with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
                # 1. Members
                async with db.execute("SELECT * FROM members") as cursor:
                    rows = await cursor.fetchall()
                    cols = [desc[0] for desc in cursor.description]
                    if rows: pd.DataFrame(rows, columns=cols).to_excel(writer, sheet_name='Members', index=False)
                    else: pd.DataFrame(columns=cols).to_excel(writer, sheet_name='Members', index=False)
                    
                # 2. Attendance Sessions
                async with db.execute("SELECT * FROM attendance_sessions") as cursor:
                    rows = await cursor.fetchall()
                    cols = [desc[0] for desc in cursor.description]
                    if rows: pd.DataFrame(rows, columns=cols).to_excel(writer, sheet_name='Attendance_Sessions', index=False)
                    else: pd.DataFrame(columns=cols).to_excel(writer, sheet_name='Attendance_Sessions', index=False)
                    
                # 3. Attendance Logs
                async with db.execute("""
                    SELECT a.session_id, s.title, a.telegram_id, m.full_name, a.timestamp 
                    FROM attendance_logs a 
                    LEFT JOIN attendance_sessions s ON a.session_id = s.session_id
                    LEFT JOIN members m ON a.telegram_id = m.telegram_id
                """) as cursor:
                    rows = await cursor.fetchall()
                    cols = ["Session_ID", "Event_Title", "Telegram_ID", "Full_Name", "Timestamp"]
                    if rows: pd.DataFrame(rows, columns=cols).to_excel(writer, sheet_name='Attendance_Logs', index=False)
                    else: pd.DataFrame(columns=cols).to_excel(writer, sheet_name='Attendance_Logs', index=False)
                    
                # 4. Leave Logs (Rest)
                async with db.execute("""
                    SELECT l.id, l.telegram_id, m.full_name, l.leave_date, l.reason 
                    FROM leave_logs l
                    LEFT JOIN members m ON l.telegram_id = m.telegram_id
                """) as cursor:
                    rows = await cursor.fetchall()
                    cols = ["ID", "Telegram_ID", "Full_Name", "Leave_Date_Range", "Reason"]
                    if rows: pd.DataFrame(rows, columns=cols).to_excel(writer, sheet_name='Rest_Logs', index=False)
                    else: pd.DataFrame(columns=cols).to_excel(writer, sheet_name='Rest_Logs', index=False)
                    
                # 5. Point Logs
                async with db.execute("""
                    SELECT p.id, p.telegram_id, m.full_name, p.point_type, p.amount, p.reason, p.issued_by, p.timestamp
                    FROM point_logs p
                    LEFT JOIN members m ON p.telegram_id = m.telegram_id
                """) as cursor:
                    rows = await cursor.fetchall()
                    cols = ["ID", "Telegram_ID", "Full_Name", "Point_Type", "Amount", "Reason", "Issued_By", "Timestamp"]
                    if rows: pd.DataFrame(rows, columns=cols).to_excel(writer, sheet_name='Point_Logs', index=False)
                    else: pd.DataFrame(columns=cols).to_excel(writer, sheet_name='Point_Logs', index=False)
                    
                # 6. AIA Claims
                async with db.execute("""
                    SELECT c.id, c.telegram_id, m.full_name, c.claim_type, c.event_name, c.points, c.status, c.timestamp
                    FROM aia_claims c
                    LEFT JOIN members m ON c.telegram_id = m.telegram_id
                """) as cursor:
                    rows = await cursor.fetchall()
                    cols = ["ID", "Telegram_ID", "Full_Name", "Claim_Type", "Event_Name", "Points", "Status", "Timestamp"]
                    if rows: pd.DataFrame(rows, columns=cols).to_excel(writer, sheet_name='AIA_Claims', index=False)
                    else: pd.DataFrame(columns=cols).to_excel(writer, sheet_name='AIA_Claims', index=False)
        
        with open(file_path, 'rb') as doc:
            await context.bot.send_document(chat_id=query.message.chat_id, document=doc, filename="COP_Database_Backup.xlsx")
            
        os.remove(file_path)
        # Restore dashboard menu
        await query.message.reply_text(
            "✅ Full Database Excel file sent successfully!\n⚙️ *ADMIN DASHBOARD*",
            reply_markup=get_dashboard_main_keyboard(query.from_user.id),
            parse_mode="Markdown"
        )

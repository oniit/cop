import logging
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

from config import BOT_TOKEN
from bot.database import init_db

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

from bot.handlers.general import start, daftar_handler, profil, leaderboard, edit_profile_handler
from bot.handlers.admin import edit_role, add_poin, dashboard, dashboard_callback, cmd_pull, cmd_reload
from bot.handlers.attendance import open_attendance, close_attendance, active_sessions, attendance_button, reopen_attendance_button, close_attendance_button
from bot.handlers.rest import rest_handler, sync_rest_status_job, set_active
from bot.handlers.aia import claim_handler, admin_claim_action, my_claims
from bot.handlers.tags import cmd_cop, cmd_cop_muse, cmd_cop_profile, cmd_structure
from telegram.ext import CallbackQueryHandler
import os
import json

async def setup(application):
    """Fungsi yang dijalankan otomatis saat bot baru menyala"""
    await init_db()
    
    # Cek apakah bot baru saja direstart via /reload
    if os.path.exists(".restart.json"):
        try:
            with open(".restart.json", "r") as f:
                data = json.load(f)
            
            chat_id = data.get("chat_id")
            message_id = data.get("message_id")
            
            if chat_id and message_id:
                await application.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text="✅ Bot berhasil dimulai ulang (Restarted)."
                )
        except Exception as e:
            print(f"Failed to process .restart.json: {e}")
        finally:
            if os.path.exists(".restart.json"):
                os.remove(".restart.json")

def main():
    application = ApplicationBuilder().token(BOT_TOKEN).post_init(setup).build()
    
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('profile', profil))
    application.add_handler(CommandHandler('edit_role', edit_role))
    application.add_handler(CommandHandler('point', add_poin))
    application.add_handler(CommandHandler('leaderboard', leaderboard))
    application.add_handler(CommandHandler('dashboard', dashboard))
    application.add_handler(CommandHandler('active', set_active))
    
    # System Commands
    application.add_handler(CommandHandler('pull', cmd_pull))
    application.add_handler(CommandHandler('reload', cmd_reload))
    
    application.add_handler(daftar_handler)
    application.add_handler(edit_profile_handler)
    application.add_handler(rest_handler)
    application.add_handler(claim_handler)
    application.add_handler(CommandHandler('myclaims', my_claims))
    application.add_handler(CallbackQueryHandler(admin_claim_action, pattern='^claim_(app|rej)_'))
    
    # Handler Tags
    application.add_handler(CommandHandler('cop', cmd_cop))
    application.add_handler(CommandHandler('cop_muse', cmd_cop_muse))
    application.add_handler(CommandHandler('cop_profile', cmd_cop_profile))
    application.add_handler(CommandHandler('structure', cmd_structure))
    
    # Handler Presensi
    application.add_handler(CommandHandler('open_attendance', open_attendance))
    application.add_handler(CommandHandler('close_attendance', close_attendance))
    application.add_handler(CommandHandler('attendance', active_sessions))
    application.add_handler(CallbackQueryHandler(attendance_button, pattern='^att_'))
    application.add_handler(CallbackQueryHandler(reopen_attendance_button, pattern='^reopenatt_'))
    application.add_handler(CallbackQueryHandler(close_attendance_button, pattern='^closeatt_'))
    application.add_handler(CallbackQueryHandler(dashboard_callback, pattern='^dash_'))
    
    # Background Job: Cek status rest secara berkala (setiap jam)
    application.job_queue.run_repeating(sync_rest_status_job, interval=3600, first=10)
    
    print("Bot sedang berjalan... Tekan Ctrl+C untuk berhenti.")
    application.run_polling()

if __name__ == '__main__':
    if not BOT_TOKEN:
        print("PERINGATAN: Belum memasukkan Token Bot di file .env!")
    else:
        main()

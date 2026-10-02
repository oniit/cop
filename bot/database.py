import aiosqlite
import os
import sys

# Menambahkan parent directory ke sys.path agar bisa import config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DB_PATH

async def init_db():
    """Inisialisasi tabel-tabel SQLite"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    
    async with aiosqlite.connect(DB_PATH) as db:
        # Tabel Members
        await db.execute('''
            CREATE TABLE IF NOT EXISTS members (
                telegram_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                codename TEXT,
                agent_id TEXT UNIQUE,
                muse TEXT,
                position TEXT,
                dob TEXT,
                motto TEXT,
                join_date TEXT,
                status TEXT DEFAULT 'Active',
                aia_points INTEGER DEFAULT 0,
                cop_points INTEGER DEFAULT 0
            )
        ''')
        
        # Tabel Izin (Leave)
        await db.execute('''
            CREATE TABLE IF NOT EXISTS leave_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER,
                leave_date TEXT,
                reason TEXT,
                FOREIGN KEY(telegram_id) REFERENCES members(telegram_id)
            )
        ''')
        
        # Tabel Histori Poin
        await db.execute('''
            CREATE TABLE IF NOT EXISTS point_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER,
                point_type TEXT,
                amount INTEGER,
                reason TEXT,
                issued_by INTEGER,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(telegram_id) REFERENCES members(telegram_id)
            )
        ''')
        
        # Tabel Sesi Presensi
        await db.execute('''
            CREATE TABLE IF NOT EXISTS attendance_sessions (
                session_id TEXT PRIMARY KEY,
                title TEXT,
                is_active BOOLEAN DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tabel Histori Presensi (1 member hanya bisa 1x per sesi)
        await db.execute('''
            CREATE TABLE IF NOT EXISTS attendance_logs (
                session_id TEXT,
                telegram_id INTEGER,
                status TEXT DEFAULT 'Present',
                points_awarded INTEGER DEFAULT 0,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (session_id, telegram_id),
                FOREIGN KEY(session_id) REFERENCES attendance_sessions(session_id),
                FOREIGN KEY(telegram_id) REFERENCES members(telegram_id)
            )
        ''')
        
        # Tabel Klaim RP
        await db.execute('''
            CREATE TABLE IF NOT EXISTS aia_claims (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER,
                claim_type TEXT,
                event_name TEXT,
                points INTEGER,
                status TEXT DEFAULT 'Pending',
                claim_link TEXT,
                event_date TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(telegram_id) REFERENCES members(telegram_id)
            )
        ''')
        
        await db.commit()
    print("Database SQLite berhasil diinisialisasi.")

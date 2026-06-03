import aiosqlite, os
from dotenv import load_dotenv

load_dotenv()

DB = os.getenv("DB_PATH", "trikmed.db")
RECORDINGS_DIR = os.getenv("RECORDINGS_DIR", "recordings")

async def init_db():
    os.makedirs(RECORDINGS_DIR, exist_ok=True)
    async with aiosqlite.connect(DB) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, phone TEXT UNIQUE NOT NULL,
            initials TEXT, specialization TEXT,
            patient_mode INTEGER DEFAULT 0,
            total_recordings INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS recordings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recording_id TEXT UNIQUE NOT NULL,
            doctor_id TEXT, doctor_name TEXT, doctor_phone TEXT,
            specialization TEXT, template_id INTEGER, template_text TEXT,
            audio_path TEXT NOT NULL, duration_sec REAL,
            patient_mode INTEGER DEFAULT 0,
            record_date TEXT, record_time TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        await db.commit()

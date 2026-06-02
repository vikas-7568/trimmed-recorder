import aiosqlite

DB_PATH = "trikmed.db"


async def get_db():
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    try:
        yield db
    finally:
        await db.close()


async def _add_column_if_missing(db, table: str, column: str, col_type: str):
    try:
        await db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
    except Exception:
        pass  # column already exists


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT UNIQUE NOT NULL,
                initials TEXT,
                specialization TEXT,
                patient_mode INTEGER DEFAULT 0,
                total_recordings INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS recordings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recording_id TEXT UNIQUE NOT NULL,
                student_id INTEGER,
                student_name TEXT,
                template_id INTEGER,
                template_text TEXT,
                audio_path TEXT NOT NULL,
                duration_sec REAL,
                file_size_bytes INTEGER,
                patient_mode INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Add new columns — safe to run repeatedly (ignored if already exist)
        new_cols = [
            ("doctor_id",      "TEXT"),
            ("doctor_name",    "TEXT"),
            ("doctor_phone",   "TEXT"),
            ("specialization", "TEXT"),
            ("record_date",    "TEXT"),
            ("record_time",    "TEXT"),
            ("audio_url",      "TEXT"),
        ]
        for col, col_type in new_cols:
            await _add_column_if_missing(db, "recordings", col, col_type)

        await db.commit()

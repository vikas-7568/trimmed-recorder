import time
from datetime import datetime
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Depends, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import aiosqlite
from database import init_db, get_db

RECORDINGS_DIR = Path("recordings")
STATIC_DIR = Path("static")

# Create dirs at module level so StaticFiles mount doesn't fail on cold start
RECORDINGS_DIR.mkdir(exist_ok=True)
STATIC_DIR.mkdir(exist_ok=True)

TEMPLATES = [
    {"id": 1,  "category": "fever",     "text": "Dolo 650 twice daily, after meals, 5 days. Pantop 40 morning empty stomach, 7 days. ORS 3 times daily.",                          "hindi_hint": "Fever, pain"},
    {"id": 2,  "category": "diabetes",  "text": "Metformin 500mg morning and evening with food. Glimepiride 1mg morning empty stomach. Telma 40 at bedtime.",                              "hindi_hint": "Diabetes + BP"},
    {"id": 3,  "category": "antibiotic","text": "Azithral 500 once daily, 3 days. Moxikind-CV 625 three times daily, 5 days. Dolo 650 as needed (SOS).",                                  "hindi_hint": "Infection / antibiotic"},
    {"id": 4,  "category": "cough",     "text": "Ascoril LS syrup 2 teaspoons three times daily, 5 days. Levocet once daily at night, 5 days.",                                           "hindi_hint": "Cough / allergy"},
    {"id": 5,  "category": "pediatric", "text": "Calpol 250 twice daily, after meals. ORS 3-4 times a day. Zinc 20mg once daily, 14 days.",                                               "hindi_hint": "Child — fever/diarrhea"},
    {"id": 6,  "category": "BP",        "text": "Amlong 5mg morning. Atenolol 50mg morning. Ecosprin 75 at bedtime after meals.",                                                          "hindi_hint": "High blood pressure"},
    {"id": 7,  "category": "stomach",   "text": "Pantocid IT morning empty stomach, 14 days. Librax twice daily before meals. Cremaffin at bedtime.",                                      "hindi_hint": "Stomach pain / acidity"},
    {"id": 8,  "category": "eye",       "text": "Moxifloxacin eye drops every 2 hours, 5 days. Prednisolone drops 4 times a day. Lubricant drops as needed.",                             "hindi_hint": "Eye infection"},
    {"id": 9,  "category": "skin",      "text": "Betamethasone cream apply morning and evening, 7 days. Levocetirizine once daily at night, 10 days.",                                     "hindi_hint": "Skin rash / itching"},
    {"id": 10, "category": "vitamin",   "text": "Shelcal 500 twice daily, after meals. Neurobion Forte once daily. Vitamin D 60K weekly.",                                                "hindi_hint": "Vitamins / calcium"},
    {"id": 11, "category": "joint",     "text": "Etoricoxib 90mg once daily, 5 days. Take Pantop 40 alongside. Calcium + D3 once daily.",                                                 "hindi_hint": "Joint pain"},
    {"id": 12, "category": "general",   "text": "Augmentin 625 three times daily, 7 days. Dolo 650 twice daily. Sporlac twice daily, alongside.",                                         "hindi_hint": "General infection"},
]


def generate_initials(name: str) -> str:
    words = name.strip().split()
    return "".join(w[0].upper() for w in words if w)[:3]


@asynccontextmanager
async def lifespan(app: FastAPI):
    RECORDINGS_DIR.mkdir(exist_ok=True)
    STATIC_DIR.mkdir(exist_ok=True)
    await init_db()
    yield


app = FastAPI(title="TrikMed Recorder", lifespan=lifespan)


# ── Size limit middleware (50 MB) ─────────────────────────────────────────────
@app.middleware("http")
async def limit_upload_size(request: Request, call_next):
    if request.method == "POST" and request.url.path == "/api/upload":
        cl = request.headers.get("content-length")
        if cl and int(cl) > 50 * 1024 * 1024:
            return JSONResponse({"error": "File too large (max 50 MB)"}, status_code=413)
    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Models ────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    name: str
    phone: str
    specialization: str = ""
    patient_mode: bool = False


# ── Root + PWA files ─────────────────────────────────────────────────────────

@app.get("/")
async def serve_index():
    index = STATIC_DIR / "index.html"
    if not index.exists():
        return JSONResponse({"error": "Frontend not built yet"}, status_code=404)
    return FileResponse(str(index))

@app.get("/manifest.json")
async def serve_manifest():
    f = STATIC_DIR / "manifest.json"
    return FileResponse(str(f), media_type="application/manifest+json")

@app.get("/sw.js")
async def serve_sw():
    # Must be served from root so SW scope covers the whole app
    f = STATIC_DIR / "sw.js"
    return FileResponse(str(f), media_type="application/javascript")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.post("/api/register")
async def register_student(body: RegisterRequest, db: aiosqlite.Connection = Depends(get_db)):
    try:
        async with db.execute("SELECT * FROM students WHERE phone = ?", (body.phone,)) as cur:
            row = await cur.fetchone()

        if row:
            return {
                "student_id":       row["id"],
                "name":             row["name"],
                "phone":            row["phone"],
                "initials":         row["initials"],
                "specialization":   row["specialization"],
                "already_existed":  True,
                "total_recordings": row["total_recordings"],
            }

        initials = generate_initials(body.name)
        async with db.execute(
            "INSERT INTO students (name, phone, initials, specialization, patient_mode) VALUES (?,?,?,?,?)",
            (body.name, body.phone, initials, body.specialization, 1 if body.patient_mode else 0),
        ) as cur:
            student_id = cur.lastrowid
        await db.commit()

        return {
            "student_id":       student_id,
            "name":             body.name,
            "phone":            body.phone,
            "initials":         initials,
            "specialization":   body.specialization,
            "already_existed":  False,
            "total_recordings": 0,
        }
    except Exception as e:
        print(f"Register error: {e}")
        raise HTTPException(status_code=500, detail="Registration failed")


@app.get("/api/student/{phone}")
async def get_student(phone: str, db: aiosqlite.Connection = Depends(get_db)):
    try:
        async with db.execute("SELECT * FROM students WHERE phone = ?", (phone,)) as cur:
            row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Student not found")
        return dict(row)
    except HTTPException:
        raise
    except Exception as e:
        print(f"Get student error: {e}")
        raise HTTPException(status_code=500, detail="Lookup failed")


@app.post("/api/upload")
async def upload_recording(
    audio: UploadFile = File(...),
    student_id: int = Form(...),
    student_name: str = Form(...),
    student_initials: str = Form(...),
    phone_last4: str = Form(...),
    student_phone: str = Form(""),
    doctor_id: str = Form(""),
    specialization: str = Form(""),
    template_id: int = Form(...),
    template_text: str = Form(...),
    duration_sec: float = Form(...),
    patient_mode: int = Form(0),
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        # Use doctor_id from client if provided, otherwise derive from phone
        if not doctor_id:
            doctor_id = f"DR-{student_phone[-6:]}" if len(student_phone) >= 6 else f"DR-{phone_last4}"
        ts           = int(time.time() * 1000)
        recording_id = f"{doctor_id}-{ts}"
        audio_path   = RECORDINGS_DIR / f"{recording_id}.webm"

        content = await audio.read()
        audio_path.write_bytes(content)
        now         = datetime.now()
        record_date = now.strftime("%Y-%m-%d")
        record_time = now.strftime("%H:%M:%S")
        audio_url   = str(audio_path)

        await db.execute(
            """INSERT INTO recordings
               (recording_id, student_id, student_name, template_id, template_text,
                audio_path, duration_sec, file_size_bytes, patient_mode,
                doctor_id, doctor_name, doctor_phone, specialization,
                record_date, record_time, audio_url)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (recording_id, student_id, student_name, template_id, template_text,
             str(audio_path), duration_sec, len(content), patient_mode,
             doctor_id, student_name, student_phone, specialization,
             record_date, record_time, audio_url),
        )
        await db.execute(
            "UPDATE students SET total_recordings = total_recordings + 1 WHERE id = ?",
            (student_id,),
        )
        await db.commit()

        async with db.execute(
            "SELECT total_recordings FROM students WHERE id = ?", (student_id,)
        ) as cur:
            row = await cur.fetchone()

        return {"recording_id": recording_id, "saved": True, "total_recordings": row["total_recordings"] if row else 0}

    except Exception as e:
        print(f"Upload error: {e}")
        raise HTTPException(status_code=500, detail="Upload failed")


@app.get("/api/templates")
async def get_templates():
    return TEMPLATES


@app.get("/api/stats")
async def get_stats(db: aiosqlite.Connection = Depends(get_db)):
    try:
        today = datetime.now().strftime("%Y-%m-%d")

        async with db.execute("SELECT COUNT(*) as cnt FROM recordings") as cur:
            total_recordings = (await cur.fetchone())["cnt"]
        async with db.execute(
            "SELECT COUNT(DISTINCT doctor_id) as cnt FROM recordings WHERE doctor_id IS NOT NULL"
        ) as cur:
            total_doctors = (await cur.fetchone())["cnt"]
        async with db.execute(
            "SELECT COUNT(*) as cnt FROM recordings WHERE COALESCE(record_date, DATE(created_at)) = ?",
            (today,)
        ) as cur:
            today_recordings = (await cur.fetchone())["cnt"]
        async with db.execute(
            """SELECT doctor_id, doctor_name, COUNT(*) as clips_today
               FROM recordings
               WHERE COALESCE(record_date, DATE(created_at)) = ? AND doctor_id IS NOT NULL
               GROUP BY doctor_id, doctor_name
               ORDER BY clips_today DESC""",
            (today,)
        ) as cur:
            today_rows = await cur.fetchall()

        return {
            "today_recordings": today_recordings,
            "total_recordings": total_recordings,
            "total_doctors":    total_doctors,
            "today_doctors":    [
                {"doctor_id": r["doctor_id"], "doctor_name": r["doctor_name"], "clips_today": r["clips_today"]}
                for r in today_rows
            ],
        }
    except Exception as e:
        print(f"Stats error: {e}")
        raise HTTPException(status_code=500, detail="Stats fetch failed")


@app.get("/api/admin/recordings")
async def admin_recordings(
    limit:  int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        async with db.execute(
            """SELECT recording_id, student_name, template_id, template_text,
                      duration_sec, file_size_bytes, patient_mode, created_at
               FROM recordings ORDER BY created_at DESC LIMIT ? OFFSET ?""",
            (limit, offset),
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"Admin recordings error: {e}")
        raise HTTPException(status_code=500, detail="Query failed")


@app.get("/api/doctor/{doctor_id}/recordings")
async def get_doctor_recordings(doctor_id: str, db: aiosqlite.Connection = Depends(get_db)):
    try:
        async with db.execute(
            """SELECT recording_id, doctor_name, doctor_phone, doctor_id,
                      specialization, record_date, record_time,
                      duration_sec, audio_url, template_text
               FROM recordings WHERE doctor_id = ? ORDER BY created_at DESC""",
            (doctor_id,)
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"Doctor recordings error: {e}")
        raise HTTPException(status_code=500, detail="Query failed")


@app.get("/api/recordings/all")
async def get_all_recordings(db: aiosqlite.Connection = Depends(get_db)):
    try:
        async with db.execute(
            """SELECT recording_id, doctor_id, doctor_name, doctor_phone,
                      specialization, record_date, record_time,
                      duration_sec, audio_url, template_text
               FROM recordings ORDER BY created_at DESC"""
        ) as cur:
            rows = await cur.fetchall()

        grouped: dict = {}
        for r in rows:
            r = dict(r)
            did = r["doctor_id"] or "UNKNOWN"
            if did not in grouped:
                grouped[did] = {
                    "doctor_name":    r["doctor_name"],
                    "doctor_phone":   r["doctor_phone"],
                    "specialization": r["specialization"],
                    "total_clips":    0,
                    "recordings":     [],
                }
            grouped[did]["total_clips"] += 1
            grouped[did]["recordings"].append(r)

        return grouped
    except Exception as e:
        print(f"All recordings error: {e}")
        raise HTTPException(status_code=500, detail="Query failed")


@app.get("/api/audio/{recording_id}")
async def get_audio(recording_id: str):
    try:
        audio_path = RECORDINGS_DIR / f"{recording_id}.webm"
        if not audio_path.exists():
            raise HTTPException(status_code=404, detail="Audio file not found")
        return FileResponse(str(audio_path), media_type="audio/webm")
    except HTTPException:
        raise
    except Exception as e:
        print(f"Audio error: {e}")
        raise HTTPException(status_code=500, detail="Audio fetch failed")


# ── Static assets — must be last so API routes win ───────────────────────────
app.mount("/static", StaticFiles(directory="static"), name="static")

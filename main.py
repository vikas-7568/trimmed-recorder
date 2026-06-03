from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from datetime import datetime
from database import init_db, DB
import aiosqlite, os, time

@asynccontextmanager
async def lifespan(app):
    await init_db()
    yield

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"],
    allow_methods=["*"], allow_headers=["*"])

TEMPLATES = [
    {"id":1,"text":"Dolo 650 do baar roz, khana ke baad, 5 din. Pantop 40 subah khali pet. ORS teen baar roz."},
    {"id":2,"text":"Metformin 500mg subah shaam khane ke saath. Glimepiride 1mg subah khali pet. Telma 40 raat ko."},
    {"id":3,"text":"Azithral 500 ek baar roz 3 din. Moxikind-CV 625 teen baar roz 5 din. Dolo 650 zarurat ho to."},
    {"id":4,"text":"Ascoril syrup do chammach teen baar roz 5 din. Levocet ek baar roz raat ko 5 din."},
    {"id":5,"text":"Calpol 250 do baar roz. ORS din mein 3-4 baar. Zinc 20mg ek baar roz 14 din."},
    {"id":6,"text":"Amlong 5mg subah. Atenolol 50mg subah. Ecosprin 75 raat ko khana ke baad."},
    {"id":7,"text":"Pantocid IT subah khali pet 14 din. Librax do baar roz khane se pehle. Cremaffin raat ko."},
    {"id":8,"text":"Moxifloxacin eye drops har 2 ghante 5 din. Prednisolone drops din mein 4 baar. Lubricant drops."},
    {"id":9,"text":"Betamethasone cream subah shaam 7 din. Levocetirizine ek baar raat ko 10 din."},
    {"id":10,"text":"Shelcal 500 do baar roz khane ke baad. Neurobion Forte ek baar roz. Vitamin D 60K weekly."},
    {"id":11,"text":"Etoricoxib 90mg ek baar roz 5 din. Pantop 40 saath mein lo. Calcium D3 ek baar roz."},
    {"id":12,"text":"Augmentin 625 teen baar roz 7 din. Dolo 650 do baar roz. Sporlac do baar roz."},
]

@app.get("/api/templates")
async def get_templates():
    return TEMPLATES

@app.post("/api/register")
async def register(data: dict):
    name = data.get("name","").strip()
    phone = data.get("phone","").strip()
    if not name or not phone:
        raise HTTPException(400, "Required")
    initials = "".join(w[0].upper() for w in name.split() if w)[:3]
    pm = 1 if data.get("patient_mode") else 0
    spec = data.get("specialization","")
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        row = await (await db.execute(
            "SELECT * FROM students WHERE phone=?", (phone,))).fetchone()
        if row:
            return {**dict(row), "already_existed": True}
        await db.execute(
            "INSERT INTO students (name,phone,initials,specialization,patient_mode) VALUES (?,?,?,?,?)",
            (name,phone,initials,spec,pm))
        await db.commit()
        row = await (await db.execute(
            "SELECT * FROM students WHERE phone=?", (phone,))).fetchone()
        return {**dict(row), "already_existed": False}

@app.post("/api/upload")
async def upload(
    audio: UploadFile = File(...),
    student_name: str = Form(""),
    student_phone: str = Form(""),
    doctor_id: str = Form(""),
    specialization: str = Form(""),
    template_id: int = Form(0),
    template_text: str = Form(""),
    duration_sec: float = Form(0),
    patient_mode: int = Form(0),
):
    rid = (doctor_id or "DR-000000") + "-" + str(int(time.time()*1000))
    path = f"recordings/{rid}.webm"
    with open(path, "wb") as f:
        f.write(await audio.read())
    today = datetime.now().strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB) as db:
        await db.execute("""INSERT INTO recordings
            (recording_id,doctor_id,doctor_name,doctor_phone,specialization,
             template_id,template_text,audio_path,duration_sec,patient_mode,
             record_date,record_time)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (rid,doctor_id,student_name,student_phone,specialization,
             template_id,template_text,path,duration_sec,patient_mode,
             today,datetime.now().strftime("%H:%M:%S")))
        await db.execute(
            "UPDATE students SET total_recordings=total_recordings+1 WHERE phone=?",
            (student_phone,))
        await db.commit()
    return {"recording_id": rid, "saved": True}

@app.get("/api/audio/{rid}")
async def audio(rid: str):
    for ext in [".webm",".mp3",".wav"]:
        p = f"recordings/{rid}{ext}"
        if os.path.exists(p): return FileResponse(p)
    raise HTTPException(404)

@app.get("/api/stats")
async def stats():
    today = datetime.now().strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB) as db:
        total = (await (await db.execute("SELECT COUNT(*) FROM recordings")).fetchone())[0]
        tc = (await (await db.execute(
            "SELECT COUNT(*) FROM recordings WHERE record_date=?", (today,))).fetchone())[0]
        docs = await (await db.execute("""
            SELECT doctor_id,doctor_name,COUNT(*) FROM recordings
            WHERE record_date=? GROUP BY doctor_id""", (today,))).fetchall()
        return {"total_recordings":total,"today_recordings":tc,
                "today_doctors":[{"doctor_id":r[0],"doctor_name":r[1],
                "clips_today":r[2]} for r in docs]}

@app.get("/api/doctor/{doctor_id}/recordings")
async def doctor_recordings(doctor_id: str):
    async with aiosqlite.connect(DB) as db:
        rows = await (await db.execute("""
            SELECT recording_id, duration_sec, record_date,
            record_time, template_text
            FROM recordings WHERE doctor_id=?
            ORDER BY created_at DESC LIMIT 50
        """, (doctor_id,))).fetchall()
        return [{"id":r[0],"duration":r[1],"date":r[2],
                 "time":r[3],"template":r[4]} for r in rows]

app.mount("/", StaticFiles(directory="static", html=True), name="static")

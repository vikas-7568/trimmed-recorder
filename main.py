from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from database import init_db, DB, RECORDINGS_DIR
from dotenv import load_dotenv
import aiosqlite, os, time, random, string
import resend

load_dotenv()

@asynccontextmanager
async def lifespan(app):
    await init_db()
    yield

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"],
    allow_methods=["*"], allow_headers=["*"])

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "trikmed@admin2026")
OTP_EXPIRE = int(os.getenv("OTP_EXPIRE_MINUTES", "10"))

def send_otp_email(to_email: str, otp: str, doctor_name: str):
    resend.api_key = os.getenv("RESEND_API_KEY")
    resend.Emails.send({
        "from": "TrikMed <onboarding@resend.dev>",
        "to": to_email,
        "subject": f"Your TrikMed verification code: {otp}",
        "html": f"""
        <div style="font-family:sans-serif;max-width:400px;
          margin:0 auto;padding:30px">
          <div style="background:#0F1F3D;padding:20px;
            border-radius:12px;text-align:center;margin-bottom:20px">
            <span style="color:white;font-size:24px;font-weight:900">
              TrikMed</span>
          </div>
          <p>Hi Dr. {doctor_name},</p>
          <div style="background:#f8f8f8;border-radius:12px;
            padding:24px;text-align:center;margin:20px 0">
            <p style="color:#666;font-size:13px;margin:0 0 8px">
              YOUR VERIFICATION CODE</p>
            <p style="font-size:42px;font-weight:900;
              color:#C0392B;letter-spacing:8px;margin:0">
              {otp}</p>
            <p style="color:#999;font-size:12px;margin:8px 0 0">
              Valid for 10 minutes</p>
          </div>
          <p style="color:#999;font-size:12px">
            If you did not request this, ignore this email.</p>
        </div>"""
    })

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
    path = f"{RECORDINGS_DIR}/{rid}.webm"
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
        p = f"{RECORDINGS_DIR}/{rid}{ext}"
        if os.path.exists(p): return FileResponse(p)
    raise HTTPException(404)

@app.get("/api/stats")
async def stats(doctor_id: str = ""):
    today = datetime.now().strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB) as db:
        if doctor_id:
            total = (await (await db.execute(
                "SELECT COUNT(*) FROM recordings WHERE doctor_id=?",
                (doctor_id,))).fetchone())[0]
            tc = (await (await db.execute(
                "SELECT COUNT(*) FROM recordings WHERE doctor_id=? AND record_date=?",
                (doctor_id, today))).fetchone())[0]
            docs = await (await db.execute("""
                SELECT doctor_id, doctor_name, COUNT(*)
                FROM recordings
                WHERE doctor_id=? AND record_date=?
                GROUP BY doctor_id""",
                (doctor_id, today))).fetchall()
        else:
            total = (await (await db.execute(
                "SELECT COUNT(*) FROM recordings")).fetchone())[0]
            tc = (await (await db.execute(
                "SELECT COUNT(*) FROM recordings WHERE record_date=?",
                (today,))).fetchone())[0]
            docs = await (await db.execute("""
                SELECT doctor_id, doctor_name, COUNT(*)
                FROM recordings WHERE record_date=?
                GROUP BY doctor_id""", (today,))).fetchall()
        return {
            "total_recordings": total,
            "today_recordings": tc,
            "today_doctors": [
                {"doctor_id":r[0],"doctor_name":r[1],"clips_today":r[2]}
                for r in docs
            ]
        }

@app.post("/api/admin/login")
async def admin_login(data: dict):
    if data.get("password") != ADMIN_PASSWORD:
        raise HTTPException(403, "Wrong password")
    return {"token": "admin-" + ADMIN_PASSWORD, "success": True}

@app.get("/api/admin/all-recordings")
async def all_recordings(token: str = ""):
    if token != "admin-" + ADMIN_PASSWORD:
        raise HTTPException(403, "Unauthorized")
    async with aiosqlite.connect(DB) as db:
        rows = await (await db.execute("""
            SELECT recording_id, doctor_id, doctor_name,
            doctor_phone, specialization, duration_sec,
            record_date, record_time, patient_mode, template_text
            FROM recordings ORDER BY created_at DESC
        """)).fetchall()
        return [{"id":r[0],"doctor_id":r[1],"doctor_name":r[2],
                 "phone":r[3],"spec":r[4],"duration":r[5],
                 "date":r[6],"time":r[7],"patient":r[8],
                 "template":r[9]} for r in rows]

@app.get("/api/admin/doctors")
async def all_doctors(token: str = ""):
    if token != "admin-" + ADMIN_PASSWORD:
        raise HTTPException(403, "Unauthorized")
    async with aiosqlite.connect(DB) as db:
        rows = await (await db.execute("""
            SELECT s.name, s.phone, s.specialization,
            s.total_recordings, s.created_at,
            COUNT(r.id) as actual_count
            FROM students s
            LEFT JOIN recordings r ON s.phone = r.doctor_phone
            GROUP BY s.id ORDER BY actual_count DESC
        """)).fetchall()
        return [{"name":r[0],"phone":r[1],"spec":r[2],
                 "total":r[5],"joined":r[4]} for r in rows]

@app.get("/api/admin/export-csv")
async def export_csv(token: str = ""):
    if token != "admin-" + ADMIN_PASSWORD:
        raise HTTPException(403, "Unauthorized")
    import csv, io
    async with aiosqlite.connect(DB) as db:
        rows = await (await db.execute("""
            SELECT recording_id, doctor_name, doctor_phone,
            specialization, duration_sec, record_date,
            record_time, patient_mode, template_text
            FROM recordings ORDER BY record_date DESC
        """)).fetchall()
    output = io.StringIO()
    w = csv.writer(output)
    w.writerow(["Recording ID","Doctor Name","Phone",
                "Specialization","Duration(sec)","Date",
                "Time","Patient Present","Template"])
    w.writerows(rows)
    from fastapi.responses import Response
    return Response(content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition":
            "attachment; filename=trikmed_recordings.csv"})

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

@app.post("/api/send-otp")
async def send_otp(data: dict):
    email = data.get("email","").strip().lower()
    phone = data.get("phone","").strip()
    name  = data.get("name","").strip()
    if not email or not phone or not name:
        raise HTTPException(400, "Required fields missing")
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        existing = await (await db.execute(
            "SELECT * FROM students WHERE phone=? AND otp_verified=1",
            (phone,))).fetchone()
        if existing:
            return {"already_registered": True, "student": dict(existing)}
    otp = ''.join(random.choices(string.digits, k=6))
    expires = (datetime.now() + timedelta(minutes=OTP_EXPIRE)).strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB) as db:
        await db.execute("DELETE FROM otp_store WHERE phone=?", (phone,))
        await db.execute(
            "INSERT INTO otp_store (email,phone,otp,expires_at) VALUES (?,?,?,?)",
            (email, phone, otp, expires))
        await db.commit()
    try:
        send_otp_email(email, otp, name)
    except Exception as e:
        raise HTTPException(500, f"Email failed: {str(e)}")
    masked = email[:3] + "***" + email[email.index('@'):]
    return {"sent": True, "email": masked}

@app.post("/api/verify-otp")
async def verify_otp(data: dict):
    phone = data.get("phone","").strip()
    otp   = data.get("otp","").strip()
    name  = data.get("name","").strip()
    email = data.get("email","").strip().lower()
    spec  = data.get("specialization","")
    pm    = 1 if data.get("patient_mode") else 0
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        row = await (await db.execute("""
            SELECT * FROM otp_store
            WHERE phone=? AND otp=? AND used=0
            AND expires_at > datetime('now','localtime')
            ORDER BY id DESC LIMIT 1""",
            (phone, otp))).fetchone()
        if not row:
            raise HTTPException(400, "Invalid or expired OTP")
        await db.execute("UPDATE otp_store SET used=1 WHERE id=?", (row["id"],))
        initials = "".join(w[0].upper() for w in name.split() if w)[:3]
        existing = await (await db.execute(
            "SELECT * FROM students WHERE phone=?", (phone,))).fetchone()
        if existing:
            await db.execute(
                "UPDATE students SET otp_verified=1, email=? WHERE phone=?",
                (email, phone))
        else:
            await db.execute("""
                INSERT INTO students
                (name,phone,initials,specialization,patient_mode,email,otp_verified)
                VALUES (?,?,?,?,?,?,1)""",
                (name, phone, initials, spec, pm, email))
        await db.commit()
        student = await (await db.execute(
            "SELECT * FROM students WHERE phone=?", (phone,))).fetchone()
        return dict(student)

app.mount("/", StaticFiles(directory="static", html=True), name="static")

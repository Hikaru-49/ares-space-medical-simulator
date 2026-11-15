"""
FastAPI HMAC-Signed Hardware Telemetry Ingestion Endpoint.
Run alongside Streamlit: uvicorn ingest_api:app --port 8085
"""
import hmac
import hashlib
import sqlite3
from contextlib import closing
from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel
from db import DB_FILE, utc_now

HMAC_SECRET = b"ares-hardware-shared-secret-key-2026"
app = FastAPI(title="A.R.E.S. Hardware Telemetry Ingestion Gateway")

class TelemetryPacket(BaseModel):
    astro_id: str
    device_mac: str
    hr: int
    sys_bp: int
    dia_bp: int
    sleep: float
    bone_t: float
    muscle_idx: float
    radiation_msv: float

@app.post("/api/v1/telemetry")
async def ingest_packet(packet: TelemetryPacket, request: Request, x_ares_signature: str = Header(None)):
    raw_body = await request.body()
    expected_sig = hmac.new(HMAC_SECRET, raw_body, hashlib.sha256).hexdigest()
    if not x_ares_signature or not hmac.compare_digest(expected_sig, x_ares_signature):
        raise HTTPException(status_code=401, detail="Invalid HMAC-SHA256 hardware signature.")

    now = utc_now()
    with closing(sqlite3.connect(DB_FILE)) as conn, conn:
        c = conn.cursor()
        c.execute("SELECT MAX(day) FROM logs WHERE astro_id = ?", (packet.astro_id,))
        next_day = (c.fetchone()[0] or 14) + 1
        c.execute('''INSERT INTO logs (
            timestamp, astro_id, day, hr, sys_bp, dia_bp, sleep, bone_t, muscle_idx,
            radiation_msv, mood_score, stress_score, calories, water_intake, body_temp, glucose, source
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (
            now, packet.astro_id, next_day, packet.hr, packet.sys_bp, packet.dia_bp,
            packet.sleep, packet.bone_t, packet.muscle_idx, packet.radiation_msv,
            8, 3, 2600, 2.8, 37.0, 90, f"FASTAPI-HMAC:{packet.device_mac}"
        ))
        c.execute("INSERT INTO audit_log VALUES (NULL, ?, 'FASTAPI_GATEWAY', 'HMAC_PACKET', ?, ?)",
                  (now, packet.astro_id, f"Verified HMAC packet from {packet.device_mac}"))
    return {"status": "committed", "day": next_day, "timestamp": now}

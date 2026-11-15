import sqlite3
import hashlib
import os
import hmac
from datetime import datetime, timezone
from contextlib import closing
import pandas as pd
import numpy as np
import streamlit as st
from config import ENV_SPECS, PROTOCOLS

DB_FILE = os.path.join(os.path.dirname(__file__), "ares_telemetry.db")

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_WINDOW_SECONDS = 300

def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

def utc_timestamp() -> int:
    return int(datetime.now(timezone.utc).timestamp())

def check_stale_telemetry(timestamp_str: str, threshold_hours: float = 24.0) -> tuple[bool, float]:
    """Returns (is_stale, age_hours) for a UTC timestamp string."""
    try:
        dt = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S UTC").replace(tzinfo=timezone.utc)
        age_hours = (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0
        return (age_hours > threshold_hours), round(max(0.0, age_hours), 1)
    except Exception:
        return True, -1.0

def hash_pin(pin: str, salt_hex: str = None) -> str:
    salt = bytes.fromhex(salt_hex) if salt_hex else os.urandom(16)
    digest = hashlib.scrypt(pin.strip().encode("utf-8"), salt=salt, n=16384, r=8, p=1, dklen=32)
    return f"{salt.hex()}${digest.hex()}"

def verify_pin(pin: str, stored_hash: str) -> bool:
    try:
        salt_hex, _ = stored_hash.split("$", 1)
        expected = hash_pin(pin, salt_hex)
        return hmac.compare_digest(expected, stored_hash)
    except Exception:
        return False

def apply_protocol_effects(vitals: dict, protocol_key: str) -> dict:
    updated = dict(vitals)
    effects = PROTOCOLS.get(protocol_key, {}).get("effects", {})
    if not effects:
        return updated

    updated["hr"] = int(np.clip(updated["hr"] + effects.get("hr", 0), 48, 180))
    updated["sys_bp"] = int(np.clip(updated["sys_bp"] + effects.get("sys_bp", 0), 85, 210))
    updated["dia_bp"] = int(np.clip(updated.get("dia_bp", 78) + effects.get("dia_bp", 0), 50, 130))
    updated["sleep"] = round(float(np.clip(updated["sleep"] + effects.get("sleep", 0.0), 1.0, 10.0)), 1)
    updated["bone_t"] = round(float(np.clip(updated["bone_t"] + effects.get("bone_t", 0.0), -4.5, 1.5)), 2)
    updated["muscle_idx"] = round(float(np.clip(updated["muscle_idx"] + effects.get("muscle_idx", 0.0), 40.0, 100.0)), 1)
    updated["radiation_msv"] = round(float(max(0.0, updated["radiation_msv"] + effects.get("radiation_msv", 0.0))), 1)
    updated["mood_score"] = int(np.clip(updated.get("mood_score", 8) + effects.get("mood_score", 0), 1, 10))
    updated["stress_score"] = int(np.clip(updated.get("stress_score", 3) + effects.get("stress_score", 0), 1, 10))
    return updated

def evaluate_system_status(astro: dict, env_name: str) -> dict:
    spec = ENV_SPECS[env_name]
    status = {}
    status["brain"] = (
        "CRITICAL" if (astro["sleep"] < 4.5 or astro.get("stress_score", 3) >= 8)
        else ("WARNING" if (astro["sleep"] < spec["sleep_min"] or astro.get("stress_score", 3) >= 6) else "NOMINAL")
    )
    status["heart"] = (
        "CRITICAL" if (astro["hr"] > spec["hr_max"] + 15 or astro["sys_bp"] > spec["sys_max"] + 15)
        else ("WARNING" if (astro["hr"] > spec["hr_max"] or astro["sys_bp"] > spec["sys_max"]) else "NOMINAL")
    )
    status["bone"] = (
        "CRITICAL" if astro["bone_t"] < spec["bone_min"] - 0.6
        else ("WARNING" if astro["bone_t"] < spec["bone_min"] else "NOMINAL")
    )
    status["muscle"] = (
        "CRITICAL" if astro["muscle_idx"] < spec["muscle_min"] - 7.0
        else ("WARNING" if astro["muscle_idx"] < spec["muscle_min"] else "NOMINAL")
    )
    status["radiation"] = (
        "CRITICAL" if astro["radiation_msv"] > spec["rad_limit"] + 20.0
        else ("WARNING" if astro["radiation_msv"] > spec["rad_limit"] else "NOMINAL")
    )
    return status

def calculate_risk(astro: dict) -> int:
    risk = 0
    if astro["hr"] > 100: risk += 20
    if astro["sleep"] < 5.0: risk += 20
    if astro["bone_t"] < -2.0: risk += 20
    if astro["muscle_idx"] < 82.0: risk += 20
    if astro["radiation_msv"] > 100.0: risk += 20
    if astro.get("stress_score", 3) >= 8: risk += 15
    if astro.get("calories", 2500) < 2000: risk += 10
    return int(min(max(risk, 5), 100))

def calculate_eva_readiness_detailed(astro: dict, env_name: str) -> tuple[str, int, list[dict]]:
    """Returns (eva_state, total_probability_pct, contributing_factors_list)."""
    spec = ENV_SPECS[env_name]
    prob = 98
    factors = []

    hr_pen = int((astro["hr"] - spec["hr_max"]) * 1.2) if astro["hr"] > spec["hr_max"] else 0
    prob -= hr_pen
    factors.append({"factor": "Cardiovascular (HR)", "value": f"{astro['hr']} bpm (≤{spec['hr_max']})", "delta": f"-{hr_pen}%" if hr_pen else "0% (Nominal)"})

    slp_pen = int((spec["sleep_min"] - astro["sleep"]) * 8) if astro["sleep"] < spec["sleep_min"] else 0
    prob -= slp_pen
    factors.append({"factor": "Circadian Reserve (Sleep)", "value": f"{astro['sleep']} h (≥{spec['sleep_min']}h)", "delta": f"-{slp_pen}%" if slp_pen else "0% (Nominal)"})

    myo_pen = int((spec["muscle_min"] - astro["muscle_idx"]) * 1.8) if astro["muscle_idx"] < spec["muscle_min"] else 0
    prob -= myo_pen
    factors.append({"factor": "Neuromuscular (Myo Index)", "value": f"{astro['muscle_idx']}% (≥{spec['muscle_min']}%)", "delta": f"-{myo_pen}%" if myo_pen else "0% (Nominal)"})

    bmd_pen = int(abs(spec["bone_min"] - astro["bone_t"]) * 12) if astro["bone_t"] < spec["bone_min"] else 0
    prob -= bmd_pen
    factors.append({"factor": "Skeletal Load (BMD T-Score)", "value": f"{astro['bone_t']} (≥{spec['bone_min']})", "delta": f"-{bmd_pen}%" if bmd_pen else "0% (Nominal)"})

    rad_pen = 18 if astro["radiation_msv"] > spec["rad_limit"] else 0
    prob -= rad_pen
    factors.append({"factor": "Simulated Dosimetry", "value": f"{astro['radiation_msv']} mSv (≤{spec['rad_limit']})", "delta": f"-{rad_pen}%" if rad_pen else "0% (Nominal)"})

    prob = max(12, min(99, prob))
    return ("EVA READY" if prob >= 75 else "EVA RESTRICTED"), prob, factors

def init_db():
    with closing(sqlite3.connect(DB_FILE, isolation_level=None)) as conn:
        c = conn.cursor()
        c.execute("BEGIN IMMEDIATE")
        try:
            c.execute('''CREATE TABLE IF NOT EXISTS crew (
                id TEXT PRIMARY KEY,
                pin_hash TEXT NOT NULL,
                name TEXT NOT NULL,
                role TEXT NOT NULL,
                device_mac TEXT NOT NULL,
                env TEXT NOT NULL
            )''')
            c.execute('''CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                astro_id TEXT NOT NULL,
                day INTEGER NOT NULL,
                hr INTEGER NOT NULL,
                sys_bp INTEGER NOT NULL,
                dia_bp INTEGER NOT NULL,
                sleep REAL NOT NULL,
                bone_t REAL NOT NULL,
                muscle_idx REAL NOT NULL,
                radiation_msv REAL NOT NULL,
                mood_score INTEGER NOT NULL,
                stress_score INTEGER NOT NULL,
                calories INTEGER NOT NULL,
                water_intake REAL NOT NULL,
                body_temp REAL NOT NULL,
                glucose INTEGER NOT NULL,
                source TEXT NOT NULL
            )''')
            c.execute('''CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                astro_id TEXT NOT NULL,
                protocol_key TEXT NOT NULL,
                protocol_label TEXT NOT NULL,
                target_env TEXT NOT NULL,
                assigned_by TEXT NOT NULL,
                status TEXT NOT NULL,
                verification_source TEXT NOT NULL
            )''')
            c.execute('''CREATE TABLE IF NOT EXISTS symptoms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                astro_id TEXT NOT NULL,
                symptom TEXT NOT NULL,
                severity INTEGER NOT NULL,
                day INTEGER NOT NULL
            )''')
            c.execute('''CREATE TABLE IF NOT EXISTS inventory (
                item TEXT PRIMARY KEY,
                quantity INTEGER NOT NULL
            )''')
            c.execute('''CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                actor TEXT NOT NULL,
                action TEXT NOT NULL,
                target_id TEXT NOT NULL,
                details TEXT NOT NULL
            )''')
            c.execute('''CREATE TABLE IF NOT EXISTS auth_attempts (
                target_id TEXT PRIMARY KEY,
                failed_count INTEGER NOT NULL,
                first_failed_ts INTEGER NOT NULL,
                locked_until_ts INTEGER NOT NULL
            )''')

            inv_seed = [
                ("Sterile Bandages", 50),
                ("Analgesics / Ibuprofen", 100),
                ("IV Saline Fluids (1L)", 25),
                ("Emergency Oxygen Canisters", 20),
                ("Broad-Spectrum Antibiotics", 40),
                ("B-Complex Neuro-Ocular Supplement", 60)
            ]
            c.executemany("INSERT OR IGNORE INTO inventory VALUES (?, ?)", inv_seed)

            c.execute("SELECT COUNT(*) FROM crew")
            if c.fetchone()[0] == 0:
                now = utc_now()
                c.execute("INSERT INTO crew VALUES (?,?,?,?,?,?)",
                          ("ASTRO-001", hash_pin("1111"), "Cmdr. Elena Vance", "Mission Commander", "00:1A:7D:DA:71:13", "Earth Orbit (LEO Station)"))
                c.execute("INSERT INTO crew VALUES (?,?,?,?,?,?)",
                          ("ASTRO-002", hash_pin("2222"), "Dr. Marcus Chen", "Payload Specialist", "00:1A:7D:DA:71:99", "Deep Space Transit"))

                for d in range(1, 15):
                    c.execute('''INSERT INTO logs (
                        timestamp, astro_id, day, hr, sys_bp, dia_bp, sleep, bone_t, muscle_idx,
                        radiation_msv, mood_score, stress_score, calories, water_intake, body_temp, glucose, source
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (
                        now, "ASTRO-001", d, int(64 + np.random.normal(0, 2)), int(116 + np.random.normal(0, 3)), 74,
                        round(7.6 + np.random.normal(0, 0.2), 1), round(-0.4 - d * 0.01, 2), round(98.4 - d * 0.03, 1),
                        round(12.0 + d * 0.2, 1), 9, 2, 2800, 3.1, 36.8, 88, "SIM-SENSOR:00:1A:7D:DA:71:13"
                    ))
                    c.execute('''INSERT INTO logs (
                        timestamp, astro_id, day, hr, sys_bp, dia_bp, sleep, bone_t, muscle_idx,
                        radiation_msv, mood_score, stress_score, calories, water_intake, body_temp, glucose, source
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (
                        now, "ASTRO-002", d, int(74 + d * 2.4), int(120 + d * 2.0), 94,
                        round(max(2.6, 7.2 - d * 0.28), 1), round(-0.8 - d * 0.10, 2), round(94.0 - d * 0.9, 1),
                        round(85.0 + d * 3.8, 1), 4, 8, 1920, 1.7, 37.3, 106, "SIM-SENSOR:00:1A:7D:DA:71:99"
                    ))

                seed_tasks = [
                    (now, "ASTRO-002", "ARED_AXIAL", PROTOCOLS["ARED_AXIAL"]["label"], "Martian Surface Habitat", "Flight Surgeon Console", "PENDING HARDWARE SYNC", "Awaiting ARED Strain-Gauge Packet"),
                    (now, "ASTRO-002", "CIRCADIAN_PSG", PROTOCOLS["CIRCADIAN_PSG"]["label"], "Martian Surface Habitat", "Flight Surgeon Console", "PENDING HARDWARE SYNC", "Awaiting Actigraphy Watch Sync"),
                    (now, "ASTRO-002", "SHIELDING_ROTATION", PROTOCOLS["SHIELDING_ROTATION"]["label"], "Martian Surface Habitat", "Flight Surgeon Console", "PENDING HARDWARE SYNC", "Awaiting Dosimeter Verification"),
                    (now, "ASTRO-001", "CEVIS_AEROBIC", PROTOCOLS["CEVIS_AEROBIC"]["label"], "Earth Orbit (LEO Station)", "Flight Surgeon Console", "VERIFIED & LOGGED", "SIM-SENSOR:00:1A:7D:DA:71:13")
                ]
                c.executemany('''INSERT INTO tasks (
                    timestamp, astro_id, protocol_key, protocol_label, target_env, assigned_by, status, verification_source
                ) VALUES (?,?,?,?,?,?,?,?)''', seed_tasks)

                c.execute("INSERT INTO symptoms VALUES (NULL, ?, 'ASTRO-002', 'Neuro-Ocular Visual Shift / Phosphenes', 6, 12)", (now,))
                c.execute("INSERT INTO symptoms VALUES (NULL, ?, 'ASTRO-002', 'Circadian Sleep Fragmentation', 8, 14)", (now,))
                c.execute("INSERT INTO audit_log VALUES (NULL, ?, 'SYSTEM', 'DB_SEED', 'ALL', 'Initialized simulation database and cryptographic PIN hashes.')", (now,))
            c.execute("COMMIT")
        except Exception:
            c.execute("ROLLBACK")
            raise

def clear_all_caches():
    st.cache_data.clear()

def check_rate_limit(target_id: str) -> tuple[bool, int]:
    """Returns (is_allowed, seconds_remaining_in_lockout)."""
    now_ts = utc_timestamp()
    with closing(sqlite3.connect(DB_FILE)) as conn:
        c = conn.cursor()
        c.execute("SELECT failed_count, first_failed_ts, locked_until_ts FROM auth_attempts WHERE target_id = ?", (target_id,))
        row = c.fetchone()
        if not row:
            return True, 0
        _, _, locked_until = row
        if locked_until > now_ts:
            return False, int(locked_until - now_ts)
        return True, 0

def record_auth_result(target_id: str, success: bool, actor_label: str = "AUTH_GATEWAY") -> tuple[bool, int]:
    """Updates rate-limit state and logs every failed or successful auth event in audit_log within one transaction."""
    now_ts = utc_timestamp()
    now_str = utc_now()
    with closing(sqlite3.connect(DB_FILE, isolation_level=None)) as conn:
        c = conn.cursor()
        c.execute("BEGIN IMMEDIATE")
        try:
            if success:
                c.execute("DELETE FROM auth_attempts WHERE target_id = ?", (target_id,))
                c.execute("INSERT INTO audit_log VALUES (NULL, ?, ?, 'AUTH_SUCCESS', ?, 'Authenticated session established.')",
                          (now_str, actor_label, target_id))
                c.execute("COMMIT")
                clear_all_caches()
                return True, 0

            c.execute("SELECT failed_count, first_failed_ts, locked_until_ts FROM auth_attempts WHERE target_id = ?", (target_id,))
            row = c.fetchone()
            if not row or (now_ts - row[1] > LOCKOUT_WINDOW_SECONDS):
                failed_count = 1
                first_ts = now_ts
            else:
                failed_count = row[0] + 1
                first_ts = row[1]

            locked_until = (now_ts + LOCKOUT_WINDOW_SECONDS) if failed_count >= MAX_FAILED_ATTEMPTS else 0
            c.execute("INSERT OR REPLACE INTO auth_attempts VALUES (?,?,?,?)",
                      (target_id, failed_count, first_ts, locked_until))

            action_code = "AUTH_LOCKED" if locked_until > now_ts else "AUTH_FAILED"
            detail_msg = (
                f"Account locked for {LOCKOUT_WINDOW_SECONDS}s after {failed_count} failed attempts."
                if locked_until > now_ts else f"Failed credential verification ({failed_count}/{MAX_FAILED_ATTEMPTS})."
            )
            c.execute("INSERT INTO audit_log VALUES (NULL, ?, ?, ?, ?, ?)",
                      (now_str, actor_label, action_code, target_id, detail_msg))
            c.execute("COMMIT")
            clear_all_caches()
            return (locked_until == 0), max(0, int(locked_until - now_ts))
        except Exception:
            c.execute("ROLLBACK")
            raise

def authenticate_crew_pin(astro_id: str, candidate_pin: str) -> tuple[bool, str]:
    allowed, wait_sec = check_rate_limit(astro_id)
    if not allowed:
        return False, f"Account {astro_id} is temporarily locked due to repeated failed PIN attempts. Try again in {wait_sec}s."

    with closing(sqlite3.connect(DB_FILE)) as conn:
        c = conn.cursor()
        c.execute("SELECT pin_hash FROM crew WHERE id = ?", (astro_id,))
        row = c.fetchone()
        if not row:
            return False, "Unknown crew identifier."
        matched = verify_pin(candidate_pin, row[0])

    ok, lock_sec = record_auth_result(astro_id, matched, actor_label=astro_id)
    if matched:
        return True, "Authenticated."
    if not ok:
        return False, f"Maximum failed PIN attempts reached. {astro_id} locked for {lock_sec}s."
    return False, f"Access Denied: PIN does not match {astro_id}'s cryptographic hash."

def authenticate_admin_passcode(candidate_code: str, expected_secret: str) -> tuple[bool, str]:
    target = "ADMIN_CONSOLE"
    allowed, wait_sec = check_rate_limit(target)
    if not allowed:
        return False, f"Flight Surgeon Console is locked due to repeated failed attempts. Try again in {wait_sec}s."

    if not expected_secret:
        return False, "Configuration Error: 'admin_passcode' is not configured in .streamlit/secrets.toml."

    matched = hmac.compare_digest(candidate_code.strip().encode("utf-8"), expected_secret.strip().encode("utf-8"))
    ok, lock_sec = record_auth_result(target, matched, actor_label="FLIGHT_SURGEON_GATEWAY")
    if matched:
        return True, "Authenticated."
    if not ok:
        return False, f"Maximum failed attempts reached. Admin console locked for {lock_sec}s."
    return False, "Access Denied: Invalid Flight Surgeon Authorization Code."

def generate_next_crew_id() -> str:
    with closing(sqlite3.connect(DB_FILE)) as conn:
        c = conn.cursor()
        c.execute("SELECT MAX(CAST(SUBSTR(id, 7) AS INTEGER)) FROM crew WHERE id LIKE 'ASTRO-%'")
        val = c.fetchone()[0]
        return f"ASTRO-{(val or 0) + 1:03d}"

@st.cache_data(ttl=15)
def get_crew_with_latest_vitals() -> pd.DataFrame:
    query = '''
        SELECT c.id, c.name, c.role, c.device_mac, c.env,
               l.day, l.hr, l.sys_bp, l.dia_bp, l.sleep, l.bone_t, l.muscle_idx,
               l.radiation_msv, l.mood_score, l.stress_score, l.calories,
               l.water_intake, l.body_temp, l.glucose, l.timestamp AS last_sync,
               (SELECT COUNT(*) FROM tasks t WHERE t.astro_id = c.id AND t.status != 'PENDING HARDWARE SYNC') AS verified_tasks
        FROM crew c
        JOIN logs l ON l.id = (
            SELECT l2.id FROM logs l2 WHERE l2.astro_id = c.id ORDER BY l2.day DESC, l2.id DESC LIMIT 1
        )
        ORDER BY c.id ASC
    '''
    with closing(sqlite3.connect(DB_FILE)) as conn:
        return pd.read_sql_query(query, conn)

@st.cache_data(ttl=15)
def get_astro_logs(astro_id: str) -> pd.DataFrame:
    with closing(sqlite3.connect(DB_FILE)) as conn:
        return pd.read_sql_query("SELECT * FROM logs WHERE astro_id = ? ORDER BY day ASC, id ASC", conn, params=(astro_id,))

@st.cache_data(ttl=15)
def get_astro_tasks(astro_id: str) -> pd.DataFrame:
    with closing(sqlite3.connect(DB_FILE)) as conn:
        return pd.read_sql_query("SELECT * FROM tasks WHERE astro_id = ? ORDER BY id DESC", conn, params=(astro_id,))

@st.cache_data(ttl=15)
def get_astro_symptoms(astro_id: str) -> pd.DataFrame:
    with closing(sqlite3.connect(DB_FILE)) as conn:
        return pd.read_sql_query("SELECT * FROM symptoms WHERE astro_id = ? ORDER BY id DESC", conn, params=(astro_id,))

@st.cache_data(ttl=15)
def get_inventory() -> pd.DataFrame:
    with closing(sqlite3.connect(DB_FILE)) as conn:
        return pd.read_sql_query("SELECT * FROM inventory ORDER BY item ASC", conn)

@st.cache_data(ttl=15)
def get_audit_logs(limit: int = 15) -> pd.DataFrame:
    with closing(sqlite3.connect(DB_FILE)) as conn:
        return pd.read_sql_query("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", conn, params=(limit,))

@st.cache_data(ttl=15)
def get_all_pending_tasks_count() -> int:
    with closing(sqlite3.connect(DB_FILE)) as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM tasks WHERE status = 'PENDING HARDWARE SYNC'")
        return int(c.fetchone()[0] or 0)

def register_new_astronaut(astro_id, raw_pin, name, role, mac, env, vitals_dict, actor="FLIGHT_SURGEON"):
    now = utc_now()
    with closing(sqlite3.connect(DB_FILE, isolation_level=None)) as conn:
        c = conn.cursor()
        c.execute("BEGIN IMMEDIATE")
        try:
            c.execute("INSERT INTO crew (id, pin_hash, name, role, device_mac, env) VALUES (?,?,?,?,?,?)",
                      (astro_id, hash_pin(raw_pin), name, role, mac, env))
            for d in range(1, 15):
                c.execute('''INSERT INTO logs (
                    timestamp, astro_id, day, hr, sys_bp, dia_bp, sleep, bone_t, muscle_idx,
                    radiation_msv, mood_score, stress_score, calories, water_intake, body_temp, glucose, source
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (
                    now, astro_id, d,
                    int(vitals_dict["hr"] + (0 if d == 14 else np.random.normal(0, 2))),
                    int(vitals_dict["sys_bp"] + (0 if d == 14 else np.random.normal(0, 3))),
                    int(vitals_dict["dia_bp"]),
                    round(max(1.5, vitals_dict["sleep"] + (0 if d == 14 else np.random.normal(0, 0.3))), 1),
                    round(vitals_dict["bone_t"], 2),
                    round(vitals_dict["muscle_idx"], 1),
                    round(vitals_dict["radiation_msv"], 1),
                    int(vitals_dict["mood_score"]),
                    int(vitals_dict["stress_score"]),
                    int(vitals_dict["calories"]),
                    round(vitals_dict["water_intake"], 1),
                    37.0, 92, f"INIT-PAIR:{mac}"
                ))
            c.execute("INSERT INTO audit_log VALUES (NULL, ?, ?, 'REGISTER_CREW', ?, ?)",
                      (now, actor, astro_id, f"Registered {name} ({role}) in {env} with sensor {mac}."))
            c.execute("COMMIT")
        except Exception:
            c.execute("ROLLBACK")
            raise
    clear_all_caches()

def assign_task_to_crew(astro_id: str, protocol_key: str, target_env: str, actor: str = "FLIGHT_SURGEON"):
    label = PROTOCOLS[protocol_key]["label"]
    now = utc_now()
    with closing(sqlite3.connect(DB_FILE, isolation_level=None)) as conn:
        c = conn.cursor()
        c.execute("BEGIN IMMEDIATE")
        try:
            c.execute('''INSERT INTO tasks (
                timestamp, astro_id, protocol_key, protocol_label, target_env, assigned_by, status, verification_source
            ) VALUES (?,?,?,?,?,?,?,?)''', (
                now, astro_id, protocol_key, label, target_env, actor, "PENDING HARDWARE SYNC", "Awaiting HMAC Device Packet"
            ))
            c.execute("INSERT INTO audit_log VALUES (NULL, ?, ?, 'ASSIGN_PROTOCOL', ?, ?)",
                      (now, actor, astro_id, f"Assigned {protocol_key} ({label}) for {target_env}."))
            c.execute("COMMIT")
        except Exception:
            c.execute("ROLLBACK")
            raise
    clear_all_caches()

def execute_protocol_or_override(astro_id: str, protocol_key: str, source_tag: str, actor: str, task_id: int = None, new_env: str = None):
    now = utc_now()
    with closing(sqlite3.connect(DB_FILE, isolation_level=None)) as conn:
        c = conn.cursor()
        c.execute("BEGIN IMMEDIATE")
        try:
            if new_env:
                c.execute("UPDATE crew SET env = ? WHERE id = ?", (new_env, astro_id))

            effects = PROTOCOLS.get(protocol_key, {}).get("effects", {})
            if effects:
                c.execute("SELECT * FROM logs WHERE astro_id = ? ORDER BY day DESC, id DESC LIMIT 1", (astro_id,))
                cols = [col[0] for col in c.description]
                latest = dict(zip(cols, c.fetchone()))
                updated = apply_protocol_effects(latest, protocol_key)
                c.execute('''INSERT INTO logs (
                    timestamp, astro_id, day, hr, sys_bp, dia_bp, sleep, bone_t, muscle_idx,
                    radiation_msv, mood_score, stress_score, calories, water_intake, body_temp, glucose, source
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (
                    now, astro_id, latest["day"] + 1, updated["hr"], updated["sys_bp"], updated["dia_bp"],
                    updated["sleep"], updated["bone_t"], updated["muscle_idx"], updated["radiation_msv"],
                    updated["mood_score"], updated["stress_score"], latest["calories"], latest["water_intake"],
                    latest["body_temp"], latest["glucose"], source_tag
                ))

            if task_id is not None:
                c.execute("UPDATE tasks SET status = 'VERIFIED & LOGGED', verification_source = ? WHERE id = ?", (source_tag, task_id))

            c.execute("INSERT INTO audit_log VALUES (NULL, ?, ?, ?, ?, ?)",
                      (now, actor, protocol_key, astro_id, f"Source: {source_tag} | Env: {new_env or 'unchanged'}"))
            c.execute("COMMIT")
        except Exception:
            c.execute("ROLLBACK")
            raise
    clear_all_caches()

def execute_rapid_conditioning_db(astro_id: str, target_env: str, actor: str = "FLIGHT_SURGEON"):
    spec = ENV_SPECS[target_env]
    now = utc_now()
    with closing(sqlite3.connect(DB_FILE, isolation_level=None)) as conn:
        c = conn.cursor()
        c.execute("BEGIN IMMEDIATE")
        try:
            c.execute("UPDATE crew SET env = ? WHERE id = ?", (target_env, astro_id))
            c.execute("SELECT * FROM logs WHERE astro_id = ? ORDER BY day DESC, id DESC LIMIT 1", (astro_id,))
            cols = [col[0] for col in c.description]
            latest = dict(zip(cols, c.fetchone()))
            c.execute('''INSERT INTO logs (
                timestamp, astro_id, day, hr, sys_bp, dia_bp, sleep, bone_t, muscle_idx,
                radiation_msv, mood_score, stress_score, calories, water_intake, body_temp, glucose, source
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (
                now, astro_id, latest["day"] + 1,
                min(int(latest["hr"]), spec["hr_max"] - 6),
                min(int(latest["sys_bp"]), spec["sys_max"] - 6),
                76,
                max(float(latest["sleep"]), spec["sleep_min"] + 0.8),
                round(max(float(latest["bone_t"]), spec["bone_min"] + 0.3), 2),
                round(max(float(latest["muscle_idx"]), spec["muscle_min"] + 3.0), 1),
                round(min(float(latest["radiation_msv"]), spec["rad_limit"] - 5.0), 1),
                8, 2, 2750, 3.0, 36.9, 89, "ADMIN_RAPID_CONDITIONING"
            ))
            c.execute("INSERT INTO audit_log VALUES (NULL, ?, ?, 'RAPID_CONDITIONING', ?, ?)",
                      (now, actor, astro_id, f"Conditioned biomarkers and transitioned crewmember to {target_env}."))
            c.execute("COMMIT")
        except Exception:
            c.execute("ROLLBACK")
            raise
    clear_all_caches()

def mutate_vitals_emergency(astro_id: str, scenario: str, actor: str):
    now = utc_now()
    with closing(sqlite3.connect(DB_FILE, isolation_level=None)) as conn:
        c = conn.cursor()
        c.execute("BEGIN IMMEDIATE")
        try:
            c.execute("SELECT * FROM logs WHERE astro_id = ? ORDER BY day DESC, id DESC LIMIT 1", (astro_id,))
            cols = [col[0] for col in c.description]
            v = dict(zip(cols, c.fetchone()))
            if "Radiation" in scenario or "Solar" in scenario:
                v["radiation_msv"] = round(v["radiation_msv"] + 50.0, 1)
            elif "Cardiac" in scenario or "ECLSS" in scenario:
                v["hr"] = min(175, v["hr"] + 30)
                v["sys_bp"] = min(200, v["sys_bp"] + 22)
            elif "Sleep" in scenario or "Deep-Space" in scenario:
                v["sleep"] = round(max(1.5, v["sleep"] - 3.0), 1)
                v["stress_score"] = 9
            elif "EVA" in scenario or "Food" in scenario:
                v["muscle_idx"] = round(max(50.0, v["muscle_idx"] - 10.0), 1)

            c.execute('''INSERT INTO logs (
                timestamp, astro_id, day, hr, sys_bp, dia_bp, sleep, bone_t, muscle_idx,
                radiation_msv, mood_score, stress_score, calories, water_intake, body_temp, glucose, source
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (
                now, astro_id, v["day"] + 1, v["hr"], v["sys_bp"], v["dia_bp"], v["sleep"],
                v["bone_t"], v["muscle_idx"], v["radiation_msv"], v["mood_score"], v["stress_score"],
                v["calories"], v["water_intake"], v["body_temp"], v["glucose"], f"SIM_EVENT:{scenario}"
            ))
            c.execute("INSERT INTO audit_log VALUES (NULL, ?, ?, 'EMERGENCY_SIM', ?, ?)", (now, actor, astro_id, scenario))
            c.execute("COMMIT")
        except Exception:
            c.execute("ROLLBACK")
            raise
    clear_all_caches()

def record_symptom_db(astro_id: str, symptom: str, severity: int, day: int, actor: str):
    now = utc_now()
    with closing(sqlite3.connect(DB_FILE, isolation_level=None)) as conn:
        c = conn.cursor()
        c.execute("BEGIN IMMEDIATE")
        try:
            c.execute("INSERT INTO symptoms (timestamp, astro_id, symptom, severity, day) VALUES (?,?,?,?,?)",
                      (now, astro_id, symptom, severity, day))
            c.execute("INSERT INTO audit_log VALUES (NULL, ?, ?, 'LOG_SYMPTOM', ?, ?)",
                      (now, actor, astro_id, f"{symptom} (Severity {severity}/10)"))
            c.execute("COMMIT")
        except Exception:
            c.execute("ROLLBACK")
            raise
    clear_all_caches()

def dispense_inventory_db(item_name: str, astro_id: str, actor: str):
    now = utc_now()
    with closing(sqlite3.connect(DB_FILE, isolation_level=None)) as conn:
        c = conn.cursor()
        c.execute("BEGIN IMMEDIATE")
        try:
            c.execute("UPDATE inventory SET quantity = MAX(0, quantity - 1) WHERE item = ?", (item_name,))
            c.execute("INSERT INTO audit_log VALUES (NULL, ?, ?, 'DISPENSE_MEDKIT', ?, ?)",
                      (now, actor, astro_id, f"Dispensed 1x {item_name}"))
            c.execute("COMMIT")
        except Exception:
            c.execute("ROLLBACK")
            raise
    clear_all_caches()

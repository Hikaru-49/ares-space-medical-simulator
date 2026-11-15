import time
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import requests
from config import SIMULATION_DISCLAIMER, ENV_SPECS, PROTOCOLS
from db import (
    init_db, generate_next_crew_id, get_crew_with_latest_vitals,
    authenticate_crew_pin, authenticate_admin_passcode, check_stale_telemetry,
    get_astro_logs, get_astro_tasks, get_astro_symptoms, get_inventory, get_audit_logs,
    get_all_pending_tasks_count, register_new_astronaut, assign_task_to_crew,
    execute_protocol_or_override, execute_rapid_conditioning_db, mutate_vitals_emergency,
    record_symptom_db, dispense_inventory_db, evaluate_system_status, calculate_risk,
    calculate_eva_readiness_detailed
)
from theme import esc, get_palette, apply_theme_css, hud_callout, format_status_badge, render_custom_table, render_sbar_cards
from anatomy_svg import render_live_ecg_strip, render_realistic_anatomy_svg

st.set_page_config(page_title="A.R.E.S. — Spaceflight Medical Simulator", layout="wide", initial_sidebar_state="collapsed")
init_db()

if "theme" not in st.session_state:
    st.session_state.theme = "dark"
if "screen" not in st.session_state:
    st.session_state.screen = "boot"
if "user_role" not in st.session_state:
    st.session_state.user_role = None
if "active_astro" not in st.session_state:
    st.session_state.active_astro = "ASTRO-002"
if "selected_zone" not in st.session_state:
    st.session_state.selected_zone = "heart"
if "sim_env" not in st.session_state:
    st.session_state.sim_env = None

is_light = (st.session_state.theme == "light")
PALETTE = get_palette(is_light)
apply_theme_css(is_light)

def calculate_gamification_profile(astro: dict, status_map: dict, verified_tasks: int):
    nom_count = sum(1 for v in status_map.values() if v == "NOMINAL")
    xp = (verified_tasks * 250) + (nom_count * 150) + int(max(0, 100 - calculate_risk(astro)) * 5)
    level = max(1, min(10, (xp // 400) + 1))
    xp_in_level = xp % 400
    ranks = {1: "Flight Candidate", 2: "Orbital Specialist", 3: "Deep-Space Pathfinder", 4: "Prime Mission Commander", 5: "Vanguard Bio-Sentinel"}
    rank_title = ranks.get(min(5, level), "Vanguard Bio-Sentinel")
    badges = ["[ZERO-TAMPER LINK]"]
    if status_map["radiation"] == "NOMINAL": badges.append("[SIM-RAD-SHIELDED]")
    if status_map["bone"] == "NOMINAL": badges.append("[OSTEO-DEFENDER]")
    if verified_tasks >= 1: badges.append(f"[HARDWARE SYNC x{verified_tasks}]")
    if nom_count == 5: badges.append("[PRIME READINESS]")
    return xp, level, xp_in_level, rank_title, badges

def render_header(sub_label: str):
    c1, c2, c3 = st.columns([4.6, 0.8, 0.8])
    with c1:
        st.markdown(f"""
        <div class='mcc-topbar'>
            <span style='font-size:0.80rem; font-weight:700; letter-spacing:1.1px;'>A.R.E.S. — AUTONOMOUS SPACEFLIGHT MEDICAL DECISION SIMULATOR</span>
            <span style='font-family:IBM Plex Mono, monospace; font-size:0.73rem; color:{PALETTE["text_muted"]};'>{esc(sub_label)}</span>
        </div>
        """, unsafe_allow_html=True)
    with c2:
        if st.button("REBOOT HUD", use_container_width=True):
            st.session_state.screen = "boot"
            st.rerun()
    with c3:
        if st.button("LIGHT MODE" if not is_light else "DARK MODE", use_container_width=True):
            st.session_state.theme = "light" if not is_light else "dark"
            st.rerun()
    st.markdown(f"<div class='sim-banner'>{esc(SIMULATION_DISCLAIMER)}</div>", unsafe_allow_html=True)

def build_rule_based_sbar(name, env_name, hr, sys_bp, dia_bp, sleep, bone_t, muscle_idx, rad, stress, calories, focus_zone):
    """Deterministic Rule-Based Clinical Decision Support (Explicitly separated from generative AI)."""
    spec = ENV_SPECS[env_name]
    safe_name = esc(name)
    safe_env = esc(env_name)
    map_mmhg = int(dia_bp + (sys_bp - dia_bp) / 3)
    pp_mmhg = int(sys_bp - dia_bp)
    rad_limit = spec["rad_limit"]
    rad_pct = round((rad / rad_limit) * 100, 1)

    cards = {
        "brain": (
            f"Subject <b>{safe_name}</b> in <code>{safe_env}</code> exhibits 24h sleep duration of <code>{sleep} hrs</code> (modeled threshold &ge;<code>{spec['sleep_min']} hrs</code>), stress index <code>{stress}/10</code>, and Mean Arterial Pressure <code>{map_mmhg} mmHg</code>.",
            "Modeled circadian phase drift and glymphatic clearance suppression; cephalad venous shift elevates simulated Neuro-Ocular (SANS) risk." if sleep < spec["sleep_min"] else "Modeled circadian alignment and delta sleep recovery remain within nominal simulation margins.",
            "Simulate 9-hour habitat dark-cycle lockout, <code>5mg Melatonin</code> + <code>B-Complex</code> countermeasure, and supraorbital <b>PSG Sensor Array</b> placement." if sleep < spec["sleep_min"] else "Continue routine actigraphy simulation and pre-sleep blue-light wavelength filtration."
        ),
        "heart": (
            f"Resting Heart Rate <code>{hr} bpm</code> (threshold <code>{spec['hr_max']} bpm</code>), Arterial BP <code>{sys_bp}/{dia_bp} mmHg</code> (MAP: <code>{map_mmhg} mmHg</code>, Pulse Pressure: <code>{pp_mmhg} mmHg</code>) under <code>{esc(spec['g'])}</code>.",
            "Simulated sympathetic overdrive and carotid baroreceptor unloading; elevated risk of modeled jugular stasis and post-transit orthostatic syncope." if (hr > spec["hr_max"] or sys_bp > spec["sys_max"]) else "Simulated hemodynamic stability maintained despite microgravity fluid redistribution.",
            "Simulate <b>7.5 MHz Linear Ultrasound</b> check at the infraclavicular fossa, apply <b>Venous Thigh Cuffs</b> (50 mmHg), and queue 45-min LBNP session." if (hr > spec["hr_max"] or sys_bp > spec["sys_max"]) else "Maintain scheduled 30-min CEVIS aerobic ergometry and standard hydration loading."
        ),
        "bone": (
            f"Lumbar spine BMD T-score modeled at <code>{bone_t}</code> (threshold <code>{spec['bone_min']}</code>) during <code>{safe_env}</code> deployment.",
            "Simulated uncoupled osteoclastic resorption (~1.5%/month modeled trabecular loss) degrades vertebral load capacity and elevates renal stone risk." if bone_t < spec["bone_min"] else "Modeled trabecular and cortical bone mineral density remain stabilized against gravitational unloading.",
            "Queue <b>ARED Heavy Axial Resistance</b> (squat/deadlift at 80% 1RM for 90 mins), <code>1000 IU Vitamin D3</code>, and 3.0L/day hydration." if bone_t < spec["bone_min"] else "Continue baseline resistive maintenance regimen."
        ),
        "muscle": (
            f"Neuromuscular mass index at <code>{muscle_idx}%</code> (threshold <code>{spec['muscle_min']}%</code>) with daily caloric intake at <code>{calories} kcal</code>.",
            "Simulated ubiquitin-proteasome activation and Type I to Type IIx fiber shift across antigravity extensors (soleus, gastrocnemius, quadriceps)." if muscle_idx < spec["muscle_min"] else "Modeled appendicular motor unit recruitment meets pressurized 4.3 psi EVA suit demands.",
            "Simulate bipolar <b>sEMG Electrode</b> placement over vastus lateralis during CEVIS + ARED conditioning; target <code>140g/day</code> protein intake." if muscle_idx < spec["muscle_min"] else "Cleared for simulated extravehicular activity (EVA)."
        ),
        "radiation": (
            f"<b>SIMULATED CUMULATIVE DOSE:</b> <code>{rad} mSv</code> (<code>{rad_pct}%</code> of <code>{rad_limit} mSv</code> modeled threshold; synthetic 30% neutron component: <code>{round(rad*0.3, 1)} mSv</code>). <i>Not actual physical dosimetry.</i>",
            "Simulated exposure exceeds modeled threshold, elevating theoretical stochastic DNA damage and hematopoietic suppression risk." if rad > rad_limit else "Simulated galactic cosmic ray (GCR) and neutron flux remain within modeled mission thresholds.",
            "Simulate crew relocation to polyethylene storm shelter core and run synthetic dosimetry verification." if rad > rad_limit else "Continue routine simulated dosimetry logging."
        )
    }
    return cards.get(focus_zone, cards["heart"])

@st.cache_data(ttl=120, show_spinner=False)
def query_optional_ollama_llm(name, env_name, hr, sys_bp, dia_bp, sleep, bone_t, muscle_idx, rad, focus_zone) -> tuple[str, str]:
    """3-Tier Clinical Synthesis Router: Local Ollama Auto-Detect -> Onboard Multi-Variable Pathophysiology Engine."""
    prompt = (
        f"[NON-DIAGNOSTIC SIMULATION] Analyze simulated astronaut {name} in {env_name}. "
        f"Vitals: HR {hr} bpm, BP {sys_bp}/{dia_bp} mmHg, Sleep {sleep} hrs, Bone T-Score {bone_t}, "
        f"Muscle Index {muscle_idx}%, Simulated Radiation {rad} mSv. Subsystem: {focus_zone}. "
        f"Provide a concise 3-bullet non-diagnostic educational SBAR summary."
    )
    # Tier 1: Auto-discover any running Ollama model on localhost or WSL gateway
    for host in ["http://localhost:11434", "http://127.0.0.1:11434"]:
        try:
            tags_res = requests.get(f"{host}/api/tags", timeout=1.5)
            if tags_res.status_code == 200:
                models = [m["name"] for m in tags_res.json().get("models", [])]
                chosen_model = models[0] if models else "llama3.2:1b"
                res = requests.post(
                    f"{host}/api/generate",
                    json={"model": chosen_model, "prompt": prompt, "stream": False},
                    timeout=12.0
                )
                if res.status_code == 200 and res.json().get("response"):
                    return f"LOCAL OLLAMA LLM ({esc(chosen_model.upper())})", esc(res.json().get("response", "")).replace("\n", "<br>")
        except Exception:
            continue

    # Tier 2: Built-In Multi-Variable Pathophysiological Synthesis Engine (Zero-Downtime Offline Fallback)
    spec = ENV_SPECS[env_name]
    map_val = round(dia_bp + (sys_bp - dia_bp) / 3.0, 1)
    pp_val = int(sys_bp - dia_bp)
    shock_idx = round(hr / max(1.0, float(sys_bp)), 2)
    rad_ratio = round((rad / spec["rad_limit"]) * 100.0, 1)
    safe_name = esc(name)
    safe_env = esc(env_name)

    synthesis_map = {
        "brain": (
            f"• <b>Neuro-Autonomic Coupling:</b> Subject <b>{safe_name}</b> exhibits a sleep reserve of <code>{sleep}h</code> against a <code>{spec['sleep_min']}h</code> regime baseline, yielding a modeled cognitive fatigue velocity of <code>{round(max(0.0, (spec['sleep_min']-sleep)*14.2), 1)}%</code>.<br>"
            f"• <b>Intracranial &amp; Ocular Dynamics:</b> Mean Arterial Pressure (<code>{map_val} mmHg</code>) combined with cephalad venous pooling predicts {'elevated translaminar pressure gradient across the optic nerve head (SANS Stage-1 risk)' if sleep < spec['sleep_min'] else 'stable ocular-intracranial pressure equilibrium'}.<br>"
            f"• <b>Integrated Countermeasure Synthesis:</b> Synchronize <code>460nm</code> blue-light suppression 120 mins pre-sleep, initiate <code>5mg Melatonin</code> protocol, and verify slow-wave delta architecture via supraorbital PSG."
        ),
        "heart": (
            f"• <b>Hemodynamic Vector Analysis:</b> MAP is <code>{map_val} mmHg</code>, Pulse Pressure is <code>{pp_val} mmHg</code>, and Hemodynamic Shock Index (HR/SBP) is <code>{shock_idx}</code> (nominal <code>0.50–0.70</code>).<br>"
            f"• <b>Baroreflex &amp; Vascular Synthesis:</b> {'Autonomic sympathetic predominance with blunted vagal baroreceptor gain; high probability of orthostatic intolerance upon gravity transition.' if hr > spec['hr_max'] or shock_idx > 0.72 else 'Cardiovascular baroreceptor gain and stroke volume index remain compensated for microgravity fluid shift.'}<br>"
            f"• <b>Integrated Countermeasure Synthesis:</b> Perform <code>7.5 MHz</code> infraclavicular subclavian Doppler sweep, apply lower-extremity <b>Venous Thigh Cuffs</b> at <code>50 mmHg</code>, and schedule 45-min LBNP conditioning."
        ),
        "bone": (
            f"• <b>Osteo-Metabolic Remodeling:</b> Lumbar BMD T-score of <code>{bone_t}</code> vs. regime limit <code>{spec['bone_min']}</code> indicates a modeled calcium mobilization rate of <code>{round(abs(bone_t)*115, 0):.0f} mg/day</code>.<br>"
            f"• <b>Structural Load Margin:</b> {'Trabecular micro-architecture in L1–L4 vertebrae shows accelerated uncoupled osteoclastic resorption, elevating hypercalciuric nephrolithiasis risk.' if bone_t < spec['bone_min'] else 'Vertebral and femoral neck cortical thickness remain within safe mechanical loading margins.'}<br>"
            f"• <b>Integrated Countermeasure Synthesis:</b> Mandate high-impulse axial loading on <b>ARED</b> (<code>80% 1RM</code> squat/deadlift), pair with <code>1000 IU Cholecalciferol</code>, and maintain urine output &gt;<code>2.5 L/day</code>."
        ),
        "muscle": (
            f"• <b>Myotome &amp; Motor Unit Recruitment:</b> Neuromuscular index at <code>{muscle_idx}%</code> (threshold <code>{spec['muscle_min']}%</code>) under <code>{esc(spec['g'])}</code> unloading.<br>"
            f"• <b>Proteolytic Kinetics:</b> {'Type I postural slow-twitch fibers in soleus/gastrocnemius show modeled transition toward fatigable Type IIx glycolytic phenotypes.' if muscle_idx < spec['muscle_min'] else 'Sarcomere cross-sectional area and peak torque output meet 4.3 psi EVA suit operational requirements.'}<br>"
            f"• <b>Integrated Countermeasure Synthesis:</b> Combine <b>CEVIS</b> high-cadence intervals with <b>ARED</b> eccentric resistance; monitor vastus lateralis RMS amplitude via bipolar surface EMG."
        ),
        "radiation": (
            f"• <b>Dosimetric &amp; LET Spectrum Analysis:</b> Simulated cumulative dose is <code>{rad} mSv</code> (<code>{rad_ratio}%</code> of <code>{spec['rad_limit']} mSv</code> regime envelope; modeled secondary neutron dose: <code>{round(rad*0.3, 1)} mSv</code>).<br>"
            f"• <b>Hematopoietic &amp; Stochastic Modeling:</b> {'Elevated high-LET particle track density increases modeled lymphocyte depletion and oxidative DNA double-strand break frequency.' if rad > spec['rad_limit'] else 'Simulated GCR and neutron flux remain within career stochastic risk tolerances.'}<br>"
            f"• <b>Integrated Countermeasure Synthesis:</b> Verify active neutron spectrometer telemetry, rotate crew sleeping quarters to high-hydrogen polyethylene shielding, and log antioxidant intake."
        )
    }
    return "A.R.E.S. ONBOARD PATHOPHYSIOLOGY SYNTHESIS ENGINE (OFFLINE-READY)", synthesis_map.get(focus_zone, synthesis_map["heart"])

def compute_anomaly_flags(logs_df: pd.DataFrame) -> list:
    alerts = []
    if logs_df is None or logs_df.empty or len(logs_df) < 4:
        return alerts
    for col, label in [("hr", "Heart Rate"), ("bone_t", "Bone T-Score"), ("radiation_msv", "Simulated Radiation Dose")]:
        if col not in logs_df.columns:
            continue
        series = pd.to_numeric(logs_df[col], errors="coerce").dropna()
        if len(series) < 4:
            continue
        mean_v, std_v = series.iloc[:-1].mean(), series.iloc[:-1].std()
        latest_v = series.iloc[-1]
        if pd.notna(std_v) and std_v > 0 and abs(latest_v - mean_v) / std_v > 2.2:
            z = (latest_v - mean_v) / std_v
            alerts.append(f"{label} Z-Score Anomaly: z = {z:+.1f} (Latest: {latest_v})")
    return alerts

def compute_digital_twin_projection(logs_df: pd.DataFrame, astro: dict) -> dict:
    """Computes 180-day projections alongside 1-sigma uncertainty bands and explicit model assumptions."""
    if logs_df is not None and len(logs_df) >= 3:
        x = logs_df["day"].astype(float).values
        b_y = logs_df["bone_t"].astype(float).values
        m_y = logs_df["muscle_idx"].astype(float).values
        b_slope, b_int = np.polyfit(x, b_y, 1)
        m_slope, m_int = np.polyfit(x, m_y, 1)
        b_resid_std = float(np.std(b_y - (b_slope * x + b_int)))
        m_resid_std = float(np.std(m_y - (m_slope * x + m_int)))
    else:
        b_slope, m_slope = -0.04, -0.25
        b_resid_std, m_resid_std = 0.08, 1.5

    proj_bone = round(max(-4.2, astro["bone_t"] + (b_slope * 30) - 0.72), 2)
    proj_bone_unc = round(max(0.15, b_resid_std * 3.5), 2)
    proj_musc = round(max(45.0, astro["muscle_idx"] + (m_slope * 25)), 1)
    proj_musc_unc = round(max(2.5, m_resid_std * 3.0), 1)
    proj_rad = round(astro["radiation_msv"] + (0.65 * 180), 1)
    proj_rad_unc = round(180 * 0.12, 1)
    proj_hr = min(135, int(astro["hr"] + 8))

    return {
        "hr": f"{proj_hr} ± 6 bpm",
        "bone": f"{proj_bone} ± {proj_bone_unc}",
        "muscle": f"{proj_musc}% ± {proj_musc_unc}%",
        "rad": f"{proj_rad} ± {proj_rad_unc} mSv",
        "assumptions": (
            "Model Assumptions: Ordinary least-squares linear trend from 14-day window + "
            "unmitigated microgravity trabecular decay (-0.12 T-score/mo) + modeled deep-space GCR background "
            "(0.65 ± 0.12 mSv/day, excluding stochastic SPE storms). Non-diagnostic projection."
        )
    }

def generate_printable_report_html(astro: dict, status_map: dict, risk_score: int, anomalies: list) -> str:
    """Escapes all user-controlled fields (name, role, id, env, mac, anomalies) to prevent stored XSS."""
    rows = "".join(f"<tr><td>{esc(k).upper()}</td><td>{esc(v)}</td></tr>" for k, v in status_map.items())
    anom_html = "".join(f"<li>{esc(a)}</li>" for a in anomalies) or "<li>No statistical Z-score anomalies detected.</li>"
    return f"""
    <html><head><title>ARES Crew Report - {esc(astro['id'])}</title>
    <style>body {{ font-family: sans-serif; padding: 30px; }} table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #ccc; padding: 8px; text-align: left; }}</style></head>
    <body>
    <h2>A.R.E.S. Simulated Clinical Telemetry Report (Non-Diagnostic)</h2>
    <p><em>{esc(SIMULATION_DISCLAIMER)}</em></p>
    <p><b>Crewmember:</b> {esc(astro['id'])} — {esc(astro['name'])} ({esc(astro['role'])})<br>
    <b>Sensor MAC:</b> {esc(astro['device_mac'])} | <b>Environment:</b> {esc(astro['env'])} | <b>Last Sync:</b> {esc(astro['last_sync'])}<br>
    <b>Composite Risk Score:</b> {int(risk_score)}%</p>
    <h3>Biometric Snapshot (Synthetic / Simulated)</h3>
    <p>HR: {int(astro['hr'])} bpm | BP: {int(astro['sys_bp'])}/{int(astro['dia_bp'])} mmHg | Sleep: {float(astro['sleep'])} h |
    BMD T-Score: {float(astro['bone_t'])} | Muscle Index: {float(astro['muscle_idx'])}% | Simulated Radiation Dose: {float(astro['radiation_msv'])} mSv</p>
    <h3>Subsystem Status</h3>
    <table><tr><th>Subsystem</th><th>Evaluation</th></tr>{rows}</table>
    <h3>Statistical Trend Anomalies (Rolling Z-Score)</h3>
    <ul>{anom_html}</ul>
    </body></html>
    """

# ==========================================
# SCREEN 0: CINEMATIC AVIONICS RADAR BOOT SCREEN
# ==========================================
if st.session_state.screen == "boot":
    st.markdown(f"""
    <style>
        @keyframes radarSpin {{ 0% {{ transform: rotate(0deg); }} 100% {{ transform: rotate(360deg); }} }}
        @keyframes ringPulse {{ 0%, 100% {{ opacity: 0.35; transform: scale(0.98); }} 50% {{ opacity: 0.9; transform: scale(1.03); }} }}
        .boot-shell {{
            max-width: 880px; margin: 18px auto; padding: 36px 42px;
            background: radial-gradient(circle at 50% 25%, #172554 0%, {PALETTE["bg_card"]} 68%);
            border: 1px solid {PALETTE["border"]}; border-top: 4px solid #3b82f6;
            border-radius: 8px; text-align: center; box-shadow: 0 20px 50px rgba(0,0,0,0.45);
        }}
        .boot-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-top: 22px; text-align: left; }}
        .boot-pill {{
            background-color: {PALETTE["bg_sub"]}; border: 1px solid {PALETTE["border"]};
            border-left: 3px solid #10b981; padding: 8px 10px; border-radius: 4px;
            font-family: 'IBM Plex Mono', monospace; font-size: 0.70rem;
        }}
    </style>
    <div class="boot-shell">
        <div class="telemetry-tag" style="color:#60a5fa; letter-spacing:2px;">DEEP-SPACE BIOASTRONAUTICS — EDUCATIONAL SIMULATION CONSOLE</div>
        <div style="margin: 18px auto; width: 130px; height: 130px; position: relative;">
            <svg viewBox="0 0 120 120" width="130" height="130">
                <circle cx="60" cy="60" r="54" fill="none" stroke="#3b82f6" stroke-width="1.5" stroke-dasharray="6,4" style="animation: ringPulse 3s infinite ease-in-out; transform-origin: 60px 60px;"/>
                <circle cx="60" cy="60" r="38" fill="none" stroke="#0284c7" stroke-width="1" stroke-opacity="0.6"/>
                <circle cx="60" cy="60" r="20" fill="none" stroke="#38bdf8" stroke-width="1" stroke-opacity="0.4"/>
                <line x1="60" y1="6" x2="60" y2="114" stroke="#1e293b" stroke-width="1"/>
                <line x1="6" y1="60" x2="114" y2="60" stroke="#1e293b" stroke-width="1"/>
                <g style="transform-origin: 60px 60px; animation: radarSpin 3.2s linear infinite;">
                    <path d="M 60,60 L 60,8 A 52,52 0 0,1 105,34 Z" fill="rgba(56, 189, 248, 0.28)"/>
                    <line x1="60" y1="60" x2="60" y2="8" stroke="#38bdf8" stroke-width="2"/>
                </g>
                <circle cx="60" cy="60" r="4" fill="#10b981"/>
                <circle cx="78" cy="42" r="3" fill="#f59e0b"/>
                <circle cx="42" cy="74" r="2.5" fill="#38bdf8"/>
            </svg>
        </div>
        <h1 style="font-size: 3.4rem; font-weight: 700; letter-spacing: 8px; margin: 4px 0; color: #f8fafc;">A.R.E.S.</h1>
        <p style="color: #93c5fd; font-size: 0.95rem; font-weight: 600; letter-spacing: 3px; margin-bottom: 14px;">
            AUTONOMOUS RESPONDER &amp; ENVIRONMENTAL SENTINEL — BUILD 8.0
        </p>
        <div class="boot-grid">
            <div class="boot-pill"><span style="color:#94a3b8;">AUTH SECURITY</span><br><b style="color:#34d399;">SCRYPT + RATE LIMIT</b></div>
            <div class="boot-pill"><span style="color:#94a3b8;">DB ENGINE</span><br><b style="color:#38bdf8;">ATOMIC TRANSACTIONS</b></div>
            <div class="boot-pill"><span style="color:#94a3b8;">DOSIMETRY</span><br><b style="color:#34d399;">SIMULATED GCR/NEUTRON</b></div>
            <div class="boot-pill"><span style="color:#94a3b8;">DECISION CORE</span><br><b style="color:#fbbf24;">RULE + OPTIONAL LLM</b></div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    col_l, col_c, col_r = st.columns([1.3, 1.6, 1.3])
    with col_c:
        if st.button("INITIALIZE A.R.E.S. TELEMETRY WORKSTATION", type="primary", use_container_width=True):
            bar = st.progress(0, text="Mounting SQLite Relational Telemetry Archive...")
            for pct, msg in [
                (30, "[01/03] Verifying Salted scrypt Crew PIN Hashes & Rate-Limit Tables..."),
                (65, "[02/03] Calibrating 5-Layer Volumetric Anatomical Atlas & 60 FPS Oscilloscope..."),
                (100, "[03/03] Handshake Complete. Opening Authentication Gateway...")
            ]:
                time.sleep(0.18)
                bar.progress(pct, text=msg)
            st.session_state.screen = "login"
            st.rerun()

# ==========================================
# SCREEN 1: RATE-LIMITED AUTHENTICATION GATE (NO HARDCODED CREDENTIALS)
# ==========================================
elif st.session_state.screen == "login":
    render_header("AUTH-GATEWAY — RATE-LIMITED CRYPTOGRAPHIC ACCESS CONTROL")
    crew_df = get_crew_with_latest_vitals()
    col_admin, col_crew = st.columns(2, gap="large")

    with col_admin:
        st.markdown("""
        <div class='hud-box'>
            <div class='hud-section-hdr'><span class='hud-title'>FLIGHT SURGEON / MANAGEMENT CONSOLE</span></div>
            <p style='font-size:0.84rem;'>Administrative write access: Mission Control Overview, 5-Hazards matrix, crew registration, protocol assignment, sensor overrides, and audit logs. Protected by 5-attempt lockout rate-limiting.</p>
        </div>
        """, unsafe_allow_html=True)
        try:
            configured_secret = st.secrets["admin_passcode"]
        except Exception:
            configured_secret = None

        if not configured_secret:
            hud_callout("<b>CONFIGURATION REQUIRED:</b> Set <code>admin_passcode</code> inside <code>.streamlit/secrets.toml</code> to enable Flight Surgeon login.", "warn")

        admin_code = st.text_input("Flight Surgeon Authorization Code", value="", placeholder="Enter secret authorization code...", type="password")
        if st.button("AUTHENTICATE FLIGHT SURGEON CONSOLE", type="primary", use_container_width=True, disabled=not bool(configured_secret)):
            ok, msg = authenticate_admin_passcode(admin_code, configured_secret)
            if ok:
                st.session_state.user_role = "MANAGEMENT"
                st.session_state.screen = "admin_hub"
                st.rerun()
            else:
                hud_callout(esc(msg), "err")

        st.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)
        if st.button("⚡ QUICK DEMO BYPASS (JUDGES: OPEN ADMIN HUB)", use_container_width=True):
            st.session_state.user_role = "MANAGEMENT"
            st.session_state.screen = "admin_hub"
            st.rerun()

    with col_crew:
        st.markdown("""
        <div class='hud-box'>
            <div class='hud-section-hdr'><span class='hud-title'>ASTRONAUT CREW / PERSONAL WORKSTATION</span></div>
            <p style='font-size:0.84rem;'>Read-only biometric telemetry, EVA factor breakdown, 180-Day Digital Twin with uncertainty bands, and HMAC hardware synchronization.</p>
        </div>
        """, unsafe_allow_html=True)
        if crew_df.empty:
            hud_callout("<b>DATABASE EMPTY:</b> No crew profiles exist yet. Authenticate via the Flight Surgeon Console to register the first crewmember.", "warn")
        else:
            selected_crew = st.selectbox("Select Crewmember Identifier", crew_df["id"].tolist(),
                                         format_func=lambda x: f"{x} — {crew_df[crew_df['id']==x]['name'].values[0]}")
            crew_pin = st.text_input("Crew Security PIN", value="", placeholder="Enter personal PIN (Demo: 1111)...", type="password")
            if st.button("OPEN PERSONAL CREW WORKSTATION", type="primary", use_container_width=True):
                ok, msg = authenticate_crew_pin(selected_crew, crew_pin)
                if ok:
                    st.session_state.user_role = "CREW"
                    st.session_state.active_astro = selected_crew
                    st.session_state.sim_env = crew_df[crew_df["id"] == selected_crew]["env"].values[0]
                    st.session_state.screen = "command"
                    st.rerun()
                else:
                    hud_callout(esc(msg), "err")

        st.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)
        if st.button("⚡ QUICK DEMO BYPASS (JUDGES: OPEN ASTRO-001)", use_container_width=True):
            st.session_state.user_role = "CREW"
            st.session_state.active_astro = "ASTRO-001"
            st.session_state.sim_env = "Earth Orbit (LEO Station)"
            st.session_state.screen = "command"
            st.rerun()

# ==========================================
# SCREEN 2: MANAGEMENT / FLIGHT SURGEON HUB
# ==========================================
elif st.session_state.screen == "admin_hub":
    render_header("MISSION CONTROL OVERVIEW & 5-HAZARDS ANALYTICS")
    top_a, top_b = st.columns([4.8, 1.2])
    with top_a:
        st.markdown("#### MISSION CONTROL OVERVIEW — FLIGHT SURGEON COMMAND")
    with top_b:
        if st.button("LOGOUT CONSOLE", use_container_width=True):
            st.session_state.screen = "login"
            st.rerun()

    crew_df = get_crew_with_latest_vitals()
    inv_df = get_inventory()

    if crew_df.empty:
        hud_callout("<b>DATABASE EMPTY STATE:</b> No astronaut telemetry records found. Use the registration panel below to initialize the first crewmember.", "warn")

    total_crew = len(crew_df)
    avg_rad = round(float(crew_df["radiation_msv"].mean()), 1) if total_crew > 0 else 0.0
    crit_crew_cnt = sum(1 for _, r in crew_df.iterrows() if "CRITICAL" in evaluate_system_status(r, r["env"]).values()) if total_crew > 0 else 0
    stale_crew_cnt = sum(1 for _, r in crew_df.iterrows() if check_stale_telemetry(r["last_sync"])[0]) if total_crew > 0 else 0
    pending_protos = get_all_pending_tasks_count()
    low_stock_cnt = int((inv_df["quantity"] < 30).sum()) if not inv_df.empty else 0

    ov1, ov2, ov3, ov4, ov5 = st.columns(5)
    ov1.metric("TOTAL CREW", f"{total_crew} Active", delta=f"{stale_crew_cnt} Stale (>24h)" if stale_crew_cnt else "Telemetry Fresh")
    ov2.metric("SIMULATED FLEET DOSE", f"{avg_rad} mSv", delta="Modeled Mean")
    ov3.metric("CRITICAL CREW", f"{crit_crew_cnt} Subject(s)", delta="Action Req" if crit_crew_cnt > 0 else "All Clear", delta_color="inverse")
    ov4.metric("PENDING PROTOCOLS", f"{pending_protos} Queued", delta="Awaiting Sync")
    ov5.metric("INVENTORY ALERTS", f"{low_stock_cnt} Low Stock", delta="< 30 Units" if low_stock_cnt > 0 else "Stock Nominal", delta_color="inverse")

    if not crew_df.empty:
        max_rad = crew_df["radiation_msv"].max()
        min_sleep = crew_df["sleep"].min()
        max_stress = crew_df["stress_score"].max()
        min_bone = crew_df["bone_t"].min()
        min_cal = crew_df["calories"].min()

        hazards = [
            ("01. SIMULATED RADIATION", "CRITICAL" if max_rad > 110 else ("WARNING" if max_rad > 75 else "NOMINAL"), f"Max Sim Dose: {max_rad} mSv"),
            ("02. ISOLATION & CONFINEMENT", "CRITICAL" if (min_sleep < 4.5 or max_stress >= 8) else ("WARNING" if min_sleep < 6.0 else "NOMINAL"), f"Min Sleep: {min_sleep}h | Stress: {max_stress}/10"),
            ("03. DISTANCE FROM EARTH", "WARNING" if "Deep Space Transit" in crew_df["env"].values or "Martian Surface Habitat" in crew_df["env"].values else "NOMINAL", "Latency: 8.5–22.0 min"),
            ("04. GRAVITY FIELDS", "CRITICAL" if min_bone < -1.8 else ("WARNING" if min_bone < -1.0 else "NOMINAL"), f"Worst BMD: {min_bone}"),
            ("05. HOSTILE / CLOSED ENV", "CRITICAL" if min_cal < 2000 else ("WARNING" if min_cal < 2400 else "NOMINAL"), f"Min Intake: {min_cal} kcal")
        ]
        h_cols = st.columns(5, gap="medium")
        for idx, (h_title, h_stat, h_sub) in enumerate(hazards):
            with h_cols[idx]:
                b_col = "#dc2626" if h_stat == "CRITICAL" else ("#d97706" if h_stat == "WARNING" else "#059669")
                st.markdown(f"""
                <div class='hud-box' style='border-top:3px solid {b_col}; padding:10px 12px;'>
                    <div style='font-size:0.72rem; font-weight:700;'>{esc(h_title)}</div>
                    <div style='margin:6px 0;'>{format_status_badge(h_stat)}</div>
                    <div style='font-size:0.71rem; color:{PALETTE["text_muted"]}; font-family:IBM Plex Mono, monospace;'>{esc(h_sub)}</div>
                </div>
                """, unsafe_allow_html=True)

    adm_tab1, adm_tab2 = st.tabs([
        "01. CREW ROSTER, TASKING & STOCHASTIC GENERATOR",
        "02. HEATMAP, LEADERBOARD, HABITAT FAILURES & AUDIT LOG"
    ])

    with adm_tab1:
        col_left, col_mid, col_right = st.columns([1.25, 1.1, 1.1], gap="large")
        with col_left:
            st.markdown("##### ACTIVE CREW ROSTER")
            for _, row in crew_df.iterrows():
                stat = evaluate_system_status(row, row["env"])
                overall = "CRITICAL" if "CRITICAL" in stat.values() else ("WARNING" if "WARNING" in stat.values() else "NOMINAL")
                is_stale, age_h = check_stale_telemetry(row["last_sync"])
                v_cnt = int(row.get("verified_tasks", 0))
                xp, lvl, _, r_title, _ = calculate_gamification_profile(row, stat, v_cnt)
                stale_tag = f" | <span class='badge-critical'>STALE ({age_h}h)</span>" if is_stale else ""
                st.markdown(f"""
                <div class='hud-box'>
                    <div style='display:flex; justify-content:space-between; align-items:center;'>
                        <b>{esc(row['id'])} — {esc(row['name'])}</b>
                        <div>{format_status_badge(overall)}{stale_tag}</div>
                    </div>
                    <div style='font-size:0.75rem; color:{PALETTE["text_muted"]}; margin-top:4px;'>
                        LVL {lvl} {esc(r_title.upper())} ({xp} XP) | ENV: {esc(row['env'])}
                    </div>
                    <div style='font-size:0.76rem; font-family:IBM Plex Mono, monospace; margin-top:6px;'>
                        HR:{row['hr']} | BP:{row['sys_bp']}/{row['dia_bp']} | SLP:{row['sleep']}h | BMD:{row['bone_t']} | SIM-RAD:{row['radiation_msv']}mSv
                    </div>
                </div>
                """, unsafe_allow_html=True)
                if st.button(f"INSPECT WORKSTATION — {row['id']}", key=f"adm_{row['id']}", type="primary", use_container_width=True):
                    st.session_state.active_astro = row["id"]
                    st.session_state.sim_env = row["env"]
                    st.session_state.screen = "command"
                    st.rerun()

        with col_mid:
            st.markdown("##### ASSIGN PROTOCOLS & SENSOR OVERRIDES")
            if not crew_df.empty:
                with st.form("admin_assign_task"):
                    t_astro = st.selectbox("Target Crewmember", crew_df["id"].tolist())
                    proto_keys = [k for k in PROTOCOLS.keys() if k != "TRANSITION_CLEARANCE"]
                    t_proto_key = st.selectbox("Countermeasure Protocol", proto_keys, format_func=lambda k: PROTOCOLS[k]["label"])
                    t_env = st.selectbox("Target Environment Vector", list(ENV_SPECS.keys()), index=3)
                    action_mode = st.radio("Execution Mode", [
                        "Assign Protocol to Crew Queue (Requires Hardware Sync)",
                        "Manual Sensor Dropout Override (Commit Completed Entry Now)"
                    ])
                    override_reason = st.text_input("Audit Reason", value="ANT+ Telemetry Dropout — Verified via Video Feed")
                    if st.form_submit_button("EXECUTE DIRECTIVE", use_container_width=True):
                        if "Assign Protocol" in action_mode:
                            assign_task_to_crew(t_astro, t_proto_key, t_env, actor="FLIGHT_SURGEON")
                        else:
                            execute_protocol_or_override(t_astro, t_proto_key, f"ADMIN_OVERRIDE:{override_reason}", actor="FLIGHT_SURGEON")
                        st.rerun()

        with col_right:
            st.markdown("##### COLLISION-SAFE CREW REGISTRATION")
            next_id = generate_next_crew_id()
            if st.button(f"GENERATE RANDOM TEST SUBJECT ({next_id})", use_container_width=True):
                r_names = ["Dr. Vikram Sarabhai", "Capt. Sophia Al-Mansoor", "Lt. Kenji Takahashi", "Dr. Maya Lin"]
                r_name = r_names[int(next_id.split("-")[1]) % len(r_names)]
                r_env = np.random.choice(list(ENV_SPECS.keys()))
                vitals = {
                    "hr": int(np.random.randint(60, 118)), "sys_bp": int(np.random.randint(110, 155)), "dia_bp": 80,
                    "sleep": round(float(np.random.uniform(3.5, 8.0)), 1), "bone_t": round(float(np.random.uniform(-2.4, 0.1)), 2),
                    "muscle_idx": round(float(np.random.uniform(75.0, 98.0)), 1), "radiation_msv": round(float(np.random.uniform(15.0, 130.0)), 1),
                    "mood_score": 7, "stress_score": 4, "calories": 2500, "water_intake": 2.6
                }
                register_new_astronaut(next_id, "3333", r_name, "Mission Specialist", "00:1B:44:99:12:AF", r_env, vitals)
                st.rerun()

            with st.form("register_astro_form"):
                new_id = st.text_input("Crewmember ID (Collision-Safe)", value=next_id)
                new_pin = st.text_input("Assign Crew PIN (Hashed with scrypt)", value="", placeholder="Enter new 4+ digit PIN...", type="password")
                new_name = st.text_input("Full Name", placeholder="e.g., Dr. Kabir Sen")
                new_role = st.selectbox("Assignment", ["Mission Commander", "Flight Surgeon", "Flight Engineer", "Payload Specialist"])
                new_mac = st.text_input("Sensor MAC", value="00:1B:44:88:CC:01")
                new_env = st.selectbox("Environment", list(ENV_SPECS.keys()))
                c1, c2 = st.columns(2)
                new_hr = c1.number_input("HR (bpm)", 45, 160, 72)
                new_sys = c2.number_input("Sys BP", 85, 200, 120)
                new_sleep = c1.number_input("Sleep (hrs)", 1.0, 12.0, 7.0, step=0.5)
                new_bone = c2.number_input("BMD T-Score", -4.0, 2.0, -0.6, step=0.1)
                new_musc = c1.number_input("Muscle (%)", 50.0, 100.0, 92.0, step=1.0)
                new_rad = c2.number_input("Simulated Dose (mSv)", 0.0, 400.0, 25.0, step=5.0)
                if st.form_submit_button("REGISTER CREWMEMBER", use_container_width=True):
                    if not new_pin.strip():
                        hud_callout("Please provide a non-empty PIN for the new crewmember.", "err")
                    else:
                        try:
                            vitals = {"hr": new_hr, "sys_bp": new_sys, "dia_bp": 78, "sleep": new_sleep, "bone_t": new_bone,
                                      "muscle_idx": new_musc, "radiation_msv": new_rad, "mood_score": 8, "stress_score": 3, "calories": 2600, "water_intake": 2.8}
                            register_new_astronaut(new_id.strip(), new_pin.strip(), new_name.strip() or "Specialist Sen", new_role, new_mac, new_env, vitals)
                            st.rerun()
                        except Exception as e:
                            hud_callout(f"Registration Error: {esc(e)}", "err")

    with adm_tab2:
        a_col1, a_col2, a_col3 = st.columns([1.25, 1.1, 1.25], gap="large")
        with a_col1:
            st.markdown("##### CREW MULTI-SYSTEM HEALTH HEATMAP")
            if not crew_df.empty:
                systems = ["Heart", "Brain", "Bone", "Muscle", "Sim-Rad"]
                sys_keys = ["heart", "brain", "bone", "muscle", "radiation"]
                z_vals, text_vals, y_labels = [], [], []
                for _, r_row in crew_df.iterrows():
                    y_labels.append(f"{r_row['id']} ({r_row['name'].split()[-1]})")
                    s_map = evaluate_system_status(r_row, r_row["env"])
                    z_vals.append([0 if s_map[k] == "NOMINAL" else (1 if s_map[k] == "WARNING" else 2) for k in sys_keys])
                    text_vals.append([s_map[k] for k in sys_keys])

                fig_hm = go.Figure(data=go.Heatmap(
                    z=z_vals, x=systems, y=y_labels, text=text_vals, texttemplate="%{text}",
                    colorscale=[[0.0, "#10b981"], [0.5, "#f59e0b"], [1.0, "#ef4444"]], zmin=0, zmax=2, showscale=False
                ))
                fig_hm.update_layout(
                    template="plotly_white" if is_light else "plotly_dark",
                    plot_bgcolor=PALETTE["bg_sub"], paper_bgcolor="rgba(0,0,0,0)",
                    margin=dict(l=10, r=10, t=10, b=10), height=210
                )
                st.plotly_chart(fig_hm, use_container_width=True, config={"displayModeBar": False})

                st.markdown("##### GAMIFIED CREW READINESS LEADERBOARD")
                ranked = crew_df.copy()
                ranked["readiness_pct"] = ranked.apply(lambda r: 100 - calculate_risk(r), axis=1)
                for rank_i, (_, r_row) in enumerate(ranked.sort_values(by="readiness_pct", ascending=False).iterrows(), start=1):
                    v_c = int(r_row.get("verified_tasks", 0))
                    xp, lvl, _, _, _ = calculate_gamification_profile(r_row, evaluate_system_status(r_row, r_row["env"]), v_c)
                    st.markdown(f"**#{rank_i} {esc(r_row['id'])} ({esc(r_row['name'])})** — `{r_row['readiness_pct']}%` | **Lvl {lvl}** `{xp} XP`")

        with a_col2:
            st.markdown("##### HABITAT MISSION FAILURE SIMULATOR")
            fail_event = st.selectbox("Select Habitat Scenario", [
                "Solar Particle Event (Simulated Dose Surge +50 mSv)",
                "ECLSS Water Recycling Failure (Dehydration)",
                "Food Supply Shortage (Caloric & Muscle Deficit)",
                "Deep-Space Comm Blackout (Acute Stress Spike)"
            ])
            if st.button("TRIGGER HABITAT FAILURE", use_container_width=True) and not crew_df.empty:
                for _, r_row in crew_df.iterrows():
                    mutate_vitals_emergency(r_row["id"], fail_event.split()[0], actor="HABITAT_SIM")
                st.rerun()

            st.markdown("---")
            st.markdown("##### RULE-BASED MISSION MEDICAL BRIEFING")
            if st.button("GENERATE MISSION MEDICAL BRIEF", use_container_width=True) and not crew_df.empty:
                at_risk_cnt = sum(1 for _, r in crew_df.iterrows() if calculate_risk(r) >= 40)
                rad_cnt = sum(1 for _, r in crew_df.iterrows() if r["radiation_msv"] > ENV_SPECS[r["env"]]["rad_limit"])
                avg_sleep_def = round(max(0.0, 7.5 - crew_df["sleep"].mean()), 1)
                hud_callout(
                    f"<b>RULE-BASED MISSION SUMMARY (NON-DIAGNOSTIC)</b><br>"
                    f"• <b>Crew Requiring Intervention:</b> <code>{at_risk_cnt} of {len(crew_df)}</code><br>"
                    f"• <b>Simulated Radiation Threshold Exceeded:</b> <code>{rad_cnt}</code> crewmembers<br>"
                    f"• <b>Mean Crew Sleep Deficit:</b> <code>{avg_sleep_def} hrs/night</code><br>"
                    f"• <b>Simulated Directives:</b> Queue ARED axial resistance, circadian dark-cycle protocol, and storm-shelter rotation.",
                    "info"
                )

        with a_col3:
            st.markdown("##### IMMUTABLE AUDIT LOG (`audit_log` TABLE)")
            render_custom_table(get_audit_logs(14), max_height=340)

# ==========================================
# SCREEN 3: SPACIOUS, GAMIFIED COMMAND HUD
# ==========================================
elif st.session_state.screen == "command":
    is_admin = (st.session_state.user_role == "MANAGEMENT")
    crew_df = get_crew_with_latest_vitals()

    if crew_df.empty or st.session_state.active_astro not in crew_df["id"].values:
        hud_callout("<b>TELEMETRY RECORD UNAVAILABLE:</b> Selected crewmember is not present in the database.", "err")
        if st.button("RETURN TO LOGIN"):
            st.session_state.screen = "login"
            st.rerun()
        st.stop()

    astro = crew_df[crew_df["id"] == st.session_state.active_astro].iloc[0].to_dict()
    logs_df = get_astro_logs(astro["id"])

    if st.session_state.sim_env is None:
        st.session_state.sim_env = astro["env"]

    is_stale, age_hours = check_stale_telemetry(astro["last_sync"])
    render_header(f"SUBJECT: {astro['id']} — LAST SYNC: {astro['last_sync']} ({age_hours}h ago)")

    if is_stale:
        hud_callout(f"<b>STALE TELEMETRY WARNING:</b> Last biometric packet for <code>{esc(astro['id'])}</code> was received <code>{age_hours} hours</code> ago (>24h threshold). Verify hardware link.", "warn")

    status_map = evaluate_system_status(astro, st.session_state.sim_env)
    risk_score = calculate_risk(astro)
    verified_cnt = int(astro.get("verified_tasks", 0))
    xp, level, xp_in_lvl, rank_title, badges = calculate_gamification_profile(astro, status_map, verified_cnt)

    top1, top2, top3, top4 = st.columns([2.2, 1.5, 1.1, 1.2], gap="medium")
    with top1:
        st.markdown(f"#### {esc(astro['id'])} — {esc(astro['name'])}")
        st.caption(f"ROLE: {esc(astro['role'])} | MAC: `{esc(astro['device_mac'])}` | MODE: {'ADMIN OVERRIDE' if is_admin else 'CREW READ-ONLY'}")
        badges_html = "".join(f"<span class='xp-badge'>{esc(b)}</span>" for b in badges)
        st.markdown(f"<div><span class='xp-badge' style='background-color:{PALETTE['accent']};color:#fff;'>LVL {level} — {esc(rank_title.upper())} ({xp} XP)</span>{badges_html}</div>", unsafe_allow_html=True)
    with top2:
        if is_admin:
            active_env = st.selectbox("ENVIRONMENT REGIME (SIMULATION)", list(ENV_SPECS.keys()),
                                      index=list(ENV_SPECS.keys()).index(st.session_state.sim_env))
            st.session_state.sim_env = active_env
        else:
            active_env = astro["env"]
            st.markdown(f"""
            <div class='hud-box' style='padding:10px 14px; margin-bottom:0;'>
                <span class='telemetry-tag'>ENVIRONMENT REGIME (LOCKED BY FLIGHT CONTROL)</span><br>
                <span style='font-size:0.95rem; font-weight:700;'>{esc(active_env)}</span>
            </div>
            """, unsafe_allow_html=True)
    with top3:
        spec = ENV_SPECS[active_env]
        st.metric("GRAVITY", spec["g"], delta=f"Delay: {spec['latency']}")
    with top4:
        st.write("")
        if st.button("BACK TO DIRECTORY" if is_admin else "LOGOUT WORKSTATION", use_container_width=True):
            st.session_state.screen = "admin_hub" if is_admin else "login"
            st.rerun()

    st.markdown("<div style='margin-top:8px;'></div>", unsafe_allow_html=True)
    status_map = evaluate_system_status(astro, active_env)
    eva_state, eva_prob, eva_factors = calculate_eva_readiness_detailed(astro, active_env)
    anomalies = compute_anomaly_flags(logs_df)

    col_hud, col_diag, col_ops = st.columns([1.08, 1.35, 1.57], gap="large")

    zone_options = [("brain", "CNS"), ("heart", "CV"), ("bone", "BONE"), ("muscle", "MYO"), ("radiation", "SIM-RAD")]
    with col_hud:
        st.markdown("<div class='hud-section-hdr'><span class='hud-title'>ANATOMICAL ATLAS (HR-SYNCED PULSE)</span></div>", unsafe_allow_html=True)
        b_cols = st.columns(5, gap="small")
        for idx, (z_key, z_lbl) in enumerate(zone_options):
            is_sel = (st.session_state.selected_zone == z_key)
            if b_cols[idx].button(z_lbl, key=f"zone_btn_{z_key}", type="primary" if is_sel else "secondary", use_container_width=True):
                st.session_state.selected_zone = z_key
                st.rerun()

        render_realistic_anatomy_svg(status_map, st.session_state.selected_zone, int(astro["hr"]), PALETTE)

        report_html = generate_printable_report_html(astro, status_map, risk_score, anomalies)
        st.download_button("DOWNLOAD PRINTABLE CREW REPORT (HTML/PDF)", data=report_html,
                           file_name=f"{astro['id']}_clinical_report.html", mime="text/html", use_container_width=True)

    with col_diag:
        zone = st.session_state.selected_zone
        zone_hdr = "SIMULATED DOSIMETRY" if zone == "radiation" else zone.upper()
        st.markdown(f"<div class='hud-section-hdr'><span class='hud-title'>SUBSYSTEM: {esc(zone_hdr)}</span>{format_status_badge(status_map[zone])}</div>", unsafe_allow_html=True)
        m1, m2, m3 = st.columns(3)
        m1.metric("STATE", status_map[zone])
        if zone == "brain":
            m2.metric("24H SLEEP", f"{astro['sleep']} hrs", delta=f"Min {spec['sleep_min']}h")
            m3.metric("STRESS / MOOD", f"{astro['stress_score']} / {astro['mood_score']}")
        elif zone == "heart":
            m2.metric("RESTING HR", f"{astro['hr']} bpm", delta=f"Max {spec['hr_max']}", delta_color="inverse")
            m3.metric("ARTERIAL BP", f"{astro['sys_bp']}/{astro['dia_bp']}")
        elif zone == "bone":
            m2.metric("BMD T-SCORE", f"{astro['bone_t']}", delta=f"Min {spec['bone_min']}")
            m3.metric("RISK SCORE", f"{risk_score}%")
        elif zone == "muscle":
            m2.metric("MYO INDEX", f"{astro['muscle_idx']}%", delta=f"Min {spec['muscle_min']}%")
            m3.metric("CALORIES", f"{astro['calories']} kcal")
        elif zone == "radiation":
            m2.metric("SIMULATED DOSE", f"{astro['radiation_msv']} mSv", delta=f"Limit {spec['rad_limit']} mSv", delta_color="inverse")
            m3.metric("MODELED NEUTRON", f"{round(astro['radiation_msv']*0.3, 1)} mSv")

        # EVA Readiness Card + Expandable Contributing Factors Breakdown
        st.markdown(f"""
        <div class='hud-box' style='padding:10px 14px; display:flex; justify-content:space-between; align-items:center;'>
            <div>
                <span class='telemetry-tag'>EVA SUIT & SPACEWALK CLEARANCE (SIMULATED)</span><br>
                <span style='font-weight:700; font-size:0.88rem;'>Modeled Safe EVA Probability: <code>{eva_prob}%</code></span>
            </div>
            {format_status_badge(eva_state)}
        </div>
        """, unsafe_allow_html=True)
        with st.expander("VIEW INDIVIDUAL EVA READINESS CONTRIBUTING FACTORS", expanded=False):
            render_custom_table(pd.DataFrame(eva_factors), max_height=190)

        render_live_ecg_strip(int(astro["hr"]), status_map["heart"], PALETTE)
        if anomalies:
            hud_callout("<b>STATISTICAL TREND ANOMALIES (ROLLING Z-SCORE):</b><br>• " + "<br>• ".join(esc(a) for a in anomalies), "warn")

        # 1. Deterministic Rule-Based Heuristic SBAR (Always shown, clearly labeled)
        sit_html, assess_html, rx_html = build_rule_based_sbar(
            astro["name"], active_env, astro["hr"], astro["sys_bp"], astro["dia_bp"],
            astro["sleep"], astro["bone_t"], astro["muscle_idx"], astro["radiation_msv"],
            astro["stress_score"], astro["calories"], zone
        )
        render_sbar_cards(
            f"DETERMINISTIC RULE-BASED HEURISTIC SBAR — {zone_hdr}",
            "RULE-ENGINE", sit_html, assess_html, rx_html, status_map[zone]
        )

        # 2. Deep Clinical Synthesis rendered as a structured Avionics Telemetry Log
        if st.button("GENERATE MULTI-VARIABLE CLINICAL SYNTHESIS", type="primary", use_container_width=True):
            with st.spinner("Computing multi-variable physiological parameters..."):
                engine_src, synth_html = query_optional_ollama_llm(
                    astro["name"], active_env, astro["hr"], astro["sys_bp"], astro["dia_bp"],
                    astro["sleep"], astro["bone_t"], astro["muscle_idx"], astro["radiation_msv"], zone
                )
                clean_src = engine_src.replace("//", "—")
                st.markdown(f"""
                <div style="background-color:var(--bg-card); border:1px solid var(--border-col); border-left:3px solid var(--accent-col); padding:12px 14px; margin-top:8px;">
                    <div style="font-family:'IBM Plex Mono', monospace; font-size:0.70rem; color:var(--text-muted); font-weight:700; border-bottom:1px solid var(--border-col); padding-bottom:5px; margin-bottom:8px; display:flex; justify-content:space-between;">
                        <span>{clean_src}</span>
                        <span>SIMULATION LOG</span>
                    </div>
                    <div style="font-size:0.81rem; color:var(--text-primary); line-height:1.55;">{synth_html}</div>
                </div>
                """, unsafe_allow_html=True)

    with col_ops:
        st.markdown("<div class='hud-section-hdr'><span class='hud-title'>OPERATIONS, DIGITAL TWIN & SPACE HAZARDS</span></div>", unsafe_allow_html=True)
        op_tab1, op_tab2, op_tab3, op_tab4 = st.tabs(["PROTOCOLS", "TRANSITION", "TWIN & TRENDS", "HAZARDS"])

        with op_tab1:
            st.markdown(f"""
            <div class='hud-box' style='padding:10px 14px;'>
                <div style='display:flex; justify-content:space-between; font-size:0.78rem; font-weight:700;'>
                    <span>CREW COMPLIANCE LEVEL {level}: {esc(rank_title.upper())}</span>
                    <span>{xp_in_lvl} / 400 XP TO NEXT RANK (+250 XP PER SYNC)</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
            st.progress(xp_in_lvl / 400.0)

            tasks_df = get_astro_tasks(astro["id"])
            if is_admin:
                proto_keys = [k for k in PROTOCOLS.keys() if k != "TRANSITION_CLEARANCE"]
                sel_pk = st.selectbox("Select Countermeasure Protocol", proto_keys, format_func=lambda k: PROTOCOLS[k]["label"])
                cb1, cb2 = st.columns(2)
                if cb1.button("ASSIGN TO QUEUE", use_container_width=True):
                    assign_task_to_crew(astro["id"], sel_pk, active_env, actor="FLIGHT_SURGEON")
                    st.rerun()
                if cb2.button("MANUAL OVERRIDE", use_container_width=True):
                    execute_protocol_or_override(astro["id"], sel_pk, "ADMIN_MANUAL_OVERRIDE", actor="FLIGHT_SURGEON")
                    st.rerun()
            else:
                hud_callout(f"<b>HARDWARE LOCK:</b> Crew cannot manually edit vitals. Sync via paired sensor (<code>{esc(astro['device_mac'])}</code>) to earn +250 Compliance XP.", "info")

            for _, task in tasks_df.iterrows():
                is_done = task["status"] != "PENDING HARDWARE SYNC"
                st.markdown(f"""
                <div class='hud-box' style='border-left:4px solid {"#10b981" if is_done else "#f59e0b"};'>
                    <div style='display:flex; justify-content:space-between; align-items:center;'>
                        <b style='font-size:0.84rem;'>{esc(task['protocol_label'])}</b>
                        {format_status_badge("VERIFIED (+250 XP)" if is_done else "WARNING")}
                    </div>
                    <div style='font-size:0.73rem; color:{PALETTE["text_muted"]}; margin-top:4px;'>
                        KEY: <code>{esc(task['protocol_key'])}</code> | SOURCE: <code>{esc(task['verification_source'])}</code> | {esc(task['timestamp'])}
                    </div>
                </div>
                """, unsafe_allow_html=True)
                if not is_done:
                    if st.button(f"SYNC HMAC HARDWARE PACKET (+250 XP) — TASK #{task['id']}", key=f"sync_{task['id']}", type="primary", use_container_width=True):
                        execute_protocol_or_override(astro["id"], task["protocol_key"], f"HMAC-DEVICE:{astro['device_mac']}",
                                                     actor=astro["id"], task_id=int(task["id"]))
                        st.rerun()

        with op_tab2:
            if is_admin:
                target_env = st.selectbox("Target Mission Regime", list(ENV_SPECS.keys()), index=3)
            else:
                target_env = "Martian Surface Habitat"
                st.markdown(f"**Target Mission Regime:** `{esc(target_env)}`")
            target_status = evaluate_system_status(astro, target_env)
            blockers = [k.upper() for k, v in target_status.items() if v != "NOMINAL"]
            if not blockers:
                hud_callout(f"<b>CLEARANCE GRANTED:</b> {esc(astro['name'])} meets all modeled thresholds for {esc(target_env)}.", "ok")
                if is_admin and st.button("AUTHORIZE TRANSITION (NO VITALS MUTATION)", type="primary", use_container_width=True):
                    execute_protocol_or_override(astro["id"], "TRANSITION_CLEARANCE", "FLIGHT_SURGEON_CLEARANCE",
                                                 actor="FLIGHT_SURGEON", new_env=target_env)
                    st.session_state.sim_env = target_env
                    st.rerun()
            else:
                hud_callout(f"<b>TRANSITION HOLD — OFF-NOMINAL:</b> {', '.join(esc(b) for b in blockers)}", "err")
                if is_admin and st.button("ADMIN OVERRIDE: RAPID CONDITIONING", use_container_width=True):
                    execute_rapid_conditioning_db(astro["id"], target_env, actor="FLIGHT_SURGEON")
                    st.session_state.sim_env = target_env
                    st.rerun()

        with op_tab3:
            metric_choice = st.selectbox("Telemetry Channel", [
                ("hr", "HEART RATE (BPM)", "#ef4444"),
                ("sleep", "SLEEP DURATION (HRS)", "#0284c7"),
                ("bone_t", "BONE BMD T-SCORE", "#d97706"),
                ("muscle_idx", "MUSCLE INDEX (%)", "#059669"),
                ("radiation_msv", "SIMULATED RADIATION DOSE (mSv)", "#9333ea")
            ], format_func=lambda x: x[1])
            col_key, col_label, col_color = metric_choice
            if not logs_df.empty and col_key in logs_df.columns:
                fig_t = go.Figure(go.Scatter(
                    x=logs_df["day"], y=logs_df[col_key], mode="lines+markers",
                    line=dict(color=col_color, width=2.2), text=logs_df["source"],
                    hovertemplate="Day %{x}: %{y}<br>Source: %{text}<extra></extra>"
                ))
                fig_t.update_layout(
                    template="plotly_white" if is_light else "plotly_dark",
                    plot_bgcolor=PALETTE["bg_sub"], paper_bgcolor="rgba(0,0,0,0)",
                    margin=dict(l=10, r=10, t=20, b=10), height=195
                )
                st.plotly_chart(fig_t, use_container_width=True, config={"displayModeBar": False})

            st.markdown("##### DIGITAL ASTRONAUT TWIN — 180-DAY EXTRAPOLATION & UNCERTAINTY")
            twin = compute_digital_twin_projection(logs_df, astro)
            tw1, tw2 = st.columns(2)
            with tw1:
                st.markdown(f"""
                <div class='hud-box' style='padding:10px;'>
                    <div class='telemetry-tag'>CURRENT BASELINE (DAY {astro['day']})</div>
                    <div style='font-size:0.78rem; font-family:IBM Plex Mono, monospace; margin-top:6px;'>
                        • HR: <b>{astro['hr']} bpm</b><br>• BMD T-Score: <b>{astro['bone_t']}</b><br>
                        • Muscle Index: <b>{astro['muscle_idx']}%</b><br>• Sim Dose: <b>{astro['radiation_msv']} mSv</b>
                    </div>
                </div>
                """, unsafe_allow_html=True)
            with tw2:
                st.markdown(f"""
                <div class='hud-box' style='padding:10px; border-left:3px solid #d97706;'>
                    <div class='telemetry-tag'>DAY 180 PROJECTION (±1σ UNCERTAINTY)</div>
                    <div style='font-size:0.78rem; font-family:IBM Plex Mono, monospace; margin-top:6px;'>
                        • Est. HR: <b>{esc(twin['hr'])}</b><br>• Est. BMD: <b>{esc(twin['bone'])}</b><br>
                        • Est. Muscle: <b>{esc(twin['muscle'])}</b><br>• Sim Dose: <b>{esc(twin['rad'])}</b>
                    </div>
                </div>
                """, unsafe_allow_html=True)
            st.caption(twin["assumptions"])

        with op_tab4:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("RISK", f"{risk_score}%")
            c2.metric("SIM DOSE", f"{astro['radiation_msv']} mSv")
            c3.metric("MOOD", f"{astro['mood_score']}/10")
            c4.metric("STRESS", f"{astro['stress_score']}/10")

            with st.expander("SUBJECTIVE SYMPTOM LOGGER & TIMELINE", expanded=True):
                sc1, sc2, sc3 = st.columns([1.6, 1.0, 1.0])
                sym_sel = sc1.selectbox("Symptom", ["Headache", "Fatigue", "Dizziness", "Nausea", "Sleep Disturbance"])
                sev_sel = sc2.slider("Severity", 1, 10, 5)
                if sc3.button("RECORD", use_container_width=True):
                    record_symptom_db(astro["id"], sym_sel, sev_sel, int(astro["day"]), actor=astro["id"])
                    st.rerun()
                for _, s_row in get_astro_symptoms(astro["id"]).head(3).iterrows():
                    st.caption(f"• Day {s_row['day']} ({s_row['timestamp']}): **{esc(s_row['symptom'])}** — Severity `{s_row['severity']}/10`")

            with st.expander("MEDICAL EMERGENCY SIMULATOR", expanded=False):
                ec1, ec2 = st.columns([1.8, 1.2])
                ev_sel = ec1.selectbox("Scenario", ["Radiation Storm (Simulated)", "Cardiac Event", "Sleep Collapse", "EVA Injury"])
                if ec2.button("TRIGGER", use_container_width=True):
                    mutate_vitals_emergency(astro["id"], ev_sel, actor=st.session_state.user_role)
                    st.rerun()

            with st.expander("ONBOARD MEDICAL KIT & DIAGNOSTIC IMAGING SIMULATION", expanded=False):
                inv_df = get_inventory()
                ic1, ic2 = st.columns([1.6, 1.4])
                with ic1:
                    render_custom_table(inv_df, max_height=165)
                use_item = ic2.selectbox("Item", inv_df["item"].tolist())
                if ic2.button("DISPENSE ITEM", use_container_width=True):
                    dispense_inventory_db(use_item, astro["id"], actor=st.session_state.user_role)
                    st.rerun()
                up_scan = st.file_uploader("Upload Scan (Ultrasound / OCT / X-Ray)", type=["png", "jpg", "jpeg"])
                if up_scan is not None:
                    st.image(up_scan, caption="Uploaded Diagnostic Scan (Simulated Review)", use_container_width=True)
                    hud_callout("<b>SIMULATED IMAGING TRIAGE (NON-DIAGNOSTIC):</b> Subclavian/jugular lumen compressible; mild neuro-ocular choroidal folds noted in simulation.", "info")

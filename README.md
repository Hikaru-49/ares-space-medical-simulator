# A.R.E.S. // Autonomous Spaceflight Medical Decision Simulator

A modular, zero-trust medical telemetry simulation console built for spaceflight missions (Artemis II / ISS / Mars Transit). Developed for hackathon evaluation and bioastronautics research.

---
## 🌐 Live Demo & Access
**Live Streamlit App:** https://ares-space-medical-simulator.streamlit.app

**GitHub Repository:** https://github.com/Hikaru-49/ares-space-medical-simulator

---
## 🔑 Demo Access & Credentials (For Judges & Reviewers)

To test the application instantly without manual registration, use the built-in demo credentials or click the **Quick Demo Bypass** buttons on the login screen:

* **Flight Surgeon / Management Console:**
  * **Passcode:** `ARES-ADMIN`
* **Astronaut Crew Workstation:**
  * **ASTRO-001 (Cmdr. Elena Vance):** PIN `1111`
  * **ASTRO-002 (Dr. Marcus Chen):** PIN `2222`

---

## 📂 Codebase Architecture & File Manifest

| File Name | Architecture Role & Key Logic |
| :--- | :--- |
| **`app.py`** | Main Streamlit orchestrator managing the cinematic radar boot screen, Flight Surgeon command hub, and crew workstation UI fragments. |
| **`db.py`** | Relational SQLite database engine utilizing explicit atomic transactions (`BEGIN IMMEDIATE`), salted `scrypt` credential hashing, rate-limiting, and immutable audit logging. |
| **`theme.py`** | Clean CSS variable injection, responsive grid layouts, XSS-safe HTML table generator (`render_custom_table`), and structured SBAR clinical log cards. |
| **`anatomy_svg.py`** | 60 FPS HiDPI HTML5 `<canvas>` ECG oscilloscope and HR-synchronized 5-layer volumetric anatomical SVG atlas (ribs, limbs, striated myotomes, gyri). |
| **`config.py`** | Central configuration constants, 5 NASA spaceflight environment hazard specifications (`ENV_SPECS`), and data-driven countermeasure protocols (`PROTOCOLS`). |
| **`ingest_api.py`** | FastAPI background telemetry ingestion gateway verifying HMAC-SHA256 signed hardware packets (`/api/v1/telemetry`). |
| **`test_ares.py`** | Comprehensive `pytest` test suite verifying physiological thresholds, transaction integrity, non-mutation transition checks, and cryptographic PIN hashing. |

---

## 🚀 Local Installation & Running Instructions

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/Hikaru-49/ares-space-medical-simulator.git](https://github.com/Hikaru-49/ares-space-medical-simulator.git)
   cd ares-space-medical-simulator

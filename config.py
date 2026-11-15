SIMULATION_DISCLAIMER = (
    "SIMULATION / EDUCATIONAL PROTOTYPE — Synthetic telemetry, modeled physiological thresholds, "
    "and simulated 60 FPS waveforms. Not affiliated with or endorsed by NASA."
)

ENV_SPECS = {
    "Earth Orbit (LEO Station)": {
        "g": "0.00 G (Microgravity)",
        "latency": "0.02 sec",
        "hr_max": 90,
        "sys_max": 135,
        "sleep_min": 6.0,
        "bone_min": -1.5,
        "muscle_min": 85.0,
        "rad_limit": 50.0,
        "desc": "Magnetospheric shielding (~30% modeled neutron contribution). High cephalad fluid shift and neuro-ocular risk."
    },
    "Deep Space Transit": {
        "g": "0.00 G (Interplanetary)",
        "latency": "8.5 min",
        "hr_max": 85,
        "sys_max": 130,
        "sleep_min": 6.5,
        "bone_min": -1.0,
        "muscle_min": 88.0,
        "rad_limit": 100.0,
        "desc": "Unshielded galactic cosmic ray flux, circadian drift, and zero mechanical skeletal loading (~1.5%/mo modeled bone loss)."
    },
    "Lunar Surface Outpost": {
        "g": "0.16 G (Hypogravity)",
        "latency": "1.3 sec",
        "hr_max": 95,
        "sys_max": 140,
        "sleep_min": 6.0,
        "bone_min": -1.5,
        "muscle_min": 85.0,
        "rad_limit": 80.0,
        "desc": "Partial axial loading (1/6 G). Elevated risk of silicate dust inhalation and high-exertion EVA workloads."
    },
    "Martian Surface Habitat": {
        "g": "0.38 G (Partial Gravity)",
        "latency": "22.0 min",
        "hr_max": 95,
        "sys_max": 135,
        "sleep_min": 6.5,
        "bone_min": -1.2,
        "muscle_min": 90.0,
        "rad_limit": 120.0,
        "desc": "Up to 22-minute one-way communication latency. High orthostatic intolerance risk following microgravity transit."
    },
    "Spacecraft (EVA Prep)": {
        "g": "0.00 G (4.3 psi Suit)",
        "latency": "0.1 sec",
        "hr_max": 80,
        "sys_max": 125,
        "sleep_min": 7.0,
        "bone_min": -1.0,
        "muscle_min": 92.0,
        "rad_limit": 60.0,
        "desc": "Denitrogenation pre-breathe protocol (decompression vs. mild hypoxia trade-off). High upper-limb strain."
    }
}

PROTOCOLS = {
    "ARED_AXIAL": {
        "label": "ARED Heavy Axial Resistance (Squat/Deadlift - 90 mins)",
        "effects": {"bone_t": 0.45, "muscle_idx": 5.0}
    },
    "CEVIS_AEROBIC": {
        "label": "CEVIS High-Intensity Cycle Ergometry + Hydration Load",
        "effects": {"hr": -14, "sys_bp": -12, "muscle_idx": 3.0}
    },
    "CIRCADIAN_PSG": {
        "label": "Actigraphy Circadian Blackout + 5mg Melatonin + PSG Array",
        "effects": {"sleep": 2.4, "hr": -10, "sys_bp": -8, "stress_score": -2, "mood_score": 2}
    },
    "THIGH_CUFF_SANS": {
        "label": "Venous Thigh Cuff + B-Complex Neuro-Ocular Countermeasure",
        "effects": {"hr": -8, "sys_bp": -10}
    },
    "SHIELDING_ROTATION": {
        "label": "Storm-Shelter Polyethylene Shielding Rotation & Dosimetry Check",
        "effects": {"radiation_msv": -15.0, "stress_score": -1}
    },
    "TRANSITION_CLEARANCE": {
        "label": "Environment Transition Clearance (No-Op Audit Record)",
        "effects": {}  # Explicit no-effect path so transitions never alter vitals
    }
}

PROTOCOL_BY_LABEL = {v["label"]: k for k, v in PROTOCOLS.items()}

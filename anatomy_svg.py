import streamlit.components.v1 as components

def render_live_ecg_strip(hr_bpm: int, status_str: str, palette: dict):
    stroke_col = "#ef4444" if status_str == "CRITICAL" else ("#f59e0b" if status_str == "WARNING" else "#0284c7")
    ecg_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@500;700&display=swap');
        body {{ margin: 0; padding: 0; background: transparent; font-family: 'IBM Plex Mono', monospace; overflow: hidden; }}
        .ecg-box {{ background-color: {palette["bg_card"]}; border: 1px solid {palette["border"]}; border-radius: 3px; padding: 8px 12px; }}
        .ecg-hdr {{ display: flex; justify-content: space-between; font-size: 10.5px; color: {palette["text_muted"]}; margin-bottom: 5px; }}
        canvas {{ display: block; width: 100%; height: 54px; background-color: {palette["bg_sub"]}; border: 1px solid {palette["grid_line"]}; }}
    </style>
    </head>
    <body>
    <div class="ecg-box">
        <div class="ecg-hdr">
            <span>SYNTHETIC LEAD-II WAVEFORM SIMULATOR (60 FPS)</span>
            <span style="color:{stroke_col}; font-weight:700;">HR: {hr_bpm} BPM — MODELED SWEEP</span>
        </div>
        <canvas id="ecgCanvas"></canvas>
    </div>
    <script>
        const canvas = document.getElementById('ecgCanvas');
        const ctx = canvas.getContext('2d');
        const dpr = window.devicePixelRatio || 1;
        const cssW = canvas.parentElement.clientWidth - 2;
        const cssH = 54;
        canvas.width = cssW * dpr;
        canvas.height = cssH * dpr;
        ctx.scale(dpr, dpr);
        const W = cssW, H = cssH, bpm = {hr_bpm};
        function pqrstWave(phase) {{
            let y = 0;
            y -= 4.0 * Math.exp(-Math.pow((phase - 0.18) / 0.030, 2));
            y += 3.5 * Math.exp(-Math.pow((phase - 0.275) / 0.008, 2));
            y -= 23.0 * Math.exp(-Math.pow((phase - 0.30) / 0.010, 2));
            y += 6.2 * Math.exp(-Math.pow((phase - 0.325) / 0.010, 2));
            y -= 5.8 * Math.exp(-Math.pow((phase - 0.52) / 0.045, 2));
            return (H * 0.64) + y;
        }}
        const points = new Array(Math.ceil(W)).fill(null);
        let headX = 0, phase = 0;
        const speedPx = 2;
        const phaseStep = (bpm / 60.0) / 60.0 / speedPx;
        function renderFrame() {{
            for (let s = 0; s < speedPx; s++) {{
                headX = (headX + 1) % points.length;
                phase = (phase + phaseStep) % 1.0;
                points[headX] = pqrstWave(phase);
                for (let g = 1; g <= 24; g++) points[(headX + g) % points.length] = null;
            }}
            ctx.fillStyle = "{palette['bg_sub']}";
            ctx.fillRect(0, 0, W, H);
            ctx.strokeStyle = "{palette['grid_line']}";
            ctx.lineWidth = 0.6;
            ctx.beginPath();
            for (let gx = 0; gx < W; gx += 14) {{ ctx.moveTo(gx, 0); ctx.lineTo(gx, H); }}
            for (let gy = 0; gy < H; gy += 14) {{ ctx.moveTo(0, gy); ctx.lineTo(W, gy); }}
            ctx.stroke();

            ctx.strokeStyle = "{stroke_col}";
            ctx.lineWidth = 1.25;
            ctx.beginPath();
            let drawing = false;
            for (let i = 0; i < points.length; i++) {{
                if (points[i] !== null) {{
                    if (!drawing) {{ ctx.moveTo(i, points[i]); drawing = true; }}
                    else {{ ctx.lineTo(i, points[i]); }}
                }} else {{ drawing = false; }}
            }}
            ctx.stroke();
            if (points[headX] !== null) {{
                ctx.fillStyle = "{stroke_col}";
                ctx.beginPath();
                ctx.arc(headX, points[headX], 2.0, 0, Math.PI * 2);
                ctx.fill();
            }}
            requestAnimationFrame(renderFrame);
        }}
        requestAnimationFrame(renderFrame);
    </script>
    </body>
    </html>
    """
    components.html(ecg_html, height=88)

def render_realistic_anatomy_svg(status_dict: dict, selected_zone: str, hr_bpm: int, palette: dict):
    """Full volumetric anatomical atlas with ribcage, limbs, striated myotomes, gyri, and HR-synced pulse."""
    color_map = {"NOMINAL": "#0284c7", "WARNING": "#d97706", "CRITICAL": "#dc2626"}
    c_brain = color_map[status_dict["brain"]]
    c_heart = color_map[status_dict["heart"]]
    c_bone = color_map[status_dict["bone"]]
    c_muscle = color_map[status_dict["muscle"]]
    c_rad = color_map[status_dict["radiation"]]

    op_brain = "0.90" if selected_zone == "brain" else "0.55"
    op_heart = "0.95" if selected_zone == "heart" else "0.75"
    op_bone = "0.92" if selected_zone == "bone" else "0.68"
    op_muscle = "0.65" if selected_zone == "muscle" else "0.32"

    beat_sec = round(60.0 / max(45, min(200, int(hr_bpm))), 2)
    flow_sec = round(42.0 / max(45, min(200, int(hr_bpm))), 2)

    target_coords = {
        "brain": (160, 68, "REGION: CRANIAL VAULT — CNS & OCULAR"),
        "heart": (166, 178, f"REGION: MEDIASTINUM — CARDIAC CYCLE {beat_sec}s ({hr_bpm} BPM)"),
        "bone": (160, 248, "REGION: AXIAL SKELETON — TRABECULAR SPINE & PELVIS"),
        "muscle": (106, 200, "REGION: APPENDICULAR MYOTOMES — SKELETAL MUSCLE"),
        "radiation": (160, 145, "REGION: DOSIMETRY — BONE MARROW & NEUTRON FLUX")
    }
    tx, ty, tlabel = target_coords.get(selected_zone, target_coords["heart"])

    vertebrae_svg = ""
    for i, vy in enumerate(range(108, 272, 11)):
        vw = 7 + (i * 0.35)
        vertebrae_svg += f'<rect x="{160-vw}" y="{vy}" width="{vw*2}" height="7.5" rx="2" fill="{c_bone}" fill-opacity="0.45" stroke="{c_bone}" stroke-width="1.2"/>'
        vertebrae_svg += f'<path d="M {160-vw-4},{vy+3.5} L {160-vw},{vy+3.5} M {160+vw},{vy+3.5} L {160+vw+4},{vy+3.5}" stroke="{c_bone}" stroke-width="1.2"/>'

    svg_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&display=swap');
        body {{ margin: 0; background: transparent; display: flex; justify-content: center; font-family: 'IBM Plex Mono', monospace; overflow: hidden; }}
        .scanner-wrap {{
            position: relative; width: 340px; height: 535px;
            background-color: {palette["bg_sub"]}; border: 1px solid {palette["border"]};
            border-radius: 4px; display: flex; flex-direction: column; justify-content: space-between; overflow: hidden;
        }}
        .hud-top-bar {{
            background-color: {palette["bg_card"]}; border-bottom: 1px solid {palette["border"]};
            padding: 6px 10px; color: {palette["text_muted"]}; font-size: 9px; letter-spacing: 0.6px;
            display: flex; justify-content: space-between;
        }}
        .hud-bottom-bar {{
            background-color: {palette["bg_card"]}; border-top: 1px solid {palette["border"]};
            padding: 6px 10px; text-align: center; color: {palette["text_primary"]};
            font-size: 9px; font-weight: 600; letter-spacing: 0.7px;
        }}
        .scan-beam {{
            position: absolute; left: 0; width: 100%; height: 26px;
            background: linear-gradient(180deg, transparent, rgba(2, 132, 199, 0.10), rgba(2, 132, 199, 0.26), transparent);
            border-bottom: 1px solid rgba(2, 132, 199, 0.45);
            animation: coronalSweep 5.5s ease-in-out infinite; pointer-events: none;
        }}
        @keyframes coronalSweep {{ 0% {{ top: 28px; opacity: 0.2; }} 50% {{ top: 470px; opacity: 0.85; }} 100% {{ top: 28px; opacity: 0.2; }} }}
        @keyframes cardiacBeat {{
            0% {{ transform: scale(1); }}
            18% {{ transform: scale(1.11); }}
            34% {{ transform: scale(0.97); }}
            50% {{ transform: scale(1.06); }}
            100% {{ transform: scale(1); }}
        }}
        .heart-chamber {{ transform-origin: 164px 172px; animation: cardiacBeat {beat_sec}s infinite ease-in-out; }}
        @keyframes arterialFlow {{ to {{ stroke-dashoffset: -24; }} }}
        .vascular-flow {{ stroke-dasharray: 6, 6; animation: arterialFlow {flow_sec}s linear infinite; }}
        @keyframes reticlePulse {{ 0% {{ transform: scale(1); opacity: 0.95; }} 50% {{ transform: scale(1.08); opacity: 0.55; }} 100% {{ transform: scale(1); opacity: 0.95; }} }}
        .target-box {{ transform-origin: {tx}px {ty}px; animation: reticlePulse 2.2s infinite ease-in-out; }}
    </style>
    </head>
    <body>
    <div class="scanner-wrap">
        <div class="scan-beam"></div>
        <div class="hud-top-bar">
            <span>CORONAL ATLAS</span>
            <span>HEART CYCLE: {beat_sec}s ({hr_bpm} BPM)</span>
        </div>

        <svg viewBox="0 20 320 500" width="340" height="480" xmlns="http://www.w3.org/2000/svg">
            <defs>
                <pattern id="grid" width="20" height="20" patternUnits="userSpaceOnUse">
                    <path d="M 20 0 L 0 0 0 20" fill="none" stroke="{palette['grid_line']}" stroke-width="0.9"/>
                </pattern>
                <pattern id="striation" width="4" height="4" patternTransform="rotate(25 0 0)" patternUnits="userSpaceOnUse">
                    <line x1="0" y1="0" x2="0" y2="4" stroke="{c_muscle}" stroke-width="1.2" stroke-opacity="0.48" />
                </pattern>
                <radialGradient id="organGlow" cx="50%" cy="50%" r="50%">
                    <stop offset="0%" stop-color="{c_heart}" stop-opacity="0.95"/>
                    <stop offset="100%" stop-color="{c_heart}" stop-opacity="0.55"/>
                </radialGradient>
            </defs>

            <rect x="0" y="20" width="320" height="500" fill="url(#grid)" />
            <line x1="14" y1="45" x2="14" y2="495" stroke="{palette['border']}" stroke-width="1" />
            <path d="M 14,60 L 20,60 M 14,120 L 22,120 M 14,180 L 20,180 M 14,240 L 22,240 M 14,300 L 20,300 M 14,360 L 22,360 M 14,420 L 20,420 M 14,480 L 22,480" stroke="{palette['text_muted']}" stroke-width="1.2" />

            <!-- 1. OUTER DERMAL CONTOUR -->
            <path d="M 160,32 C 141,32 131,46 132,68 C 133,82 139,93 144,101 C 145,107 143,113 137,116 C 118,121 95,125 83,140 C 72,154 68,176 64,200 C 59,226 51,252 46,278 C 43,290 38,304 42,311 C 46,316 55,310 59,298 C 66,276 74,250 81,224 C 86,204 92,182 99,168 C 101,192 106,216 108,238 C 110,256 103,276 101,302 C 98,338 103,376 107,412 C 110,442 110,470 107,492 C 105,502 124,504 127,492 C 131,470 133,442 136,412 C 140,374 146,336 151,306 L 160,306 L 169,306 C 174,336 180,374 184,412 C 187,442 189,470 193,492 C 196,504 215,502 213,492 C 210,470 210,442 213,412 C 217,376 222,338 219,302 C 217,276 210,256 212,238 C 214,216 219,192 221,168 C 228,182 234,204 239,224 C 246,250 254,276 261,298 C 265,310 274,316 278,311 C 282,304 277,290 274,278 C 269,252 261,226 256,200 C 252,176 248,154 237,140 C 225,125 202,121 183,116 C 177,113 175,107 176,101 C 181,93 187,82 188,68 C 189,46 179,32 160,32 Z"
                  fill="{palette['body_fill']}" stroke="{c_rad if selected_zone=='radiation' else palette['body_stroke']}" stroke-width="{2.8 if selected_zone=='radiation' else 1.8}" />

            <!-- 2. STRIATED MUSCULAR SYSTEM (Full Multi-Headed Bellies) -->
            <g stroke="{c_muscle}" stroke-width="1.2" fill="url(#striation)" opacity="{op_muscle}">
                <path d="M 145,100 L 132,122 L 112,128 L 142,112 Z" fill="{c_muscle}" fill-opacity="0.35"/>
                <path d="M 175,100 L 188,122 L 208,128 L 178,112 Z" fill="{c_muscle}" fill-opacity="0.35"/>
                <path d="M 157,130 C 138,126 116,132 98,144 C 102,165 118,176 156,172 Z" fill="{c_muscle}" fill-opacity="0.35"/>
                <path d="M 163,130 C 182,126 204,132 222,144 C 218,165 202,176 164,172 Z" fill="{c_muscle}" fill-opacity="0.35"/>
                <path d="M 98,128 C 82,136 73,156 72,182 C 82,180 92,166 98,146 Z" fill="{c_muscle}" fill-opacity="0.4"/>
                <path d="M 222,128 C 238,136 247,156 248,182 C 238,180 228,166 222,146 Z" fill="{c_muscle}" fill-opacity="0.4"/>
                <path d="M 76,176 C 68,196 66,216 70,228 C 80,226 88,204 92,176 Z" fill="{c_muscle}" fill-opacity="0.38"/>
                <path d="M 244,176 C 252,196 254,216 250,228 C 240,226 232,204 228,176 Z" fill="{c_muscle}" fill-opacity="0.38"/>
                <path d="M 67,232 C 58,252 52,272 52,288 C 61,286 72,262 78,234 Z" fill="{c_muscle}" fill-opacity="0.35"/>
                <path d="M 253,232 C 262,252 268,272 268,288 C 259,286 248,262 242,234 Z" fill="{c_muscle}" fill-opacity="0.35"/>
                <path d="M 142,182 L 158,182 L 158,252 L 144,252 Z" fill="{c_muscle}" fill-opacity="0.25"/>
                <path d="M 162,182 L 178,182 L 176,252 L 162,252 Z" fill="{c_muscle}" fill-opacity="0.25"/>
                <line x1="142" y1="202" x2="178" y2="202" stroke="{c_muscle}" stroke-width="1.2"/>
                <line x1="143" y1="224" x2="177" y2="224" stroke="{c_muscle}" stroke-width="1.2"/>
                <path d="M 118,296 C 112,334 114,372 120,398 C 128,398 134,362 134,298 Z" fill="{c_muscle}" fill-opacity="0.42"/>
                <path d="M 106,302 C 100,336 102,368 110,392 C 115,382 115,340 116,302 Z" fill="{c_muscle}" fill-opacity="0.32"/>
                <path d="M 136,315 C 135,348 132,378 126,398 C 138,396 145,368 144,322 Z" fill="{c_muscle}" fill-opacity="0.38"/>
                <path d="M 202,296 C 208,334 206,372 200,398 C 192,398 186,362 186,298 Z" fill="{c_muscle}" fill-opacity="0.42"/>
                <path d="M 214,302 C 220,336 218,368 210,392 C 205,382 205,340 204,302 Z" fill="{c_muscle}" fill-opacity="0.32"/>
                <path d="M 184,315 C 185,348 188,378 194,398 C 182,396 175,368 176,322 Z" fill="{c_muscle}" fill-opacity="0.38"/>
                <path d="M 110,418 C 105,442 108,468 114,484 C 122,484 125,456 123,418 Z" fill="{c_muscle}" fill-opacity="0.38"/>
                <path d="M 125,418 C 124,452 122,476 126,484 C 133,476 136,446 134,418 Z" fill="{c_muscle}" fill-opacity="0.32"/>
                <path d="M 210,418 C 215,442 212,468 206,484 C 198,484 195,456 197,418 Z" fill="{c_muscle}" fill-opacity="0.38"/>
                <path d="M 195,418 C 196,452 198,476 194,484 C 187,476 184,446 186,418 Z" fill="{c_muscle}" fill-opacity="0.32"/>
            </g>

            <!-- 3. VOLUMETRIC OSTEOLOGY (Ribcage, Spine, Pelvis, Humerus, Radius/Ulna, Femur, Patella, Tibia/Fibula) -->
            <g opacity="{op_bone}">
                {vertebrae_svg}
                <path d="M 154,124 C 136,118 114,116 96,126 C 98,131 134,124 154,129 Z" fill="{c_bone}" fill-opacity="0.5" stroke="{c_bone}" stroke-width="1.4"/>
                <path d="M 166,124 C 184,118 206,116 224,126 C 222,131 186,124 166,129 Z" fill="{c_bone}" fill-opacity="0.5" stroke="{c_bone}" stroke-width="1.4"/>
                <path d="M 153,124 L 167,124 L 169,136 L 164,140 L 165,180 L 160,192 L 155,180 L 156,140 L 151,136 Z" fill="{c_bone}" fill-opacity="0.55" stroke="{c_bone}" stroke-width="1.5"/>
                <g fill="none" stroke="{c_bone}" stroke-width="2.7" stroke-linecap="round">
                    <path d="M 152,134 C 132,130 116,136 112,146 C 118,150 138,144 155,142"/>
                    <path d="M 168,134 C 188,130 204,136 208,146 C 202,150 182,144 165,142"/>
                    <path d="M 152,146 C 126,142 108,150 106,162 C 114,166 138,158 155,154"/>
                    <path d="M 168,146 C 194,142 212,150 214,162 C 206,166 182,158 165,154"/>
                    <path d="M 152,158 C 122,154 104,166 105,179 C 115,182 138,174 155,166"/>
                    <path d="M 168,158 C 198,154 216,166 215,179 C 205,182 182,174 165,166"/>
                    <path d="M 152,170 C 122,168 106,182 108,195 C 120,198 140,188 156,176"/>
                    <path d="M 168,170 C 198,168 214,182 212,195 C 200,198 180,188 164,176"/>
                    <path d="M 152,182 C 125,184 112,196 116,208 C 128,208 144,198 156,182" stroke-width="2.2"/>
                    <path d="M 168,182 C 195,184 208,196 204,208 C 192,208 176,198 164,182" stroke-width="2.2"/>
                </g>
                <path d="M 149,264 C 134,250 112,250 107,266 C 103,280 114,296 122,306 C 132,316 146,318 160,316 C 174,318 188,316 198,306 C 206,296 217,280 213,266 C 208,250 186,250 171,264 L 160,285 Z"
                      fill="{c_bone}" fill-opacity="0.38" stroke="{c_bone}" stroke-width="1.8"/>
                <ellipse cx="160" cy="288" rx="18" ry="12" fill="{palette['bg_sub']}" stroke="{c_bone}" stroke-width="1.2"/>
                <ellipse cx="138" cy="305" rx="7" ry="5" fill="{palette['bg_sub']}" stroke="{c_bone}" stroke-width="1.1"/>
                <ellipse cx="182" cy="305" rx="7" ry="5" fill="{palette['bg_sub']}" stroke="{c_bone}" stroke-width="1.1"/>
                <path d="M 94,128 C 88,128 84,134 86,142 L 73,218 C 69,224 77,228 82,222 L 94,142 C 98,136 98,128 94,128 Z" fill="{c_bone}" fill-opacity="0.4" stroke="{c_bone}" stroke-width="1.4"/>
                <path d="M 226,128 C 232,128 236,134 234,142 L 247,218 C 251,224 243,228 238,222 L 226,142 C 222,136 222,128 226,128 Z" fill="{c_bone}" fill-opacity="0.4" stroke="{c_bone}" stroke-width="1.4"/>
                <path d="M 73,224 L 54,288 M 79,226 L 61,290" stroke="{c_bone}" stroke-width="2.4" stroke-linecap="round"/>
                <path d="M 247,224 L 266,288 M 241,226 L 259,290" stroke="{c_bone}" stroke-width="2.4" stroke-linecap="round"/>
                <path d="M 124,296 C 116,294 111,300 114,308 L 118,396 C 114,404 128,406 128,396 L 123,308 C 127,302 128,298 124,296 Z" fill="{c_bone}" fill-opacity="0.45" stroke="{c_bone}" stroke-width="1.5"/>
                <path d="M 196,296 C 204,294 209,300 206,308 L 202,396 C 206,404 192,406 192,396 L 197,308 C 193,302 192,298 196,296 Z" fill="{c_bone}" fill-opacity="0.45" stroke="{c_bone}" stroke-width="1.5"/>
                <circle cx="122" cy="405" r="5.5" fill="{c_bone}" fill-opacity="0.6" stroke="{c_bone}" stroke-width="1.3"/>
                <circle cx="198" cy="405" r="5.5" fill="{c_bone}" fill-opacity="0.6" stroke="{c_bone}" stroke-width="1.3"/>
                <path d="M 117,414 L 116,486 L 123,486 L 125,414 Z" fill="{c_bone}" fill-opacity="0.45" stroke="{c_bone}" stroke-width="1.4"/>
                <line x1="112" y1="416" x2="112" y2="484" stroke="{c_bone}" stroke-width="2.0"/>
                <path d="M 203,414 L 204,486 L 197,486 L 195,414 Z" fill="{c_bone}" fill-opacity="0.45" stroke="{c_bone}" stroke-width="1.4"/>
                <line x1="208" y1="416" x2="208" y2="484" stroke="{c_bone}" stroke-width="2.0"/>
            </g>

            <!-- 4. CARDIOVASCULAR CORE -->
            <g opacity="{op_heart}">
                <path d="M 153,120 L 153,162 M 153,182 L 155,275 L 132,335 M 155,275 L 188,335" fill="none" stroke="#0284c7" stroke-width="2.4" stroke-opacity="0.75"/>
                <path d="M 162,160 C 162,138 148,136 148,152" fill="none" stroke="{c_heart}" stroke-width="4.2"/>
                <path d="M 153,140 L 150,92 M 160,140 L 164,92" fill="none" stroke="{c_heart}" stroke-width="2.0"/>
                <path d="M 150,144 C 126,138 104,142 88,162 L 75,222" fill="none" stroke="{c_heart}" stroke-width="2.2" class="vascular-flow"/>
                <path d="M 162,144 C 194,138 216,142 232,162 L 245,222" fill="none" stroke="{c_heart}" stroke-width="2.2" class="vascular-flow"/>
                <path d="M 162,184 L 162,272 L 126,355 M 162,272 L 194,355" fill="none" stroke="{c_heart}" stroke-width="2.8" class="vascular-flow"/>
                <path d="M 154,156 C 146,156 144,168 150,178 C 155,186 168,194 176,190 C 183,186 184,170 176,160 C 170,152 160,154 154,156 Z"
                      class="heart-chamber" fill="url(#organGlow)" stroke="{palette['reticle']}" stroke-width="1.3"/>
                <path d="M 162,162 Q 166,175 173,188" fill="none" stroke="{palette['reticle']}" stroke-width="1.0" stroke-opacity="0.8"/>
            </g>

            <!-- 5. BRAIN & CENTRAL NERVOUS SYSTEM -->
            <g opacity="{op_brain}">
                <path d="M 159,38 C 142,38 135,50 136,65 C 137,78 145,86 159,86 Z" fill="{c_brain}" fill-opacity="0.52" stroke="{c_brain}" stroke-width="1.8"/>
                <path d="M 161,38 C 178,38 185,50 184,65 C 183,78 175,86 161,86 Z" fill="{c_brain}" fill-opacity="0.52" stroke="{c_brain}" stroke-width="1.8"/>
                <path d="M 146,84 Q 160,94 174,84" fill="{c_brain}" fill-opacity="0.65" stroke="{c_brain}" stroke-width="1.4"/>
                <path d="M 140,52 Q 149,47 156,55 M 138,63 Q 148,58 156,67 M 142,74 Q 150,70 157,77 M 180,52 Q 171,47 164,55 M 182,63 Q 172,58 164,67 M 178,74 Q 170,70 163,77"
                      fill="none" stroke="{palette['reticle']}" stroke-width="1.1" stroke-opacity="0.75"/>
            </g>

            <!-- 6. TARGET LOCK RETICLE -->
            <rect class="target-box" x="{tx-24}" y="{ty-24}" width="48" height="48" rx="2" fill="none" stroke="{palette['reticle']}" stroke-width="1.5" stroke-dasharray="7,4" />
            <circle cx="{tx}" cy="{ty}" r="14" fill="none" stroke="{palette['reticle']}" stroke-width="0.9" stroke-opacity="0.6" />
            <line x1="{tx-7}" y1="{ty}" x2="{tx+7}" y2="{ty}" stroke="{palette['reticle']}" stroke-width="1.4" />
            <line x1="{tx}" y1="{ty-7}" x2="{tx}" y2="{ty+7}" stroke="{palette['reticle']}" stroke-width="1.4" />
        </svg>

        <div class="hud-bottom-bar">{tlabel}</div>
    </div>
    </body>
    </html>
    """
    components.html(svg_html, height=540)

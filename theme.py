import html
import streamlit as st
import pandas as pd

def esc(val) -> str:
    """Safely escapes any user-controlled or database string before HTML rendering."""
    return html.escape(str(val), quote=True)

def get_palette(is_light: bool) -> dict:
    return {
        "bg_main": "#f4f6f9" if is_light else "#0c0f14",
        "bg_card": "#ffffff" if is_light else "#151921",
        "bg_sub": "#f8fafc" if is_light else "#10141b",
        "input_bg": "#ffffff" if is_light else "#1c222d",
        "btn_bg": "#ffffff" if is_light else "#1e2530",
        "btn_border": "#cbd5e1" if is_light else "#333f50",
        "text_primary": "#0f172a" if is_light else "#f1f5f9",
        "text_secondary": "#334155" if is_light else "#cbd5e1",
        "text_muted": "#64748b" if is_light else "#94a3b8",
        "border": "#cbd5e1" if is_light else "#262c36",
        "accent": "#0b3d91" if is_light else "#3b82f6",
        "grid_line": "#e2e8f0" if is_light else "#1e242d",
        "body_fill": "#e2e8f0" if is_light else "#161b24",
        "body_stroke": "#475569" if is_light else "#64748b",
        "reticle": "#0f172a" if is_light else "#f8fafc"
    }

def render_custom_table(df: pd.DataFrame, max_height: int = 220):
    """Renders an XSS-escaped HTML table obeying current theme variables."""
    if df is None or df.empty:
        st.caption("No records available.")
        return
    headers = "".join(f"<th>{esc(col).upper()}</th>" for col in df.columns)
    rows_html = ""
    for _, row in df.iterrows():
        cells = "".join(f"<td>{esc(val)}</td>" for val in row.values)
        rows_html += f"<tr>{cells}</tr>"
    st.markdown(f"""
    <div style="max-height:{max_height}px; overflow-y:auto; border:1px solid var(--border-col); border-radius:4px; background-color:var(--bg-card); margin-bottom:8px;">
        <table style="width:100%; border-collapse:collapse; font-family:'IBM Plex Mono', monospace; font-size:0.75rem; color:var(--text-primary);">
            <thead>
                <tr style="background-color:var(--bg-sub); border-bottom:1px solid var(--border-col); text-align:left; color:var(--text-muted);">
                    {headers}
                </tr>
            </thead>
            <tbody>{rows_html}</tbody>
        </table>
    </div>
    """, unsafe_allow_html=True)

def render_sbar_cards(engine_label: str, mode_badge: str, situation_html: str, assessment_html: str, rx_html: str, status_str: str):
    """Renders an authentic tabular Avionics Clinical Log (no generic // or neon AI callout boxes)."""
    state_col = "#ef4444" if status_str == "CRITICAL" else ("#f59e0b" if status_str == "WARNING" else "#94a3b8")
    clean_label = engine_label.replace("//", "—")
    st.markdown(f"""
    <div style="background-color:var(--bg-card); border:1px solid var(--border-col); border-radius:2px; margin:10px 0;">
        <div style="background-color:var(--bg-sub); padding:7px 12px; border-bottom:1px solid var(--border-col); display:flex; justify-content:space-between; align-items:center;">
            <span style="font-family:'IBM Plex Mono', monospace; font-size:0.72rem; font-weight:700; color:var(--text-primary); letter-spacing:0.6px;">
                {esc(clean_label)}
            </span>
            <span style="font-family:'IBM Plex Mono', monospace; font-size:0.66rem; color:var(--text-muted); border:1px solid var(--border-col); padding:1px 6px;">
                {esc(mode_badge)} | NON-DIAGNOSTIC
            </span>
        </div>
        <div style="padding:10px 12px; border-bottom:1px solid var(--border-col);">
            <div style="font-family:'IBM Plex Mono', monospace; font-size:0.66rem; color:var(--text-muted); font-weight:700; text-transform:uppercase; letter-spacing:0.8px;">
                TELEMETRY VECTOR &amp; BASELINE
            </div>
            <div style="font-size:0.81rem; color:var(--text-primary); margin-top:4px; line-height:1.45;">{situation_html}</div>
        </div>
        <div style="padding:10px 12px; border-bottom:1px solid var(--border-col); border-left:3px solid {state_col};">
            <div style="font-family:'IBM Plex Mono', monospace; font-size:0.66rem; color:var(--text-secondary); font-weight:700; text-transform:uppercase; letter-spacing:0.8px;">
                PHYSIOLOGICAL EVALUATION
            </div>
            <div style="font-size:0.81rem; color:var(--text-primary); margin-top:4px; line-height:1.45;">{assessment_html}</div>
        </div>
        <div style="padding:10px 12px;">
            <div style="font-family:'IBM Plex Mono', monospace; font-size:0.66rem; color:var(--text-muted); font-weight:700; text-transform:uppercase; letter-spacing:0.8px;">
                COUNTERMEASURE PROTOCOL
            </div>
            <div style="font-size:0.81rem; color:var(--text-primary); margin-top:4px; line-height:1.45;">{rx_html}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

def apply_theme_css(is_light: bool):
    p = get_palette(is_light)
    st.markdown(f"""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600;700&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap');
        :root {{
            --bg-main: {p["bg_main"]};
            --bg-card: {p["bg_card"]};
            --bg-sub: {p["bg_sub"]};
            --input-bg: {p["input_bg"]};
            --btn-bg: {p["btn_bg"]};
            --btn-border: {p["btn_border"]};
            --text-primary: {p["text_primary"]};
            --text-secondary: {p["text_secondary"]};
            --text-muted: {p["text_muted"]};
            --border-col: {p["border"]};
            --accent-col: {p["accent"]};
        }}
        .stApp {{
            background-color: var(--bg-main) !important;
            color: var(--text-primary) !important;
            font-family: 'IBM Plex Sans', sans-serif;
        }}
        .block-container {{
            padding-top: 1.2rem !important;
            padding-bottom: 2rem !important;
            max-width: 96% !important;
        }}
        header, footer {{ visibility: hidden !important; }}
        h1, h2, h3, h4, h5, p, span, label, li {{
            font-family: 'IBM Plex Sans', sans-serif;
            color: var(--text-primary);
        }}
        table th, table td {{
            padding: 7px 10px !important;
            border-bottom: 1px solid var(--border-col) !important;
            color: var(--text-primary) !important;
        }}
        code {{
            font-family: 'IBM Plex Mono', monospace !important;
            background-color: transparent !important;
            color: {"#b45309" if is_light else "#f59e0b"} !important;
            border: none !important;
            border-bottom: 1px dashed {"#cbd5e1" if is_light else "#334155"} !important;
            padding: 0px 2px !important;
            border-radius: 0px !important;
            font-weight: 700 !important;
        }}

        div.stButton > button:not([kind="primary"]),
        div[data-testid="stFormSubmitButton"] > button,
        div.stDownloadButton > button {{
            background-color: var(--btn-bg) !important;
            color: var(--text-primary) !important;
            border: 1px solid var(--btn-border) !important;
            border-radius: 4px !important;
            font-family: 'IBM Plex Sans', sans-serif !important;
            font-size: 0.76rem !important;
            font-weight: 600 !important;
            padding: 0.42rem 0.65rem !important;
        }}
        div.stButton > button:not([kind="primary"]) p,
        div.stButton > button:not([kind="primary"]) span,
        div[data-testid="stFormSubmitButton"] > button p,
        div.stDownloadButton > button p {{
            color: var(--text-primary) !important;
        }}

        div.stButton > button[kind="primary"] {{
            background-color: var(--accent-col) !important;
            color: #ffffff !important;
            border: 1px solid var(--accent-col) !important;
            border-radius: 4px !important;
            font-weight: 700 !important;
            box-shadow: 0 0 10px rgba(59, 130, 246, 0.3) !important;
        }}
        div.stButton > button[kind="primary"] p,
        div.stButton > button[kind="primary"] span {{
            color: #ffffff !important;
        }}

        div.stButton > button:hover,
        div[data-testid="stFormSubmitButton"] > button:hover,
        div.stDownloadButton > button:hover {{
            background-color: var(--accent-col) !important;
            border-color: var(--accent-col) !important;
            color: #ffffff !important;
        }}
        div.stButton > button:hover p,
        div.stButton > button:hover span,
        div[data-testid="stFormSubmitButton"] > button:hover p,
        div.stDownloadButton > button:hover p {{
            color: #ffffff !important;
        }}

        [data-testid="stExpander"],
        [data-testid="stExpander"] details {{
            background-color: var(--bg-card) !important;
            border: 1px solid var(--border-col) !important;
            border-radius: 4px !important;
            margin-bottom: 10px !important;
        }}
        [data-testid="stExpander"] summary,
        [data-testid="stExpander"] details[open] > summary,
        [data-testid="stExpander"] summary:hover {{
            background-color: var(--bg-sub) !important;
            color: var(--text-primary) !important;
            padding: 10px 14px !important;
            border-radius: 4px !important;
        }}
        [data-testid="stExpander"] summary p,
        [data-testid="stExpander"] summary span,
        [data-testid="stExpander"] summary svg {{
            color: var(--text-primary) !important;
            fill: var(--text-primary) !important;
            font-weight: 700 !important;
            font-size: 0.80rem !important;
        }}
        [data-testid="stExpanderDetails"] {{
            background-color: var(--bg-card) !important;
            padding: 12px 14px !important;
        }}

        div[data-baseweb="input"],
        div[data-baseweb="input"] > div,
        div[data-baseweb="base-input"],
        div[data-baseweb="select"],
        div[data-baseweb="select"] > div {{
            background-color: var(--input-bg) !important;
            border-color: var(--btn-border) !important;
            color: var(--text-primary) !important;
            border-radius: 4px !important;
        }}
        div[data-baseweb="input"] input,
        div[data-baseweb="select"] span,
        div[data-baseweb="select"] div {{
            background-color: transparent !important;
            color: var(--text-primary) !important;
            -webkit-text-fill-color: var(--text-primary) !important;
            font-family: 'IBM Plex Mono', monospace !important;
            font-weight: 600 !important;
        }}
        div[data-baseweb="select"] svg, div[data-baseweb="input"] svg {{
            fill: var(--text-primary) !important;
        }}
        [data-testid="stFileUploaderDropzone"] {{
            background-color: var(--bg-sub) !important;
            border: 1px dashed var(--btn-border) !important;
            color: var(--text-primary) !important;
        }}
        [data-testid="stFileUploaderDropzone"] button {{
            background-color: var(--btn-bg) !important;
            color: var(--text-primary) !important;
            border: 1px solid var(--btn-border) !important;
        }}
        div[data-baseweb="popover"], div[data-baseweb="menu"], ul[role="listbox"] {{
            background-color: var(--bg-card) !important;
            border: 1px solid var(--btn-border) !important;
        }}
        li[role="option"] {{
            background-color: var(--bg-card) !important;
            color: var(--text-primary) !important;
        }}
        li[role="option"] * {{ color: var(--text-primary) !important; }}
        li[role="option"]:hover, li[role="option"][aria-selected="true"] {{
            background-color: var(--bg-sub) !important;
            color: var(--accent-col) !important;
            font-weight: 700 !important;
        }}

        button[data-baseweb="tab"] {{
            padding: 8px 10px !important;
            font-size: 0.76rem !important;
            font-weight: 700 !important;
        }}
        [data-testid="stMetricValue"] {{
            font-family: 'IBM Plex Mono', monospace !important;
            color: var(--text-primary) !important;
            font-size: 1.25rem !important;
            font-weight: 700 !important;
        }}
        [data-testid="stMetricLabel"] p {{
            color: var(--text-muted) !important;
            font-weight: 700 !important;
            font-size: 0.72rem !important;
        }}
        [data-testid="stMetricDelta"] {{
            background-color: {"#e2e8f0" if is_light else "#1e293b"} !important;
            padding: 2px 6px !important;
            border-radius: 3px !important;
            font-family: 'IBM Plex Mono', monospace !important;
            font-size: 0.70rem !important;
        }}
        [data-testid="stMetricDelta"] > div {{ color: var(--text-primary) !important; }}

        .mcc-topbar {{
            background-color: var(--bg-card);
            border: 1px solid var(--border-col);
            border-top: 3px solid var(--accent-col);
            padding: 10px 18px;
            margin-bottom: 8px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-radius: 4px;
        }}
        .sim-banner {{
            background-color: {"#fffbeb" if is_light else "rgba(245, 158, 11, 0.12)"};
            border: 1px solid #d97706;
            color: {"#92400e" if is_light else "#fbbf24"};
            padding: 5px 12px;
            font-family: 'IBM Plex Mono', monospace;
            font-size: 0.72rem;
            text-align: center;
            margin-bottom: 14px;
            border-radius: 4px;
            font-weight: 600;
        }}
        .hud-box {{
            background-color: var(--bg-card);
            border: 1px solid var(--border-col);
            border-radius: 6px;
            padding: 14px 16px;
            margin-bottom: 12px;
        }}
        .hud-section-hdr {{
            background-color: var(--bg-card);
            border: 1px solid var(--border-col);
            border-left: 4px solid var(--accent-col);
            padding: 9px 14px;
            margin-bottom: 12px;
            border-radius: 4px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .hud-title {{
            font-size: 0.80rem;
            font-weight: 700;
            letter-spacing: 0.8px;
            text-transform: uppercase;
            margin: 0;
        }}
        .xp-badge {{
            display: inline-block;
            background-color: {"#eff6ff" if is_light else "#1e293b"};
            border: 1px solid var(--accent-col);
            color: var(--accent-col);
            padding: 2px 8px;
            border-radius: 12px;
            font-family: 'IBM Plex Mono', monospace;
            font-size: 0.68rem;
            font-weight: 700;
            margin-right: 6px;
            margin-top: 4px;
        }}
        .badge-nominal {{
            background-color: {"#d1fae5" if is_light else "rgba(16, 185, 129, 0.2)"};
            border: 1px solid #059669;
            color: {"#065f46" if is_light else "#34d399"};
            padding: 3px 8px;
            border-radius: 3px;
            font-family: 'IBM Plex Mono', monospace;
            font-size: 0.69rem;
            font-weight: 700;
        }}
        .badge-warning {{
            background-color: {"#fef3c7" if is_light else "rgba(245, 158, 11, 0.2)"};
            border: 1px solid #d97706;
            color: {"#92400e" if is_light else "#fbbf24"};
            padding: 3px 8px;
            border-radius: 3px;
            font-family: 'IBM Plex Mono', monospace;
            font-size: 0.69rem;
            font-weight: 700;
        }}
        .badge-critical {{
            background-color: {"#fee2e2" if is_light else "rgba(239, 68, 68, 0.2)"};
            border: 1px solid #dc2626;
            color: {"#991b1b" if is_light else "#f87171"};
            padding: 3px 8px;
            border-radius: 3px;
            font-family: 'IBM Plex Mono', monospace;
            font-size: 0.69rem;
            font-weight: 700;
        }}
        .telemetry-tag {{
            font-family: 'IBM Plex Mono', monospace !important;
            color: var(--text-muted);
            font-size: 0.71rem;
            font-weight: 600;
            text-transform: uppercase;
        }}
        .callout-info, .callout-warn, .callout-err, .callout-ok {{
            background-color: var(--bg-sub);
            border: 1px solid var(--border-col);
            padding: 10px 14px;
            border-radius: 4px;
            margin: 8px 0;
            font-size: 0.82rem;
            line-height: 1.45;
        }}
        .callout-info {{ border-left: 4px solid #3b82f6; }}
        .callout-warn {{ border-left: 4px solid #f59e0b; }}
        .callout-err {{ border-left: 4px solid #ef4444; }}
        .callout-ok {{ border-left: 4px solid #10b981; }}
    </style>
    """, unsafe_allow_html=True)

def hud_callout(text_html: str, kind: str = "info"):
    st.markdown(f"<div class='callout-{kind}'>{text_html}</div>", unsafe_allow_html=True)

def format_status_badge(status_str: str) -> str:
    if status_str in ["CRITICAL", "EVA RESTRICTED", "STALE TELEMETRY"]:
        return f"<span class='badge-critical'>{esc(status_str)}</span>"
    if status_str == "WARNING":
        return "<span class='badge-warning'>CAUTION</span>"
    return f"<span class='badge-nominal'>{esc(status_str)}</span>"

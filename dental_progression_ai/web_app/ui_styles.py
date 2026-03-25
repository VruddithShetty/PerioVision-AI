"""Shared CSS design system — premium blue & white market-ready theme."""

GLOBAL_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&family=Outfit:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;700&display=swap');

/* ═══ ROOT TOKENS ═══ */
:root {
    --bg-deep:      #020617;
    --bg-surface:   rgba(15, 23, 42, 0.4);
    --glass-bg:     rgba(15, 23, 42, 0.7);
    --glass-border: rgba(255, 255, 255, 0.08);
    --neon-blue:    #38BDF8;
    --neon-purple:  #A855F7;
    --neon-cyan:    #22D3EE;
    --text-primary: #F8FAFC;
    --text-muted:   #94A3B8;
    --accent:       linear-gradient(135deg, #0EA5E9 0%, #6366F1 100%);
    --accent-glow:  0 0 30px rgba(14, 165, 233, 0.3);
    --radius-lg:    32px;
    --radius-md:    20px;
}

/* ═══ GLOBAL ═══ */
.stApp {
    background: radial-gradient(circle at 10% 10%, #0F172A 0%, #020617 100%) !important;
    font-family: 'Outfit', sans-serif !important;
    color: var(--text-primary) !important;
}

/* Ensure all labels and text are visible */
label, p, span, div, .stMarkdown {
    color: var(--text-primary) !important;
}

[data-testid="stSidebar"] p, [data-testid="stSidebar"] span {
    color: var(--text-muted) !important;
}

/* ═══ 3D GLASS CARDS ═══ */
[data-testid="stVerticalBlockBorderWrapper"], .stTabs, [data-testid="metric-container"], .stExpander, .stForm {
    background: var(--glass-bg) !important;
    backdrop-filter: blur(25px) saturate(200%) !important;
    border: 1px solid var(--glass-border) !important;
    border-radius: var(--radius-md) !important;
    box-shadow: 0 10px 40px -10px rgba(0,0,0,0.5) !important;
}

/* ═══ BUTTONS ═══ */
.stButton > button {
    background: var(--accent) !important;
    color: #FFFFFF !important;
    border: none !important;
    border-radius: 12px !important;
    padding: 0.85rem 1.8rem !important;
    font-weight: 800 !important;
    text-transform: uppercase !important;
    letter-spacing: 1.5px !important;
}

/* ═══ INPUT FIELDS (Total Reset) ═══ */
div[data-baseweb="input"], div[data-baseweb="input"] > div,
div[data-baseweb="textarea"], div[data-baseweb="textarea"] > div,
div[data-baseweb="select"] > div {
    background-color: rgba(15, 23, 42, 0.6) !important;
    background: rgba(15, 23, 42, 0.6) !important;
    border: 1px solid var(--glass-border) !important;
    border-radius: 12px !important;
    color: var(--text-primary) !important;
    backdrop-filter: blur(5px) !important;
}

/* Target the actual input element */
input, textarea {
    color: var(--text-primary) !important;
    -webkit-text-fill-color: var(--text-primary) !important;
    caret-color: var(--neon-blue) !important;
    background: transparent !important;
}

input::placeholder, textarea::placeholder {
    color: var(--text-muted) !important;
    opacity: 0.5 !important;
}

/* Focus state */
div[data-baseweb="input"]:focus-within, div[data-baseweb="textarea"]:focus-within, div[data-baseweb="select"]:focus-within {
    border: 1px solid var(--neon-blue) !important;
    box-shadow: 0 0 15px rgba(56, 189, 248, 0.2) !important;
}

/* ═══ HEADINGS ═══ */
h1, h2, h3, h4, h5, h6 { 
    font-family: 'Space Grotesk', sans-serif !important;
    color: var(--text-primary) !important;
    -webkit-text-fill-color: var(--text-primary) !important;
    font-weight: 700 !important;
}

/* ═══ CONTAINERS ═══ */
.stSecondaryButton > button {
    background: rgba(255,255,255,0.05) !important;
    border: 1px solid var(--glass-border) !important;
    color: var(--text-primary) !important;
}

/* Hide Streamlit components */
#MainMenu, footer, header { display: none !important; }
</style>
"""

BRAND_HTML = """
<div style="
    background: #0F172A;
    padding: 1.5rem 2.5rem;
    margin: -1rem -2rem 2.5rem -2rem;
    border-bottom: 2px solid rgba(56, 189, 248, 0.2);
    display: flex;
    align-items: center;
    justify-content: space-between;
    box-shadow: 0 10px 30px rgba(0,0,0,0.4);
    position: sticky;
    top: 0;
    z-index: 1000;
">
    <div style="display: flex; align-items: center; gap: 24px;">
        <div class="quantum-logo" style="
            background: var(--accent);
            border-radius: 20px;
            width: 64px; height: 64px;
            display: flex; align-items: center; justify-content: center;
            font-size: 2.2rem;
            box-shadow: var(--accent-glow);
            animation: float-3d 4s ease-in-out infinite;
        ">🦷</div>
        <div>
            <h1 style="margin:0; line-height:1; font-size: 2.5rem !important; letter-spacing: -1.5px;">PerioVision <span style="color:var(--neon-blue); -webkit-text-fill-color: var(--neon-blue);">AI</span></h1>
            <p style="margin:5px 0 0; color:var(--text-muted); font-size:0.85rem; font-weight:600; text-transform:uppercase; letter-spacing:2px;">
                Quantum Periodontal Intelligence • TALPA-V4
            </p>
        </div>
    </div>
    <div style="display: flex; gap: 20px; align-items: center;">
        <div class="active-glow" style="background: rgba(34, 211, 238, 0.05); color: var(--neon-cyan); padding: 8px 20px; border-radius: 40px; border: 1px solid rgba(34, 211, 238, 0.3); font-size: 0.8rem; font-weight: 800; letter-spacing: 1px;">
            🛰️ CORE LIVE
        </div>
        <div id="neural-sync"></div>
    </div>
</div>

<style>
@keyframes float-3d {
    0%, 100% { transform: translateY(0px) rotate(-2deg); }
    50% { transform: translateY(-10px) rotate(4deg); }
}
</style>

<script>
    setInterval(() => {
        const sync = document.getElementById('neural-sync');
        if (sync) {
            sync.innerHTML = '<div style="color:var(--neon-purple); font-size:0.75rem; font-weight:700; opacity:0.8;">🧠 NEURAL SYNC ACTIVE</div>';
        }
    }, 1000);
</script>
"""

def stat_card(icon, value, label, color="#38BDF8"):
    return f"""
<div style="
    background: var(--glass-bg);
    border: 1px solid var(--glass-border);
    border-radius: var(--radius-md);
    padding: 24px;
    text-align: center;
    backdrop-filter: blur(10px);
    transition: all 0.3s ease;
    box-shadow: 0 4px 20px rgba(0,0,0,0.2);
    position: relative;
    overflow: hidden;
">
    <div style="position:absolute; top:0; left:0; width:100%; height:2px; background:linear-gradient(90deg, transparent, {color}, transparent);"></div>
    <div style="font-size: 2.5rem; margin-bottom: 10px; filter: drop-shadow(0 0 10px {color}40);">{icon}</div>
    <div style="font-size: 2.2rem; font-weight: 800; color: #F8FAFC; font-family: 'Space Grotesk', sans-serif; margin-bottom: 4px;">{value}</div>
    <div style="font-size: 0.75rem; font-weight: 700; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1.5px;">{label}</div>
</div>"""

def section_title(text, icon=""):
    return f"""
<div style="
    display: flex; align-items: center; gap: 12px;
    margin: 40px 0 20px 0;
    padding-bottom: 12px;
    border-bottom: 1px solid var(--glass-border);
">
    <span style="font-size: 1.5rem;">{icon}</span>
    <h2 style="margin:0; font-size: 1.4rem !important; background: var(--accent); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">{text}</h2>
</div>"""

def info_card(title, value, color="#38BDF8"):
    return f"""
<div style="
    background: rgba(30, 41, 59, 0.3);
    border: 1px solid {color}30;
    border-left: 4px solid {color};
    border-radius: 8px;
    padding: 16px 20px;
    margin-bottom: 12px;
    transition: all 0.2s ease;
">
    <div style="font-size: 0.7rem; font-weight: 700; color: {color}; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 4px;">{title}</div>
    <div style="font-size: 1.1rem; font-weight: 600; color: #F1F5F9;">{value}</div>
</div>"""

def badge(text, level="info"):
    schemes = {
        "info":    ("var(--neon-blue)", "rgba(56, 189, 248, 0.1)"),
        "success": ("#34D399", "rgba(52, 211, 153, 0.1)"),
        "warning": ("#FBBF24", "rgba(251, 191, 36, 0.1)"),
        "danger":  ("#F87171", "rgba(248, 113, 113, 0.1)"),
    }
    color, bg = schemes.get(level, schemes["info"])
    return f'<span style="background:{bg}; color:{color}; border:1px solid {color}40; border-radius:20px; padding:4px 12px; font-size:0.75rem; font-weight:700; text-transform: uppercase; letter-spacing: 0.5px;">{text}</span>'

def page_header(title, subtitle=""):
    subtitle_html = f"<p style='color:var(--text-muted); margin-top:-10px; margin-bottom:25px; font-size:1rem; font-weight:500;'>{subtitle}</p>" if subtitle else ""
    return f"""
    <div style="margin-bottom: 30px;">
        <h2 style="margin:0; font-size: 2.2rem !important; letter-spacing: -1px;">{title}</h2>
        {subtitle_html}
    </div>
    """

def empty_state_container(icon, title, subtitle):
    return f"""
    <div style="
        background: var(--glass-bg);
        border: 2px dashed var(--glass-border);
        border-radius: var(--radius-md);
        padding: 60px 40px;
        text-align: center;
        backdrop-filter: blur(10px);
        margin: 20px 0;
    ">
        <div style="font-size: 4rem; margin-bottom: 20px; filter: drop-shadow(0 0 15px rgba(56, 189, 248, 0.2));">{icon}</div>
        <h3 style="color:var(--text-primary) !important; margin-bottom: 10px;">{title}</h3>
        <p style="color:var(--text-muted) !important; font-size: 1rem;">{subtitle}</p>
    </div>
    """

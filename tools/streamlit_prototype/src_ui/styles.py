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

label, p, span, div, .stMarkdown { color: var(--text-primary) !important; }
[data-testid="stSidebar"] p, [data-testid="stSidebar"] span { color: var(--text-muted) !important; }

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

/* ═══ INPUT FIELDS ═══ */
div[data-baseweb="input"], div[data-baseweb="input"] > div,
div[data-baseweb="textarea"], div[data-baseweb="textarea"] > div,
div[data-baseweb="select"] > div {
    background-color: rgba(15, 23, 42, 0.6) !important;
    border: 1px solid var(--glass-border) !important;
    border-radius: 12px !important;
    color: var(--text-primary) !important;
}

input, textarea { color: var(--text-primary) !important; -webkit-text-fill-color: var(--text-primary) !important; }

input::placeholder, textarea::placeholder {
    color: var(--text-muted) !important;
    opacity: 1 !important;
}

div[data-baseweb="input"] input::placeholder,
div[data-baseweb="textarea"] textarea::placeholder {
    color: var(--text-muted) !important;
    opacity: 1 !important;
}

/* ═══ HEADINGS ═══ */
h1, h2, h3, h4, h5, h6 { 
    font-family: 'Space Grotesk', sans-serif !important;
    color: var(--text-primary) !important;
    font-weight: 700 !important;
}

#MainMenu, footer, header { display: none !important; }
</style>
"""

BRAND_HTML = """
<div style="background: #0F172A; padding: 1.5rem 2.5rem; margin: -1rem -2rem 2.5rem -2rem; border-bottom: 2px solid rgba(56, 189, 248, 0.2); display: flex; align-items: center; justify-content: space-between; box-shadow: 0 10px 30px rgba(0,0,0,0.4); position: sticky; top: 0; z-index: 1000;">
    <div style="display: flex; align-items: center; gap: 24px;">
        <div style="background: var(--accent); border-radius: 20px; width: 64px; height: 64px; display: flex; align-items: center; justify-content: center; font-size: 2.2rem; box-shadow: var(--accent-glow);">🦷</div>
        <div>
            <h1 style="margin:0; line-height:1; font-size: 2.5rem !important;">PerioVision <span style="color:var(--neon-blue);">AI</span></h1>
            <p style="margin:5px 0 0; color:var(--text-muted); font-size:0.85rem; font-weight:600; text-transform:uppercase; letter-spacing:2px;">Quantum Periodontal Intelligence</p>
        </div>
    </div>
    <div style="display: flex; gap: 20px; align-items: center;">
        <div style="background: rgba(34, 197, 94, 0.1); color: #4ade80; padding: 8px 16px; border-radius: 8px; border: 1px solid rgba(34, 197, 94, 0.3); font-size: 0.75rem; font-weight: 700;">🛡️ HIPAA SECURED</div>
        <div style="background: rgba(34, 211, 238, 0.05); color: var(--neon-cyan); padding: 8px 20px; border-radius: 40px; border: 1px solid rgba(34, 211, 238, 0.3); font-size: 0.8rem; font-weight: 800;">🛰️ CORE LIVE</div>
    </div>
</div>
<div style="display: flex; justify-content: center; gap: 40px; margin: -2.5rem 0 2rem 0; opacity: 0.7;">
    <div style="font-size: 0.65rem; color: var(--text-muted);">🔒 AES-256-GCM ENCRYPTED</div>
    <div style="font-size: 0.65rem; color: var(--text-muted);">🔗 MERKLE-VERIFIED AUDIT</div>
    <div style="font-size: 0.65rem; color: var(--text-muted);">🤖 ADVERSARIAL DEFENSE ACTIVE</div>
</div>
"""

def stat_card(icon, value, label, color="#38BDF8"):
    return f"""
<div style="background: var(--glass-bg); border: 1px solid var(--glass-border); border-radius: var(--radius-md); padding: 24px; text-align: center; position: relative;">
    <div style="position:absolute; top:0; left:0; width:100%; height:2px; background:linear-gradient(90deg, transparent, {color}, transparent);"></div>
    <div style="font-size: 2.5rem; margin-bottom: 10px;">{icon}</div>
    <div style="font-size: 2.2rem; font-weight: 800; color: #F8FAFC;">{value}</div>
    <div style="font-size: 0.75rem; font-weight: 700; color: var(--text-muted); text-transform: uppercase;">{label}</div>
</div>"""

def page_header(title, subtitle=""):
    subtitle_html = f"<p style='color:var(--text-muted); margin-top:-10px; margin-bottom:25px;'>{subtitle}</p>" if subtitle else ""
    return f'<div style="margin-bottom: 30px;"><h2 style="margin:0; font-size: 2.2rem !important;">{title}</h2>{subtitle_html}</div>'

def empty_state_container(icon, title, subtitle):
    return f'<div style="background: var(--glass-bg); border: 2px dashed var(--glass-border); border-radius: var(--radius-md); padding: 60px 40px; text-align: center; margin: 20px 0;"><div style="font-size: 4rem; margin-bottom: 20px;">{icon}</div><h3 style="color:var(--text-primary) !important;">{title}</h3><p style="color:var(--text-muted) !important;">{subtitle}</p></div>'

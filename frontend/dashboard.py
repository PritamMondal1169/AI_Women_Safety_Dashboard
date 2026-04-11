"""
frontend/dashboard.py — Multi-tab Streamlit dashboard (file-reader only).
Reads shared JSON/JPEG files written by main.py. No CV dependencies needed.

Run:
    streamlit run frontend/dashboard.py
"""

import json
import time
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Women Safety Monitor",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

_DATA_DIR       = Path("data")
_STATE_FILE     = _DATA_DIR / "dashboard_state.json"
_ALERT_LOG_FILE = _DATA_DIR / "alert_log.json"
_FRAME_FILE     = _DATA_DIR / "latest_frame.jpg"
_HISTORY_FILE   = _DATA_DIR / "dashboard_history.json"
_RT_CONFIG_FILE = _DATA_DIR / "runtime_config.json"
_REFRESH_MS     = 150


def _inject_css():
    st.markdown("""
    <style>
    [data-testid="stSidebar"] { background: #0f172a; }
    [data-testid="stSidebar"] * { color: #e2e8f0 !important; }
    .badge-HIGH   { background:#dc2626; color:#fff; padding:2px 10px; border-radius:9999px; font-weight:700; }
    .badge-MEDIUM { background:#ea580c; color:#fff; padding:2px 10px; border-radius:9999px; font-weight:700; }
    .badge-LOW    { background:#ca8a04; color:#fff; padding:2px 10px; border-radius:9999px; font-weight:700; }
    .badge-NONE   { background:#16a34a; color:#fff; padding:2px 10px; border-radius:9999px; font-weight:700; }
    #MainMenu, footer { visibility: hidden; }
    </style>""", unsafe_allow_html=True)


def _load_state() -> Dict[str, Any]:
    try:
        if _STATE_FILE.exists():
            return json.loads(_STATE_FILE.read_text())
    except Exception:
        pass
    return {}


def _load_alerts() -> List[Dict]:
    try:
        if _ALERT_LOG_FILE.exists():
            data = json.loads(_ALERT_LOG_FILE.read_text())
            return data if isinstance(data, list) else []
    except Exception:
        pass
    return []


def _load_frame_bytes():
    try:
        if _FRAME_FILE.exists():
            return _FRAME_FILE.read_bytes()
    except Exception:
        pass
    return None


def _render_sidebar(state: Dict):
    with st.sidebar:
        st.markdown("## 🛡️ Women Safety")
        st.markdown("**Edge-AI Monitoring System**")
        st.divider()
        running = state.get("running", False)
        st.markdown(f"**Pipeline:** {'🟢 Running' if running else '🔴 Stopped'}")
        if state:
            st.markdown(f"**Source:** `{state.get('camera_source', '—')}`")
            st.markdown(f"**Resolution:** `{state.get('resolution', '—')}`")
            st.markdown(f"**Model:** `{state.get('model_path', '—')}`")
            st.markdown(f"**Device:** `{state.get('model_device', '—')}`")
            st.markdown(f"**XGBoost:** {'✅' if state.get('xgb_loaded') else '⚠️ heuristic-only'}")
        st.divider()
        st.markdown(f"🕐 **{time.strftime('%H:%M:%S')}**")
        st.caption("Auto-refreshes every 0.5s")


def _tab_live(state: Dict):
    col_feed, col_status = st.columns([3, 1])

    with col_feed:
        st.subheader("📹 Live Camera Feed")
        frame_bytes = _load_frame_bytes()
        if frame_bytes:
            st.image(frame_bytes, use_container_width=True)
        else:
            st.info("No frame yet. Start main.py in another terminal.", icon="⏳")

    with col_status:
        st.subheader("Status")
        summary = state.get("threat_summary", {})
        high, medium, low = summary.get("HIGH",0), summary.get("MEDIUM",0), summary.get("LOW",0)

        if high:
            dom, dom_color, dom_icon = "HIGH",   "#dc2626", "🔴"
        elif medium:
            dom, dom_color, dom_icon = "MEDIUM", "#ea580c", "🟠"
        elif low:
            dom, dom_color, dom_icon = "LOW",    "#ca8a04", "🟡"
        else:
            dom, dom_color, dom_icon = "CLEAR",  "#16a34a", "🟢"

        st.markdown(f"""
        <div style='background:{dom_color};border-radius:12px;padding:20px;text-align:center;margin-bottom:16px'>
          <div style='font-size:40px'>{dom_icon}</div>
          <div style='color:#fff;font-size:22px;font-weight:700'>{dom}</div>
        </div>""", unsafe_allow_html=True)

        st.metric("FPS",            f"{state.get('fps', 0.0):.1f}")
        st.metric("Inference",      f"{state.get('avg_inference_ms', 0.0):.1f} ms")
        st.metric("Persons",        state.get("person_count", 0))
        st.metric("Active Tracks",  state.get("active_tracks", 0))
        st.metric("Total Alerts",   state.get("total_alerts", 0))
        st.metric("HIGH",           high)
        st.metric("MEDIUM",         medium)
        st.metric("LOW",            low)

        location  = state.get("location", "—")
        maps_url  = state.get("maps_url", "")
        st.markdown("**📍 Location**")
        st.markdown(f"[{location}]({maps_url})" if maps_url else location or "—")


def _tab_alerts():
    st.subheader("📋 Alert Log")
    alerts = _load_alerts()

    col_filter, col_clear = st.columns([3, 1])
    with col_filter:
        level_filter = st.multiselect("Filter by level",
            ["HIGH", "MEDIUM", "LOW"], default=["HIGH", "MEDIUM", "LOW"])
    with col_clear:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🗑️ Clear log", use_container_width=True):
            try:
                _ALERT_LOG_FILE.write_text("[]")
                st.success("Cleared.")
            except Exception as e:
                st.error(str(e))

    if not alerts:
        st.info("No alerts yet.", icon="ℹ️")
        return

    filtered = [a for a in alerts if a.get("threat_level") in level_filter]
    if not filtered:
        st.info("No alerts match the filter.")
        return

    df = pd.DataFrame(filtered)
    preferred = ["timestamp_str","track_id","threat_level","threat_score","location","channels"]
    cols = [c for c in preferred if c in df.columns]
    df = df[cols].rename(columns={
        "timestamp_str":"Time","track_id":"Track","threat_level":"Level",
        "threat_score":"Score","location":"Location","channels":"Channels"})

    def _colour(val):
        return {"HIGH":"background-color:#fef2f2;color:#dc2626;font-weight:700",
                "MEDIUM":"background-color:#fff7ed;color:#ea580c;font-weight:700",
                "LOW":"background-color:#fefce8;color:#ca8a04;font-weight:700"}.get(val,"")

    st.dataframe(df.style.map(_colour, subset=["Level"]),
                 use_container_width=True, height=400)
    st.caption(f"{len(filtered)} of {len(alerts)} alerts")
    st.download_button("⬇️ Download CSV", df.to_csv(index=False),
        f"alerts_{time.strftime('%Y%m%d_%H%M%S')}.csv", "text/csv")


def _tab_config(state: Dict):
    st.subheader("⚙️ Runtime Configuration")
    st.info("Changes are picked up by main.py within ~15 frames (no restart needed).", icon="ℹ️")

    rt_cfg: Dict = {}
    try:
        if _RT_CONFIG_FILE.exists():
            rt_cfg = json.loads(_RT_CONFIG_FILE.read_text())
    except Exception:
        pass

    with st.form("config_form"):
        st.markdown("#### 🎯 Threat Thresholds")
        c1, c2, c3 = st.columns(3)
        low_t  = c1.slider("LOW",    0.10, 0.90, float(rt_cfg.get("THREAT_LOW",    0.35)), 0.01)
        med_t  = c2.slider("MEDIUM", 0.10, 0.90, float(rt_cfg.get("THREAT_MEDIUM", 0.60)), 0.01)
        high_t = c3.slider("HIGH",   0.10, 0.99, float(rt_cfg.get("THREAT_HIGH",   0.80)), 0.01)

        st.markdown("#### ⏱ Timing")
        c4, c5 = st.columns(2)
        sustained = c4.slider("Sustained frames", 3, 60, int(rt_cfg.get("THREAT_SUSTAINED_FRAMES", 15)))
        cooldown  = c5.slider("Alert cooldown (s)", 5, 300, int(rt_cfg.get("ALERT_COOLDOWN", 60)))

        st.markdown("#### 📷 Detection")
        c6, c7 = st.columns(2)
        conf  = c6.slider("YOLO confidence", 0.10, 0.95, float(rt_cfg.get("MODEL_CONFIDENCE", 0.45)), 0.01)
        skip  = c7.slider("Frame skip", 0, 5, int(rt_cfg.get("SKIP_FRAMES", 0)))

        submitted = st.form_submit_button("💾 Apply", use_container_width=True)

    if submitted:
        if not (low_t < med_t < high_t):
            st.error("Must satisfy: LOW < MEDIUM < HIGH")
        else:
            try:
                _DATA_DIR.mkdir(parents=True, exist_ok=True)
                _RT_CONFIG_FILE.write_text(json.dumps({
                    "THREAT_LOW": low_t, "THREAT_MEDIUM": med_t, "THREAT_HIGH": high_t,
                    "THREAT_SUSTAINED_FRAMES": sustained, "ALERT_COOLDOWN": cooldown,
                    "MODEL_CONFIDENCE": conf, "SKIP_FRAMES": skip,
                    "_updated_at": time.time(),
                }, indent=2))
                st.success("✅ Config saved.")
            except Exception as e:
                st.error(str(e))


def _tab_stats(state: Dict):
    st.subheader("📊 Performance & Threat Statistics")
    history: List[Dict] = []
    try:
        if _HISTORY_FILE.exists():
            history = json.loads(_HISTORY_FILE.read_text())
    except Exception:
        pass

    if len(history) < 2:
        st.info("Not enough history yet. Keep main.py running.", icon="📈")
        return

    df_h = pd.DataFrame(history)
    df_h["time"] = pd.to_datetime(df_h.get("timestamp", []), unit="s", errors="coerce")

    if "fps" in df_h.columns:
        st.markdown("#### FPS Over Time")
        st.line_chart(df_h[["time","fps"]].set_index("time"), height=200, use_container_width=True)

    threat_cols = [c for c in ["HIGH","MEDIUM","LOW","NONE"] if c in df_h.columns]
    if threat_cols:
        st.markdown("#### Threat Levels Over Time")
        st.area_chart(df_h[["time"]+threat_cols].set_index("time"), height=200, use_container_width=True)

    if "avg_inference_ms" in df_h.columns:
        st.markdown("#### Inference Latency (ms)")
        st.line_chart(df_h[["time","avg_inference_ms"]].set_index("time"), height=160, use_container_width=True)

    st.divider()
    alerts = _load_alerts()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Alerts", len(alerts))
    c2.metric("HIGH Alerts",  sum(1 for a in alerts if a.get("threat_level")=="HIGH"))
    c3.metric("Avg FPS",      f"{df_h['fps'].mean():.1f}" if "fps" in df_h else "—")
    c4.metric("Frames Logged", len(df_h))


def main():
    _inject_css()
    state = _load_state()
    _render_sidebar(state)

    st.markdown("""
    <h1 style='margin:0;font-size:28px'>🛡️ Women Safety Monitoring Dashboard</h1>
    <p style='color:#64748b;margin-top:4px;margin-bottom:24px'>
      Real-time edge-AI threat detection &amp; alert management
    </p>""", unsafe_allow_html=True)

    summary = state.get("threat_summary", {})
    if summary.get("HIGH", 0) > 0:
        st.markdown("""
        <div style='background:#dc2626;color:#fff;padding:12px 20px;
                    border-radius:8px;font-weight:700;font-size:16px;margin-bottom:16px'>
          🔴 HIGH THREAT ACTIVE — Immediate attention required!
        </div>""", unsafe_allow_html=True)

    tab1, tab2, tab3, tab4 = st.tabs(["📹 Live Feed","📋 Alert Log","⚙️ Config","📊 Stats"])
    with tab1: _tab_live(state)
    with tab2: _tab_alerts()
    with tab3: _tab_config(state)
    with tab4: _tab_stats(state)

    time.sleep(_REFRESH_MS / 1000.0)
    st.rerun()


if __name__ == "__main__":
    main()

import json
import time
import queue
import random
import streamlit as st
import pandas as pd
import paho.mqtt.client as mqtt

st.set_page_config(page_title="HAES // Telemetry", page_icon="🛰️", layout="wide")

# --------------------------------------------------
# MILITARY-STYLE THEME
# --------------------------------------------------
st.markdown("""
<style>
.stApp { background-color:#0b0f0c; color:#c8e6c9; font-family:'Courier New', monospace; }
[data-testid="stMetricValue"] { color:#7CFC00; }
.status-ok   { background:#123d1a; color:#7CFC00; padding:6px 12px; border-radius:4px; display:inline-block; }
.status-warn { background:#3d2f12; color:#ffb020; padding:6px 12px; border-radius:4px; display:inline-block; }
.status-crit { background:#3d1212; color:#ff4040; padding:6px 12px; border-radius:4px; display:inline-block; }
</style>
""", unsafe_allow_html=True)

st.title("🛰️ HAES — High-Altitude Environmental Shield")
st.caption("LAC Forward Deployment Simulation · Battery Microclimate Control · Unit: ZeroK2026")

TARGET_TEMP = 15.0
BAND = 2.0  # acceptable ± band around target

# --------------------------------------------------
# MQTT CLIENT + QUEUE
# --------------------------------------------------
@st.cache_resource
def start_mqtt():
    mqtt_queue = queue.Queue()

    def on_connect(client, userdata, flags, reason_code, properties=None):
        client.subscribe("haes/esp32/telemetry/aasakti2026")

    def on_message(client, userdata, msg):
        try:
            data = json.loads(msg.payload.decode())
            mqtt_queue.put(data)
        except Exception as e:
            print("MQTT MESSAGE ERROR:", e)

    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    except AttributeError:
        client = mqtt.Client()

    client.on_connect = on_connect
    client.on_message = on_message
    try:
        client.connect("broker.hivemq.com", 1883, 60)
        client.loop_start()
    except Exception as e:
        print("MQTT CONNECTION ERROR:", e)

    return client, mqtt_queue


client, mqtt_queue = start_mqtt()

# --------------------------------------------------
# SESSION STATE
# --------------------------------------------------
if "latest_data" not in st.session_state:
    st.session_state.latest_data = {"temp": 25.0, "press": 1013.0, "heat": 0, "motor": 255}

if "history" not in st.session_state:
    st.session_state.history = pd.DataFrame(
        columns=["t", "Temperature", "Heater_PWM", "Pressure", "Current_mA"]
    )

if "tick" not in st.session_state:
    st.session_state.tick = 0

if "wdt_resets" not in st.session_state:
    st.session_state.wdt_resets = 0

if "tmr_faults" not in st.session_state:
    st.session_state.tmr_faults = 0

# --------------------------------------------------
# SIDEBAR — SIMULATED FAULT INJECTION (mimics field conditions
# your physical rig can't reproduce indoors: radiation SEUs, brownouts)
# --------------------------------------------------
st.sidebar.header("⚙️ Field Condition Injection")
inject_seu = st.sidebar.button("⚡ Inject Cosmic-Ray Bit Flip (SEU)")
inject_brownout = st.sidebar.button("🔻 Simulate Brownout / WDT Reset")
sim_altitude_hpa = st.sidebar.slider("Simulated Altitude Pressure Override (hPa)", 550, 1013, 1013,
                                      help="Drag down to mimic climbing toward 15,000 ft if your BMP180 can't reach that range physically.")

if inject_seu:
    st.session_state.tmr_faults += 1
if inject_brownout:
    st.session_state.wdt_resets += 1

# --------------------------------------------------
# LIVE DASHBOARD
# --------------------------------------------------
@st.fragment(run_every=1)
def live_dashboard():
    while not mqtt_queue.empty():
        data = mqtt_queue.get()
        required = ["temp", "press", "heat", "motor"]
        if all(key in data for key in required):
            st.session_state.latest_data = data
            st.session_state.tick += 1

            heat = int(data["heat"])
            # Simulated current draw — proxy for a physical INA219, scaled off
            # heater PWM (thermal load) + a small idle baseline + jitter
            simulated_current = 80 + (heat / 255.0) * 900 + random.uniform(-5, 5)

            new_row = pd.DataFrame({
                "t": [st.session_state.tick],
                "Temperature": [float(data["temp"])],
                "Heater_PWM": [heat],
                "Pressure": [float(data["press"])],
                "Current_mA": [simulated_current],
            })
            st.session_state.history = pd.concat(
                [st.session_state.history, new_row], ignore_index=True
            )

    if len(st.session_state.history) > 200:
        st.session_state.history = st.session_state.history.iloc[-200:]

    data = st.session_state.latest_data
    temp = float(data["temp"])
    pressure = min(float(data["press"]), sim_altitude_hpa) if sim_altitude_hpa < 1013 else float(data["press"])
    heat = int(data["heat"])
    motor = int(data["motor"])

    # --------------------------------------------------
    # STATUS ROW
    # --------------------------------------------------
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        in_band = abs(temp - TARGET_TEMP) <= BAND
        css = "status-ok" if in_band else "status-warn"
        st.markdown(f'<span class="{css}">🌡️ PID LOCK: {"STABLE" if in_band else "SEEKING"}</span>',
                    unsafe_allow_html=True)
    with c2:
        css = "status-ok" if st.session_state.tmr_faults == 0 else "status-warn"
        st.markdown(f'<span class="{css}">🛡️ TMR VOTES CORRECTED: {st.session_state.tmr_faults}</span>',
                    unsafe_allow_html=True)
    with c3:
        css = "status-ok" if st.session_state.wdt_resets == 0 else "status-crit"
        st.markdown(f'<span class="{css}">🐕 WDT RESETS: {st.session_state.wdt_resets}</span>',
                    unsafe_allow_html=True)
    with c4:
        alt_status = "NOMINAL" if pressure > 800 else "HIGH-ALT THROTTLE ACTIVE"
        css = "status-ok" if pressure > 800 else "status-warn"
        st.markdown(f'<span class="{css}">⛰️ {alt_status}</span>', unsafe_allow_html=True)

    st.divider()

    # --------------------------------------------------
    # METRICS
    # --------------------------------------------------
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Battery Microclimate Temp", f"{temp:.2f} °C", delta=f"{temp - TARGET_TEMP:+.2f} vs target")
    m2.metric("Heater PID Output", f"{heat}/255")
    m3.metric("Barometric Pressure", f"{pressure:.1f} hPa")
    m4.metric("Max Motor PWM Limit", f"{motor}/255")

    # --------------------------------------------------
    # CHARTS
    # --------------------------------------------------
    st.subheader("Live Telemetry")
    if not st.session_state.history.empty:
        cc1, cc2 = st.columns(2)
        with cc1:
            st.line_chart(st.session_state.history, x="t", y="Temperature", height=250)
            st.line_chart(st.session_state.history, x="t", y="Pressure", height=250)
        with cc2:
            st.line_chart(st.session_state.history, x="t", y="Heater_PWM", height=250)
            st.line_chart(st.session_state.history, x="t", y="Current_mA", height=250)

        st.download_button(
            "⬇️ Export Mission Log (CSV)",
            st.session_state.history.to_csv(index=False),
            file_name=f"haes_log_{int(time.time())}.csv",
            mime="text/csv",
        )
    else:
        st.info("Waiting for data stream from ESP32...")


live_dashboard()

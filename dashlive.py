import json
import queue
import streamlit as st
import pandas as pd
import paho.mqtt.client as mqtt


# --------------------------------------------------
# PAGE CONFIG
# --------------------------------------------------

st.set_page_config(
    page_title="ESP32 MQTT Dashboard",
    page_icon="🔋",
    layout="centered"
)

st.title("🔋 ESP32 Live MQTT Telemetry Dashboard")


# --------------------------------------------------
# MQTT CLIENT + QUEUE
# BOTH ARE CREATED ONCE
# --------------------------------------------------

@st.cache_resource
def start_mqtt():

    mqtt_queue = queue.Queue()

    def on_connect(client, userdata, flags, reason_code, properties=None):

        print("=================================")
        print("CONNECTED TO MQTT BROKER")
        print("Reason:", reason_code)
        print("=================================")

        client.subscribe("haes/esp32/telemetry")

        print("SUBSCRIBED TO: haes/esp32/telemetry")

    def on_message(client, userdata, msg):

        try:

            payload = msg.payload.decode()

            print("MQTT RECEIVED:")
            print(payload)

            data = json.loads(payload)

            mqtt_queue.put(data)

        except Exception as e:

            print("MQTT MESSAGE ERROR:", e)

    try:

        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2
        )

    except AttributeError:

        client = mqtt.Client()

    client.on_connect = on_connect
    client.on_message = on_message

    try:

        client.connect(
            "broker.hivemq.com",
            1883,
            60
        )

        print("MQTT CONNECTION STARTED")

        client.loop_start()

    except Exception as e:

        print("MQTT CONNECTION ERROR:", e)

    return client, mqtt_queue


client, mqtt_queue = start_mqtt()


# --------------------------------------------------
# SESSION STATE
# --------------------------------------------------

if "latest_data" not in st.session_state:

    st.session_state.latest_data = {
        "temp": 0.0,
        "press": 0.0,
        "heat": 0,
        "motor": 255
    }


if "history" not in st.session_state:

    st.session_state.history = pd.DataFrame(
        columns=["Temperature"]
    )


# --------------------------------------------------
# LIVE DASHBOARD
# --------------------------------------------------

@st.fragment(run_every=1)
def live_dashboard():

    # ----------------------------------------------
    # READ MQTT QUEUE
    # ----------------------------------------------

    received = False

    while not mqtt_queue.empty():

        data = mqtt_queue.get()

        print("PROCESSING DATA:", data)

        required = [
            "temp",
            "press",
            "heat",
            "motor"
        ]

        if all(key in data for key in required):

            st.session_state.latest_data = data

            new_row = pd.DataFrame({
                "Temperature": [
                    float(data["temp"])
                ]
            })

            st.session_state.history = pd.concat(
                [
                    st.session_state.history,
                    new_row
                ],
                ignore_index=True
            )

            received = True

    # ----------------------------------------------
    # KEEP LAST 40 VALUES
    # ----------------------------------------------

    if len(st.session_state.history) > 40:

        st.session_state.history = (
            st.session_state.history.iloc[-40:]
        )

    # ----------------------------------------------
    # CURRENT DATA
    # ----------------------------------------------

    data = st.session_state.latest_data

    # ----------------------------------------------
    # METRICS
    # ----------------------------------------------

    col1, col2 = st.columns(2)

    with col1:

        st.metric(
            "Battery Temperature",
            f"{float(data['temp']):.2f} °C"
        )

        st.metric(
            "Heater PWM Output",
            int(data["heat"])
        )

    with col2:

        st.metric(
            "Barometric Pressure",
            f"{float(data['press']):.2f} hPa"
        )

        st.metric(
            "Max Motor Limit",
            int(data["motor"])
        )

    # ----------------------------------------------
    # GRAPH
    # ----------------------------------------------

    st.subheader("Live Temperature Trend")

    if not st.session_state.history.empty:

        st.line_chart(
            st.session_state.history,
            y="Temperature"
        )

    else:

        st.info(
            "Waiting for data stream from ESP32..."
        )


# --------------------------------------------------
# RUN
# --------------------------------------------------

live_dashboard()

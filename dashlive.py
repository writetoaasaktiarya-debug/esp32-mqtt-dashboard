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
    layout="centered"
)

st.title("🔋 ESP32 Live MQTT Telemetry Dashboard")


# --------------------------------------------------
# GLOBAL MQTT QUEUE
# DO NOT PUT THIS IN st.session_state
# --------------------------------------------------

mqtt_queue = queue.Queue()


# --------------------------------------------------
# MQTT CALLBACKS
# --------------------------------------------------

def on_connect(client, userdata, flags, reason_code, properties=None):

    print("Connected to MQTT broker")

    client.subscribe("haes/esp32/telemetry")

    print("Subscribed to: haes/esp32/telemetry")


def on_message(client, userdata, msg):

    try:

        payload = msg.payload.decode()

        print("MQTT RECEIVED:", payload)

        data = json.loads(payload)

        mqtt_queue.put(data)

    except Exception as e:

        print("MQTT ERROR:", e)


# --------------------------------------------------
# START MQTT
# --------------------------------------------------

@st.cache_resource
def start_mqtt():

    try:
        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2
        )
    except AttributeError:
        client = mqtt.Client()

    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(
        "broker.hivemq.com",
        1883,
        60
    )

    client.loop_start()

    return client


client = start_mqtt()


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

    # Process all received MQTT messages
    while not mqtt_queue.empty():

        data = mqtt_queue.get()

        print("PROCESSING:", data)

        # Make sure all required fields exist
        if all(
            key in data
            for key in ["temp", "press", "heat", "motor"]
        ):

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

            # Keep only latest 40 readings
            if len(st.session_state.history) > 40:

                st.session_state.history = (
                    st.session_state.history.iloc[-40:]
                )

    # Current values
    data = st.session_state.latest_data


    # --------------------------------------------------
    # METRICS
    # --------------------------------------------------

    col1, col2 = st.columns(2)

    with col1:

        st.metric(
            "Battery Temperature",
            f"{float(data['temp']):.2f} °C"
        )

        st.metric(
            "Heater PWM Output",
            data["heat"]
        )


    with col2:

        st.metric(
            "Barometric Pressure",
            f"{float(data['press']):.2f} hPa"
        )

        st.metric(
            "Max Motor Limit",
            data["motor"]
        )


    # --------------------------------------------------
    # GRAPH
    # --------------------------------------------------

    st.subheader("Live Temperature Trend")

    if not st.session_state.history.empty:

        st.line_chart(
            st.session_state.history,
            y="Temperature"
        )

    else:

        st.info(
            "Waiting for data stream from ESP32 simulation..."
        )


# Run dashboard
live_dashboard()
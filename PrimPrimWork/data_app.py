# Created By: Simon Rosinski

############ IMPORTS ############
import pandas as pd
import numpy as np
import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
import io, base64
from flask import Flask, render_template, request, jsonify

###############################
app = Flask(__name__)

df = pd.read_csv("Occupancy_Estimation.csv")
df["DateTime"] = pd.to_datetime(df["Date"] + " " + df["Time"])
df = df.sort_values("DateTime").reset_index(drop=True)


def df_to_base64(fig):
    """Convert Matplotlib figure → base64 string."""
    buf = io.BytesIO()
    fig.savefig(buf, format='png', bbox_inches='tight')
    buf.seek(0)
    encoded = base64.b64encode(buf.getvalue()).decode()
    plt.close(fig)
    return encoded


def compute_pir_latency(i):
    event_time = df.loc[i, "DateTime"]
    sub = df.loc[i:i + 50]
    change = sub[sub["S6_PIR"].diff().fillna(0) != 0]
    if change.empty:
        return np.nan
    return (change.iloc[0]["DateTime"] - event_time).total_seconds()


def compute_light_latency(i, threshold=50):
    event_time = df.loc[i, "DateTime"]
    sub = df.loc[i:i + 200]
    change = sub[sub["S1_Light"] > threshold]
    if change.empty:
        return np.nan
    return (change.iloc[0]["DateTime"] - event_time).total_seconds()


def compute_sound_latency(i, threshold=2):
    event_time = df.loc[i, "DateTime"]
    sub = df.iloc[i:i + 200]
    change = sub[sub["S1_Sound"] > threshold]
    if change.empty:
        return np.nan
    return (change.iloc[0]["DateTime"] - event_time).total_seconds()


PIR_latencies = []
Light_latencies = []
Sound_latencies = []
Latency_times = []
Temp_latencies = []

for i in range(1, len(df)):
    now = df.loc[i, "Room_Occupancy_Count"]
    prev = df.loc[i - 1, "Room_Occupancy_Count"]

    if now != prev:  # true occupancy change
        PIR_latencies.append(compute_pir_latency(i))
        Light_latencies.append(compute_light_latency(i))
        Sound_latencies.append(compute_sound_latency(i))
        Latency_times.append(df.loc[i, "DateTime"])


def plot_pir_vs_occ(sub):
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.step(sub["DateTime"], sub["Room_Occupancy_Count"], label="True Occupancy", linewidth=2, where="post")
    ax.step(sub["DateTime"], sub["S6_PIR"], label="PIR (S6)", alpha=0.7)
    ax.set_title("PIR Activation vs Ground Truth")
    ax.set_ylabel("Count / Binary")
    ax.legend()
    return df_to_base64(fig)


def plot_latency_timeline():
    fig, ax = plt.subplots(figsize=(12, 5))

    ax.plot(Latency_times, PIR_latencies, label="PIR", marker="o")
    ax.plot(Latency_times, Light_latencies, label="Light")
    ax.plot(Latency_times, Sound_latencies, label="Sound")
    ax.set_title("Sensor Detection Latencies Over Time")
    ax.set_xlabel("Time")
    ax.set_ylabel("Latency (seconds)")
    ax.legend()
    ax.grid(True, alpha=0.3)

    return df_to_base64(fig)


def plot_latency_comparison():
    sensors = ["PIR", "Light", "Sound"]

    means = [
        np.nanmean(PIR_latencies),
        np.nanmean(Light_latencies),
        np.nanmean(Sound_latencies),
    ]

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(sensors, means, color=["green", "red", "blue"])

    ax.set_title("Mean Detection Latency by Sensor Type")
    ax.set_ylabel("Latency (seconds)")
    ax.grid(True, axis='y', alpha=0.3)

    return df_to_base64(fig)


######### FLASK ROUTES #########

@app.route('/')
def index():
    return render_template('index.html', max_index=len(df) - 1)


@app.route("/get_data")
def get_data():
    idx = int(request.args.get("time"))
    idx = max(0, min(idx, len(df) - 1))

    selected_time = df.loc[idx, "DateTime"]
    subset = df[df["DateTime"] <= selected_time]

    true_count = df.loc[idx, "Room_Occupancy_Count"]

    graphs = {
        "pir_vs_occ": plot_pir_vs_occ(subset),
        "latency_timeline": plot_latency_timeline(),
        "latency_comparison": plot_latency_comparison(),
    }

    return jsonify({
        "current_time": selected_time.strftime("%H:%M:%S"),
        "true_count": int(true_count),
        **graphs
    })


if __name__ == "__main__":
    app.run(debug=True)

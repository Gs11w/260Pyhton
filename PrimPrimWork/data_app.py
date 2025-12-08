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
df = df.iloc[:4201].copy()

GLOBAL_X_MIN = df["DateTime"].min()
GLOBAL_X_MAX = df["DateTime"].max()

PIR_times = []
Light_times = []
Sound_times = []


def df_to_base64(fig):
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

for i in range(1, len(df)):
    now = df.loc[i, "Room_Occupancy_Count"]
    prev = df.loc[i - 1, "Room_Occupancy_Count"]

    if now != prev:  # true occupancy change
        event_time = df.loc[i, "DateTime"]
        pir = compute_pir_latency(i)
        light = compute_light_latency(i)
        sound = compute_sound_latency(i)

        if not pd.isnull(pir):
            PIR_latencies.append(pir)
            PIR_times.append(event_time + pd.to_timedelta(pir, unit="s"))
        if not pd.isnull(light):
            Light_latencies.append(light)
            Light_times.append(event_time + pd.to_timedelta(light, unit="s"))
        if not pd.isnull(sound):
            Sound_latencies.append(sound)
            Sound_times.append(event_time + pd.to_timedelta(sound, unit="s"))

MAX_ROWS = 3000

PIR_times = PIR_times[:MAX_ROWS]
Light_times = Light_times[:MAX_ROWS]
Sound_times = Sound_times[:MAX_ROWS]

PIR_latencies = PIR_latencies[:MAX_ROWS]
Light_latencies = Light_latencies[:MAX_ROWS]
Sound_latencies = Sound_latencies[:MAX_ROWS]

VISIBLE_MIN_TIME = PIR_times[0]
VISIBLE_MAX_TIME = PIR_times[-1]


def plot_pir_vs_occ(sub):
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.step(sub["DateTime"], sub["Room_Occupancy_Count"], label="True Occupancy", linewidth=2, where="post")
    ax.step(sub["DateTime"], sub["S6_PIR"], label="PIR (S6)", alpha=0.7)
    ax.step(sub["DateTime"], sub["S7_PIR"], label="PIR (S7)", alpha=0.7)

    ax.set_xlim(GLOBAL_X_MIN, GLOBAL_X_MAX)

    ax.set_title("PIR Activation vs Ground Truth")
    ax.set_ylabel("Count / Binary")
    ax.legend()
    return df_to_base64(fig)


def plot_latency_timeline():
    fig, ax = plt.subplots(figsize=(12, 5))

    ax.plot(PIR_times, PIR_latencies, marker="o", label="PIR")
    ax.plot(Light_times, Light_latencies, marker="o", label="Light")
    ax.plot(Sound_times, Sound_latencies, marker="o", label="Sound")

    ax.set_xlim(GLOBAL_X_MIN, GLOBAL_X_MAX)

    ax.set_title("Sensor Detection Latencies Over Time")
    ax.set_xlabel("Time")
    ax.set_ylabel("Latency (seconds)")
    ax.grid(True, alpha=0.3)
    ax.legend()

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


FULL_pir_vs_occ = plot_pir_vs_occ(df)  # ALL DATA
FULL_latency_timeline = plot_latency_timeline()  # ONLY FIRST 3000
FULL_latency_comparison = plot_latency_comparison()

visible_idx_min = df.index[df["DateTime"] >= VISIBLE_MIN_TIME][0]
visible_idx_max = df.index[df["DateTime"] <= VISIBLE_MAX_TIME][-1]


######### FLASK ROUTES #########

@app.route('/')
def index():
    return render_template('index.html',
                           max_index=visible_idx_max,
                           min_index=visible_idx_min,
                           FULL_pir_vs_occ=FULL_pir_vs_occ,
                           FULL_latency_timeline=FULL_latency_timeline,
                           FULL_latency_comparison=FULL_latency_comparison
                           )


@app.route("/get_data")
def get_data():
    idx = int(request.args.get("time"))
    idx = max(visible_idx_min, min(idx, visible_idx_max))

    row = df.loc[idx]
    selected_time = row["DateTime"]

    graphs = {
        "pir_vs_occ": FULL_pir_vs_occ,
        "latency_timeline": FULL_latency_timeline,
        "latency_comparison": FULL_latency_comparison
    }

    return jsonify({
        "current_time": selected_time.strftime("%y-%m-%d %H:%M:%S"),
        "true_count": int(row["Room_Occupancy_Count"]),
        "s6_pir": int(row["S6_PIR"]),
        "s7_pir": int(row["S7_PIR"]),
        "avg_temp": float(np.mean([row["S1_Temp"], row["S2_Temp"], row["S3_Temp"], row["S4_Temp"]])),
        "avg_light": float(np.mean([row["S1_Light"], row["S2_Light"], row["S3_Light"], row["S4_Light"]])),
        "avg_sound": float(np.mean([row["S1_Sound"], row["S2_Sound"], row["S3_Sound"], row["S4_Sound"]])),
        "co2": float(row["S5_CO2"]),
        #"pir_vs_occ": FULL_pir_vs_occ,
        #"latency_timeline": FULL_latency_timeline,   # shouldn't need bc static
        #"latency_comparison": FULL_latency_comparison
    })


if __name__ == "__main__":
    app.run(debug=True)

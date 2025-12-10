# Created By: Simon Rosinski

############ IMPORTS ############
import pandas as pd
import numpy as np
import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.dates import DateFormatter
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
CO2_times = []
True_change_times = []


def df_to_base64(fig):  # Base 64 for images
    buf = io.BytesIO()
    fig.savefig(buf, format='png', bbox_inches='tight')
    buf.seek(0)
    encoded = base64.b64encode(buf.getvalue()).decode()
    plt.close(fig)
    return encoded


def compute_pir_latency(i, window=50):
    event_time = df.loc[i, "DateTime"]

    start = max(0, i - window)
    end = min(len(df), i + window)

    sub = df.loc[start:end].copy()
    sub["change"] = sub["S6_PIR"].diff().fillna(0)
    change = sub[sub["S6_PIR"].diff().fillna(0) != 0]
    if change.empty:
        return np.nan
    closest = change.iloc[(change["DateTime"] - event_time).abs().argmin()]
    return abs((closest["DateTime"] - event_time).total_seconds())


def compute_light_latency(i, threshold=40):
    event_time = df.loc[i, "DateTime"]
    sub = df.loc[i:i + 200]
    change = sub[sub["S1_Light"] > threshold]
    if change.empty:
        return np.nan
    return (change.iloc[0]["DateTime"] - event_time).total_seconds()


def compute_sound_latency(i, threshold=1.3):
    event_time = df.loc[i, "DateTime"]
    sub = df.iloc[i:i + 200]
    change = sub[sub["S1_Sound"] > threshold]
    if change.empty:
        return np.nan
    return (change.iloc[0]["DateTime"] - event_time).total_seconds()


def compute_co2_latency(i, threshold=700):
    event_time = df.loc[i, "DateTime"]
    sub = df.iloc[i:i + 200]
    change = sub[sub["S5_CO2"] > threshold]
    if change.empty:
        return np.nan
    return (change.iloc[0]["DateTime"] - event_time).total_seconds()


# Lists for latency plots
PIR_latencies = []
Light_latencies = []
Sound_latencies = []
Latency_times = []
CO2_latencies = []

for i in range(1, len(df)):
    now = df.loc[i, "Room_Occupancy_Count"]
    prev = df.loc[i - 1, "Room_Occupancy_Count"]

    if now != prev:  # true occupancy change
        event_time = df.loc[i, "DateTime"]
        pir = compute_pir_latency(i)
        light = compute_light_latency(i)
        sound = compute_sound_latency(i)
        co2 = compute_co2_latency(i)
        True_change_times.append(event_time)

        if not pd.isnull(pir):
            PIR_latencies.append(pir)
            PIR_times.append(event_time + pd.to_timedelta(pir, unit="s"))
        if not pd.isnull(light):
            Light_latencies.append(light)
            Light_times.append(event_time + pd.to_timedelta(light, unit="s"))
        if not pd.isnull(sound):
            Sound_latencies.append(sound)
            Sound_times.append(event_time + pd.to_timedelta(sound, unit="s"))
        if not pd.isnull(co2):
            CO2_latencies.append(co2)
            CO2_times.append(event_time + pd.to_timedelta(co2, unit="s"))

'''MAX_ROWS = 3000

PIR_times = PIR_times[:MAX_ROWS]
Light_times = Light_times[:MAX_ROWS]
Sound_times = Sound_times[:MAX_ROWS]
CO2_times = CO2_times[:MAX_ROWS]

PIR_latencies = PIR_latencies[:MAX_ROWS]
Light_latencies = Light_latencies[:MAX_ROWS]
Sound_latencies = Sound_latencies[:MAX_ROWS]
CO2_latencies = CO2_latencies[:MAX_ROWS]'''

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
    ax.xaxis.set_major_formatter(DateFormatter("%y-%m-%d %H:%M:%S"))
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
    fig.tight_layout()

    return df_to_base64(fig)


def plot_co2_vs_occupancy():
    fig, ax1 = plt.subplots(figsize=(12, 5))

    # CO2 Line
    ax1.plot(df["DateTime"], df["S5_CO2"], color="darkred", label="CO₂ Level")
    ax1.set_xlabel("Time")
    ax1.set_ylabel("CO₂ (ppm)", color="darkred")
    ax1.tick_params(axis='y', labelcolor="darkred")
    ax1.set_xlim(GLOBAL_X_MIN, GLOBAL_X_MAX)

    # Occupancy (Secondary Axis)
    ax2 = ax1.twinx()
    ax2.step(df["DateTime"], df["Room_Occupancy_Count"], where="post",
             color="black", label="Occupancy")
    ax2.set_ylabel("Occupancy Count", color="black")
    ax2.tick_params(axis='y', labelcolor="black")

    ax1.set_title("CO₂ Levels vs Room Occupancy Over Time")
    ax1.xaxis.set_major_formatter(DateFormatter("%y-%m-%d %H:%M:%S"))
    plt.setp(ax1.get_xticklabels(), rotation=45, ha="right")
    fig.tight_layout()

    return df_to_base64(fig)


def plot_light_vs_occupancy():
    fig, ax1 = plt.subplots(figsize=(12, 5))

    # Light Level Line
    ax1.plot(df["DateTime"], df["S1_Light"], label="Light Level", alpha=0.8)
    ax1.set_xlabel("Time")
    ax1.set_ylabel("Light (units)", color="blue")
    ax1.tick_params(axis='y', labelcolor="blue")
    ax1.set_xlim(GLOBAL_X_MIN, GLOBAL_X_MAX)

    # Occupancy (Secondary Axis)
    ax2 = ax1.twinx()
    ax2.step(df["DateTime"], df["Room_Occupancy_Count"], where="post",
             color="black", label="Occupancy")
    ax2.set_ylabel("Occupancy Count", color="black")
    ax2.tick_params(axis='y', labelcolor="black")

    ax1.set_title("Light Levels vs Room Occupancy Over Time")
    ax1.xaxis.set_major_formatter(DateFormatter("%y-%m-%d %H:%M:%S"))
    plt.setp(ax1.get_xticklabels(), rotation=45, ha="right")
    fig.tight_layout()

    return df_to_base64(fig)


def plot_latency_timeline():
    fig, ax = plt.subplots(figsize=(12, 7))

    ax.plot(PIR_times, PIR_latencies, marker="o", label="PIR")
    ax.plot(Light_times, Light_latencies, marker="o", label="Light")
    ax.plot(Sound_times, Sound_latencies, marker="o", label="Sound")
    ax.plot(CO2_times, CO2_latencies, marker="o", label="CO2")
    ax.set_xlim(GLOBAL_X_MIN, GLOBAL_X_MAX)

    for cp in True_change_times:
        plt.axvline(x=cp, linestyle="-", linewidth=0.5)

    ax.set_title("Sensor Detection Latencies Over Time")
    ax.set_xlabel("Time")
    ax.set_ylabel("Latency (ms)")
    ax.grid(True, alpha=0.5)
    ax.legend()
    ax.xaxis.set_major_formatter(DateFormatter('%y-%m-%d %H:%M:%S'))
    plt.setp(ax.get_xticklabels(), rotation=45, ha='right')
    fig.tight_layout()

    return df_to_base64(fig)


def plot_latency_comparison():
    sensors = ["PIR", "Light", "Sound", "CO2"]

    means = [
        np.nanmean(PIR_latencies),
        np.nanmean(Light_latencies),
        np.nanmean(Sound_latencies),
        np.nanmean(CO2_latencies)
    ]

    fig, ax = plt.subplots(figsize=(10, 5))
    bars = ax.bar(sensors, means)

    ax.bar(sensors, means, color=["green", "red", "blue"])
    ax.set_title("Mean Detection Latency by Sensor Type")
    ax.set_ylabel("Latency (ms)")
    ax.grid(True, axis='y', alpha=0.3)

    for bar, value in zip(bars, means):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            value,
            f"{value:.2f}",
            ha="center",
            va="bottom",
            fontsize=10
        )
    return df_to_base64(fig)


FULL_pir_vs_occ = plot_pir_vs_occ(df)  # ALL DATA
FULL_latency_timeline = plot_latency_timeline()  # ONLY FIRST 3000
FULL_latency_comparison = plot_latency_comparison()
FULL_co2_vs_occ = plot_co2_vs_occupancy()
FULL_light_vs_occ = plot_light_vs_occupancy()

visible_idx_min = df.index[df["DateTime"] >= VISIBLE_MIN_TIME][0]
visible_idx_max = df.index[df["DateTime"] <= VISIBLE_MAX_TIME][-1]


######### FLASK ROUTES #########

@app.route('/')
def index():
    return render_template(
        'index.html',
        max_index=visible_idx_max,
        min_index=visible_idx_min,
        FULL_pir_vs_occ=FULL_pir_vs_occ,
        FULL_latency_timeline=FULL_latency_timeline,
        FULL_latency_comparison=FULL_latency_comparison,
        FULL_co2_vs_occ=FULL_co2_vs_occ,
        FULL_light_vs_occ=FULL_light_vs_occ,
    )


@app.route("/get_data")
def get_data():
    idx = int(request.args.get("time"))
    idx = max(visible_idx_min, min(idx, visible_idx_max))

    row = df.loc[idx]
    selected_time = row["DateTime"]

    return jsonify({
        "current_time": selected_time.strftime("%y-%m-%d %H:%M:%S"),
        "true_count": int(row["Room_Occupancy_Count"]),
        "s6_pir": int(row["S6_PIR"]),
        "s7_pir": int(row["S7_PIR"]),
        "avg_temp": float(np.mean([row["S1_Temp"], row["S2_Temp"], row["S3_Temp"], row["S4_Temp"]])),
        "avg_light": float(np.mean([row["S1_Light"], row["S2_Light"], row["S3_Light"]])),
        "avg_sound": float(np.mean([row["S1_Sound"], row["S2_Sound"], row["S3_Sound"], row["S4_Sound"]])),
        "co2": float(row["S5_CO2"]),
    })


if __name__ == "__main__":
    app.run(debug=True)

import os
import sys
import uuid  # Generate unique iD's
import time
import threading  # Used by watchdog
import webbrowser
from threading import Timer
from datetime import datetime, timezone, timedelta

from flask import Flask, request, render_template, redirect, url_for, session
from werkzeug.utils import secure_filename  # Secure filename uploads (from user)

# ------- Configuration -------
if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")  # Stores uploaded .ics
EASTERN = timezone(timedelta(hours=-5))  # Static timezone used ( no daylight savings handled )
DAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


# ---------------------------------------------------------------------------
# RWU block schedule  (24hr clock)
# e.g. 8:00am - 8:50am
# ---------------------------------------------------------------------------
def t(h, m=0):  # Converts clock time to integer
    return h * 60 + m


_MWF_BLOCKS = [  # Standard Class times for MWF
    (t(8, 0), t(8, 50)),
    (t(9, 0), t(9, 50)),
    (t(10, 0), t(10, 50)),
    (t(11, 0), t(11, 50)),
    (t(12, 0), t(12, 50)),
    (t(13, 0), t(13, 50)),
    (t(14, 0), t(15, 20)),
    (t(15, 30), t(16, 50)),
    (t(17, 0), t(18, 20)),
]

_TTH_BLOCKS = [  # Standard Class times for TTH
    (t(8, 0), t(9, 20)),
    (t(9, 30), t(10, 50)),
    (t(11, 0), t(12, 20)),
    (t(12, 30), t(13, 50)),
    (t(14, 0), t(15, 20)),
    (t(15, 30), t(16, 50)),
    (t(17, 0), t(18, 20)),
]

_EVENING = (t(18, 30), t(21, 30))  # Evening class threshold

BLOCKS = {  # Assigns day to block
    "Monday": _MWF_BLOCKS,
    "Tuesday": _TTH_BLOCKS,
    "Wednesday": _MWF_BLOCKS,
    "Thursday": _TTH_BLOCKS,
    "Friday": _MWF_BLOCKS,
    "Saturday": [],
    "Sunday": [],
}

app = Flask(__name__, template_folder=os.path.join(BASE_DIR, "templates"))
app.secret_key = "your-secret-key"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024  # Max 4MB
app.config["MAX_STUDENTS"] = 10

os.makedirs(UPLOAD_FOLDER, exist_ok=True)  # Creates upload folder


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def fmt(minutes):  # Converts int time back to clock time
    h, m = divmod(minutes, 60)
    suffix = "AM" if h < 12 else "PM"
    h = h if h <= 12 else h - 12
    h = 12 if h == 0 else h
    return f"{h}:{m:02d} {suffix}"


def parse_busy_slots(filepath):
    with open(filepath, encoding="utf-8") as f:
        content = f.read()  # Whole content read
    busy = set()
    for block in content.split("BEGIN:VEVENT"):  # Splitting on the iCal values for each block
        if "END:VEVENT" not in block:
            continue
        lines = {}
        for line in block.splitlines():
            if ":" in line:
                key, _, val = line.partition(":")
                lines[key.strip()] = val.strip()  # Build lines with meeting values
        if "DTSTART" not in lines or "DTEND" not in lines:
            continue
        try:
            dt_start = datetime.strptime(lines["DTSTART"], "%Y%m%dT%H%M%SZ").replace(
                tzinfo=timezone.utc)  # iCal time format YYYYMMDD-T-HHMMSS-Z
            dt_end = datetime.strptime(lines["DTEND"], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        local_start = dt_start.astimezone(
            EASTERN)  # Kinda unnecessary but makes sure everything in iCal file is a class by making sure its longer than 2 months
        if local_start.month > 2:
            continue
        local_end = dt_end.astimezone(EASTERN)
        busy.add((  # This set just overwrites duplicates
            local_start.strftime("%A"),  # Day
            local_start.hour * 60 + local_start.minute,  # Start int
            local_end.hour * 60 + local_end.minute,  # End int
        ))
    return busy


def find_free_blocks(all_busy, show_evening=False, min_duration=50):
    result = {}
    for day in DAY_ORDER:
        occupied = [(s, e) for busy in all_busy for (d, s, e) in busy if
                    d == day]  # Compresses the all_busy set into just the busy times for that day
        occupied.sort()  # Sorts list from earliest to latest (important order)
        merged = []
        for s, e in occupied:
            if merged and s <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], e))
            else:
                merged.append([s, e])  # First case just appends i.e. merged = [[480, 570]]
            # Iteration 2 — (540, 630):
            #   540 <= 570? YES, they overlap
            #   new end = max(570, 630) = 630
            #   extend last interval
            #   merged = [[480, 630]]

        def is_free(blk_start, blk_end):  # Check to see if the two imputed blocks overlap
            for bs, be in merged:
                if bs < blk_end and be > blk_start:
                    return False
            return True

        day_blocks = list(BLOCKS.get(day, []))
        if show_evening:  # Optionally append evening times
            day_blocks = day_blocks + [_EVENING]

        free = []
        for blk_start, blk_end in day_blocks:
            if (blk_end - blk_start) >= min_duration and is_free(blk_start,
                                                                 blk_end):  # If a block meets 50min min and doesnt overlap then its free
                free.append((fmt(blk_start), fmt(blk_end)))

        if free:
            result[day] = free  # Add the free days to result under that day

    return result


def init_session():  # Stores user data from each browser session (reopened same students)
    if "students" not in session:
        session["students"] = []
        session["result"] = None
        session["duration"] = 50
        session["show_evening"] = False


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

@app.route("/", methods=["GET", "POST"])
def index():
    init_session()
    error = None

    if request.method == "POST":  # Upload, remove, compare
        action = request.form.get("action")

        if action == "upload":
            name = request.form.get("name", "").strip()
            file = request.files.get("file")
            students = session.get("students", [])
            if not name:
                error = "Please enter a name."  # Requires a student name
            elif not file or file.filename == "":
                error = "Please select a .ics file."
            elif not file.filename.lower().endswith(".ics"):  # Requires file to end in .ics
                error = "Only .ics files are accepted."
            elif len(students) >= app.config["MAX_STUDENTS"]:  # Max students enforced
                error = f"Maximum of {app.config['MAX_STUDENTS']} students."
            else:
                filename = secure_filename(
                    f"{uuid.uuid4().hex[:8]}_{name}_{file.filename}")  # Generate a secure filename
                filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)  # Saved to uploads folder
                file.save(filepath)
                students.append({"name": name, "file": filename})  # Add the file and name to students list
                session["students"] = students
                session["result"] = None  # Clear session results
                session.modified = True

        elif action == "remove":
            idx = int(request.form.get("index", -1))  # The form returns the index
            students = session.get("students", [])  # Pulls current student list
            if 0 <= idx < len(students):
                filepath = os.path.join(app.config["UPLOAD_FOLDER"], students[idx]["file"])
                if os.path.exists(filepath):
                    os.remove(filepath)  # Remove their iCal file from uploads
                students.pop(idx)  # Remove that student from list
                session["students"] = students
                session["result"] = None
                session.modified = True

        elif action == "compare":
            students = session.get("students", [])
            try:
                duration = int(request.form.get("duration", 50))  # Gets duration from user
                duration = max(15, min(duration, 480))
            except ValueError:
                duration = 50
            show_evening = request.form.get("show_evening") == "1"  # Check if user wants evening

            if len(students) < 2:  # Need at least two students to compare
                error = "Add at least 2 students to compare."
            else:
                all_busy = []
                for s in students:
                    fp = os.path.join(app.config["UPLOAD_FOLDER"], s["file"])
                    if os.path.exists(fp):
                        all_busy.append(parse_busy_slots(fp))
                session["result"] = find_free_blocks(all_busy, show_evening=show_evening, min_duration=duration)
                session["duration"] = duration
                session["show_evening"] = show_evening
                session.modified = True

        return redirect(url_for("index"))

    return render_template(
        "template.html",
        students=session.get("students", []),
        result=session.get("result"),
        duration=session.get("duration", 50),
        show_evening=session.get("show_evening", False),
        error=error,
    )


# ---------------------------------------------------------------------------
# Tab-close watchdog
# ---------------------------------------------------------------------------

last_ping = time.time()


@app.route("/ping", methods=["POST"])
def ping():
    global last_ping
    last_ping = time.time()
    return "ok"


def watchdog():
    global last_ping
    while True:
        time.sleep(3)
        if time.time() - last_ping > 15:
            os.kill(os.getpid(), 9)


threading.Thread(target=watchdog, daemon=True).start()


def open_browser():
    webbrowser.open_new("http://127.0.0.1:5000/")


# can change to not WERKZEUmmmmG
if __name__ == "__main__":
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        Timer(0.8, open_browser).start()
    app.run(debug=True, host="127.0.0.1", port=5000)

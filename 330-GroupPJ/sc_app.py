import os
import sys
import uuid
import time
import threading
import webbrowser
from threading import Timer
from datetime import datetime, timezone, timedelta

from flask import Flask, request, render_template, redirect, url_for, session
from werkzeug.utils import secure_filename

# ------- Configuration -------
if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
EASTERN = timezone(timedelta(hours=-5))
DAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


# ---------------------------------------------------------------------------
# RWU block schedule  (all times in minutes-since-midnight)
# ---------------------------------------------------------------------------
def t(h, m=0):
    return h * 60 + m


_MWF_BLOCKS = [
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

_TTH_BLOCKS = [
    (t(8, 0), t(9, 20)),
    (t(9, 30), t(10, 50)),
    (t(11, 0), t(12, 20)),
    (t(12, 30), t(13, 50)),
    (t(14, 0), t(15, 20)),
    (t(15, 30), t(16, 50)),
    (t(17, 0), t(18, 20)),
]

_EVENING = (t(18, 30), t(21, 30))

BLOCKS = {
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
app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024
app.config["MAX_STUDENTS"] = 10

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def fmt(minutes):
    h, m = divmod(minutes, 60)
    suffix = "AM" if h < 12 else "PM"
    h = h if h <= 12 else h - 12
    h = 12 if h == 0 else h
    return f"{h}:{m:02d} {suffix}"


def parse_busy_slots(filepath):
    with open(filepath, encoding="utf-8") as f:
        content = f.read()
    busy = set()
    for block in content.split("BEGIN:VEVENT"):
        if "END:VEVENT" not in block:
            continue
        lines = {}
        for line in block.splitlines():
            if ":" in line:
                key, _, val = line.partition(":")
                lines[key.strip()] = val.strip()
        if "DTSTART" not in lines or "DTEND" not in lines:
            continue
        try:
            dt_start = datetime.strptime(lines["DTSTART"], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
            dt_end = datetime.strptime(lines["DTEND"], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        local_start = dt_start.astimezone(EASTERN)
        if local_start.month > 2:
            continue
        local_end = dt_end.astimezone(EASTERN)
        busy.add((
            local_start.strftime("%A"),
            local_start.hour * 60 + local_start.minute,
            local_end.hour * 60 + local_end.minute,
        ))
    return busy


def find_free_blocks(all_busy, show_evening=False, min_duration=50):
    result = {}
    for day in DAY_ORDER:
        occupied = [(s, e) for busy in all_busy for (d, s, e) in busy if d == day]
        occupied.sort()
        merged = []
        for s, e in occupied:
            if merged and s <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], e))
            else:
                merged.append([s, e])

        def is_free(blk_start, blk_end):
            for bs, be in merged:
                if bs < blk_end and be > blk_start:
                    return False
            return True

        day_blocks = list(BLOCKS.get(day, []))
        if show_evening:
            day_blocks = day_blocks + [_EVENING]

        free = []
        for blk_start, blk_end in day_blocks:
            if (blk_end - blk_start) >= min_duration and is_free(blk_start, blk_end):
                free.append((fmt(blk_start), fmt(blk_end)))

        if free:
            result[day] = free

    return result


def init_session():
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

    if request.method == "POST":
        action = request.form.get("action")

        if action == "upload":
            name = request.form.get("name", "").strip()
            file = request.files.get("file")
            students = session.get("students", [])
            if not name:
                error = "Please enter a name."
            elif not file or file.filename == "":
                error = "Please select a .ics file."
            elif not file.filename.lower().endswith(".ics"):
                error = "Only .ics files are accepted."
            elif len(students) >= app.config["MAX_STUDENTS"]:
                error = f"Maximum of {app.config['MAX_STUDENTS']} students."
            else:
                filename = secure_filename(f"{uuid.uuid4().hex[:8]}_{name}_{file.filename}")
                filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
                file.save(filepath)
                students.append({"name": name, "file": filename})
                session["students"] = students
                session["result"] = None
                session.modified = True

        elif action == "remove":
            idx = int(request.form.get("index", -1))
            students = session.get("students", [])
            if 0 <= idx < len(students):
                fp = os.path.join(app.config["UPLOAD_FOLDER"], students[idx]["file"])
                if os.path.exists(fp):
                    os.remove(fp)
                students.pop(idx)
                session["students"] = students
                session["result"] = None
                session.modified = True

        elif action == "compare":
            students = session.get("students", [])
            try:
                duration = int(request.form.get("duration", 50))
                duration = max(15, min(duration, 480))
            except ValueError:
                duration = 50
            show_evening = request.form.get("show_evening") == "1"

            if len(students) < 2:
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


# can change to not WERKZEUG
if __name__ == "__main__":
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        Timer(0.8, open_browser).start()
    app.run(debug=True, host="127.0.0.1", port=5000)

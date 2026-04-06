"""
🌐 Job Auto-Applier — Web Frontend (Flask Backend)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Multi-user web app for configuring and running the
job auto-applier bot. Each user signs up, saves their
credentials + profile, configures phases, and launches.
"""

import os
import json
import hashlib
import uuid
import subprocess
import threading
import time
import signal
from datetime import datetime
from flask import (
    Flask, render_template, request, jsonify,
    session, redirect, url_for
)
import google.generativeai as genai

app = Flask(__name__)
app.secret_key = os.urandom(24).hex()

USERS_DIR = os.path.join(os.path.dirname(__file__), "users")
os.makedirs(USERS_DIR, exist_ok=True)

# Track running bot processes per user
BOT_PROCESSES = {}
BOT_LOGS = {}


# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


def get_user_path(username):
    safe = "".join(c for c in username if c.isalnum() or c in ("_", "-"))
    return os.path.join(USERS_DIR, f"{safe}.json")


def load_user(username):
    path = get_user_path(username)
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return None


def save_user(username, data):
    path = get_user_path(username)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def generate_config_for_user(user_data):
    """Convert user JSON data into a CONFIG dict that the bot can use."""
    profile = user_data.get("profile", {})
    linkedin = user_data.get("linkedin", {})
    phases = user_data.get("phases", {})
    linkedin_phase = phases.get("linkedin", {})

    keywords = linkedin_phase.get("keywords", [
        "Product Management Intern",
        "Business Analyst Intern",
    ])

    role_agents = []
    for kw in keywords:
        role_agents.append({
            "name": kw.replace(" Intern", ""),
            "emoji": "🔹",
            "keywords": [kw],
        })

    config = {
        "username": user_data.get("username", ""),
        "gemini_api_key": user_data.get("gemini_api_key", ""),
        "name": profile.get("full_name", ""),
        "phone": profile.get("phone", ""),
        "email": profile.get("email", ""),
        "resume_path": user_data.get("resume_path", ""),
        "linkedin": {
            "email": linkedin.get("email", ""),
            "password": linkedin.get("password", ""),
            "enabled": phases.get("linkedin", {}).get("enabled", True),
        },
        "wellfound": {
            "email": user_data.get("wellfound", {}).get("email", ""),
            "password": user_data.get("wellfound", {}).get("password", ""),
            "enabled": phases.get("wellfound", {}).get("enabled", True),
        },
        "internshala": {
            "email": user_data.get("internshala", {}).get("email", ""),
            "password": user_data.get("internshala", {}).get("password", ""),
            "enabled": phases.get("internshala", {}).get("enabled", True),
        },
        "unstop": {
            "email": user_data.get("unstop", {}).get("email", ""),
            "password": user_data.get("unstop", {}).get("password", ""),
            "enabled": phases.get("unstop", {}).get("enabled", True),
        },
        "naukri": {
            "email": user_data.get("naukri", {}).get("email", ""),
            "password": user_data.get("naukri", {}).get("password", ""),
            "enabled": phases.get("naukri", {}).get("enabled", True),
        },
        "keywords": keywords,
        "locations": linkedin_phase.get("locations", ["India", "Remote"]),
        "recently_posted": linkedin_phase.get("recently_posted", True),
        "role_agents": role_agents,
        "cover_letter": user_data.get("cover_letter") or profile.get("cover_letter", ""),
        "profile": profile,
        "web_search": {
            "enabled": phases.get("web_search", {}).get("enabled", True),
            "max_results_per_query": 15,
            "target_companies": [],
            "ats_domains": [
                "lever.co", "greenhouse.io", "workday.com",
                "smartrecruiters.com", "icims.com", "ashbyhq.com",
                "smartrecruiters.com", "icims.com", "ashbyhq.com",
                "jobs.lever.co", "boards.greenhouse.io",
            ],
        },
        "phases": {
            "linkedin": { "enabled": phases.get("linkedin", {}).get("enabled", True) },
            "wellfound": { "enabled": phases.get("wellfound", {}).get("enabled", True) },
            "internshala": { "enabled": phases.get("internshala", {}).get("enabled", True) },
            "unstop": { "enabled": phases.get("unstop", {}).get("enabled", True) },
            "naukri": { "enabled": phases.get("naukri", {}).get("enabled", True) },
            "google_form": { "enabled": phases.get("google_form", {}).get("enabled", True) },
        },
        "max_jobs_per_day": 100,
        "min_per_keyword": 10,
        "delay_between_applies_sec": (3, 8),
        "continuous_mode": False,
        "cycle_delay_minutes": 30,
        "headless": False,
        "dry_run": False,
    }

    # Google Form autofill answers
    gf_answers = phases.get("google_form", {}).get("custom_answers", {})
    for key, val in gf_answers.items():
        config["profile"][key] = val

    # Duration preference
    config["internship_duration_preference"] = linkedin_phase.get(
        "duration", "3 months"
    )

    return config


# ─────────────────────────────────────────────
#  ROUTES
# ─────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/signup", methods=["POST"])
def signup():
    data = request.json
    username = data.get("username", "").strip().lower()
    password = data.get("password", "")
    email = data.get("email", "")

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    if len(username) < 3:
        return jsonify({"error": "Username must be at least 3 characters"}), 400

    if load_user(username):
        return jsonify({"error": "Username already exists"}), 409

    user_data = {
        "username": username,
        "password_hash": hash_password(password),
        "email": email,
        "created_at": datetime.now().isoformat(),
        "profile": {},
        "linkedin": {},
        "internshala": {},
        "unstop": {},
        "naukri": {},
        "wellfound": {},
        "phases": {},
        "gemini_api_key": "",
        "resume_path": "",
    }

    save_user(username, user_data)
    session["user"] = username
    return jsonify({"success": True, "username": username})


@app.route("/api/login", methods=["POST"])
def login():
    data = request.json
    username = data.get("username", "").strip().lower()
    password = data.get("password", "")

    user_data = load_user(username)
    if not user_data:
        return jsonify({"error": "User not found"}), 404

    if user_data["password_hash"] != hash_password(password):
        return jsonify({"error": "Invalid password"}), 401

    session["user"] = username
    return jsonify({"success": True, "username": username})


@app.route("/api/logout", methods=["POST"])
def logout():
    session.pop("user", None)
    return jsonify({"success": True})


@app.route("/api/profile", methods=["GET"])
def get_profile():
    username = session.get("user")
    if not username:
        return jsonify({"error": "Not logged in"}), 401

    user_data = load_user(username)
    if not user_data:
        return jsonify({"error": "User not found"}), 404

    # Don't send password hash
    safe_data = {k: v for k, v in user_data.items() if k != "password_hash"}
    return jsonify(safe_data)


@app.route("/api/profile", methods=["POST"])
def save_profile():
    username = session.get("user")
    if not username:
        return jsonify({"error": "Not logged in"}), 401

    user_data = load_user(username)
    if not user_data:
        return jsonify({"error": "User not found"}), 404

    incoming = request.json

    # Merge incoming data into user_data
    for key in ["profile", "linkedin", "internshala", "unstop",
                 "naukri", "wellfound", "phases", "gemini_api_key",
                 "resume_path", "cover_letter"]:
        if key in incoming:
            if isinstance(incoming[key], dict) and isinstance(user_data.get(key), dict):
                user_data[key].update(incoming[key])
            else:
                user_data[key] = incoming[key]

    user_data["updated_at"] = datetime.now().isoformat()
    save_user(username, user_data)
    return jsonify({"success": True})


@app.route("/api/run_bot", methods=["POST"])
def run_bot():
    username = session.get("user")
    if not username:
        return jsonify({"error": "Not logged in"}), 401

    user_data = load_user(username)
    if not user_data:
        return jsonify({"error": "User not found"}), 404

    # Check if already running
    if username in BOT_PROCESSES and BOT_PROCESSES[username].poll() is None:
        return jsonify({"error": "Bot is already running"}), 409

    # Generate config
    config = generate_config_for_user(user_data)

    # Write a temporary config file for the user
    config_path = os.path.join(USERS_DIR, f"{username}_config.py")
    with open(config_path, "w") as f:
        f.write(f"CONFIG = {json.dumps(config, indent=2)}\n")

    # Launch bot subprocess
    bot_script = os.path.join(os.path.dirname(__file__), "run_all_phases.py")
    env = os.environ.copy()
    env["USER_CONFIG_PATH"] = config_path

    BOT_LOGS[username] = []

    def stream_output(proc, username):
        for line in iter(proc.stdout.readline, ""):
            if line:
                BOT_LOGS[username].append(line.strip())
                # Keep only last 500 lines
                if len(BOT_LOGS[username]) > 500:
                    BOT_LOGS[username] = BOT_LOGS[username][-500:]
        proc.wait()

    proc = subprocess.Popen(
        ["python3", bot_script],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=os.path.dirname(__file__),
        env=env,
        start_new_session=True  # For robust termination
    )
    BOT_PROCESSES[username] = proc

    t = threading.Thread(target=stream_output, args=(proc, username), daemon=True)
    t.start()

    return jsonify({"success": True, "message": "Bot started!"})


@app.route("/api/stop_bot", methods=["POST"])
def stop_bot():
    username = session.get("user")
    if not username:
        return jsonify({"error": "Not logged in"}), 401

    proc = BOT_PROCESSES.get(username)
    if proc and proc.poll() is None:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except ProcessLookupError:
            proc.terminate()
        return jsonify({"success": True, "message": "Bot stopped"})
    return jsonify({"error": "No bot running"}), 404

@app.route("/api/analyze_log", methods=["POST"])
def analyze_log():
    username = session.get("user")
    if not username:
        return jsonify({"error": "Not logged in"}), 401
    
    user_data = load_user(username)
    apikey = user_data.get("gemini_api_key", "")
    if not apikey:
        return jsonify({"error": "Gemini API key is not configured"}), 400
        
    logs = BOT_LOGS.get(username, [])
    if not logs:
        return jsonify({"analysis": "No logs found to analyze."})
        
    try:
        genai.configure(api_key=apikey)
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
        log_text = "\\n".join(logs[-150:]) # Send last 150 lines
        prompt = f"Analyze these application logs and tell me if there are any errors. If there are, explain what failed and how to fix it:\\n\\n{log_text}"
        
        response = model.generate_content(prompt)
        return jsonify({"analysis": response.text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/bot_status", methods=["GET"])
def bot_status():
    username = session.get("user")
    if not username:
        return jsonify({"error": "Not logged in"}), 401

    proc = BOT_PROCESSES.get(username)
    running = proc is not None and proc.poll() is None
    logs = BOT_LOGS.get(username, [])[-50:]

    return jsonify({
        "running": running,
        "logs": logs,
    })


# ─────────────────────────────────────────────
#  RUN
# ─────────────────────────────────────────────
if __name__ == "__main__":
    print("\n" + "=" * 55)
    print("  🚀 Job Auto-Applier Web App")
    print("  🌐 Open: http://localhost:5001")
    print("=" * 55 + "\n")
    app.run(debug=True, port=5001)

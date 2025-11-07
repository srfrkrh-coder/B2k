# server.py
import os
import random
import time
import json
from threading import Lock
from flask import Flask, render_template, request, session, jsonify, redirect, url_for
from flask_socketio import SocketIO, emit, disconnect, join_room, leave_room

# config
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "Ninjago1382!!"
SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "change_this_secret_in_prod")
PORT = int(os.getenv("PORT", 5000))

# app
app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = SECRET_KEY
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# state
LOCK = Lock()
players = {}       # sid -> username
user_sids = {}     # username -> sid
scores = {}        # username -> total score
blocked = set()
chat_open = True
current_letter = None
round_active = False
ROUND_DURATION = 60
SCORES_FILE = "scores.json"

letters = list("الفبپتثجچحخدذرزژسشصضطظعغفقکگلمنوهی")

def load_scores():
    global scores
    try:
        with open(SCORES_FILE, "r", encoding="utf-8") as f:
            scores = json.load(f)
    except Exception:
        scores = {}

def save_scores():
    try:
        with open(SCORES_FILE, "w", encoding="utf-8") as f:
            json.dump(scores, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

load_scores()

def pick_letter():
    return random.choice(letters)

def broadcast_players():
    with LOCK:
        online = [{"username": u, "score": scores.get(u,0)} for sid,u in players.items()]
    socketio.emit("player_list", {"players": online})

# ROUTES
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/join", methods=["POST"])
def join():
    data = request.json or {}
    username = (data.get("username") or "").strip()
    if not username:
        return jsonify({"ok": False, "error": "نام کاربری لازم است"}), 400
    if username in blocked:
        return jsonify({"ok": False, "error": "این نام مسدود شده است."}), 403
    # ensure unique: currently online
    if username in user_sids:
        return jsonify({"ok": False, "error": "این نام فعلاً آنلاین است."}), 409
    return jsonify({"ok": True})

@app.route("/game")
def game():
    username = request.args.get("username","").strip()
    if not username:
        return redirect(url_for("index"))
    return render_template("game.html", username=username, chat_open=chat_open)

@app.route("/admin")
def admin_page():
    is_admin = session.get("is_admin", False)
    return render_template("admin.html", is_admin=is_admin)

@app.route("/admin-login", methods=["POST"])
def admin_login():
    data = request.json or request.form
    u = data.get("username",""); p = data.get("password","")
    if u == ADMIN_USERNAME and p == ADMIN_PASSWORD:
        session["is_admin"] = True
        return jsonify({"ok": True})
    return jsonify({"ok": False, "message": "نام کاربری یا رمز اشتباه است."}), 401

@app.route("/admin-logout", methods=["POST"])
def admin_logout():
    session.pop("is_admin", None)
    return jsonify({"ok": True})

# admin REST actions
@app.route("/admin/block", methods=["POST"])
def admin_block():
    if not session.get("is_admin"): return jsonify({"ok": False}), 403
    data = request.json or request.form
    username = data.get("username")
    with LOCK:
        blocked.add(username)
        sid = user_sids.get(username)
        if sid:
            try:
                socketio.emit("system", f"🔒 {username} توسط مدیر مسدود شد.", broadcast=True)
                socketio.server.disconnect(sid)
            except Exception:
                pass
    broadcast_players(); save_scores()
    return jsonify({"ok": True})

@app.route("/admin/unblock", methods=["POST"])
def admin_unblock():
    if not session.get("is_admin"): return jsonify({"ok": False}), 403
    data = request.json or request.form
    username = data.get("username")
    with LOCK:
        blocked.discard(username)
    socketio.emit("system", f"🔓 {username} آزاد شد.", broadcast=True)
    broadcast_players()
    return jsonify({"ok": True})

@app.route("/admin/toggle_chat", methods=["POST"])
def admin_toggle():
    if not session.get("is_admin"): return jsonify({"ok": False}), 403
    global chat_open
    chat_open = not chat_open
    socketio.emit("chat_status", {"open": chat_open}, broadcast=True)
    socketio.emit("system", f"🔇 وضعیت چت: {'باز' if chat_open else 'بسته'}", broadcast=True)
    return jsonify({"ok": True, "chat_open": chat_open})

# SOCKETS
@socketio.on("connect")
def on_connect():
    pass

@socketio.on("join")
def on_join(data):
    username = data.get("username") if isinstance(data, dict) else data
    sid = request.sid
    if not username or username.strip() == "":
        username = f"مهمان_{sid[:5]}"
    if username in blocked:
        emit("blocked", {"msg":"شما مسدود شده‌اید."}); disconnect(); return
    with LOCK:
        players[sid] = username
        user_sids[username] = sid
        if username not in scores: scores[username] = 0
    emit("joined", {"username":username, "scores":scores, "current_letter":current_letter, "round_active":round_active}, room=sid)
    socketio.emit("system", f"✨ {username} وارد شد.", broadcast=True)
    broadcast_players()

@socketio.on("start_round")
def on_start_round():
    global round_active
    if round_active:
        emit("error", {"msg":"دور در حال اجراست."}, room=request.sid); return
    round_active = True
    socketio.start_background_task(round_task)

def round_task():
    global current_letter, round_active
    with LOCK:
        current_letter = pick_letter()
    socketio.emit("round_started", {"letter":current_letter, "duration": ROUND_DURATION}, broadcast=True)
    remaining = ROUND_DURATION
    while remaining > 0:
        socketio.sleep(1)
        remaining -= 1
        socketio.emit("time_update", {"time_left": remaining}, broadcast=True)
    # end
    round_active = False
    socketio.emit("round_ended", {"letter": current_letter}, broadcast=True)
    save_scores(); broadcast_players()

@socketio.on("submit_answers")
def on_submit_answers(data):
    username = data.get("username") or players.get(request.sid, "مهمان")
    answers = data.get("answers", {})
    if not round_active:
        emit("submission_result", {"ok": False, "message":"دور فعال نیست."}, room=request.sid); return
    if not current_letter:
        emit("submission_result", {"ok": False, "message":"حرف فعالی وجود ندارد."}, room=request.sid); return
    earned = 0
    for k,v in (answers or {}).items():
        v = (v or "").strip()
        if not v: continue
        if v[0] == current_letter: earned += 10
    with LOCK:
        scores[username] = scores.get(username,0) + earned
        save_scores()
    emit("submission_result", {"ok": True, "earned":earned, "total":scores[username]}, room=request.sid)
    socketio.emit("score_update", {"scores":scores}, broadcast=True)
    broadcast_players()

@socketio.on("chat")
def on_chat(data):
    username = data.get("username") or players.get(request.sid, "مهمان")
    text = data.get("text","").strip()
    if username in blocked:
        emit("blocked", {"msg":"مسدود شده‌اید."}, room=request.sid); disconnect(); return
    if not chat_open:
        emit("chat_closed", {"msg":"چت بسته است."}, room=request.sid); return
    socketio.emit("chat", {"from":username, "text":text}, broadcast=True)

@socketio.on("disconnect")
def on_disconnect():
    sid = request.sid
    uname = players.pop(sid, None)
    if uname and user_sids.get(uname) == sid: user_sids.pop(uname, None)
    if uname: socketio.emit("system", f"❌ {uname} خارج شد.", broadcast=True)
    broadcast_players()

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=PORT)
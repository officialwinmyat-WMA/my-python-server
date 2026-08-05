import os
import sqlite3
import random
import requests
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template_string, session, send_file

# Python compatibility fix for gevent (Disabled patch for ssl to prevent recursion error)
import sys
from gevent import monkey
try:
    monkey.patch_all(ssl=False)
except Exception:
    pass

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "wma_qq_secure_secret_key_123")

from flask_socketio import SocketIO, emit
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

# Database Initialization (Supporting both Group and Private Chats)
def init_db():
    conn = sqlite3.connect('wma_qq_private.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_info TEXT,
            msg_type TEXT,
            content TEXT,
            filename TEXT,
            store_type TEXT,
            room TEXT,
            expire_at DATETIME,
            timestamp DATETIME
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT UNIQUE,
            google_account TEXT,
            status TEXT,
            last_active DATETIME
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            password TEXT,
            device_id TEXT,
            remember_token TEXT,
            verification_code TEXT,
            is_verified INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def clean_expired_history():
    try:
        conn = sqlite3.connect('wma_qq_private.db')
        cursor = conn.cursor()
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute('DELETE FROM history WHERE expire_at < ?', (now_str,))
        conn.commit()
        conn.close()
    except Exception as e:
        print("Cleanup error:", e)

def send_verification_email(recipient_email, code):
    try:
        resend_api_key = os.environ.get("RESEND_API_KEY", "")
        if not resend_api_key:
            print("Resend API Key not found")
            return False
        
        headers = {
            "Authorization": f"Bearer {resend_api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "from": "WMA QQ <onboarding@resend.dev>",
            "to": [recipient_email],
            "subject": f"WMA QQ - Verification Code: {code}",
            "html": f"<p>Your WMA QQ Verification Code is: <strong>{code}</strong></p><p>Please enter this 6-digit code to complete your registration.</p>"
        }
        
        response = requests.post("https://api.resend.com/emails", json=payload, headers=headers, timeout=10)
        if response.status_code in [200, 201]:
            return True
        else:
            print("Resend API error response:", response.text)
            return False
    except Exception as e:
        print("Email sending error via Resend:", e)
        return False

def send_approval_email(device_id, google_account):
    try:
        resend_api_key = os.environ.get("RESEND_API_KEY", "")
        if not resend_api_key:
            return
        
        headers = {
            "Authorization": f"Bearer {resend_api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "from": "WMA QQ <onboarding@resend.dev>",
            "to": ["officialwinmyat@gmail.com"],
            "subject": f"WMA QQ - New Device Pending Approval: {device_id}",
            "html": f"<p>New Device Access Request:</p><p>Device ID: <b>{device_id}</b></p><p>Google Account: <b>{google_account}</b></p><p>Please go to your dashboard to approve or ban this device.</p>"
        }
        
        requests.post("https://api.resend.com/emails", json=payload, headers=headers, timeout=10)
    except Exception as e:
        print("Email notification error via Resend:", e)

@app.route('/')
def index():
    return render_template_string(HTML_PAGE)

@app.route('/ping')
def ping():
    return "OK", 200

@app.route('/manifest.json')
def serve_manifest():
    return send_file('manifest.json', mimetype='application/manifest+json')

@app.route('/sw.js')
def serve_sw():
    return send_file('sw.js', mimetype='application/javascript')

@app.route('/signup', methods=['POST'])
def signup():
    data = request.json
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    device_id = data.get('device_id', '')
    
    if not email or not password:
        return jsonify({"success": False, "error": "Email နှင့် Password ထည့်ရန် လိုအပ်ပါသည်။"})
    
    code = f"{random.randint(100000, 999999)}"
    
    try:
        conn = sqlite3.connect('wma_qq_private.db')
        cursor = conn.cursor()
        cursor.execute('SELECT id, is_verified FROM users WHERE email = ?', (email,))
        existing = cursor.fetchone()
        
        if existing:
            if existing[1] == 1:
                conn.close()
                return jsonify({"success": False, "error": "ဤ Email ဖြင့် အကောင့်ရှိပြီးသား ဖြစ်ပါသည်။ Login ဝင်ပါ။"})
            else:
                cursor.execute('UPDATE users SET password = ?, device_id = ?, verification_code = ? WHERE email = ?', (password, device_id, code, email))
        else:
            cursor.execute('INSERT INTO users (email, password, device_id, verification_code, is_verified) VALUES (?, ?, ?, ?, 0)', (email, password, device_id, code))
        
        conn.commit()
        conn.close()
        
        sent = send_verification_email(email, code)
        
        # မည်သည့် Email (officialkyukyu@gmail.com သို့မဟုတ် အခြား) မဆို အမြဲတမ်း Log ထဲသို့ Verification Code ထင်ရှားစွာ ထုတ်ပေးပါမည်။
        print(f"CRITICAL: Failed or Sent Email to {email}. Verification Code is: {code}")
            
        return jsonify({"success": True, "requires_verification": True})
    except Exception as e:
        print(f"CRITICAL: Signup Error for {email} | Code: {code} | Error: {str(e)}")
        return jsonify({"success": False, "error": str(e)})

@app.route('/verify_code', methods=['POST'])
def verify_code():
    data = request.json
    email = data.get('email', '').strip().lower()
    code = data.get('code', '').strip()
    
    conn = sqlite3.connect('wma_qq_private.db')
    cursor = conn.cursor()
    cursor.execute('SELECT verification_code FROM users WHERE email = ?', (email,))
    row = cursor.fetchone()
    
    if row and row[0] == code:
        cursor.execute('UPDATE users SET is_verified = 1, verification_code = NULL WHERE email = ?', (email,))
        conn.commit()
        conn.close()
        
        session['user_email'] = email
        is_admin = (email == 'officialwinmyat@gmail.com')
        session['is_admin'] = is_admin
        return jsonify({"success": True, "is_admin": is_admin})
    else:
        conn.close()
        return jsonify({"success": False, "error": "Verification Code မှားယွင်းနေပါသည်။"})

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    remember = data.get('remember', False)
    device_id = data.get('device_id', '')
    
    conn = sqlite3.connect('wma_qq_private.db')
    cursor = conn.cursor()
    cursor.execute('SELECT password, is_verified FROM users WHERE email = ?', (email,))
    row = cursor.fetchone()
    
    if row:
        stored_password, is_verified = row
        if is_verified == 0:
            conn.close()
            return jsonify({"success": False, "error": "အကောင့်ကို Code ဖြင့် အတည်ပြုပြီးသား မရှိသေးပါ။"})
            
        if stored_password == password:
            session['user_email'] = email
            is_admin = (email == 'officialwinmyat@gmail.com')
            session['is_admin'] = is_admin
            
            token = ""
            if remember:
                token = f"token_{email}_{device_id}"
                cursor.execute('UPDATE users SET remember_token = ?, device_id = ? WHERE email = ?', (token, device_id, email))
                conn.commit()
            
            conn.close()
            return jsonify({"success": True, "is_admin": is_admin, "remember_token": token})
        else:
            conn.close()
            return jsonify({"success": False, "error": "Password မှားယွင်းနေပါသည်။"})
    else:
        conn.close()
        return jsonify({"success": False, "error": "ဤ Email ဖြင့် အကောင့်မရှိပါ။"})

@app.route('/check_remember', methods=['POST'])
def check_remember():
    data = request.json
    email = data.get('email', '').strip().lower()
    token = data.get('token', '')
    device_id = data.get('device_id', '')
    
    if not email or not token or not device_id:
        return jsonify({"logged_in": False})
        
    conn = sqlite3.connect('wma_qq_private.db')
    cursor = conn.cursor()
    cursor.execute('SELECT remember_token, device_id FROM users WHERE email = ?', (email,))
    row = cursor.fetchone()
    conn.close()
    
    if row and row[0] == token and row[1] == device_id:
        session['user_email'] = email
        is_admin = (email == 'officialwinmyat@gmail.com')
        session['is_admin'] = is_admin
        return jsonify({"logged_in": True, "email": email, "is_admin": is_admin})
    
    return jsonify({"logged_in": False})

@app.route('/reset_password_google', methods=['POST'])
def reset_password_google():
    data = request.json
    email = data.get('email', '').strip().lower()
    new_password = data.get('new_password', '')
    
    if not email or not new_password:
        return jsonify({"success": False, "error": "Email နှင့် Password အသစ်ထည့်ရန် လိုအပ်ပါသည်။"})
        
    conn = sqlite3.connect('wma_qq_private.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM users WHERE email = ?', (email,))
    row = cursor.fetchone()
    
    if row:
        cursor.execute('UPDATE users SET password = ? WHERE email = ?', (new_password, email))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    else:
        conn.close()
        return jsonify({"success": False, "error": "ဤ Email ဖြင့် အကောင့်မရှိပါ။"})

@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({"success": True})

@app.route('/check_session', methods=['GET'])
def check_session():
    if 'user_email' in session:
        email = session['user_email']
        is_admin = (email == 'officialwinmyat@gmail.com')
        session['is_admin'] = is_admin
        return jsonify({
            "logged_in": True,
            "email": email,
            "is_admin": is_admin
        })
    return jsonify({"logged_in": False})

@app.route('/get_devices', methods=['GET'])
def get_devices():
    if 'user_email' not in session:
        return jsonify([])
    conn = sqlite3.connect('wma_qq_private.db')
    cursor = conn.cursor()
    cursor.execute('SELECT device_id, google_account, status, last_active FROM devices')
    rows = cursor.fetchall()
    conn.close()
    
    devices = []
    for r in rows:
        devices.append({
            "device_id": r[0],
            "account": r[1],
            "status": 'approved' if r[1] == 'officialwinmyat@gmail.com' else r[2],
            "active": True if r[3] else False,
            "is_current_user_admin": session.get('user_email') == 'officialwinmyat@gmail.com'
        })
    return jsonify(devices)

@app.route('/get_history', methods=['GET'])
def get_history():
    room = request.args.get('room', 'main_group')
    clean_expired_history()
    conn = sqlite3.connect('wma_qq_private.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, user_info, msg_type, content, filename, store_type, room, timestamp FROM history WHERE room = ? ORDER BY id DESC', (room,))
    rows = cursor.fetchall()
    conn.close()
    
    history = []
    for r in rows:
        history.append({
            "id": r[0],
            "user": r[1],
            "type": r[2],
            "content": r[3],
            "filename": r[4],
            "store": r[5],
            "room": r[6],
            "timestamp": r[7]
        })
    return jsonify(history)

@socketio.on('register_device')
def handle_register_device(data):
    dev_id = data.get('device_id')
    google_acc = session.get('user_email', data.get('google_account', ''))
    if not dev_id or not google_acc:
        return
        
    conn = sqlite3.connect('wma_qq_private.db')
    cursor = conn.cursor()
    cursor.execute('SELECT status FROM devices WHERE device_id = ?', (dev_id,))
    row = cursor.fetchone()
    
    status = 'approved' if google_acc == 'officialwinmyat@gmail.com' else ('approved' if row and row[0] == 'approved' else 'pending')
    
    if not row:
        cursor.execute('INSERT INTO devices (device_id, google_account, status, last_active) VALUES (?, ?, ?, ?)', (dev_id, google_acc, status, datetime.now()))
        conn.commit()
        if status == 'pending' and google_acc != 'officialwinmyat@gmail.com':
            send_approval_email(dev_id, google_acc)
    else:
        cursor.execute('UPDATE devices SET google_account = ?, status = ?, last_active = ? WHERE device_id = ?', (google_acc, status, datetime.now(), dev_id))
        conn.commit()
    conn.close()
    socketio.emit('device_status_update', {'device_id': dev_id})
    socketio.emit('online_users_refresh')

@socketio.on('admin_device_action')
def handle_admin_action(data):
    if session.get('user_email') != 'officialwinmyat@gmail.com':
        return
    dev_id = data.get('device_id')
    action = data.get('action')
    
    conn = sqlite3.connect('wma_qq_private.db')
    cursor = conn.cursor()
    if action == 'remove':
        cursor.execute('SELECT google_account FROM devices WHERE device_id = ?', (dev_id,))
        dev_row = cursor.fetchone()
        if dev_row and dev_row[0]:
            acc_email = dev_row[0]
            cursor.execute('DELETE FROM users WHERE email = ?', (acc_email,))
        cursor.execute('DELETE FROM devices WHERE device_id = ?', (dev_id,))
    else:
        cursor.execute('UPDATE devices SET status = ? WHERE device_id = ?', (action, dev_id))
    conn.commit()
    conn.close()
    socketio.emit('device_status_update', {'device_id': dev_id})

@socketio.on('join_room')
def handle_join_room(data):
    from flask_socketio import join_room
    room = data.get('room')
    if room:
        join_room(room)

@socketio.on('new_message')
def handle_new_message(data):
    user = data.get('user')
    msg_type = data.get('type')
    content = data.get('content')
    filename = data.get('filename', '')
    store = data.get('store', '48 Hours Auto-Delete')
    room = data.get('room', 'main_group')
    
    now = datetime.now()
    expire_at = now + timedelta(hours=48)
        
    conn = sqlite3.connect('wma_qq_private.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO history (user_info, msg_type, content, filename, store_type, room, expire_at, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                   (user, msg_type, content, filename, store, room, expire_at.strftime('%Y-%m-%d %H:%M:%S'), now.strftime('%Y-%m-%d %H:%M:%S')))
    msg_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    socketio.emit('broadcast_message', {
        "id": msg_id,
        "user": user,
        "type": msg_type,
        "content": content,
        "filename": filename,
        "store": store,
        "room": room,
        "timestamp": now.strftime('%Y-%m-%d %H:%M:%S')
    }, room=room)

@socketio.on('delete_message_item')
def handle_delete_message(data):
    msg_id = data.get('id')
    room = data.get('room', 'main_group')
    if msg_id:
        conn = sqlite3.connect('wma_qq_private.db')
        cursor = conn.cursor()
        cursor.execute('DELETE FROM history WHERE id = ?', (msg_id,))
        conn.commit()
        conn.close()
        socketio.emit('message_deleted', {"id": msg_id}, room=room)

@socketio.on('trigger_video_call')
def handle_video_call(data):
    socketio.emit('incoming_video_call', data)

@socketio.on('video_signal')
def handle_video_signal(data):
    socketio.emit('video_signal_relay', data)

@socketio.on('reset_storage')
def handle_reset():
    if session.get('user_email') == 'officialwinmyat@gmail.com':
        conn = sqlite3.connect('wma_qq_private.db')
        cursor = conn.cursor()
        cursor.execute('DELETE FROM history')
        conn.commit()
        conn.close()
        socketio.emit('storage_reset')

HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>WMA QQ - Private & Group Anime Chat Hub</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="manifest" href="/manifest.json">
    <meta name="theme-color" content="#ec4899">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.2/socket.io.js"></script>
    <style>
        :root {
            --bg-color: #0f172a;
            --panel-bg: rgba(20, 24, 33, 0.88);
            --text-color: #f8fafc;
            --accent-color: #ec4899;
            --chat-bg: rgba(10, 14, 23, 0.85);
            --stream-bg: rgba(20, 24, 33, 0.85);
            --bg-image: url('https://images.unsplash.com/photo-1578632767115-351597cf2477?auto=format&fit=crop&w=1920&q=80');
            --char-fg-image: none;
        }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0; padding: 0;
            background-color: var(--bg-color);
            background-image: var(--bg-image);
            background-size: cover; background-position: center; background-attachment: fixed;
            color: var(--text-color);
            display: flex; height: 100vh; overflow: hidden;
            position: relative;
        }
        body::before {
            content: "";
            position: fixed;
            top: 0; left: 0; width: 100%; height: 100%;
            background-image: var(--char-fg-image);
            background-size: cover; background-position: center;
            opacity: 0.15;
            pointer-events: none;
            z-index: 1;
        }
        .left-pane, .right-pane {
            position: relative;
            z-index: 2;
        }
        .left-pane {
            width: 50%; height: 100vh; overflow-y: auto; padding: 20px; box-sizing: border-box;
            background: var(--panel-bg); border-right: 3px solid var(--accent-color);
            backdrop-filter: blur(12px);
            transition: all 0.3s ease;
        }
        .right-pane {
            width: 50%; height: 100vh; display: flex; flex-direction: column; padding: 20px; box-sizing: border-box;
            background: var(--stream-bg); backdrop-filter: blur(12px);
            border-left: 3px solid var(--accent-color);
            transition: all 0.3s ease;
        }
        .card {
            background: rgba(255,255,255,0.08); padding: 15px; border-radius: 10px; margin-bottom: 15px;
            border: 2px solid var(--accent-color); backdrop-filter: blur(8px);
            box-shadow: 0 0 15px color-mix(in srgb, var(--accent-color) 35%, transparent);
            transition: all 0.3s ease;
        }
        input, textarea, select, button {
            width: 100%; padding: 10px; margin: 8px 0; border-radius: 6px;
            border: 2px solid var(--accent-color); background: rgba(15, 23, 42, 0.92);
            color: white; box-sizing: border-box; outline: none; transition: all 0.3s ease;
        }
        input:focus, textarea:focus, select:focus {
            box-shadow: 0 0 10px var(--accent-color);
        }
        button {
            background: var(--accent-color); cursor: pointer; font-weight: bold; border: 2px solid #fff; transition: 0.2s;
        }
        button:hover { opacity: 0.9; transform: scale(1.02); box-shadow: 0 0 12px var(--accent-color); }
        #historyStream {
            flex: 1; overflow-y: auto; background: var(--chat-bg); border: 2px solid var(--accent-color);
            border-radius: 10px; padding: 12px; box-sizing: border-box; backdrop-filter: blur(8px); margin-top: 10px;
            box-shadow: inset 0 0 15px color-mix(in srgb, var(--accent-color) 20%, transparent);
            -webkit-overflow-scrolling: touch;
        }
        .history-item {
            padding: 12px; margin-bottom: 10px; background: rgba(255,255,255,0.08);
            border-left: 6px solid var(--accent-color); border-radius: 8px; font-size: 13px; word-break: break-all; position: relative;
            box-shadow: 0 2px 8px rgba(0,0,0,0.3); transition: all 0.3s ease;
        }
        .msg-actions { margin-top: 8px; display: flex; gap: 6px; flex-wrap: wrap; }
        .msg-actions button { padding: 4px 10px; font-size: 11px; width: auto; margin: 0; border-radius: 4px; background: var(--accent-color); border: 1px solid #fff; }
        
        .user-name-tag { color: var(--accent-color); cursor: pointer; text-decoration: underline; font-weight: bold; position: relative; display: inline-block; }
        .user-name-tag:hover { color: #fff; }
        
        .online-dot {
            display: inline-block;
            width: 9px;
            height: 9px;
            background-color: #22c55e;
            border-radius: 50%;
            margin-left: 5px;
            box-shadow: 0 0 6px #22c55e;
            vertical-align: middle;
        }
        
        #topNotificationBanner {
            display: none;
            position: absolute;
            top: 10px;
            left: 10px;
            z-index: 1001;
            background: rgba(236, 72, 153, 0.95);
            color: white;
            padding: 6px 12px;
            border-radius: 6px;
            font-size: 12px;
            font-weight: bold;
            box-shadow: 0 0 10px var(--accent-color);
            border: 1px solid #fff;
            animation: fadeInOut 2s ease;
        }

        #resetBtn {
            position: absolute; top: 15px; right: 15px; z-index: 999; background: #dc2626; color: white;
            padding: 6px 12px; border-radius: 6px; font-size: 12px; cursor: pointer; width: auto; border: 2px solid var(--accent-color); display: none;
        }
        #goToMainChatBtn {
            display: none; margin-bottom: 10px; background: #2563eb; color: white; font-weight: bold; border: 2px solid #fff; padding: 8px; border-radius: 6px; cursor: pointer; text-align: center;
        }
        #videoPopup {
            display: none; position: fixed; top: 10%; left: 15%; width: 70%;
            background: rgba(20, 24, 33, 0.98); border: 3px solid var(--accent-color); border-radius: 12px;
            padding: 20px; z-index: 1000; box-shadow: 0 0 35px var(--accent-color); text-align: center; backdrop-filter: blur(18px);
        }
        .video-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 15px; max-height: 380px; overflow-y: auto; margin: 15px 0; }
        .video-box { background: rgba(0,0,0,0.6); border: 2px solid var(--accent-color); border-radius: 8px; padding: 5px; }
        video { width: 100%; height: 160px; object-fit: cover; border-radius: 6px; background: #000; }
        .device-row { display: flex; justify-content: space-between; align-items: center; font-size: 12px; padding: 6px 0; border-bottom: 1px solid rgba(255,255,255,0.2); }
        #appContainer { display: none; width: 100%; height: 100vh; }
        #authOverlay, #pendingOverlay, #verifyOverlay {
            position: fixed; top: 0; left: 0; width: 100%; height: 100vh;
            background: rgba(10, 14, 23, 0.96); z-index: 9999; display: flex; flex-direction: column;
            justify-content: center; align-items: center; text-align: center; padding: 20px;
        }
        #pendingOverlay, #verifyOverlay { display: none; }
        .chat-image-preview { max-width: 100%; max-height: 200px; border-radius: 6px; margin-top: 5px; border: 2px solid var(--accent-color); display: block; }

        @media (max-width: 768px) {
            body { flex-direction: column; height: 100vh; overflow: hidden; }
            #appContainer { display: flex; flex-direction: column; height: 100vh; width: 100%; }
            .right-pane {
                order: 1; width: 100%; height: 52vh; min-height: 52vh; max-height: 52vh;
                border: none; border-bottom: 3px solid var(--accent-color);
                display: flex; flex-direction: column; padding: 10px; box-sizing: border-box; overflow: hidden;
            }
            #historyStream { flex: 1; overflow-y: auto; -webkit-overflow-scrolling: touch; margin-top: 5px; margin-bottom: 5px; }
            .left-pane {
                order: 2; width: 100%; height: 48vh; min-height: 48vh; max-height: 48vh;
                border: none; overflow-y: auto; -webkit-overflow-scrolling: touch; padding: 10px; box-sizing: border-box;
            }
            #videoPopup { width: 90%; left: 5%; top: 5%; }
        }
    </style>
</head>
<body>
    <div id="authOverlay">
        <h2 style="color: var(--accent-color); text-shadow: 0 0 10px var(--accent-color);">WMA QQ - Private & Group Anime Hub</h2>
        <p style="max-width: 450px; color: #cbd5e1; margin: 15px 0;">သင့် Email နှင့် Password ဖြင့် ဝင်ရောက်ပါ</p>
        <div style="background: rgba(255,255,255,0.08); padding: 20px; border-radius: 10px; border: 2px solid var(--accent-color); width: 320px; box-shadow: 0 0 20px var(--accent-color);">
            <input type="email" id="loginEmail" placeholder="Email (e.g. user@gmail.com)">
            <input type="password" id="loginPassword" placeholder="Password">
            <div style="text-align: left; font-size: 12px; color: #cbd5e1; margin: 5px 0;">
                <input type="checkbox" id="showPasswordToggle" onclick="togglePasswordVisibility()" style="width: auto; margin-right: 5px; accent-color: var(--accent-color);"> Password ပြရန်
            </div>
            <div style="text-align: left; font-size: 12px; color: #cbd5e1; margin: 5px 0 10px 0;">
                <input type="checkbox" id="rememberMeToggle" style="width: auto; margin-right: 5px; accent-color: var(--accent-color);"> Remember Me
            </div>
            <button onclick="loginUser()" style="background: var(--accent-color); margin-top: 5px;">Login</button>
            <button onclick="signupUser()" style="background: #3b82f6; margin-top: 5px;">Sign Up</button>
            <button onclick="openForgetPassword()" style="background: #ca8a04; margin-top: 5px; font-size: 12px;">Forget Password?</button>
            <div id="loginError" style="color: #f87171; font-size: 12px; margin-top: 10px;"></div>
        </div>
    </div>

    <div id="verifyOverlay">
        <h2 style="color: var(--accent-color);">Email Verification Required</h2>
        <p style="max-width: 400px; color: #cbd5e1; margin: 15px 0;">သင့် Email ထံသို့ ပို့လိုက်သော ဂဏန်း ၆ လုံးပါ Verification Code ကို ထည့်ပါ</p>
        <div style="background: rgba(255,255,255,0.08); padding: 20px; border-radius: 10px; border: 2px solid var(--accent-color); width: 320px;">
            <input type="text" id="verificationCodeInput" placeholder="6-digit code" maxlength="6" style="text-align:center; font-size:18px; letter-spacing:4px; font-weight:bold;">
            <button onclick="submitVerificationCode()" style="background: var(--accent-color); margin-top: 10px;">Verify Code</button>
            <div id="verifyError" style="color: #f87171; font-size: 12px; margin-top: 10px;"></div>
        </div>
    </div>

    <div id="pendingOverlay">
        <h2 id="overlayTitle" style="color: var(--accent-color);">WMA QQ - Device Verification Required</h2>
        <p id="overlayDesc" style="max-width: 500px; color: #cbd5e1; margin: 15px 0;">သင့် Device သည် Admin ထံမှ Approve အတည်ပြုချက် ရယူရန် လိုအပ်နေပါသည်။</p>
        <div style="background: rgba(255,255,255,0.08); padding: 15px; border-radius: 10px; border: 2px solid var(--accent-color); margin-bottom: 15px; width: 320px;">
            <input type="text" id="overlayDeviceId" readonly style="text-align:center; font-weight:bold;">
            <div id="overlayStatus" style="font-size: 14px; color: #facc15; font-weight: bold; margin-top: 10px;">Status: Pending Approval ⏳</div>
        </div>
        <button onclick="logoutUser()" style="background: #dc2626; width: auto; padding: 8px 15px;">Logout</button>
    </div>

    <div id="appContainer">
        <div id="videoPopup">
            <h3>WMA QQ - Anime Video Conference</h3>
            <div id="callerInfo" style="margin-bottom: 10px; font-weight: bold; color: var(--accent-color);"></div>
            <div class="video-grid" id="videoGridContainer">
                <div class="video-box"><video id="localVideo" autoplay muted playsinline></video><div>Local Stream (You)</div></div>
            </div>
            <div class="actions" style="margin-top: 15px; display: flex; justify-content: center; gap: 10px; flex-wrap: wrap;">
                <button onclick="stopConference()" style="background: #dc2626; width: auto; padding: 8px 15px;">End Conference</button>
                <button onclick="toggleMuteSpeaker()" id="muteSpeakerBtn" style="background: #ca8a04; width: auto; padding: 8px 15px;">Mute Speaker</button>
                <button onclick="toggleMuteCamera()" id="muteCameraBtn" style="background: #2563eb; width: auto; padding: 8px 15px;">Mute Camera</button>
                <button onclick="closePopup()" style="background: #475569; width: auto; padding: 8px 15px;">Close</button>
            </div>
        </div>

        <div class="right-pane" id="rightPane">
            <div id="topNotificationBanner"></div>
            <button id="resetBtn" onclick="resetStorage()">Reset Storage</button>
            
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap;">
                <h3 id="currentChatRoomTitle" style="color: var(--accent-color); text-shadow: 0 0 8px var(--accent-color); margin: 0 0 10px 0;">WMA QQ - Main Group Chat</h3>
                <button id="goToMainChatBtn" onclick="switchToMainChat()">Go to Main Chat Room</button>
            </div>

            <div style="margin-bottom: 8px;">
                <select id="privateChatSwitcher" onchange="switchPrivateChatFromDropdown(this)" style="padding: 6px; font-size: 12px; margin: 0;">
                    <option value="main_group">💬 Switch Chat Rooms / Private List...</option>
                </select>
            </div>

            <div id="historyStream"></div>
        </div>

        <div class="left-pane">
            <h2 style="color: var(--accent-color); text-shadow: 0 0 8px var(--accent-color);">WMA QQ Control Panel</h2>
            <div style="margin-bottom: 10px; font-size: 13px; color: #cbd5e1;">Logged in as: <b id="currentLoggedInName" style="color:var(--accent-color);"></b> <button onclick="logoutUser()" style="width: auto; padding: 2px 8px; font-size: 11px; margin-left: 10px; background:#dc2626;">Logout</button></div>
            
            <div class="card" style="border-color: #22c55e;">
                <h4 style="color: #22c55e;">🟢 Online Users List</h4>
                <div id="onlineUsersListContainer" style="max-height: 120px; overflow-y: auto; font-size: 12px; color: #cbd5e1;"></div>
            </div>

            <div class="card">
                <h4 style="color: var(--accent-color);">Dynamic Anime Themes</h4>
                <button onclick="autoGenerateAnimeTheme()">Randomize Anime Character Theme</button>
            </div>

            <div class="card" id="adminControlCard" style="display: none; border-color: #f59e0b;">
                <h4 style="color: #f59e0b;">👑 Admin Control Panel</h4>
                <div style="font-size: 12px; color: #facc15; margin-bottom: 5px;">Active & Pending Devices List:</div>
                <div id="activeDeviceList" style="max-height: 180px; overflow-y: auto; background: rgba(0,0,0,0.4); padding: 8px; border-radius: 6px; border: 1px solid var(--accent-color);"></div>
            </div>

            <div class="card">
                <h4 style="color: var(--accent-color);">Function 1: Voice Message (Max 3s)</h4>
                <button id="recBtn" onclick="toggleRecordVoice()">Record Voice (3s)</button>
                <div id="voiceOptions" style="display:none; margin-top: 10px;">
                    <button onclick="sendVoice('48 Hours')" style="background: var(--accent-color);">Send Voice (48h Auto-Delete)</button>
                </div>
            </div>

            <div class="card">
                <h4 style="color: var(--accent-color);">Function 2: Video Call</h4>
                <button onclick="triggerVideoCall()" style="background: #16a34a;">Call Active Users</button>
            </div>

            <div class="card">
                <h4 style="color: var(--accent-color);">Function 3: Text & Universal Equation</h4>
                <textarea id="textContent" rows="3" placeholder="Write text or equation (e.g. 50 * 20 =)" oninput="solveEquation(this)"></textarea>
                <button onclick="sendText()">Send Text (48h Auto-Delete)</button>
            </div>

            <div class="card">
                <h4 style="color: var(--accent-color);">Function 4: Original File or Image (48h Auto-Delete)</h4>
                <input type="file" id="fileInput" onchange="handleFileSelected(this)">
                <button id="sendFileBtn" onclick="sendFile()" disabled style="opacity: 0.5;">Send File / Image</button>
            </div>
        </div>
    </div>

    <script>
        const socket = io();
        let currentRoom = 'main_group';
        let mediaRecorder;
        let audioChunks = [];
        let localStream = null;
        let peerConnections = {};
        let selectedFileBase64 = null;
        let selectedFileName = '';
        let isSpeakerMuted = false;
        let isCameraMuted = false;
        let wakeLock = null;
        let activeDevicesCache = [];
        let knownPrivateRooms = new Set();
        let notificationTimeout = null;
        let pendingVerificationEmail = '';

        if ('serviceWorker' in navigator) {
            window.addEventListener('load', () => {
                navigator.serviceWorker.register('/sw.js').catch(err => console.log(err));
            });
        }

        setInterval(() => {
            fetch('/ping').catch(e => {});
        }, 300000);

        async function requestWakeLock() {
            try {
                if ('wakeLock' in navigator) {
                    wakeLock = await navigator.wakeLock.request('screen');
                    wakeLock.addEventListener('release', () => { wakeLock = null; });
                }
            } catch (err) {}
        }
        requestWakeLock();

        if ('Notification' in window && Notification.permission !== 'granted') {
            Notification.requestPermission();
        }

        const servers = { iceServers: [{ urls: 'stun:stun.l.google.com:19302' }, { urls: 'stun:stun1.l.google.com:19302' }] };

        const animeThemes = [
            { name: "Naruto Uzumaki", bg: "https://images.unsplash.com/photo-1578632767115-351597cf2477?auto=format&fit=crop&w=1920&q=80", char: "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?auto=format&fit=crop&w=1920&q=80", accent: "#f97316" },
            { name: "Gojo Satoru", bg: "https://images.unsplash.com/photo-1607604276583-eef5d076aa5f?auto=format&fit=crop&w=1920&q=80", char: "https://images.unsplash.com/photo-1579783902614-a3fb3927b675?auto=format&fit=crop&w=1920&q=80", accent: "#3b82f6" },
            { name: "Wei Wuxian (MDZS)", bg: "https://images.unsplash.com/photo-1534447677768-be436bb09401?auto=format&fit=crop&w=1920&q=80", char: "https://images.unsplash.com/photo-1563089145-599997674d42?auto=format&fit=crop&w=1920&q=80", accent: "#a855f7" },
            { name: "Nezuko Kamado", bg: "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?auto=format&fit=crop&w=1920&q=80", char: "https://images.unsplash.com/photo-1578632767115-351597cf2477?auto=format&fit=crop&w=1920&q=80", accent: "#ec4899" }
        ];

        function autoGenerateAnimeTheme() {
            const theme = animeThemes[Math.floor(Math.random() * animeThemes.length)];
            document.documentElement.style.setProperty('--accent-color', theme.accent);
            document.documentElement.style.setProperty('--bg-image', `url('${theme.bg}')`);
            document.documentElement.style.setProperty('--char-fg-image', `url('${theme.char}')`);
            localStorage.setItem('wma_current_theme', JSON.stringify(theme));
        }

        window.addEventListener('DOMContentLoaded', () => {
            const savedTheme = localStorage.getItem('wma_current_theme');
            if (savedTheme) {
                try {
                    const theme = JSON.parse(savedTheme);
                    document.documentElement.style.setProperty('--accent-color', theme.accent);
                    document.documentElement.style.setProperty('--bg-image', `url('${theme.bg}')`);
                    if(theme.char) {
                        document.documentElement.style.setProperty('--char-fg-image', `url('${theme.char}')`);
                    }
                } catch(e) {}
            }
        });

        function togglePasswordVisibility() {
            const pwd = document.getElementById('loginPassword');
            const showToggle = document.getElementById('showPasswordToggle');
            pwd.type = showToggle.checked ? 'text' : 'password';
        }

        function getDeviceId() {
            let devId = localStorage.getItem('wma_device_id');
            if (!devId) {
                devId = 'device_' + Math.random().toString(36).substring(2, 15);
                localStorage.setItem('wma_device_id', devId);
            }
            return devId;
        }

        function getUserDisplayName(email, deviceId) {
            if (email === 'officialwinmyat@gmail.com') return 'Admin';
            let storedName = localStorage.getItem('wma_custom_username_' + email);
            if (storedName) return storedName;
            return deviceId || email.split('@')[0];
        }

        window.addEventListener('DOMContentLoaded', () => {
            const savedEmail = localStorage.getItem('wma_remember_email');
            const savedToken = localStorage.getItem('wma_remember_token');
            const devId = getDeviceId();

            if (savedEmail && savedToken) {
                fetch('/check_remember', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({email: savedEmail, token: savedToken, device_id: devId})
                })
                .then(res => res.json())
                .then(data => {
                    if (data.logged_in) {
                        initAppSession(data.email, data.is_admin);
                    } else {
                        checkNormalSession();
                    }
                });
            } else {
                checkNormalSession();
            }
        });

        function checkNormalSession() {
            fetch('/check_session')
            .then(res => res.json())
            .then(data => {
                if (data.logged_in) {
                    initAppSession(data.email, data.is_admin);
                } else {
                    document.getElementById('authOverlay').style.display = 'flex';
                }
            });
        }

        function initAppSession(email, isAdmin) {
            document.getElementById('authOverlay').style.display = 'none';
            document.getElementById('verifyOverlay').style.display = 'none';
            document.getElementById('appContainer').style.display = 'flex';
            const devId = getDeviceId();
            document.getElementById('currentLoggedInName').innerText = getUserDisplayName(email, devId);
            if (isAdmin) {
                document.getElementById('adminControlCard').style.display = 'block';
                document.getElementById('resetBtn').style.display = 'block';
            }
            registerDeviceWithServer(email);
            loadChatHistory(currentRoom);
        }

        function loginUser() {
            const email = document.getElementById('loginEmail').value;
            const password = document.getElementById('loginPassword').value;
            const remember = document.getElementById('rememberMeToggle').checked;
            const devId = getDeviceId();

            fetch('/login', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({email, password, remember, device_id: devId})
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    if (remember && data.remember_token) {
                        localStorage.setItem('wma_remember_email', email);
                        localStorage.setItem('wma_remember_token', data.remember_token);
                    }
                    location.reload();
                } else {
                    document.getElementById('loginError').innerText = data.error;
                }
            });
        }

        function signupUser() {
            const email = document.getElementById('loginEmail').value;
            const password = document.getElementById('loginPassword').value;
            const devId = getDeviceId();

            fetch('/signup', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({email, password, device_id: devId})
            })
            .then(res => res.json())
            .then(data => {
                if (data.success && data.requires_verification) {
                    pendingVerificationEmail = email.trim().toLowerCase();
                    document.getElementById('authOverlay').style.display = 'none';
                    document.getElementById('verifyOverlay').style.display = 'flex';
                } else {
                    document.getElementById('loginError').innerText = data.error || "Signup error";
                }
            });
        }

        function submitVerificationCode() {
            const code = document.getElementById('verificationCodeInput').value.trim();
            const devId = getDeviceId();
            if (!code) return;

            fetch('/verify_code', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({email: pendingVerificationEmail, code: code, device_id: devId})
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    location.reload();
                } else {
                    document.getElementById('verifyError').innerText = data.error;
                }
            });
        }

        function openForgetPassword() {
            const email = prompt("Google Account (Email) ထည့်ပါ:");
            if (!email) return;
            const newPassword = prompt("Password အသစ်ထည့်ပါ:");
            if (!newPassword) return;

            fetch('/reset_password_google', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({email: email.trim().toLowerCase(), new_password: newPassword})
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) alert("Password အောင်မြင်စွာ ပြောင်းလဲပြီးပါပြီ။");
                else alert("Error: " + data.error);
            });
        }

        function logoutUser() {
            localStorage.removeItem('wma_remember_email');
            localStorage.removeItem('wma_remember_token');
            fetch('/logout', {method: 'POST'}).then(() => location.reload());
        }

        function registerDeviceWithServer(email) {
            const devId = getDeviceId();
            socket.emit('register_device', {device_id: devId, google_account: email});
            fetchDevices();
        }

        socket.on('device_status_update', () => { fetchDevices(); });
        socket.on('online_users_refresh', () => { fetchDevices(); });

        function fetchDevices() {
            fetch('/get_devices')
            .then(res => res.json())
            .then(devices => {
                const devId = getDeviceId();
                activeDevicesCache = devices;

                let currentDev = devices.find(d => d.device_id === devId);
                if (currentDev) {
                    if (currentDev.status === 'pending' && currentDev.account !== 'officialwinmyat@gmail.com') {
                        document.getElementById('pendingOverlay').style.display = 'flex';
                        document.getElementById('overlayDeviceId').value = devId;
                    } else if (currentDev.status === 'banned') {
                        document.getElementById('pendingOverlay').style.display = 'flex';
                        document.getElementById('overlayDeviceId').value = devId;
                        document.getElementById('overlayStatus').innerText = "Status: Banned ❌";
                    } else {
                        document.getElementById('pendingOverlay').style.display = 'none';
                    }
                }
                const listContainer = document.getElementById('activeDeviceList');
                if (listContainer) {
                    listContainer.innerHTML = '';
                    devices.forEach(d => {
                        let row = document.createElement('div');
                        row.className = 'device-row';
                        row.innerHTML = `<span><b>${d.device_id}</b> (${d.account}) [${d.status}]</span> 
                        <div>
                            <button onclick="adminAction('${d.device_id}', 'approved')" style="padding:2px 6px; font-size:10px; background:#16a34a; width:auto;">Approve</button>
                            <button onclick="adminAction('${d.device_id}', 'banned')" style="padding:2px 6px; font-size:10px; background:#ca8a04; width:auto;">Ban</button>
                            <button onclick="adminAction('${d.device_id}', 'remove')" style="padding:2px 6px; font-size:10px; background:#dc2626; width:auto;">Remove</button>
                        </div>`;
                        listContainer.appendChild(row);
                    });
                }
                
                updateOnlineUsersListUI();
                updateOnlineIndicators();
            });
        }

        function getDisplayNameForEmail(email) {
            let found = activeDevicesCache.find(d => d.account && d.account.trim().toLowerCase() === email.trim().toLowerCase());
            let devId = found ? found.device_id : email.split('@')[0];
            return getUserDisplayName(email, devId);
        }

        function updateOnlineUsersListUI() {
            const container = document.getElementById('onlineUsersListContainer');
            if (!container) return;
            container.innerHTML = '';
            let onlineEmails = [];
            activeDevicesCache.forEach(d => {
                if (d.account && (d.status === 'approved' || d.account === 'officialwinmyat@gmail.com')) {
                    onlineEmails.push(d.account.trim().toLowerCase());
                }
            });
            if (onlineEmails.length === 0) {
                container.innerHTML = '<i>No users online</i>';
                return;
            }
            onlineEmails.forEach(email => {
                let displayName = getDisplayNameForEmail(email);
                let div = document.createElement('div');
                div.style.padding = '4px 0';
                div.style.borderBottom = '1px solid rgba(255,255,255,0.1)';
                div.innerHTML = `<span class="online-dot"></span> <span class="user-name-tag" data-email="${email}" onclick="openPrivateChatWith('${email}')">${displayName}</span>`;
                container.appendChild(div);
            });
        }

        function updateOnlineIndicators() {
            document.querySelectorAll('.user-name-tag').forEach(tag => {
                const emailText = tag.getAttribute('data-email');
                if (emailText) {
                    let found = activeDevicesCache.find(d => d.account && d.account.trim().toLowerCase() === emailText.trim().toLowerCase());
                    const isOnline = found && (found.status === 'approved' || found.account === 'officialwinmyat@gmail.com');
                    let dot = tag.querySelector('.online-dot');
                    if (isOnline) {
                        if (!dot) {
                            dot = document.createElement('span');
                            dot.className = 'online-dot';
                            tag.appendChild(dot);
                        }
                    } else {
                        if (dot) dot.remove();
                    }
                }
            });
        }

        function adminAction(devId, action) {
            socket.emit('admin_device_action', {device_id: devId, action: action});
        }

        function loadChatHistory(roomName) {
            socket.emit('join_room', {room: roomName});
            fetch(`/get_history?room=${roomName}`)
            .then(res => res.json())
            .then(data => {
                const stream = document.getElementById('historyStream');
                stream.innerHTML = '';
                data.reverse().forEach(item => appendMessageToStream(item, false));
            });
        }

        function openPrivateChatWith(otherUserEmail) {
            const myEmail = localStorage.getItem('wma_remember_email') || '';
            const targetEmail = otherUserEmail.trim().toLowerCase();
            
            if (myEmail && myEmail.trim().toLowerCase() === targetEmail) {
                alert("သင်ကိုယ်တိုင်နှင့် Private Chat ဖွင့်၍မရပါ။");
                return;
            }

            let emails = [myEmail || 'user', targetEmail].sort();
            currentRoom = `private_${emails[0]}_${emails[1]}`;
            knownPrivateRooms.add(currentRoom);
            updatePrivateChatSwitcherDropdown();
            
            let targetDisplayName = getDisplayNameForEmail(targetEmail);
            document.getElementById('currentChatRoomTitle').innerText = `Private Chat: ${targetDisplayName}`;
            document.getElementById('goToMainChatBtn').style.display = 'block';
            
            loadChatHistory(currentRoom);
        }

        function switchToMainChat() {
            currentRoom = 'main_group';
            document.getElementById('currentChatRoomTitle').innerText = "WMA QQ - Main Group Chat";
            document.getElementById('goToMainChatBtn').style.display = 'none';
            document.getElementById('privateChatSwitcher').value = 'main_group';
            loadChatHistory(currentRoom);
        }

        function switchPrivateChatFromDropdown(selectElem) {
            const val = selectElem.value;
            if (val === 'main_group') {
                switchToMainChat();
            } else if (val.startsWith('private_')) {
                currentRoom = val;
                let parts = val.replace('private_', '').split('_');
                let myEmail = localStorage.getItem('wma_remember_email') || '';
                let otherEmail = parts[0] === myEmail ? parts[1] : parts[0];
                let otherDisplayName = getDisplayNameForEmail(otherEmail);
                document.getElementById('currentChatRoomTitle').innerText = `Private Chat: ${otherDisplayName}`;
                document.getElementById('goToMainChatBtn').style.display = 'block';
                loadChatHistory(currentRoom);
            }
        }

        function updatePrivateChatSwitcherDropdown() {
            const switcher = document.getElementById('privateChatSwitcher');
            if (!switcher) return;
            switcher.innerHTML = `<option value="main_group">💬 Main Group Chat</option>`;
            knownPrivateRooms.forEach(room => {
                let parts = room.replace('private_', '').split('_');
                let myEmail = localStorage.getItem('wma_remember_email') || '';
                let otherEmail = parts[0] === myEmail ? parts[1] : parts[0];
                let otherDisplayName = getDisplayNameForEmail(otherEmail);
                let opt = document.createElement('option');
                opt.value = room;
                opt.innerText = `🔒 Private: ${otherDisplayName}`;
                if (room === currentRoom) opt.selected = true;
                switcher.appendChild(opt);
            });
        }

        socket.on('broadcast_message', data => {
            const myEmail = localStorage.getItem('wma_remember_email') || '';
            
            if (data.room.startsWith('private_')) {
                knownPrivateRooms.add(data.room);
                updatePrivateChatSwitcherDropdown();
                
                if (data.room !== currentRoom && data.user.trim().toLowerCase() !== myEmail.toLowerCase()) {
                    let senderName = getDisplayNameForEmail(data.user);
                    triggerTopLeftNotification(`${senderName} က သင့်ကို Private message ပို့နေပါသည်`);
                }
            } else if (data.room === 'main_group' && currentRoom !== 'main_group' && data.user.trim().toLowerCase() !== myEmail.toLowerCase()) {
                let senderName = getDisplayNameForEmail(data.user);
                triggerTopLeftNotification(`${senderName} က Main Chat မှာ message ပို့နေပါသည်`);
            }

            if (data.room === currentRoom) {
                appendMessageToStream(data, true);
            }
        });

        function triggerTopLeftNotification(text) {
            const banner = document.getElementById('topNotificationBanner');
            if (!banner) return;
            banner.innerText = text;
            banner.style.display = 'block';
            if (notificationTimeout) clearTimeout(notificationTimeout);
            notificationTimeout = setTimeout(() => {
                banner.style.display = 'none';
            }, 2000);
        }

        socket.on('message_deleted', data => {
            const el = document.getElementById('msg-box-' + data.id);
            if (el) el.remove();
        });

        function appendMessageToStream(item, triggerNotification = false) {
            const stream = document.getElementById('historyStream');
            const div = document.createElement('div');
            div.className = 'history-item';
            div.id = 'msg-box-' + item.id;
            
            const cleanUserEmail = item.user.trim().toLowerCase();
            let found = activeDevicesCache.find(d => d.account && d.account.trim().toLowerCase() === cleanUserEmail);
            const isOnline = found && (found.status === 'approved' || found.account === 'officialwinmyat@gmail.com');
            let dotHtml = isOnline ? `<span class="online-dot"></span>` : ``;
            let displayName = getDisplayNameForEmail(item.user);
            let userHtml = `<span class="user-name-tag" data-email="${item.user}" onclick="openPrivateChatWith('${item.user}')">${displayName}${dotHtml}</span>`;
            let contentHtml = '';
            
            if (item.type === 'text') {
                contentHtml = `<div><b>${userHtml}:</b> ${item.content}</div>`;
            } else if (item.type === 'voice') {
                contentHtml = `<div><b>${userHtml} [Voice]:</b><audio controls src="${item.content}" style="width:100%; margin-top:5px;"></audio></div>`;
            } else if (item.type === 'file') {
                if (item.filename && (item.filename.endsWith('.jpg') || item.filename.endsWith('.png') || item.filename.endsWith('.jpeg') || item.filename.endsWith('.gif'))) {
                    contentHtml = `<div><b>${userHtml} [Image]:</b><br><img src="${item.content}" class="chat-image-preview"></div>`;
                } else {
                    contentHtml = `<div><b>${userHtml} [File]:</b> <a href="${item.content}" download="${item.filename || 'download'}" style="color:var(--accent-color);">${item.filename || 'Download File'}</a></div>`;
                }
            } else if (item.type === 'videocall_alert') {
                contentHtml = `<div><b>🚨 Anime Video Call Alert:</b> ${displayName} has started a video call!
                    <div style="margin-top: 8px; display: flex; gap: 8px;">
                        <button onclick="acceptVideoCall('${item.user}')" style="background:#16a34a; padding:4px 12px; font-size:12px; width:auto; border-radius:4px;">Accept</button>
                        <button onclick="deleteMessageItem(${item.id})" style="background:#dc2626; padding:4px 12px; font-size:12px; width:auto; border-radius:4px;">Delete</button>
                    </div>
                </div>`;
            }
            
            let actionButtons = '';
            if (item.type === 'text') {
                actionButtons = `<div class="msg-actions"><button onclick="copyTextContent('${encodeURIComponent(item.content)}')">Copy</button><button onclick="deleteMessageItem(${item.id})" style="background:#dc2626;">Delete</button></div>`;
            } else if (item.type === 'voice' || item.type === 'file') {
                actionButtons = `<div class="msg-actions"><button onclick="saveToDevice('${item.content}', '${item.filename || 'media_file'}')">Save</button><button onclick="deleteMessageItem(${item.id})" style="background:#dc2626;">Delete</button></div>`;
            } else if (item.type === 'videocall_alert') {
                actionButtons = `<div class="msg-actions"><button onclick="deleteMessageItem(${item.id})" style="background:#dc2626;">Delete</button></div>`;
            }
            
            div.innerHTML = contentHtml + (item.type !== 'videocall_alert' ? actionButtons : '') + `<div style="font-size:10px; color:#94a3b8; margin-top:4px;">${item.timestamp}</div>`;
            stream.appendChild(div);
            stream.scrollTop = stream.scrollHeight;

            let myEmail = localStorage.getItem('wma_remember_email') || '';
            if (triggerNotification && 'Notification' in window && Notification.permission === 'granted' && item.user.trim().toLowerCase() !== myEmail.toLowerCase()) {
                new Notification(`WMA QQ - Message from ${displayName}`, {
                    body: item.type === 'text' ? item.content : `New ${item.type} received!`,
                    icon: 'https://images.unsplash.com/photo-1578632767115-351597cf2477?auto=format&fit=crop&w=120&q=80'
                });
            }
        }

        function copyTextContent(encodedText) {
            navigator.clipboard.writeText(decodeURIComponent(encodedText));
        }

        function saveToDevice(dataUrl, filename) {
            const a = document.createElement('a');
            a.href = dataUrl;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
        }

        function deleteMessageItem(id) {
            socket.emit('delete_message_item', {id: id, room: currentRoom});
        }

        function toggleRecordVoice() {
            const btn = document.getElementById('recBtn');
            const options = document.getElementById('voiceOptions');
            if (btn.innerText.includes("Record")) {
                audioChunks = [];
                navigator.mediaDevices.getUserMedia({audio: true}).then(stream => {
                    mediaRecorder = new MediaRecorder(stream);
                    mediaRecorder.ondataavailable = e => audioChunks.push(e.data);
                    mediaRecorder.onstop = () => {
                        const audioBlob = new Blob(audioChunks, {type: 'audio/mp3'});
                        const reader = new FileReader();
                        reader.onloadend = () => {
                            window.tempVoiceData = reader.result;
                            options.style.display = 'block';
                        };
                        reader.readAsDataURL(audioBlob);
                    };
                    mediaRecorder.start();
                    btn.innerText = "Stop Recording...";
                    setTimeout(() => {
                        if (mediaRecorder && mediaRecorder.state === 'recording') {
                            mediaRecorder.stop();
                            btn.innerText = "Record Voice (3s)";
                        }
                    }, 3000);
                });
            }
        }

        function sendVoice(storeType) {
            if (window.tempVoiceData) {
                let myEmail = localStorage.getItem('wma_remember_email') || 'user';
                socket.emit('new_message', {
                    user: myEmail,
                    type: 'voice',
                    content: window.tempVoiceData,
                    store: '48 Hours',
                    room: currentRoom
                });
                document.getElementById('voiceOptions').style.display = 'none';
                window.tempVoiceData = null;
            }
        }

        function solveEquation(textarea) {
            let val = textarea.value.trim();
            if (val.endsWith('=')) {
                try {
                    let expr = val.slice(0, -1);
                    let result = eval(expr);
                    textarea.value = val + ' ' + result;
                } catch(e) {}
            }
        }

        function sendText() {
            const content = document.getElementById('textContent').value;
            if (!content) return;
            let myEmail = localStorage.getItem('wma_remember_email') || 'user';
            socket.emit('new_message', {
                user: myEmail,
                type: 'text',
                content: content,
                store: '48 Hours',
                room: currentRoom
            });
            document.getElementById('textContent').value = '';
        }

        function handleFileSelected(input) {
            if (input.files && input.files[0]) {
                const file = input.files[0];
                selectedFileName = file.name;
                const reader = new FileReader();
                reader.onload = function(e) {
                    selectedFileBase64 = e.target.result;
                    document.getElementById('sendFileBtn').disabled = false;
                    document.getElementById('sendFileBtn').style.opacity = '1';
                };
                reader.readAsDataURL(file);
            }
        }

        function sendFile() {
            if (!selectedFileBase64) return;
            let myEmail = localStorage.getItem('wma_remember_email') || 'user';
            socket.emit('new_message', {
                user: myEmail,
                type: 'file',
                content: selectedFileBase64,
                filename: selectedFileName,
                store: '48 Hours',
                room: currentRoom
            });
            document.getElementById('fileInput').value = '';
            selectedFileBase64 = null;
            document.getElementById('sendFileBtn').disabled = true;
            document.getElementById('sendFileBtn').style.opacity = '0.5';
        }

        function triggerVideoCall() {
            let myEmail = localStorage.getItem('wma_remember_email') || 'user';
            socket.emit('trigger_video_call', {user: myEmail});
            socket.emit('new_message', {
                user: myEmail,
                type: 'videocall_alert',
                content: 'Triggered conference',
                store: '48 Hours',
                room: currentRoom
            });
            startConferenceUI(myEmail);
        }

        socket.on('incoming_video_call', data => {});

        function acceptVideoCall(callerUser) {
            startConferenceUI(callerUser);
            let myEmail = localStorage.getItem('wma_remember_email') || 'user';
            socket.emit('video_signal', {type: 'join_call', user: myEmail});
        }

        function startConferenceUI(callerName) {
            document.getElementById('videoPopup').style.display = 'block';
            let callerDisplayName = getDisplayNameForEmail(callerName);
            document.getElementById('callerInfo').innerText = `Conference Initiated by: ${callerDisplayName}`;
            navigator.mediaDevices.getUserMedia({video: true, audio: true})
            .then(stream => {
                localStream = stream;
                document.getElementById('localVideo').srcObject = stream;
                socket.emit('video_signal', {type: 'ready_peer', sender: socket.id});
            }).catch(err => alert("Camera permission error: " + err));
        }

        socket.on('video_signal_relay', async data => {
            const senderId = data.sender;
            if (senderId === socket.id) return;
            if (data.type === 'ready_peer' || data.type === 'join_call') {
                if (!localStream) return;
                let pc = createPeerConnection(senderId);
                let offer = await pc.createOffer();
                await pc.setLocalDescription(offer);
                socket.emit('video_signal', {type: 'offer', offer: offer, sender: socket.id, target: senderId});
            } else if (data.type === 'offer' && data.target === socket.id) {
                let pc = createPeerConnection(senderId);
                await pc.setRemoteDescription(new RTCSessionDescription(data.offer));
                let answer = await pc.createAnswer();
                await pc.setLocalDescription(answer);
                socket.emit('video_signal', {type: 'answer', answer: answer, sender: socket.id, target: senderId});
            } else if (data.type === 'answer' && data.target === socket.id) {
                let pc = peerConnections[senderId];
                if (pc) await pc.setRemoteDescription(new RTCSessionDescription(data.answer));
            } else if (data.type === 'candidate' && data.target === socket.id) {
                let pc = peerConnections[senderId];
                if (pc && data.candidate) await pc.addIceCandidate(new RTCIceCandidate(data.candidate));
            }
        });

        function createPeerConnection(remoteSocketId) {
            if (peerConnections[remoteSocketId]) return peerConnections[remoteSocketId];
            let pc = new RTCPeerConnection(servers);
            peerConnections[remoteSocketId] = pc;
            if (localStream) localStream.getTracks().forEach(track => pc.addTrack(track, localStream));
            pc.onicecandidate = event => {
                if (event.candidate) socket.emit('video_signal', {type: 'candidate', candidate: event.candidate, sender: socket.id, target: remoteSocketId});
            };
            pc.ontrack = event => {
                let gridContainer = document.getElementById('videoGridContainer');
                let remoteVideoId = 'remoteVideo_' + remoteSocketId;
                let existingBox = document.getElementById(remoteVideoId);
                if (!existingBox) {
                    let remoteBox = document.createElement('div');
                    remoteBox.className = 'video-box';
                    remoteBox.id = remoteVideoId;
                    remoteBox.innerHTML = `<video autoplay playsinline></video><div>Participant</div>`;
                    gridContainer.appendChild(remoteBox);
                    existingBox = remoteBox;
                }
                let videoElement = existingBox.querySelector('video');
                if (videoElement && event.streams[0]) videoElement.srcObject = event.streams[0];
            };
            return pc;
        }

        function toggleMuteSpeaker() {
            if (!localStream) return;
            isSpeakerMuted = !isSpeakerMuted;
            localStream.getAudioTracks().forEach(track => { track.enabled = !isSpeakerMuted; });
            const btn = document.getElementById('muteSpeakerBtn');
            btn.innerText = isSpeakerMuted ? "Unmute Speaker" : "Mute Speaker";
            btn.style.background = isSpeakerMuted ? "#dc2626" : "#ca8a04";
        }

        function toggleMuteCamera() {
            if (!localStream) return;
            isCameraMuted = !isCameraMuted;
            localStream.getVideoTracks().forEach(track => { track.enabled = !isCameraMuted; });
            const btn = document.getElementById('muteCameraBtn');
            btn.innerText = isCameraMuted ? "Unmute Camera" : "Mute Camera";
            btn.style.background = isCameraMuted ? "#dc2626" : "#2563eb";
        }

        function stopConference() {
            if (localStream) {
                localStream.getTracks().forEach(track => track.stop());
                localStream = null;
            }
            for (let id in peerConnections) { peerConnections[id].close(); }
            peerConnections = {};
            let gridContainer = document.getElementById('videoGridContainer');
            gridContainer.innerHTML = '<div class="video-box"><video id="localVideo" autoplay muted playsinline></video><div>Local Stream (You)</div></div>';
            closePopup();
        }

        function closePopup() { document.getElementById('videoPopup').style.display = 'none'; }

        function resetStorage() {
            if (confirm("Are you sure you want to reset all storage?")) socket.emit('reset_storage');
        }

        socket.on('storage_reset', () => {
            document.getElementById('historyStream').innerHTML = '';
            alert("Storage has been reset.");
        });
    </script>
</body>
</html>
"""

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)

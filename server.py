import os
import sqlite3
import random
import requests
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template_string, session, send_file

# Python compatibility fix for gevent
import sys
from gevent import monkey
try:
    monkey.patch_all(ssl=False)
except Exception:
    pass

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "wemeet_secure_secret_key_123")

from flask_socketio import SocketIO, emit
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

# MasterKey Obfuscation & License partitioning (4 parts hidden for security)
_MK_P1 = "852"
_MK_P2 = "456"
def _get_master_key():
    return _MK_P1 + _MK_P2

def _verify_wemeet_license(email_str):
    p1 = "official"
    p2 = "winmyat"
    p3 = "@gmail"
    p4 = ".com"
    return email_str.strip().lower() == (p1 + p2 + p3 + p4)

def init_db():
    conn = sqlite3.connect('wemeet_private.db')
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
            is_verified INTEGER DEFAULT 0,
            account_duration TEXT DEFAULT '3 months',
            signup_time DATETIME,
            status TEXT DEFAULT 'pending',
            username TEXT,
            age INTEGER,
            sex TEXT,
            country TEXT,
            province TEXT,
            city TEXT,
            pictures TEXT,
            profile_picture TEXT,
            received_gifts TEXT,
            purchased_gifts TEXT,
            redeemed_gifts TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def clean_expired_history():
    try:
        conn = sqlite3.connect('wemeet_private.db')
        cursor = conn.cursor()
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute('DELETE FROM history WHERE expire_at < ? AND msg_type != "gift_txn"', (now_str,))
        conn.commit()
        conn.close()
    except Exception as e:
        print("Cleanup error:", e)

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

@app.route('/admin_login', methods=['POST'])
def admin_login():
    data = request.json
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    master_key = data.get('master_key', '').strip()
    
    expected_master_key = _get_master_key()
    
    if _verify_wemeet_license(email) and master_key == expected_master_key:
        session['user_email'] = email
        session['is_admin'] = True
        return jsonify({"success": True, "is_admin": True})
    return jsonify({"success": False, "error": "Master Key သို့မဟုတ် Admin အချက်အလက် မှားယွင်းနေပါသည်။"})

@app.route('/signup', methods=['POST'])
def signup():
    data = request.json
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    device_id = data.get('device_id', '')
    username = data.get('username', '').strip()
    
    if not email or not password or not username:
        return jsonify({"success": False, "error": "Email, Password နှင့် Username ထည့်ရန် လိုအပ်ပါသည်။"})
    
    if len(username) > 15:
        return jsonify({"success": False, "error": "User name သည် 15 လုံးထက် မပိုရပါ။"})

    try:
        conn = sqlite3.connect('wemeet_private.db')
        cursor = conn.cursor()
        
        cursor.execute('SELECT id FROM users WHERE username = ? AND email != ?', (username, email))
        if cursor.fetchone():
            conn.close()
            return jsonify({"success": False, "error": "ဤ User name မှာ အခြားသူသုံးပြီးသား ဖြစ်နေပါသည်။"})

        cursor.execute('SELECT status FROM devices WHERE device_id = ?', (device_id,))
        dev_row = cursor.fetchone()
        if dev_row and dev_row[0] == 'banned':
            conn.close()
            return jsonify({"success": False, "error": "ဤ Device အား Ban ထားပါသဖြင့် Sign up လုပ်၍ မရပါ။"})
            
        cursor.execute('SELECT id, is_verified, status FROM users WHERE email = ?', (email,))
        existing = cursor.fetchone()
        
        now = datetime.now()
        is_admin_email = _verify_wemeet_license(email)
        
        if existing:
            if existing[1] == 1 and existing[2] == 'verified':
                conn.close()
                return jsonify({"success": False, "error": "ဤ Email ဖြင့် အကောင့်ရှိပြီးသား ဖြစ်ပါသည်။ Login ဝင်ပါ။"})
            else:
                default_code = _get_master_key() if is_admin_email else "".join([str(random.randint(0, 9)) for _ in range(6)])
                cursor.execute('UPDATE users SET password = ?, device_id = ?, username = ?, signup_time = ?, verification_code = ?, status = "pending" WHERE email = ?', (password, device_id, username, now, default_code, email))
        else:
            default_code = _get_master_key() if is_admin_email else "".join([str(random.randint(0, 9)) for _ in range(6)])
            cursor.execute('INSERT INTO users (email, password, device_id, username, is_verified, account_duration, signup_time, verification_code, status) VALUES (?, ?, ?, ?, 0, "3 months", ?, ?, "pending")', (email, password, device_id, username, now, default_code))
        
        conn.commit()
        conn.close()
            
        return jsonify({"success": True, "requires_verification": True, "is_admin_email": is_admin_email})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/verify_code', methods=['POST'])
def verify_code():
    data = request.json
    email = data.get('email', '').strip().lower()
    code = data.get('code', '').strip()
    
    conn = sqlite3.connect('wemeet_private.db')
    cursor = conn.cursor()
    cursor.execute('SELECT signup_time, verification_code FROM users WHERE email = ?', (email,))
    row = cursor.fetchone()
    
    if row:
        assigned_code = row[1]
        is_admin_email = _verify_wemeet_license(email)
        
        # If admin email and masterkey entered, or standard matching code
        if (is_admin_email and code == _get_master_key()) or (assigned_code and assigned_code == code):
            cursor.execute('UPDATE users SET is_verified = 1, status = "verified" WHERE email = ?', (email,))
            conn.commit()
            conn.close()
            
            session['user_email'] = email
            session['is_admin'] = is_admin_email
            return jsonify({"success": True, "is_admin": is_admin_email})
            
    conn.close()
    return jsonify({"success": False, "error": "Verification Code သို့မဟုတ် Master Key မှားယွင်းနေပါသည်။"})

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    remember = data.get('remember', False)
    device_id = data.get('device_id', '')
    
    conn = sqlite3.connect('wemeet_private.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT password, is_verified, device_id, account_duration, status FROM users WHERE email = ?', (email,))
    row = cursor.fetchone()
    
    if row:
        stored_password, is_verified, stored_device_id, account_duration, user_status = row
        if user_status == 'banned':
            conn.close()
            return jsonify({"success": False, "error": "ဤအကောင့်အား Ban ထားပါသည်။"})
        if is_verified == 0 or user_status != 'verified':
            conn.close()
            return jsonify({"success": False, "error": "အကောင့်ကို Code ဖြင့် အတည်ပြုပြီးသား မရှိသေးပါ။"})
            
        is_admin = _verify_wemeet_license(email)
        if stored_password == password and (stored_device_id == device_id or is_admin):
            session['user_email'] = email
            session['is_admin'] = is_admin
            
            token = ""
            if remember:
                token = f"token_{email}_{device_id}"
                cursor.execute('UPDATE users SET remember_token = ? WHERE email = ?', (token, email))
                conn.commit()
            
            conn.close()
            return jsonify({"success": True, "is_admin": is_admin, "remember_token": token, "account_duration": account_duration})
        else:
            conn.close()
            return jsonify({"success": False, "error": "Password သို့မဟုတ် Device ID မမှန်ကန်ပါ။"})
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
        
    conn = sqlite3.connect('wemeet_private.db')
    cursor = conn.cursor()
    cursor.execute('SELECT remember_token, device_id, account_duration, status FROM users WHERE email = ?', (email,))
    row = cursor.fetchone()
    conn.close()
    
    is_admin = _verify_wemeet_license(email)
    if row and row[0] == token and (row[1] == device_id or is_admin) and row[3] != 'banned':
        session['user_email'] = email
        session['is_admin'] = is_admin
        return jsonify({"logged_in": True, "email": email, "is_admin": is_admin, "account_duration": row[2]})
    
    return jsonify({"logged_in": False})

@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({"success": True})

@app.route('/check_session', methods=['GET'])
def check_session():
    if 'user_email' in session:
        email = session['user_email']
        is_admin = _verify_wemeet_license(email)
        session['is_admin'] = is_admin
        
        conn = sqlite3.connect('wemeet_private.db')
        cursor = conn.cursor()
        cursor.execute('SELECT account_duration, status FROM users WHERE email = ?', (email,))
        row = cursor.fetchone()
        conn.close()
        
        if row and row[1] == 'banned':
            session.clear()
            return jsonify({"logged_in": False})
            
        duration = row[0] if row else '3 months'
        return jsonify({"logged_in": True, "email": email, "is_admin": is_admin, "account_duration": duration})
    return jsonify({"logged_in": False})

@app.route('/get_admin_all_lists', methods=['GET'])
def get_admin_all_lists():
    if not session.get('is_admin'):
        return jsonify({"pending": [], "verified": [], "banned": []})
    
    conn = sqlite3.connect('wemeet_private.db')
    cursor = conn.cursor()
    cursor.execute('SELECT email, device_id, verification_code, account_duration, signup_time, username FROM users WHERE is_verified = 0 AND status != "banned" ORDER BY signup_time DESC')
    pending_rows = cursor.fetchall()
    
    cursor.execute('SELECT email, device_id, account_duration, signup_time, username FROM users WHERE is_verified = 1 AND status = "verified" ORDER BY signup_time DESC')
    verified_rows = cursor.fetchall()
    
    cursor.execute('SELECT email, device_id, account_duration, signup_time, username FROM users WHERE status = "banned" ORDER BY signup_time DESC')
    banned_rows = cursor.fetchall()
    conn.close()
    
    return jsonify({
        "pending": [{"email": r[0], "device_id": r[1], "verification_code": r[2] or '', "account_duration": r[3] or '3 months', "signup_time": r[4], "username": r[5]} for r in pending_rows],
        "verified": [{"email": r[0], "device_id": r[1], "account_duration": r[2] or '3 months', "signup_time": r[3], "username": r[4]} for r in verified_rows],
        "banned": [{"email": r[0], "device_id": r[1], "account_duration": r[2] or '3 months', "signup_time": r[3], "username": r[4]} for r in banned_rows]
    })

@app.route('/get_devices', methods=['GET'])
def get_devices():
    if 'user_email' not in session:
        return jsonify([])
    conn = sqlite3.connect('wemeet_private.db')
    cursor = conn.cursor()
    cursor.execute('SELECT d.device_id, d.google_account, d.status, d.last_active, u.username FROM devices d LEFT JOIN users u ON d.google_account = u.email')
    rows = cursor.fetchall()
    conn.close()
    
    devices = []
    for r in rows:
        devices.append({
            "device_id": r[0],
            "account": r[1],
            "status": 'approved' if _verify_wemeet_license(r[1] or '') else r[2],
            "active": True if r[3] else False,
            "username": r[4] or (r[1].split('@')[0] if r[1] else 'User')
        })
    return jsonify(devices)

@app.route('/get_history', methods=['GET'])
def get_history():
    room = request.args.get('room', 'main_group')
    clean_expired_history()
    conn = sqlite3.connect('wemeet_private.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, user_info, msg_type, content, filename, store_type, room, timestamp FROM history WHERE room = ? ORDER BY id DESC', (room,))
    rows = cursor.fetchall()
    conn.close()
    
    return jsonify([{
        "id": r[0], "user": r[1], "type": r[2], "content": r[3], "filename": r[4], "store": r[5], "room": r[6], "timestamp": r[7]
    } for r in rows])

@socketio.on('register_device')
def handle_register_device(data):
    dev_id = data.get('device_id')
    google_acc = session.get('user_email', data.get('google_account', ''))
    if not dev_id or not google_acc:
        return
        
    conn = sqlite3.connect('wemeet_private.db')
    cursor = conn.cursor()
    cursor.execute('SELECT status FROM devices WHERE device_id = ?', (dev_id,))
    row = cursor.fetchone()
    
    status = 'approved' if _verify_wemeet_license(google_acc) else ('approved' if row and row[0] == 'approved' else 'pending')
    
    if not row:
        cursor.execute('INSERT INTO devices (device_id, google_account, status, last_active) VALUES (?, ?, ?, ?)', (dev_id, google_acc, status, datetime.now()))
    else:
        cursor.execute('UPDATE devices SET google_account = ?, status = ?, last_active = ? WHERE device_id = ?', (google_acc, status, datetime.now(), dev_id))
    conn.commit()
    conn.close()
    socketio.emit('online_users_refresh')

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
    store = data.get('store', '48 Hours')
    room = data.get('room', 'main_group')
    
    now = datetime.now()
    expire_at = now + timedelta(hours=48)
        
    conn = sqlite3.connect('wemeet_private.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO history (user_info, msg_type, content, filename, store_type, room, expire_at, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                   (user, msg_type, content, filename, store, room, expire_at.strftime('%Y-%m-%d %H:%M:%S'), now.strftime('%Y-%m-%d %H:%M:%S')))
    msg_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    socketio.emit('broadcast_message', {
        "id": msg_id, "user": user, "type": msg_type, "content": content, "filename": filename, "store": store, "room": room, "timestamp": now.strftime('%Y-%m-%d %H:%M:%S')
    }, room=room)

@socketio.on('delete_message_item')
def handle_delete_message(data):
    msg_id = data.get('id')
    room = data.get('room', 'main_group')
    if msg_id:
        conn = sqlite3.connect('wemeet_private.db')
        cursor = conn.cursor()
        cursor.execute('DELETE FROM history WHERE id = ?', (msg_id,))
        conn.commit()
        conn.close()
        socketio.emit('message_deleted', {"id": msg_id}, room=room)

@socketio.on('reset_storage')
def handle_reset():
    if session.get('is_admin'):
        conn = sqlite3.connect('wemeet_private.db')
        cursor = conn.cursor()
        cursor.execute('DELETE FROM history')
        conn.commit()
        conn.close()
        socketio.emit('storage_reset')

HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>WeMeet - Private & Group Anime Chat Hub</title>
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
        }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0; padding: 0; background-color: var(--bg-color); background-image: var(--bg-image);
            background-size: cover; background-position: center; background-attachment: fixed;
            color: var(--text-color); display: flex; height: 100vh; overflow: hidden; position: relative;
        }
        .left-pane, .right-pane { position: relative; z-index: 2; }
        .left-pane { width: 50%; height: 100vh; overflow-y: auto; padding: 20px; box-sizing: border-box; background: var(--panel-bg); border-right: 3px solid var(--accent-color); backdrop-filter: blur(12px); }
        .right-pane { width: 50%; height: 100vh; display: flex; flex-direction: column; padding: 20px; box-sizing: border-box; background: var(--stream-bg); backdrop-filter: blur(12px); border-left: 3px solid var(--accent-color); }
        
        @media (max-width: 768px) {
            body { flex-direction: column; height: 100vh; overflow-y: auto; }
            .right-pane { order: 1; width: 100%; height: 55vh; border-bottom: 3px solid var(--accent-color); }
            .left-pane { order: 2; width: 100%; height: 45vh; }
        }

        .card { background: rgba(255,255,255,0.08); padding: 15px; border-radius: 10px; margin-bottom: 15px; border: 2px solid var(--accent-color); backdrop-filter: blur(8px); }
        input, textarea, select, button { width: 100%; padding: 10px; margin: 8px 0; border-radius: 6px; border: 2px solid var(--accent-color); background: rgba(15, 23, 42, 0.92); color: white; box-sizing: border-box; outline: none; }
        button { background: var(--accent-color); cursor: pointer; font-weight: bold; border: 2px solid #fff; transition: 0.2s; }
        button:hover { opacity: 0.9; transform: scale(1.02); }
        #historyStream { flex: 1; overflow-y: auto; background: var(--chat-bg); border: 2px solid var(--accent-color); border-radius: 10px; padding: 12px; box-sizing: border-box; margin-top: 10px; }
        .history-item { padding: 12px; margin-bottom: 10px; background: rgba(255,255,255,0.08); border-left: 6px solid var(--accent-color); border-radius: 8px; font-size: 13px; word-break: break-all; }
        .user-name-tag { color: var(--accent-color); cursor: pointer; text-decoration: underline; font-weight: bold; }
        .online-dot { display: inline-block; width: 9px; height: 9px; background-color: #22c55e; border-radius: 50%; margin-left: 5px; box-shadow: 0 0 6px #22c55e; }
        .offline-dot { display: inline-block; width: 9px; height: 9px; background-color: #94a3b8; border-radius: 50%; margin-left: 5px; }
        #authOverlay, #verifyOverlay { position: fixed; top: 0; left: 0; width: 100%; height: 100vh; background: rgba(10, 14, 23, 0.96); z-index: 9999; display: flex; flex-direction: column; justify-content: center; align-items: center; text-align: center; padding: 20px; }
        #verifyOverlay { display: none; }

        /* Floating Live Chat Box Styles */
        #floatingChatBox {
            position: fixed; bottom: 20px; right: 20px; width: 300px; max-height: 400px;
            background: rgba(15, 23, 42, 0.95); border: 2px solid var(--accent-color); border-radius: 12px;
            z-index: 10000; display: flex; flex-direction: column; box-shadow: 0 4px 20px rgba(0,0,0,0.5);
            backdrop-filter: blur(10px); overflow: hidden;
        }
        #floatingChatHeader {
            background: var(--accent-color); color: white; padding: 10px; font-weight: bold;
            display: flex; justify-content: space-between; align-items: center; cursor: pointer;
        }
        #floatingChatBody {
            flex: 1; height: 220px; overflow-y: auto; padding: 10px; font-size: 12px; text-align: left;
        }
    </style>
</head>
<body>
    <div id="authOverlay">
        <h2 style="color: var(--accent-color);">WeMeet - Private & Group Anime Hub</h2>
        <div id="userAuthBox" style="background: rgba(255,255,255,0.08); padding: 20px; border-radius: 10px; border: 2px solid var(--accent-color); width: 320px;">
            <input type="text" id="signupUsername" placeholder="User Name (max 15 letters)" maxlength="15">
            <input type="email" id="loginEmail" placeholder="Email">
            <input type="password" id="loginPassword" placeholder="Password">
            <button onclick="loginUser()" style="background: var(--accent-color);">Sign In</button>
            <button onclick="signupUser()" style="background: #3b82f6;">Sign Up</button>
            <div id="loginError" style="color: #f87171; font-size: 12px; margin-top: 10px;"></div>
        </div>
    </div>

    <div id="verifyOverlay">
        <h2 style="color: var(--accent-color);">Verification Required</h2>
        <p style="max-width: 400px; color: #cbd5e1; margin: 15px 0;">Admin ထံမှ verification code ကို ရယူပြီး ဖြည့်သွင်းပါ။ (Admin ဖြစ်ပါက MasterKey: 852456 ထည့်ပါ)</p>
        <div style="background: rgba(255,255,255,0.08); padding: 20px; border-radius: 10px; border: 2px solid var(--accent-color); width: 340px;">
            <input type="text" id="verificationCodeInput" placeholder="6-digit code or MasterKey" style="text-align:center; font-size:18px; letter-spacing:2px; font-weight:bold;">
            <button onclick="submitVerificationCode()" style="background: var(--accent-color);">Submit Verification Code</button>
            <div id="verifyError" style="color: #f87171; font-size: 12px; margin-top: 10px;"></div>
        </div>

        <!-- Temporary Floating Live Chat Box for Verification Screen -->
        <div id="floatingChatBox">
            <div id="floatingChatHeader" onclick="toggleFloatingChat()">
                <span>💬 Admin နှင့် တိုက်ရိုက်ဆွေးနွေးရန်</span>
                <span id="chatToggleIcon">▲</span>
            </div>
            <div id="floatingChatContentContainer">
                <div id="floatingChatBody">
                    <div style="color: #94a3b8; font-style: italic; margin-bottom: 5px;">Admin သို့ Verification Code တောင်းဆိုရန် ဤနေရာတွင် စာပို့နိုင်ပါသည်။</div>
                </div>
                <div style="padding: 8px; display: flex; gap: 5px; background: rgba(0,0,0,0.2);">
                    <input type="text" id="floatingMsgInput" placeholder="Type to Admin..." style="margin:0; padding:6px; font-size:12px;">
                    <button onclick="sendFloatingMsg()" style="margin:0; width:60px; padding:6px; font-size:12px;">Send</button>
                </div>
            </div>
        </div>
    </div>

    <div id="appContainer" style="display:none; width: 100%; height: 100vh;">
        <div class="right-pane">
            <h3 id="currentChatRoomTitle" style="color: var(--accent-color); margin: 0 0 10px 0;">WeMeet - Main Group Chat</h3>
            <button id="goToMainChatBtn" onclick="switchToMainChat()" style="display:none; background:#2563eb; padding:8px; border-radius:6px; cursor:pointer;">Go to Main Chat Room</button>
            <div id="historyStream"></div>
            <div style="display:flex; gap:10px; margin-top:10px;">
                <input type="text" id="textContent" placeholder="Type message..." style="margin:0;">
                <button onclick="sendText()" style="width:100px; margin:0;">Send</button>
            </div>
        </div>
        <div class="left-pane">
            <h2 style="color: var(--accent-color);">WeMeet Control Panel</h2>
            <div style="margin-bottom: 10px; font-size: 13px; color: #cbd5e1;">
                User: <b id="currentLoggedInName" style="color:var(--accent-color);"></b>
                <button onclick="logoutUser()" style="width: auto; padding: 2px 8px; font-size: 11px; margin-left: 10px; background:#dc2626;">Logout</button>
            </div>
            <div class="card" style="border-color: #22c55e;">
                <h4 style="color: #22c55e;">🟢 Online Users List</h4>
                <div id="onlineUsersListContainer" style="max-height: 150px; overflow-y: auto; font-size: 12px;"></div>
            </div>
        </div>
    </div>

    <script>
        const socket = io();
        let currentRoom = 'main_group';
        let activeDevicesCache = [];
        let pendingVerificationEmail = '';
        let chatMinimized = false;

        function getDeviceId() {
            let devId = localStorage.getItem('wemeet_device_id');
            if (!devId) {
                devId = 'device_' + Math.random().toString(36).substring(2, 15);
                localStorage.setItem('wemeet_device_id', devId);
            }
            return devId;
        }

        window.addEventListener('DOMContentLoaded', () => {
            fetch('/check_session')
            .then(res => res.json())
            .then(data => {
                if (data.logged_in) {
                    initAppSession(data.email, data.is_admin);
                } else {
                    document.getElementById('authOverlay').style.display = 'flex';
                }
            });
        });

        function initAppSession(email, isAdmin) {
            document.getElementById('authOverlay').style.display = 'none';
            document.getElementById('verifyOverlay').style.display = 'none';
            document.getElementById('appContainer').style.display = 'flex';
            document.getElementById('currentLoggedInName').innerText = email;
            registerDeviceWithServer(email);
            loadChatHistory(currentRoom);
        }

        function loginUser() {
            const email = document.getElementById('loginEmail').value;
            const password = document.getElementById('loginPassword').value;
            const devId = getDeviceId();

            fetch('/login', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({email, password, device_id: devId})
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) location.reload();
                else document.getElementById('loginError').innerText = data.error;
            });
        }

        function signupUser() {
            const username = document.getElementById('signupUsername').value.trim();
            const email = document.getElementById('loginEmail').value.trim().toLowerCase();
            const password = document.getElementById('loginPassword').value;
            const devId = getDeviceId();

            if (!username || !email || !password) {
                document.getElementById('loginError').innerText = "အားလုံး ဖြည့်ရန် လိုအပ်ပါသည်။";
                return;
            }

            fetch('/signup', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({username, email, password, device_id: devId})
            })
            .then(res => res.json())
            .then(data => {
                if (data.success && data.requires_verification) {
                    pendingVerificationEmail = email;
                    document.getElementById('authOverlay').style.display = 'none';
                    document.getElementById('verifyOverlay').style.display = 'flex';
                    socket.emit('join_room', {room: 'verification_support_room'});
                } else {
                    document.getElementById('loginError').innerText = data.error;
                }
            });
        }

        function submitVerificationCode() {
            const code = document.getElementById('verificationCodeInput').value.trim();
            fetch('/verify_code', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({email: pendingVerificationEmail, code: code})
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) location.reload();
                else document.getElementById('verifyError').innerText = data.error;
            });
        }

        function toggleFloatingChat() {
            chatMinimized = !chatMinimized;
            const body = document.getElementById('floatingChatContentContainer');
            const icon = document.getElementById('chatToggleIcon');
            if (chatMinimized) {
                body.style.display = 'none';
                icon.innerText = '▼';
            } else {
                body.style.display = 'block';
                icon.innerText = '▲';
            }
        }

        function sendFloatingMsg() {
            const input = document.getElementById('floatingMsgInput');
            const content = input.value.trim();
            if (!content) return;
            socket.emit('new_message', {
                user: pendingVerificationEmail || 'GuestUser',
                type: 'text', content: content, room: 'verification_support_room'
            });
            input.value = '';
        }

        socket.on('broadcast_message', data => {
            if (data.room === currentRoom) {
                appendMessage(data);
            }
            if (data.room === 'verification_support_room') {
                const chatBody = document.getElementById('floatingChatBody');
                if (chatBody) {
                    const div = document.createElement('div');
                    div.style.margin = '4px 0';
                    div.innerHTML = `<b>${data.user}:</b> ${data.content}`;
                    chatBody.appendChild(div);
                    chatBody.scrollTop = chatBody.scrollHeight;
                }
            }
        });

        function logoutUser() {
            fetch('/logout', {method: 'POST'}).then(() => location.reload());
        }

        function registerDeviceWithServer(email) {
            socket.emit('register_device', {device_id: getDeviceId(), google_account: email});
            fetchDevices();
        }

        socket.on('online_users_refresh', () => { fetchDevices(); });

        function fetchDevices() {
            fetch('/get_devices')
            .then(res => res.json())
            .then(devices => {
                activeDevicesCache = devices;
                updateOnlineUsersListUI();
            });
        }

        function updateOnlineUsersListUI() {
            const container = document.getElementById('onlineUsersListContainer');
            if (!container) return;
            container.innerHTML = '';
            activeDevicesCache.forEach(d => {
                let div = document.createElement('div');
                div.style.padding = '4px 0';
                div.style.borderBottom = '1px solid rgba(255,255,255,0.1)';
                let dotClass = d.active ? 'online-dot' : 'offline-dot';
                div.innerHTML = `<span class="${dotClass}"></span> <span class="user-name-tag" onclick="openPrivateChat('${d.account}')">${d.username}</span>`;
                container.appendChild(div);
            });
        }

        function openPrivateChat(otherEmail) {
            currentRoom = `private_room_${otherEmail}`;
            document.getElementById('currentChatRoomTitle').innerText = `Private Chat: ${otherEmail}`;
            document.getElementById('goToMainChatBtn').style.display = 'block';
            loadChatHistory(currentRoom);
        }

        function switchToMainChat() {
            currentRoom = 'main_group';
            document.getElementById('currentChatRoomTitle').innerText = "WeMeet - Main Group Chat";
            document.getElementById('goToMainChatBtn').style.display = 'none';
            loadChatHistory(currentRoom);
        }

        function loadChatHistory(roomName) {
            socket.emit('join_room', {room: roomName});
            fetch(`/get_history?room=${roomName}`)
            .then(res => res.json())
            .then(data => {
                const stream = document.getElementById('historyStream');
                stream.innerHTML = '';
                data.reverse().forEach(item => appendMessage(item));
            });
        }

        function sendText() {
            const content = document.getElementById('textContent').value;
            if (!content) return;
            socket.emit('new_message', {
                user: document.getElementById('currentLoggedInName').innerText,
                type: 'text', content: content, room: currentRoom
            });
            document.getElementById('textContent').value = '';
        }

        function appendMessage(item) {
            const stream = document.getElementById('historyStream');
            const div = document.createElement('div');
            div.className = 'history-item';
            div.innerHTML = `<div><b>${item.user}:</b> ${item.content}</div><div style="font-size:10px; color:#94a3b8; margin-top:4px;">${item.timestamp}</div>`;
            stream.appendChild(div);
            stream.scrollTop = stream.scrollHeight;
        }
    </script>
</body>
</html>
"""

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)

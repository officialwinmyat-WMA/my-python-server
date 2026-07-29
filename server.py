import os
import sqlite3
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template_string, session

# Python compatibility fix for gevent
import sys
from gevent import monkey
try:
    monkey.patch_all()
except Exception:
    pass

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "wma_qq_secure_secret_key_123")

from flask_socketio import SocketIO, emit

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

DB_PATH = 'wma_qq.db'

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn

# Database Initialization
def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_info TEXT,
            msg_type TEXT,
            content TEXT,
            filename TEXT,
            store_type TEXT,
            expire_at DATETIME,
            timestamp DATETIME
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT UNIQUE,
            google_account TEXT,
            status TEXT, -- 'pending', 'approved', 'banned'
            last_active DATETIME
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            password TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def send_approval_email(device_id, google_account):
    try:
        sender_email = os.environ.get("SMTP_EMAIL", "officialwinmyat@gmail.com")
        sender_password = os.environ.get("SMTP_PASSWORD", "")
        if not sender_password:
            return
        
        msg = MIMEText(f"New Device Access Request:\n\nDevice ID: {device_id}\nGoogle Account: {google_account}\n\nPlease go to your WMA QQ dashboard to approve or ban this device.")
        msg['Subject'] = f"WMA QQ - New Device Pending Approval: {device_id}"
        msg['From'] = sender_email
        msg['To'] = "officialwinmyat@gmail.com"

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, ["officialwinmyat@gmail.com"], msg.as_string())
        server.quit()
    except Exception as e:
        print("Email notification error:", e)

@app.route('/')
def index():
    return render_template_string(HTML_PAGE)

@app.route('/signup', methods=['POST'])
def signup():
    data = request.json
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    
    if not email or not password:
        return jsonify({"success": False, "error": "Email နှင့် Password ထည့်ရန် လိုအပ်ပါသည်။"})
    
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('INSERT INTO users (email, password) VALUES (?, ?)', (email, password))
        conn.commit()
        conn.close()
        
        session['user_email'] = email
        session['is_admin'] = (email == 'officialwinmyat@gmail.com')
        return jsonify({"success": True, "is_admin": session['is_admin']})
    except sqlite3.IntegrityError:
        return jsonify({"success": False, "error": "ဤ Email ဖြင့် အကောင့်ရှိနှင့်ပြီးသား ဖြစ်ပါသည်။ Login ဝင်ပါ။"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT password FROM users WHERE email = ?', (email,))
        row = cursor.fetchone()
        conn.close()
        
        if row and row['password'] == password:
            session['user_email'] = email
            session['is_admin'] = (email == 'officialwinmyat@gmail.com')
            return jsonify({"success": True, "is_admin": session['is_admin']})
        else:
            return jsonify({"success": False, "error": "Email သို့မဟုတ် Password မှားယွင်းနေပါသည်။"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

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
    
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT device_id, google_account, status, last_active FROM devices')
        rows = cursor.fetchall()
        conn.close()
        
        devices = []
        for r in rows:
            devices.append({
                "device_id": r['device_id'],
                "account": r['google_account'],
                "status": 'approved' if r['google_account'] == 'officialwinmyat@gmail.com' else r['status'],
                "active": True if r['last_active'] else False,
                "is_current_user_admin": session.get('user_email') == 'officialwinmyat@gmail.com'
            })
        return jsonify(devices)
    except Exception as e:
        return jsonify([])

@app.route('/get_history', methods=['GET'])
def get_history():
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT id, user_info, msg_type, content, filename, store_type, timestamp FROM history ORDER BY id DESC')
        rows = cursor.fetchall()
        conn.close()
        
        history = []
        for r in rows:
            history.append({
                "id": r['id'],
                "user": r['user_info'],
                "type": r['msg_type'],
                "content": r['content'],
                "filename": r['filename'],
                "store": r['store_type'],
                "timestamp": r['timestamp']
            })
        return jsonify(history)
    except Exception as e:
        return jsonify([])

@app.route('/forgot_password', methods=['POST'])
def forgot_password():
    data = request.json
    email = data.get('email', '').strip().lower()
    if not email:
        return jsonify({"success": False, "error": "ကျေးဇူးပြု၍ Email ထည့်ပါ။"})
    
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT password FROM users WHERE email = ?', (email,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return jsonify({"success": False, "error": "ဤ Email ဖြင့် အကောင့်မရှိပါ။"})
        
        user_password = row['password']
        
        sender_email = os.environ.get("SMTP_EMAIL", "officialwinmyat@gmail.com")
        sender_password = os.environ.get("SMTP_PASSWORD", "")
        if not sender_password:
            return jsonify({"success": False, "error": "SMTP Password ထည့်သွင်းထားခြင်း မရှိပါ။ Admin ကို ဆက်သွယ်ပါ။"})
        
        msg = MIMEText(f"WMA QQ Password Recovery:\n\nYour account email: {email}\nYour password: {user_password}\n\nPlease keep your credentials safe.")
        msg['Subject'] = "WMA QQ - Password Reset Information"
        msg['From'] = sender_email
        msg['To'] = email

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, [email], msg.as_string())
        server.quit()
        
        return jsonify({"success": True, "message": "Password ကို သင်၏ Google Account သို့ ပို့ပေးလိုက်ပါပြီ။"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@socketio.on('register_device')
def handle_register_device(data):
    dev_id = data.get('device_id')
    google_acc = session.get('user_email', data.get('google_account', ''))
    
    if not dev_id or not google_acc:
        return

    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT status FROM devices WHERE device_id = ?', (dev_id,))
        row = cursor.fetchone()
        
        status = 'approved' if google_acc == 'officialwinmyat@gmail.com' else ('approved' if row and row['status'] == 'approved' else 'pending')
        
        if not row:
            cursor.execute('INSERT INTO devices (device_id, google_account, status, last_active) VALUES (?, ?, ?, ?)',
                           (dev_id, google_acc, status, datetime.now()))
            conn.commit()
            if status == 'pending' and google_acc != 'officialwinmyat@gmail.com':
                send_approval_email(dev_id, google_acc)
        else:
            cursor.execute('UPDATE devices SET google_account = ?, status = ?, last_active = ? WHERE device_id = ?',
                           (google_acc, status, datetime.now(), dev_id))
            conn.commit()
        conn.close()
        socketio.emit('device_status_update', {'device_id': dev_id})
    except Exception as e:
        print("Register device error:", e)

@socketio.on('admin_device_action')
def handle_admin_action(data):
    if session.get('user_email') != 'officialwinmyat@gmail.com':
        return

    dev_id = data.get('device_id')
    action = data.get('action') 
    
    try:
        conn = get_db()
        cursor = conn.cursor()
        if action == 'remove':
            cursor.execute('SELECT google_account FROM devices WHERE device_id = ?', (dev_id,))
            dev_row = cursor.fetchone()
            if dev_row and dev_row['google_account']:
                acc_email = dev_row['google_account']
                cursor.execute('DELETE FROM users WHERE email = ?', (acc_email,))
            
            cursor.execute('DELETE FROM devices WHERE device_id = ?', (dev_id,))
        else:
            cursor.execute('UPDATE devices SET status = ? WHERE device_id = ?', (action, dev_id))
        conn.commit()
        conn.close()
        socketio.emit('device_status_update', {'device_id': dev_id})
    except Exception as e:
        print("Admin device action error:", e)

@socketio.on('new_message')
def handle_new_message(data):
    user = data.get('user')
    msg_type = data.get('type')
    content = data.get('content')
    filename = data.get('filename', '')
    store = data.get('store', '48h')
    
    now = datetime.now()
    if store == '5m':
        expire_at = now + timedelta(minutes=5)
    elif store == '1h':
        expire_at = now + timedelta(hours=1)
    else:
        expire_at = now + timedelta(hours=48)
        
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('INSERT INTO history (user_info, msg_type, content, filename, store_type, expire_at, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)',
                       (user, msg_type, content, filename, store, expire_at, now.strftime('%Y-%m-%d %H:%M:%S')))
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
            "timestamp": now.strftime('%Y-%m-%d %H:%M:%S')
        })
    except Exception as e:
        print("New message error:", e)

@socketio.on('delete_message_item')
def handle_delete_message(data):
    msg_id = data.get('id')
    if msg_id:
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute('DELETE FROM history WHERE id = ?', (msg_id,))
            conn.commit()
            conn.close()
            socketio.emit('message_deleted', {"id": msg_id})
        except Exception as e:
            print("Delete message error:", e)

@socketio.on('trigger_video_call')
def handle_video_call(data):
    socketio.emit('incoming_video_call', data)

@socketio.on('join_conference')
def handle_join_conference(data):
    socketio.emit('user_joined_conference', data, room=request.sid)

@socketio.on('leave_conference')
def handle_leave_conference(data):
    socketio.emit('user_left_conference', data)

@socketio.on('video_signal')
def handle_video_signal(data):
    socketio.emit('video_signal_relay', data)

@socketio.on('reset_storage')
def handle_reset():
    if session.get('user_email') == 'officialwinmyat@gmail.com':
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute('DELETE FROM history')
            conn.commit()
            conn.close()
            socketio.emit('storage_reset')
        except Exception as e:
            print("Reset storage error:", e)

HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>WMA QQ - Chinese & Japanese Anime Spacial Web App</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.2/socket.io.js"></script>
    <style>
        :root {
            --bg-color: #0f172a;
            --panel-bg: rgba(20, 24, 33, 0.85);
            --text-color: #f8fafc;
            --accent-color: #ec4899;
            --chat-bg: rgba(10, 14, 23, 0.8);
            --stream-bg: rgba(20, 24, 33, 0.8);
            --bg-image: url('https://images.unsplash.com/photo-1578632767115-351597cf2477?auto=format&fit=crop&w=1920&q=80');
        }
        body { 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
            margin: 0; padding: 0; 
            background-color: var(--bg-color); 
            background-image: var(--bg-image);
            background-size: cover; background-position: center; background-attachment: fixed;
            color: var(--text-color); display: flex; height: 100vh; overflow: hidden; 
        }
        .left-pane { width: 50%; height: 100vh; overflow-y: auto; padding: 20px; box-sizing: border-box; background: var(--panel-bg); border-right: 3px solid var(--accent-color); position: relative; backdrop-filter: blur(12px); }
        .right-pane { width: 50%; height: 100vh; display: flex; flex-direction: column; padding: 20px; box-sizing: border-box; background: var(--stream-bg); position: relative; backdrop-filter: blur(12px); border-left: 3px solid var(--accent-color); }
        .card { background: rgba(255,255,255,0.06); padding: 15px; border-radius: 8px; margin-bottom: 15px; border: 2px solid var(--accent-color); backdrop-filter: blur(8px); box-shadow: 0 0 12px rgba(236,72,153,0.25); }
        input, textarea, select, button { width: 100%; padding: 10px; margin: 8px 0; border-radius: 5px; border: 2px solid var(--accent-color); background: rgba(15, 23, 42, 0.9); color: white; box-sizing: border-box; }
        button { background: var(--accent-color); cursor: pointer; font-weight: bold; border: 2px solid #fff; transition: 0.2s; }
        button:hover { opacity: 0.85; transform: scale(1.01); }
        #historyStream { flex: 1; overflow-y: auto; background: var(--chat-bg); border: 2px solid var(--accent-color); border-radius: 8px; padding: 10px; box-sizing: border-box; backdrop-filter: blur(8px); margin-top: 40px; }
        .history-item { padding: 12px; margin-bottom: 10px; background: rgba(255,255,255,0.07); border-left: 6px solid var(--accent-color); border-radius: 6px; font-size: 13px; word-break: break-all; position: relative; }
        .msg-actions { margin-top: 8px; display: flex; gap: 6px; }
        .msg-actions button { padding: 4px 10px; font-size: 11px; width: auto; margin: 0; border-radius: 4px; }
        #resetBtn { position: absolute; top: 15px; right: 15px; z-index: 999; background: #dc2626; color: white; padding: 6px 12px; border-radius: 4px; font-size: 12px; cursor: pointer; width: auto; border: 2px solid var(--accent-color); display: none; }
        #videoPopup { display: none; position: fixed; top: 10%; left: 10%; width: 80%; background: rgba(20, 24, 33, 0.98); border: 3px solid var(--accent-color); border-radius: 10px; padding: 20px; z-index: 1000; box-shadow: 0 0 35px rgba(236,72,153,0.5); text-align: center; backdrop-filter: blur(18px); }
        .video-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 15px; max-height: 380px; overflow-y: auto; margin: 15px 0; }
        .video-box { background: rgba(0,0,0,0.6); border: 2px solid var(--accent-color); border-radius: 6px; padding: 5px; position: relative; }
        .video-label { position: absolute; bottom: 10px; left: 10px; background: rgba(0,0,0,0.7); color: #fff; padding: 2px 6px; font-size: 11px; border-radius: 4px; }
        video { width: 100%; height: 160px; object-fit: cover; border-radius: 4px; background: #000; }
        .device-row { display: flex; justify-content: space-between; align-items: center; font-size: 12px; padding: 6px 0; border-bottom: 1px solid rgba(255,255,255,0.2); }
        .badge-active { height: 10px; width: 10px; background-color: #22c55e; border-radius: 50%; display: inline-block; box-shadow: 0 0 8px #22c55e; }
        .badge-inactive { height: 10px; width: 10px; background-color: #64748b; border-radius: 50%; display: inline-block; }
        #appContainer { display: none; width: 100%; height: 100vh; }
        #authOverlay, #pendingOverlay { position: fixed; top: 0; left: 0; width: 100%; height: 100vh; background: rgba(10, 14, 23, 0.96); z-index: 9999; display: flex; flex-direction: column; justify-content: center; align-items: center; text-align: center; padding: 20px; }
        #pendingOverlay { display: none; }
        .chat-image-preview { max-width: 100%; max-height: 200px; border-radius: 6px; margin-top: 5px; border: 1px solid var(--accent-color); display: block; }
    </style>
</head>
<body>

    <div id="authOverlay">
        <h2 style="color: #f472b6;">WMA QQ - Chinese & Japanese Anime Hub</h2>
        <p style="max-width: 450px; color: #cbd5e1; margin: 15px 0;">သင့် Email နှင့် Password ဖြင့် ဝင်ရောက်ပါ (သို့မဟုတ် အကောင့်အသစ်ဖွင့်ပါ)</p>
        <div style="background: rgba(255,255,255,0.08); padding: 20px; border-radius: 8px; border: 2px solid var(--accent-color); width: 320px;">
            <input type="email" id="loginEmail" placeholder="Email (e.g. user@gmail.com)">
            <input type="password" id="loginPassword" placeholder="Password">
            
            <div style="text-align: left; font-size: 12px; color: #cbd5e1; margin: 5px 0 10px 0;">
                <input type="checkbox" id="showPasswordToggle" onclick="togglePasswordVisibility()" style="width: auto; margin-right: 5px; accent-color: var(--accent-color);"> Password ပြရန်
            </div>

            <button onclick="loginUser()" style="background: var(--accent-color); margin-top: 5px;">Login</button>
            <button onclick="signupUser()" style="background: #3b82f6; margin-top: 5px;">Sign Up (အကောင့်သစ်ဖွင့်ရန်)</button>
            <button onclick="forgotPassword()" style="background: #eab308; color: #000; margin-top: 5px; font-size: 12px;">Forgot Password? (စကားဝှက်မေ့နေပါက)</button>
            <div id="loginError" style="color: #f87171; font-size: 12px; margin-top: 10px;"></div>
        </div>
    </div>

    <div id="pendingOverlay">
        <h2 style="color: #f472b6;">Device Pending Approval / Access Blocked</h2>
        <p id="pendingMessage" style="max-width: 450px; color: #cbd5e1; margin: 15px 0;">သင့်စက် သို့မဟုတ် အကောင့်ကို Admin မှ အတည်ပြုရန် စောင့်ဆိုင်းနေပါသည် သို့မဟုတ် ပိတ်ပင်ထားပါသည်။</p>
        <button onclick="checkAuthSession()" style="width: 200px; background: var(--accent-color);">Reload / စစ်ဆေးမည်</button>
        <button onclick="logoutUserSession()" style="width: 200px; background: #dc2626; margin-top: 10px;">Logout (ထွက်ရန်)</button>
    </div>

    <div id="appContainer">
        <div class="left-pane">
            <button id="resetBtn" onclick="resetStorage()">Reset All Storage</button>
            <h2>WMA QQ Control Panel</h2>
            
            <div class="card">
                <h3>User & Device Status</h3>
                <div style="font-size: 13px; margin-bottom: 8px;">Logged in as: <strong id="currentUserEmail" style="color: #f472b6;"></strong></div>
                <button onclick="logoutUserSession()" style="background: #dc2626; padding: 6px; font-size: 12px;">Logout</button>
                <div style="margin-top: 10px; max-height: 150px; overflow-y: auto;" id="deviceListContainer"></div>
            </div>

            <div class="card">
                <h3>Send Announcement / Message</h3>
                <input type="text" id="msgUser" placeholder="Your Name / Alias">
                <select id="msgType">
                    <option value="text">Text Message</option>
                    <option value="image">Image URL</option>
                    <option value="link">Web Link</option>
                </select>
                <textarea id="msgContent" placeholder="Enter message content..."></textarea>
                <input type="text" id="msgFilename" placeholder="Filename (optional)">
                <label style="font-size: 12px;">Storage Duration:</label>
                <select id="msgStore">
                    <option value="48h">48 Hours</option>
                    <option value="1h">1 Hour</option>
                    <option value="5m">5 Minutes</option>
                </select>
                <button onclick="sendMessage()">Broadcast Message</button>
            </div>

            <div class="card">
                <h3>Video Conference / Call</h3>
                <button onclick="startVideoCall()" style="background: #10b981;">Start Video Meeting</button>
            </div>
        </div>

        <div class="right-pane">
            <h2 style="margin-top: 0; color: #f472b6;">Live Stream & Chat History</h2>
            <div id="historyStream"></div>
        </div>
    </div>

    <div id="videoPopup">
        <h3 style="color: #f472b6; margin: 0;">WMA QQ Live Video Conference</h3>
        <div class="video-grid" id="videoGrid">
            <div class="video-box">
                <video id="localVideo" autoplay muted playsinline></video>
                <div class="video-label">You</div>
            </div>
        </div>
        <button onclick="closeVideoCall()" style="background: #dc2626; width: 150px; margin-top: 10px;">Leave Call</button>
    </div>

    <script>
        const socket = io();
        let currentUser = "";
        let isAdmin = false;
        let localStream = null;
        let peers = {};
        const deviceId = 'dev_' + Math.random().toString(36.25).substr(2, 9);

        window.onload = function() {
            checkAuthSession();
            loadHistory();
        };

        function togglePasswordVisibility() {
            const pwdInput = document.getElementById('loginPassword');
            pwdInput.type = document.getElementById('showPasswordToggle').checked ? 'text' : 'password';
        }

        function signupUser() {
            const email = document.getElementById('loginEmail').value;
            const password = document.getElementById('loginPassword').value;
            fetch('/signup', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({email, password})
            })
            .then(res => res.json())
            .then(data => {
                if(data.success) {
                    checkAuthSession();
                } else {
                    document.getElementById('loginError').innerText = data.error;
                }
            });
        }

        function loginUser() {
            const email = document.getElementById('loginEmail').value;
            const password = document.getElementById('loginPassword').value;
            fetch('/login', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({email, password})
            })
            .then(res => res.json())
            .then(data => {
                if(data.success) {
                    checkAuthSession();
                } else {
                    document.getElementById('loginError').innerText = data.error;
                }
            });
        }

        function forgotPassword() {
            const email = document.getElementById('loginEmail').value;
            if(!email) {
                document.getElementById('loginError').innerText = "ကျေးဇူးပြု၍ Email ထည့်ပါ။";
                return;
            }
            fetch('/forgot_password', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({email})
            })
            .then(res => res.json())
            .then(data => {
                if(data.success) {
                    alert(data.message);
                } else {
                    document.getElementById('loginError').innerText = data.error;
                }
            });
        }

        function logoutUserSession() {
            fetch('/logout', {method: 'POST'})
            .then(() => {
                document.getElementById('appContainer').style.display = 'none';
                document.getElementById('pendingOverlay').style.display = 'none';
                document.getElementById('authOverlay').style.display = 'flex';
            });
        }

        function checkAuthSession() {
            fetch('/check_session')
            .then(res => res.json())
            .then(data => {
                if(data.logged_in) {
                    currentUser = data.email;
                    isAdmin = data.is_admin;
                    document.getElementById('currentUserEmail').innerText = currentUser;
                    document.getElementById('authOverlay').style.display = 'none';
                    
                    if(isAdmin) {
                        document.getElementById('resetBtn').style.display = 'block';
                    }

                    socket.emit('register_device', {device_id: deviceId, google_account: currentUser});
                    fetchDevices();
                    
                    document.getElementById('appContainer').style.display = 'flex';
                    document.getElementById('pendingOverlay').style.display = 'none';
                } else {
                    document.getElementById('authOverlay').style.display = 'flex';
                    document.getElementById('appContainer').style.display = 'none';
                }
            });
        }

        function fetchDevices() {
            fetch('/get_devices')
            .then(res => res.json())
            .then(devices => {
                const container = document.getElementById('deviceListContainer');
                container.innerHTML = '<strong>Connected Devices:</strong>';
                let currentDeviceApproved = true;
                
                devices.forEach(d => {
                    if(d.device_id === deviceId && d.status !== 'approved' && !isAdmin) {
                        currentDeviceApproved = false;
                    }
                    
                    let div = document.createElement('div');
                    div.className = 'device-row';
                    div.innerHTML = `<span><span class="${d.active ? 'badge-active' : 'badge-inactive'}"></span> ${d.account} (${d.status})</span>`;
                    
                    if(isAdmin) {
                        let btnHtml = '';
                        if(d.status !== 'approved') btnHtml += `<button onclick="adminAction('${d.device_id}', 'approved')" style="padding:2px 6px; font-size:10px; background:#10b981; width:auto; margin-left:4px;">Approve</button>`;
                        if(d.status !== 'banned') btnHtml += `<button onclick="adminAction('${d.device_id}', 'banned')" style="padding:2px 6px; font-size:10px; background:#eab308; color:#000; width:auto; margin-left:4px;">Ban</button>`;
                        btnHtml += `<button onclick="adminAction('${d.device_id}', 'remove')" style="padding:2px 6px; font-size:10px; background:#dc2626; width:auto; margin-left:4px;">Remove</button>`;
                        div.innerHTML += `<div>${btnHtml}</div>`;
                    }
                    container.appendChild(div);
                });

                if(!currentDeviceApproved && !isAdmin) {
                    document.getElementById('appContainer').style.display = 'none';
                    document.getElementById('pendingOverlay').style.display = 'flex';
                }
            });
        }

        function adminAction(devId, action) {
            socket.emit('admin_device_action', {device_id: devId, action: action});
            setTimeout(fetchDevices, 500);
        }

        function loadHistory() {
            fetch('/get_history')
            .then(res => res.json())
            .then(history => {
                const stream = document.getElementById('historyStream');
                stream.innerHTML = '';
                history.forEach(item => appendMessageToStream(item));
            });
        }

        function sendMessage() {
            const user = document.getElementById('msgUser').value || currentUser;
            const type = document.getElementById('msgType').value;
            const content = document.getElementById('msgContent').value;
            const filename = document.getElementById('msgFilename').value;
            const store = document.getElementById('msgStore').value;

            if(!content) return;

            socket.emit('new_message', {user, type, content, filename, store});
            document.getElementById('msgContent').value = '';
        }

        function deleteMessage(id) {
            socket.emit('delete_message_item', {id: id});
        }

        socket.on('broadcast_message', function(data) {
            appendMessageToStream(data);
        });

        socket.on('message_deleted', function(data) {
            const el = document.getElementById('msg_item_' + data.id);
            if(el) el.remove();
        });

        socket.on('device_status_update', function(data) {
            fetchDevices();
        });

        function appendMessageToStream(item) {
            const stream = document.getElementById('historyStream');
            const div = document.createElement('div');
            div.className = 'history-item';
            div.id = 'msg_item_' + item.id;
            
            let contentHtml = item.content;
            if(item.type === 'image') {
                contentHtml = `<img src="${item.content}" class="chat-image-preview">`;
            } else if(item.type === 'link') {
                contentHtml = `<a href="${item.content}" target="_blank" style="color: #f472b6;">${item.content}</a>`;
            }

            div.innerHTML = `
                <strong>${item.user}</strong> <span style="font-size:10px; color:#94a3b8;">(${item.timestamp})</span><br>
                <div style="margin-top:4px;">${contentHtml}</div>
                ${item.filename ? `<div style="font-size:11px; color:#cbd5e1; margin-top:2px;">File: ${item.filename}</div>` : ''}
                <div class="msg-actions">
                    ${isAdmin ? `<button onclick="deleteMessage(${item.id})" style="background:#dc2626;">Delete</button>` : ''}
                </div>
            `;
            stream.prepend(div);
        }

        function resetStorage() {
            if(confirm("Are you sure you want to clear all history storage?")) {
                socket.emit('reset_storage');
            }
        }

        socket.on('storage_reset', function() {
            document.getElementById('historyStream').innerHTML = '';
        });

        function startVideoCall() {
            document.getElementById('videoPopup').style.display = 'block';
            navigator.mediaDevices.getUserMedia({video: true, audio: true})
            .then(stream => {
                localStream = stream;
                document.getElementById('localVideo').srcObject = stream;
                socket.emit('join_conference', {room: 'wma_qq_room'});
            }).catch(err => {
                alert("Camera/Mic access denied or error: " + err);
            });
        }

        function closeVideoCall() {
            if(localStream) {
                localStream.getTracks().forEach(track => track.stop());
            }
            document.getElementById('videoPopup').style.display = 'none';
            socket.emit('leave_conference', {});
        }
    </script>
</body>
</html>
"""

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))

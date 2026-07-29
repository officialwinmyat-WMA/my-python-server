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

# Database Initialization
def init_db():
    conn = sqlite3.connect('wma_qq.db')
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
        conn = sqlite3.connect('wma_qq.db')
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
    
    conn = sqlite3.connect('wma_qq.db')
    cursor = conn.cursor()
    cursor.execute('SELECT password FROM users WHERE email = ?', (email,))
    row = cursor.fetchone()
    conn.close()
    
    if row and row[0] == password:
        session['user_email'] = email
        session['is_admin'] = (email == 'officialwinmyat@gmail.com')
        return jsonify({"success": True, "is_admin": session['is_admin']})
    else:
        return jsonify({"success": False, "error": "Email သို့မဟုတ် Password မှားယွင်းနေပါသည်။"})

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
    
    conn = sqlite3.connect('wma_qq.db')
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
    conn = sqlite3.connect('wma_qq.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, user_info, msg_type, content, filename, store_type, timestamp FROM history ORDER BY id DESC')
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
            "timestamp": r[6]
        })
    return jsonify(history)

@socketio.on('register_device')
def handle_register_device(data):
    dev_id = data.get('device_id')
    google_acc = session.get('user_email', data.get('google_account', ''))
    
    if not dev_id or not google_acc:
        return

    conn = sqlite3.connect('wma_qq.db')
    cursor = conn.cursor()
    cursor.execute('SELECT status FROM devices WHERE device_id = ?', (dev_id,))
    row = cursor.fetchone()
    
    status = 'approved' if google_acc == 'officialwinmyat@gmail.com' else ('approved' if row and row[0] == 'approved' else 'pending')
    
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

@socketio.on('admin_device_action')
def handle_admin_action(data):
    if session.get('user_email') != 'officialwinmyat@gmail.com':
        return

    dev_id = data.get('device_id')
    action = data.get('action') 
    
    conn = sqlite3.connect('wma_qq.db')
    cursor = conn.cursor()
    if action == 'remove':
        cursor.execute('DELETE FROM devices WHERE device_id = ?', (dev_id,))
    else:
        cursor.execute('UPDATE devices SET status = ? WHERE device_id = ?', (action, dev_id))
    conn.commit()
    conn.close()
    socketio.emit('device_status_update', {'device_id': dev_id})

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
        
    conn = sqlite3.connect('wma_qq.db')
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

@socketio.on('delete_message_item')
def handle_delete_message(data):
    msg_id = data.get('id')
    if msg_id:
        conn = sqlite3.connect('wma_qq.db')
        cursor = conn.cursor()
        cursor.execute('DELETE FROM history WHERE id = ?', (msg_id,))
        conn.commit()
        conn.close()
        socketio.emit('message_deleted', {"id": msg_id})

# WebRTC & Video Conference Socket Events
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
        conn = sqlite3.connect('wma_qq.db')
        cursor = conn.cursor()
        cursor.execute('DELETE FROM history')
        conn.commit()
        conn.close()
        socketio.emit('storage_reset')


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

    <!-- Login / Sign Up Screen -->
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
            <div id="loginError" style="color: #f87171; font-size: 12px; margin-top: 10px;"></div>
        </div>
    </div>

    <!-- Pending / Ban Access Block Screen -->
    <div id="pendingOverlay">
        <h2 id="overlayTitle" style="color: #f472b6;">WMA QQ - Device Verification Required</h2>
        <p id="overlayDesc" style="max-width: 500px; color: #cbd5e1; margin: 15px 0;">သင့် Device သည် Admin (officialwinmyat@gmail.com) ထံမှ Approve အတည်ပြုချက် ရယူရန် လိုအပ်နေပါသည်။</p>
        <div style="background: rgba(255,255,255,0.08); padding: 15px; border-radius: 8px; border: 2px solid var(--accent-color); margin-bottom: 15px; width: 320px;">
            <input type="text" id="overlayDeviceId" readonly style="text-align:center; font-weight:bold;">
            <div id="overlayStatus" style="font-size: 14px; color: #facc15; font-weight: bold; margin-top: 10px;">Status: Pending Approval ⏳</div>
        </div>
        <button onclick="logoutUser()" style="background: #dc2626; width: auto; padding: 8px 15px;">Logout</button>
    </div>

    <!-- Main Application Container -->
    <div id="appContainer">
        <!-- Video Conference Popup -->
        <div id="videoPopup">
            <h3>WMA QQ - Anime Video Conference</h3>
            <div id="callerInfo" style="margin-bottom: 10px; font-weight: bold; color: #f472b6;"></div>
            <div style="font-size: 13px; color: #facc15; margin-bottom: 8px;">Active Participants in Call: <span id="activeCallCount">1</span></div>
            <div class="video-grid" id="videoGridContainer">
                <div class="video-box" id="localVideoContainer">
                    <video id="localVideo" autoplay muted playsinline></video>
                    <div class="video-label">Local Stream (You)</div>
                </div>
            </div>
            <div class="actions" style="margin-top: 15px; display: flex; justify-content: center; gap: 10px;">
                <button onclick="stopConference()" style="background: #ca8a04; width: auto; padding: 8px 15px;">Stop Video Conference</button>
                <button onclick="closePopup()" style="background: #dc2626; width: auto; padding: 8px 15px;">Close</button>
            </div>
        </div>

        <!-- Left Pane: Controls & Admin Panel -->
        <div class="left-pane">
            <h2>WMA QQ Anime Control Panel</h2>
            <div style="margin-bottom: 10px; font-size: 13px; color: #cbd5e1;">Logged in as: <b id="currentLoggedInEmail" style="color:#f472b6;"></b> <button onclick="logoutUser()" style="width: auto; padding: 2px 8px; font-size: 11px; margin-left: 10px; background:#dc2626;">Logout</button></div>
            
            <div class="card">
                <h4>Dynamic Chinese & Japanese Anime Themes</h4>
                <button onclick="autoGenerateAnimeTheme()">Randomize Anime Character Theme</button>
            </div>

            <!-- Admin Control Panel Card -->
            <div class="card" id="adminControlCard" style="display: none; border-color: #f59e0b;">
                <h4 style="color: #f59e0b;">👑 Admin Control Panel (Official Win Myat)</h4>
                <p style="font-size: 11px; color: #cbd5e1; margin: 0 0 8px 0;">ဤနေရာမှသာ Device များကို Approve, Ban သို့မဟုတ် Remove လုပ်နိုင်ပါသည်။</p>
                <div style="font-size: 12px; color: #facc15; margin-bottom: 5px;">Active & Pending Devices List:</div>
                <div id="activeDeviceList" style="max-height: 180px; overflow-y: auto; background: rgba(0,0,0,0.4); padding: 8px; border-radius: 6px; border: 1px solid var(--accent-color);"></div>
            </div>

            <!-- Function 1: Voice Message -->
            <div class="card">
                <h4>Function 1: Voice Message (Max 3s)</h4>
                <button id="recBtn" onclick="toggleRecordVoice()">Record Voice (3s)</button>
                <div id="voiceOptions" style="display:none; margin-top: 10px;">
                    <p style="font-size: 12px; margin: 5px 0;">Storage Duration ရွေးပါ:</p>
                    <button onclick="sendVoice('5m')">5 Minutes</button>
                    <button onclick="sendVoice('1h')">1 Hour</button>
                    <button onclick="sendVoice('48h')">48 Hours</button>
                </div>
            </div>

            <!-- Function 2: Video Call -->
            <div class="card">
                <h4>Function 2: Live Video Call & Conference</h4>
                <p style="font-size: 12px; color: #cbd5e1;">လိုင်းပေါ်ရှိ အခြားသူများနှင့် Video Call ချိတ်ဆက်ရန် ခလုတ်ကိုနှိပ်ပါ။</p>
                <button onclick="startVideoCall()" style="background: #2563eb;">Start / Accept Video Call</button>
            </div>

            <!-- Function 3: Text Message & Custom Notes -->
            <div class="card">
                <h4>Function 3: Text & Note Broadcast</h4>
                <textarea id="textContent" placeholder="Chinese/Japanese Anime quote သို့မဟုတ် မက်ဆေ့ဂျ်ရေးရန်..."></textarea>
                <select id="textStore">
                    <option value="48h">48 Hours Storage</option>
                    <option value="1h">1 Hour Storage</option>
                    <option value="5m">5 Minutes Storage</option>
                </select>
                <button onclick="sendText()">Send Broadcast Message</button>
            </div>

            <!-- Function 4: Image/Photo Share -->
            <div class="card">
                <h4>Function 4: Anime Photo Share</h4>
                <input type="file" id="imageFileInput" accept="image/*" onchange="previewImage(event)">
                <img id="imagePreviewContainer" class="chat-image-preview" style="display:none;">
                <select id="imageStore">
                    <option value="48h">48 Hours Storage</option>
                    <option value="1h">1 Hour Storage</option>
                    <option value="5m">5 Minutes Storage</option>
                </select>
                <button onclick="sendImage()">Upload & Share Photo</button>
            </div>
        </div>

        <!-- Right Pane: Broadcast Chat History Stream -->
        <div class="right-pane">
            <button id="resetBtn" onclick="resetStorage()">Reset Storage (Admin)</button>
            <h3>WMA QQ Live Broadcast Stream & Chat History</h3>
            <div id="historyStream"></div>
        </div>
    </div>

    <script>
        const socket = io();
        let deviceId = localStorage.getItem('wma_device_id');
        if (!deviceId) {
            deviceId = 'dev_' + Math.random().toString(36.2, 16).substring(2, 10);
            localStorage.setItem('wma_device_id', deviceId);
        }

        let currentUserEmail = '';
        let localStream = null;
        let peerConnections = {};
        let rtcConfig = { iceServers: [{ urls: 'stun:stun.l.google.com:19302' }] };
        let mediaRecorder;
        let audioChunks = [];
        let selectedBase64Image = null;

        window.onload = function() {
            checkSession();
            loadHistory();
        };

        function togglePasswordVisibility() {
            const pwd = document.getElementById('loginPassword');
            pwd.type = document.getElementById('showPasswordToggle').checked ? 'text' : 'password';
        }

        function checkSession() {
            fetch('/check_session')
            .then(res => res.json())
            .then(data => {
                if (data.logged_in) {
                    currentUserEmail = data.email;
                    document.getElementById('currentLoggedInEmailinnerText') = currentUserEmail;
                    document.getElementById('currentLoggedInEmail').textContent = currentUserEmail;
                    document.getElementById('authOverlay').style.display = 'none';
                    socket.emit('register_device', { device_id: deviceId, google_account: currentUserEmail });
                    checkDeviceApprovalStatus();
                } else {
                    document.getElementById('authOverlay').style.display = 'flex';
                }
            });
        }

        function signupUser() {
            const email = document.getElementById('loginEmail').value.trim();
            const password = document.getElementById('loginPassword').value;
            fetch('/signup', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ email, password })
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    location.reload();
                } else {
                    document.getElementById('loginError').textContent = data.error;
                }
            });
        }

        function loginUser() {
            const email = document.getElementById('loginEmail').value.trim();
            const password = document.getElementById('loginPassword').value;
            fetch('/login', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ email, password })
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    location.reload();
                } else {
                    document.getElementById('loginError').textContent = data.error;
                }
            });
        }

        function logoutUser() {
            fetch('/logout', {method: 'POST'}).then(() => location.reload());
        }

        function checkDeviceApprovalStatus() {
            fetch('/get_devices')
            .then(res => res.json())
            .then(devices => {
                const myDev = devices.find(d => d.device_id === deviceId);
                const isAdmin = currentUserEmail === 'officialwinmyat@gmail.com';
                
                if (myDev && (myDev.status === 'approved' || isAdmin)) {
                    document.getElementById('pendingOverlay').style.display = 'none';
                    document.getElementById('appContainer').style.display = 'flex';
                    if (isAdmin) {
                        document.getElementById('adminControlCard').style.display = 'block';
                        document.getElementById('resetBtn').style.display = 'block';
                        renderAdminDevices(devices);
                    }
                } else if (myDev && myDev.status === 'banned') {
                    document.getElementById('overlayTitle').textContent = 'Access Denied / Banned';
                    document.getElementById('overlayDesc').textContent = 'သင့် Device အား Admin မှ ပိတ်ပင်ထားပါသည် (Banned)။';
                    document.getElementById('overlayStatus').textContent = 'Status: Banned ❌';
                    document.getElementById('overlayStatus').style.color = '#f87171';
                    document.getElementById('overlayDeviceId').value = deviceId;
                    document.getElementById('pendingOverlay').style.display = 'flex';
                } else {
                    document.getElementById('overlayDeviceId').value = deviceId;
                    document.getElementById('pendingOverlay').style.display = 'flex';
                }
            });
        }

        function renderAdminDevices(devices) {
            let html = '';
            devices.forEach(d => {
                html += `<div class="device-row">
                    <span><b>${d.device_id}</b> (${d.account})<br><small style="color:#cbd5e1;">Status: ${d.status}</small></span>
                    <span>
                        ${d.status !== 'approved' ? `<button onclick="adminAction('${d.device_id}', 'approved')" style="padding:2px 6px; font-size:10px; background:#22c55e; width:auto;">Approve</button>` : ''}
                        ${d.status !== 'banned' ? `<button onclick="adminAction('${d.device_id}', 'banned')" style="padding:2px 6px; font-size:10px; background:#eab308; width:auto;">Ban</button>` : ''}
                        <button onclick="adminAction('${d.device_id}', 'remove')" style="padding:2px 6px; font-size:10px; background:#dc2626; width:auto;">Remove</button>
                    </span>
                </div>`;
            });
            document.getElementById('activeDeviceList').innerHTML = html || 'No devices registered.';
        }

        function adminAction(devId, action) {
            socket.emit('admin_device_action', { device_id: devId, action: action });
        }

        socket.on('device_status_update', (data) => {
            checkDeviceApprovalStatus();
        });

        // Chat History & Broadcast Functions
        function loadHistory() {
            fetch('/get_history')
            .then(res => res.json())
            .then(history => {
                const stream = document.getElementById('historyStream');
                stream.innerHTML = '';
                history.forEach(item => appendHistoryItem(item));
            });
        }

        function appendHistoryItem(item) {
            const stream = document.getElementById('historyStream');
            const div = document.createElement('div');
            div.className = 'history-item';
            div.id = `msg_${item.id}`;
            
            let contentHtml = '';
            if (item.type === 'text') {
                contentHtml = `<div>${escapeHtml(item.content)}</div>`;
            } else if (item.type === 'voice') {
                contentHtml = `<audio controls src="${item.content}" style="width:100%; margin-top:5px;"></audio>`;
            } else if (item.type === 'image') {
                contentHtml = `<img src="${item.content}" class="chat-image-preview">`;
            }

            const isAdmin = currentUserEmail === 'officialwinmyat@gmail.com';
            div.innerHTML = `
                <div style="font-size:11px; color:#f472b6; margin-bottom:3px;"><b>${escapeHtml(item.user)}</b> (${item.store} storage) - <span style="color:#94a3b8;">${item.timestamp}</span></div>
                ${contentHtml}
                ${isAdmin ? `<div class="msg-actions"><button onclick="deleteMessage(${item.id})" style="background:#dc2626;">Delete</button></div>` : ''}
            `;
            stream.appendChild(div);
        }

        socket.on('broadcast_message', (item) => {
            appendHistoryItem(item);
        });

        socket.on('message_deleted', (data) => {
            const el = document.getElementById(`msg_${data.id}`);
            if (el) el.remove();
        });

        socket.on('storage_reset', () => {
            document.getElementById('historyStream').innerHTML = '';
            alert('Storage has been reset by Admin.');
        });

        function sendText() {
            const text = document.getElementById('textContent').value.trim();
            const store = document.getElementById('textStore').value;
            if (!text) return;
            socket.emit('new_message', {
                user: currentUserEmail || deviceId,
                type: 'text',
                content: text,
                store: store
            });
            document.getElementById('textContent').value = '';
        }

        function previewImage(event) {
            const file = event.target.files[0];
            if (!file) return;
            const reader = new FileReader();
            reader.onload = function(e) {
                selectedBase64Image = e.target.result;
                const img = document.getElementById('imagePreviewContainer');
                img.src = selectedBase64Image;
                img.style.display = 'block';
            };
            reader.readAsDataURL(file);
        }

        function sendImage() {
            if (!selectedBase64Image) return;
            const store = document.getElementById('imageStore').value;
            socket.emit('new_message', {
                user: currentUserEmail || deviceId,
                type: 'image',
                content: selectedBase64Image,
                store: store
            });
            selectedBase64Image = null;
            document.getElementById('imageFileinput') = '';
            document.getElementById('imagePreviewContainer').style.display = 'none';
        }

        let isRecording = false;
        function toggleRecordVoice() {
            if (!isRecording) {
                navigator.mediaDevices.getUserMedia({ audio: true }).then(stream => {
                    mediaRecorder = new MediaRecorder(stream);
                    audioChunks = [];
                    mediaRecorder.ondataavailable = e => audioChunks.push(e.data);
                    mediaRecorder.onstop = () => {
                        const blob = new Blob(audioChunks, { type: 'audio/webm' });
                        const reader = new FileReader();
                        reader.onload = function(e) {
                            window.tempVoiceBase64 = e.target.result;
                            document.getElementById('voiceOptions').style.display = 'block';
                        };
                        reader.readAsDataURL(blob);
                    };
                    mediaRecorder.start();
                    isRecording = true;
                    document.getElementById('recBtn').textContent = 'Stop & Save Voice (Max 3s)';
                    setTimeout(() => {
                        if (isRecording) toggleRecordVoice();
                    }, 3000);
                }).catch(err => alert('Microphone permission error: ' + err));
            } else {
                mediaRecorder.stop();
                isRecording = false;
                document.getElementById('recBtn').textContent = 'Record Voice (3s)';
            }
        }

        function sendVoice(store) {
            if (!window.tempVoiceBase64) return;
            socket.emit('new_message', {
                user: currentUserEmail || deviceId,
                type: 'voice',
                content: window.tempVoiceBase64,
                store: store
            });
            window.tempVoiceBase64 = null;
            document.getElementById('voiceOptions').style.display = 'none';
        }

        function resetStorage() {
            if (confirm('Are you sure you want to reset all broadcast history?')) {
                socket.emit('reset_storage');
            }
        }

        function autoGenerateAnimeTheme() {
            const characters = [
                "Naruto Uzumaki - Hidden Leaf Village (Hokage Vibe)",
                "Gojo Satoru - Jujutsu Kaisen (Infinity Domain)",
                "Tanjiro Kamado - Demon Slayer (Hinokami Kagura)",
                "Luffy - One Piece (Gear 5 Sun God Nika)",
                "Nezuko Kamado - Demon Slayer Spacial Vibe",
                "Megumi Fushiguro - Shadow Divine Dogs"
            ];
            const chosen = characters[Math.floor(Math.random() * characters.length)];
            document.getElementById('textContent').value = `✨ WMA QQ Anime Theme Selected: ${chosen} 🌸`;
        }

        function escapeHtml(text) {
            return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
        }

        // --- Multi-User WebRTC Video Call & Conference Implementation ---
        let activeParticipantsCount = 1;

        function startVideoCall() {
            document.getElementById('videoPopup').style.display = 'block';
            document.getElementById('callerInfo').textContent = `Connected as: ${currentUserEmail || deviceId}`;
            
            navigator.mediaDevices.getUserMedia({ video: true, audio: true })
            .then(stream => {
                localStream = stream;
                document.getElementById('localVideo').srcObject = stream;
                socket.emit('join_conference', { sender: deviceId, email: currentUserEmail });
            })
            .catch(err => alert('Camera/Microphone permission denied or error: ' + err));
        }

        socket.on('incoming_video_call', (data) => {
            // Auto open conference popup when a video call is triggered/accepted
            if (document.getElementById('videoPopup').style.display !== 'block') {
                startVideoCall();
            }
        });

        socket.on('user_joined_conference', (data) => {
            if (data.sender === deviceId) return;
            createPeerConnection(data.sender, true);
        });

        socket.on('user_left_conference', (data) => {
            if (peerConnections[data.sender]) {
                peerConnections[data.sender].close();
                delete peerConnections[data.sender];
            }
            const box = document.getElementById(`remote_box_${data.sender}`);
            if (box) box.remove();
            updateParticipantCount(-1);
        });

        socket.on('video_signal_relay', async (data) => {
            if (data.target !== deviceId) return;
            const sender = data.sender;
            
            let pc = peerConnections[sender];
            if (!pc) {
                pc = createPeerConnection(sender, false);
            }

            if (data.signal.type === 'offer') {
                await pc.setRemoteDescription(new RTCSessionDescription(data.signal));
                const answer = await pc.createAnswer();
                await pc.setLocalDescription(answer);
                socket.emit('video_signal', { sender: deviceId, target: sender, signal: pc.localDescription });
            } else if (data.signal.type === 'answer') {
                await pc.setRemoteDescription(new RTCSessionDescription(data.signal));
            } else if (data.signal.candidate) {
                await pc.addIceCandidate(new RTCIceCandidate(data.signal.candidate));
            }
        });

        function createPeerConnection(remoteId, isInitiator) {
            if (peerConnections[remoteId]) return peerConnections[remoteId];

            const pc = new RTCPeerConnection(rtcConfig);
            peerConnections[remoteId] = pc;

            if (localStream) {
                localStream.getTracks().forEach(track => pc.addTrack(track, localStream));
            }

            pc.onicecandidate = event => {
                if (event.candidate) {
                    socket.emit('video_signal', { sender: deviceId, target: remoteId, signal: { candidate: event.candidate } });
                }
            };

            pc.ontrack = event => {
                let remoteVideoBox = document.getElementById(`remote_box_${remoteId}`);
                if (!remoteVideoBox) {
                    remoteVideoBox = document.createElement('div');
                    remoteVideoBox.className = 'video-box';
                    remoteVideoBox.id = `remote_box_${remoteId}`;
                    remoteVideoBox.innerHTML = `
                        <video autoplay playsinline></video>
                        <div class="video-label">Participant: ${remoteId.substring(0,6)}</div>
                    `;
                    document.getElementById('videoGridContainer').appendChild(remoteVideoBox);
                    updateParticipantCount(1);
                }
                remoteVideoBox.querySelector('video').srcObject = event.streams[0];
            };

            if (isInitiator) {
                pc.createOffer().then(offer => {
                    pc.setLocalDescription(offer);
                    socket.emit('video_signal', { sender: deviceId, target: remoteId, signal: offer });
                });
            }

            return pc;
        }

        function updateParticipantCount(change) {
            activeParticipantsCount += change;
            if (activeParticipantsCount < 1) activeParticipantsCount = 1;
            document.getElementById('activeCallCount').textContent = activeParticipantsCount;
        }

        function stopConference() {
            if (localStream) {
                localStream.getTracks().forEach(track => track.stop());
                localStream = null;
            }
            Object.keys(peerConnections).forEach(id => {
                peerConnections[id].close();
            });
            peerConnections = {};
            
            // Clear remote video boxes
            const grid = document.getElementById('videoGridContainer');
            grid.innerHTML = `
                <div class="video-box" id="localVideoContainer">
                    <video id="localVideo" autoplay muted playsinline></video>
                    <div class="video-label">Local Stream (You)</div>
                </div>
            `;
            activeParticipantsCount = 1;
            document.getElementById('activeCallCount').textContent = 1;
            socket.emit('leave_conference', { sender: deviceId });
            document.getElementById('videoPopup').style.display = 'none';
        }

        function closePopup() {
            stopConference();
        }
    </script>
</body>
</html>
"""

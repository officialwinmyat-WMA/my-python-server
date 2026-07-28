import os
import sqlite3
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template_string, session

# Python 3.11+ compatibility fix for eventlet
import sys
import eventlet
try:
    eventlet.monkey_patch()
except Exception:
    pass

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "wma_qq_secure_secret_key_123")

from flask_socketio import SocketIO, emit

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

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
    cursor.execute('SELECT user_info, msg_type, content, filename, store_type, timestamp FROM history ORDER BY id DESC')
    rows = cursor.fetchall()
    conn.close()
    
    history = []
    for r in rows:
        history.append({
            "user": r[0],
            "type": r[1],
            "content": r[2],
            "filename": r[3],
            "store": r[4],
            "timestamp": r[5]
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
    conn.commit()
    conn.close()
    
    socketio.emit('broadcast_message', {
        "user": user,
        "type": msg_type,
        "content": content,
        "filename": filename,
        "store": store,
        "timestamp": now.strftime('%Y-%m-%d %H:%M:%S')
    })

@socketio.on('trigger_video_call')
def handle_video_call(data):
    socketio.emit('incoming_video_call', data)

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
    <title>WMA QQ - Advanced Special Web App</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.2/socket.io.js"></script>
    <style>
        :root {
            --bg-color: #0f172a;
            --panel-bg: rgba(30, 41, 59, 0.75);
            --text-color: #f8fafc;
            --accent-color: #ec4899;
            --chat-bg: rgba(9, 13, 22, 0.7);
            --stream-bg: rgba(30, 41, 59, 0.7);
            --bg-image: url('https://images.unsplash.com/photo-1534447677768-be436bb09401?auto=format&fit=crop&w=1920&q=80');
        }
        body { 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
            margin: 0; padding: 0; 
            background-color: var(--bg-color); 
            background-image: var(--bg-image);
            background-size: cover; background-position: center; background-attachment: fixed;
            color: var(--text-color); display: flex; height: 100vh; overflow: hidden; 
        }
        
        .left-pane { width: 50%; height: 100vh; overflow-y: auto; padding: 20px; box-sizing: border-box; background: var(--panel-bg); border-right: 3px solid var(--accent-color); position: relative; backdrop-filter: blur(10px); }
        .right-pane { width: 50%; height: 100vh; display: flex; flex-direction: column; padding: 20px; box-sizing: border-box; background: var(--stream-bg); position: relative; backdrop-filter: blur(10px); border-left: 3px solid var(--accent-color); }

        .card { background: rgba(255,255,255,0.1); padding: 15px; border-radius: 8px; margin-bottom: 15px; border: 2px solid var(--accent-color); backdrop-filter: blur(5px); box-shadow: 0 0 10px rgba(236,72,153,0.3); }
        input, textarea, select, button { width: 100%; padding: 10px; margin: 8px 0; border-radius: 5px; border: 2px solid var(--accent-color); background: rgba(15, 23, 42, 0.85); color: white; box-sizing: border-box; }
        button { background: var(--accent-color); cursor: pointer; font-weight: bold; border: 2px solid #fff; }
        button:hover { opacity: 0.9; }

        #historyStream { flex: 1; overflow-y: auto; background: var(--chat-bg); border: 2px solid var(--accent-color); border-radius: 8px; padding: 10px; box-sizing: border-box; backdrop-filter: blur(5px); margin-top: 40px; }
        .history-item { padding: 10px; margin-bottom: 8px; background: rgba(255,255,255,0.08); border-left: 6px solid var(--accent-color); border-right: 2px solid var(--accent-color); border-radius: 4px; font-size: 13px; word-break: break-all; }
        
        #resetBtn { position: absolute; top: 15px; right: 15px; z-index: 999; background: #dc2626; color: white; padding: 6px 12px; border-radius: 4px; font-size: 12px; cursor: pointer; width: auto; border: 2px solid var(--accent-color); display: none; }
        
        #videoPopup { display: none; position: fixed; top: 10%; left: 15%; width: 70%; background: rgba(30, 41, 59, 0.95); border: 3px solid var(--accent-color); border-radius: 10px; padding: 20px; z-index: 1000; box-shadow: 0 0 30px rgba(0,0,0,0.9); text-align: center; backdrop-filter: blur(15px); }
        .video-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; max-height: 350px; overflow-y: auto; margin: 15px 0; }
        video { width: 100%; height: 160px; object-fit: cover; border-radius: 6px; background: #000; }

        .device-row { display: flex; justify-content: space-between; align-items: center; font-size: 12px; padding: 6px 0; border-bottom: 1px solid rgba(255,255,255,0.2); }
        .badge-active { height: 10px; width: 10px; background-color: #22c55e; border-radius: 50%; display: inline-block; box-shadow: 0 0 8px #22c55e; }
        .badge-inactive { height: 10px; width: 10px; background-color: #64748b; border-radius: 50%; display: inline-block; }
        
        #appContainer { display: none; width: 100%; height: 100vh; }
        #authOverlay, #pendingOverlay { position: fixed; top: 0; left: 0; width: 100%; height: 100vh; background: rgba(15, 23, 42, 0.95); z-index: 9999; display: flex; flex-direction: column; justify-content: center; align-items: center; text-align: center; padding: 20px; }
        #pendingOverlay { display: none; }
    </style>
</head>
<body>

    <!-- Login / Sign Up Screen -->
    <div id="authOverlay">
        <h2 style="color: #f472b6;">WMA QQ - Account Login & Sign Up</h2>
        <p style="max-width: 450px; color: #cbd5e1; margin: 15px 0;">သင့် Email နှင့် Password ဖြင့် ဝင်ရောက်ပါ (သို့မဟုတ် အကောင့်အသစ်ဖွင့်ပါ)</p>
        <div style="background: rgba(255,255,255,0.1); padding: 20px; border-radius: 8px; border: 2px solid var(--accent-color); width: 320px;">
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
        <div style="background: rgba(255,255,255,0.1); padding: 15px; border-radius: 8px; border: 2px solid var(--accent-color); margin-bottom: 15px; width: 320px;">
            <input type="text" id="overlayDeviceId" readonly style="text-align:center; font-weight:bold;">
            <div id="overlayStatus" style="font-size: 14px; color: #facc15; font-weight: bold; margin-top: 10px;">Status: Pending Approval ⏳</div>
        </div>
        <button onclick="logoutUser()" style="background: #dc2626; width: auto; padding: 8px 15px;">Logout</button>
    </div>

    <!-- Main Application Container -->
    <div id="appContainer">
        <div id="videoPopup">
            <h3>WMA QQ - Video Conference (10s)</h3>
            <div id="callerInfo" style="margin-bottom: 10px; font-weight: bold; color: #f472b6;"></div>
            <div class="video-grid" id="videoGridContainer">
                <div class="video-box"><video id="localVideo" autoplay muted playsinline></video><div>Local Stream</div></div>
            </div>
            <div class="actions" style="margin-top: 15px;">
                <button onclick="stopConference()" style="background: #ca8a04; width: auto; padding: 8px 15px;">Stop Video Conference</button>
                <button onclick="closePopup()" style="background: #dc2626; width: auto; padding: 8px 15px;">Close</button>
            </div>
        </div>

        <div class="left-pane">
            <h2>WMA QQ Control Panel</h2>
            <div style="margin-bottom: 10px; font-size: 13px; color: #cbd5e1;">Logged in as: <b id="currentLoggedInEmail" style="color:#f472b6;"></b> <button onclick="logoutUser()" style="width: auto; padding: 2px 8px; font-size: 11px; margin-left: 10px; background:#dc2626;">Logout</button></div>
            
            <div class="card">
                <h4>Dynamic Spacial Themes (Spider-Man, Anime, etc.)</h4>
                <button onclick="autoGenerateSpacialTheme()">Auto Generate Spacial Theme</button>
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
                <h4>Function 2: Video Call (10s)</h4>
                <button onclick="triggerVideoCall()" style="background: #16a34a;">Call All Active Users (10s)</button>
            </div>

            <!-- Function 3: Text & Universal Equation -->
            <div class="card">
                <h4>Function 3: Text & Universal Equation</h4>
                <textarea id="textContent" rows="3" placeholder="Write text or equation (e.g. 50 * 20 =)" oninput="solveEquation(this)"></textarea>
                <button onclick="sendText()">Send Text (48h)</button>
            </div>

            <!-- Function 4: File or Image -->
            <div class="card">
                <h4>Function 4: Original File or Image (48h)</h4>
                <input type="file" id="fileInput">
                <button onclick="sendFile()">Send File / Image</button>
            </div>
        </div>

        <div class="right-pane" id="rightPane">
            <button id="resetBtn" onclick="resetStorage()">Reset Storage</button>
            <h3>WMA QQ - Live Chat & History Stream</h3>
            <div id="historyStream"></div>
        </div>
    </div>

<script>
    const socket = io();
    let mediaRecorder;
    let audioChunks = [];
    let localStream = null;
    let videoCallTimeout = null;

    window.onload = function() {
        checkSession();
        loadHistory();
        loadDevices();
    };

    function togglePasswordVisibility() {
        let pwdInput = document.getElementById('loginPassword');
        pwdInput.type = document.getElementById('showPasswordToggle').checked ? 'text' : 'password';
    }

    function checkSession() {
        fetch('/check_session')
        .then(res => res.json())
        .then(data => {
            if (data.logged_in) {
                document.getElementById('authOverlay').style.display = 'none';
                document.getElementById('currentLoggedInEmail').innerText = data.email;
                if(data.is_admin) {
                    document.getElementById('adminControlCard').style.display = 'block';
                    document.getElementById('resetBtn').style.display = 'block';
                }
                verifyDevice(data.email);
            } else {
                document.getElementById('authOverlay').style.display = 'flex';
                document.getElementById('appContainer').style.display = 'none';
            }
        });
    }

    function loginUser() {
        let email = document.getElementById('loginEmail').value;
        let password = document.getElementById('loginPassword').value;
        fetch('/login', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({email, password})
        })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                location.reload();
            } else {
                document.getElementById('loginError').innerText = data.error;
            }
        });
    }

    function signupUser() {
        let email = document.getElementById('loginEmail').value;
        let password = document.getElementById('loginPassword').value;
        fetch('/signup', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({email, password})
        })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                location.reload();
            } else {
                document.getElementById('loginError').innerText = data.error;
            }
        });
    }

    function logoutUser() {
        fetch('/logout', {method: 'POST'}).then(() => location.reload());
    }

    function getDeviceId() {
        let devId = localStorage.getItem('wma_device_id');
        if (!devId) {
            devId = 'DEV-' + Math.random().toString(36).substr(2, 9).toUpperCase();
            localStorage.setItem('wma_device_id', devId);
        }
        return devId;
    }

    function verifyDevice(email) {
        let devId = getDeviceId();
        socket.emit('register_device', {device_id: devId, google_account: email});
    }

    socket.on('device_status_update', function(data) {
        loadDevices();
        fetch('/get_devices')
        .then(res => res.json())
        .then(devices => {
            let currentDevId = getDeviceId();
            let currentDev = devices.find(d => d.device_id === currentDevId);
            if (currentDev) {
                if (currentDev.status === 'approved') {
                    document.getElementById('pendingOverlay').style.display = 'none';
                    document.getElementById('appContainer').style.display = 'flex';
                } else if (currentDev.status === 'banned') {
                    document.getElementById('overlayTitle').innerText = "Access Banned ❌";
                    document.getElementById('overlayStatus').innerText = "Status: Banned by Admin";
                    document.getElementById('overlayStatus').style.color = "#ef4444";
                    document.getElementById('overlayDeviceId').value = currentDevId;
                    document.getElementById('pendingOverlay').style.display = 'flex';
                    document.getElementById('appContainer').style.display = 'none';
                } else {
                    document.getElementById('overlayDeviceId').value = currentDevId;
                    document.getElementById('pendingOverlay').style.display = 'flex';
                    document.getElementById('appContainer').style.display = 'none';
                }
            }
        });
    });

    function loadDevices() {
        fetch('/get_devices')
        .then(res => res.json())
        .then(devices => {
            let listDiv = document.getElementById('activeDeviceList');
            if(!listDiv) return;
            listDiv.innerHTML = '';
            devices.forEach(d => {
                let row = document.createElement('div');
                row.className = 'device-row';
                let actionBtns = '';
                if (d.is_current_user_admin) {
                    actionBtns = `<button onclick="adminAction('${d.device_id}', 'approved')" style="padding:2px 5px; font-size:10px; width:auto; background:#16a34a;">Approve</button>
                                  <button onclick="adminAction('${d.device_id}', 'banned')" style="padding:2px 5px; font-size:10px; width:auto; background:#ca8a04;">Ban</button>
                                  <button onclick="adminAction('${d.device_id}', 'remove')" style="padding:2px 5px; font-size:10px; width:auto; background:#dc2626;">Remove</button>`;
                }
                row.innerHTML = `<div><span class="${d.active ? 'badge-active' : 'badge-inactive'}"></span> <b>${d.device_id}</b> (${d.account}) [<b>${d.status}</b>]</div><div>${actionBtns}</div>`;
                listDiv.appendChild(row);
            });
        });
    }

    function adminAction(deviceId, action) {
        socket.emit('admin_device_action', {device_id: deviceId, action: action});
    }

    function loadHistory() {
        fetch('/get_history')
        .then(res => res.json())
        .then(history => {
            let stream = document.getElementById('historyStream');
            stream.innerHTML = '';
            history.reverse().forEach(h => appendHistoryItem(h));
        });
    }

    function appendHistoryItem(h) {
        let stream = document.getElementById('historyStream');
        let div = document.createElement('div');
        div.className = 'history-item';
        let contentDisplay = h.content;
        if(h.type === 'voice') {
            contentDisplay = `<audio controls src="${h.content}"></audio>`;
        } else if(h.type === 'file') {
            contentDisplay = `<a href="${h.content}" target="_blank" style="color:#f472b6; font-weight:bold;">📎 Download ${h.filename}</a>`;
        }
        div.innerHTML = `<b>${h.user}</b> <span style="font-size:10px; color:#94a3b8;">(${h.timestamp}) [Store: ${h.store}]</span><br>${contentDisplay}`;
        stream.appendChild(div);
        stream.scrollTop = stream.scrollHeight;
    }

    socket.on('broadcast_message', function(data) {
        appendHistoryItem(data);
    });

    let recordingTimer = null;
    function toggleRecordVoice() {
        let btn = document.getElementById('recBtn');
        if (!mediaRecorder || mediaRecorder.state === 'inactive') {
            audioChunks = [];
            navigator.mediaDevices.getUserMedia({audio: true}).then(stream => {
                mediaRecorder = new MediaRecorder(stream);
                mediaRecorder.ondataavailable = e => audioChunks.push(e.data);
                mediaRecorder.onstop = () => {
                    let blob = new Blob(audioChunks, {type: 'audio/webm'});
                    let reader = new FileReader();
                    reader.readAsDataURL(blob);
                    reader.onloadend = () => {
                        window.lastRecordedAudio = reader.result;
                        document.getElementById('voiceOptions').style.display = 'block';
                    };
                };
                mediaRecorder.start();
                btn.innerText = "Recording... (Speaking max 3s)";
                btn.style.background = "#dc2626";
                recordingTimer = setTimeout(() => {
                    if(mediaRecorder && mediaRecorder.state === 'recording') {
                        mediaRecorder.stop();
                        btn.innerText = "Record Voice (3s)";
                        btn.style.background = "var(--accent-color)";
                    }
                }, 3000);
            });
        }
    }

    function sendVoice(storeType) {
        if(window.lastRecordedAudio) {
            let userEmail = document.getElementById('currentLoggedInEmail').innerText;
            socket.emit('new_message', {
                user: userEmail,
                type: 'voice',
                content: window.lastRecordedAudio,
                store: storeType
            });
            document.getElementById('voiceOptions').style.display = 'none';
            window.lastRecordedAudio = null;
        }
    }

    function solveEquation(el) {
        let val = el.value.trim();
        if (val.endsWith('=')) {
            try {
                let expr = val.slice(0, -1).trim();
                let ans = Function('"use strict";return (' + expr + ')')();
                el.value = val + ' ' + ans;
            } catch(e) {}
        }
    }

    function sendText() {
        let text = document.getElementById('textContent').value.trim();
        if(!text) return;
        let userEmail = document.getElementById('currentLoggedInEmail').innerText;
        socket.emit('new_message', {
            user: userEmail,
            type: 'text',
            content: text,
            store: '48h'
        });
        document.getElementById('textContent').value = '';
    }

    function sendFile() {
        let fileInput = document.getElementById('fileInput');
        if(fileInput.files.length === 0) return;
        let file = fileInput.files[0];
        let reader = new FileReader();
        reader.readAsDataURL(file);
        reader.onloadend = () => {
            let userEmail = document.getElementById('currentLoggedInEmail').innerText;
            socket.emit('new_message', {
                user: userEmail,
                type: 'file',
                content: reader.result,
                filename: file.name,
                store: '48h'
            });
            fileInput.value = '';
        };
    }

    function triggerVideoCall() {
        let userEmail = document.getElementById('currentLoggedInEmail').innerText;
        socket.emit('trigger_video_call', {caller: userEmail});
    }

    socket.on('incoming_video_call', function(data) {
        document.getElementById('callerInfo').innerText = "Caller: " + data.caller;
        document.getElementById('videoPopup').style.display = 'block';
        navigator.mediaDevices.getUserMedia({video: true, audio: true}).then(stream => {
            localStream = stream;
            document.getElementById('localVideo').srcObject = stream;
        });
        videoCallTimeout = setTimeout(() => {
            stopConference();
        }, 10000);
    });

    function stopConference() {
        if(localStream) {
            localStream.getTracks().forEach(track => track.stop());
        }
        if(videoCallTimeout) clearTimeout(videoCallTimeout);
        document.getElementById('videoPopup').style.display = 'none';
    }

    function closePopup() {
        stopConference();
    }

    function resetStorage() {
        if(confirm('Are you sure you want to reset all history storage?')) {
            socket.emit('reset_storage');
        }
    }

    socket.on('storage_reset', function() {
        document.getElementById('historyStream').innerHTML = '';
    });

    let themes = [
        "url('https://images.unsplash.com/photo-1635863138275-d9b33299780b?auto=format&fit=crop&w=1920&q=80')",
        "url('https://images.unsplash.com/photo-1578632767115-351597cf2477?auto=format&fit=crop&w=1920&q=80')",
        "url('https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?auto=format&fit=crop&w=1920&q=80')"
    ];
    function autoGenerateSpacialTheme() {
        let randomTheme = themes[Math.floor(Math.random() * themes.length)];
        document.body.style.backgroundImage = randomTheme;
    }
</script>
</body>
</html>
"""

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host='0.0.0.0', port=port)

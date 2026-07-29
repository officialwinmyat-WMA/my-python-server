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
            password TEXT,
            device_id TEXT,
            remember_token TEXT
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
    device_id = data.get('device_id', '')
    
    if not email or not password:
        return jsonify({"success": False, "error": "Email နှင့် Password ထည့်ရန် လိုအပ်ပါသည်။"})
    
    try:
        conn = sqlite3.connect('wma_qq.db')
        cursor = conn.cursor()
        cursor.execute('INSERT INTO users (email, password, device_id) VALUES (?, ?, ?)', (email, password, device_id))
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
    remember = data.get('remember', False)
    device_id = data.get('device_id', '')
    
    conn = sqlite3.connect('wma_qq.db')
    cursor = conn.cursor()
    cursor.execute('SELECT password FROM users WHERE email = ?', (email,))
    row = cursor.fetchone()
    
    if row and row[0] == password:
        session['user_email'] = email
        session['is_admin'] = (email == 'officialwinmyat@gmail.com')
        
        if remember:
            token = f"token_{email}_{device_id}"
            cursor.execute('UPDATE users SET remember_token = ?, device_id = ? WHERE email = ?', (token, device_id, email))
            conn.commit()
        
        conn.close()
        return jsonify({"success": True, "is_admin": session['is_admin'], "remember_token": f"token_{email}_{device_id}" if remember else ""})
    else:
        conn.close()
        return jsonify({"success": False, "error": "Email သို့မဟုတ် Password မှားယွင်းနေပါသည်။"})

@app.route('/check_remember', methods=['POST'])
def check_remember():
    data = request.json
    email = data.get('email', '').strip().lower()
    token = data.get('token', '')
    device_id = data.get('device_id', '')
    
    if not email or not token or not device_id:
        return jsonify({"logged_in": False})
        
    conn = sqlite3.connect('wma_qq.db')
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
        
    conn = sqlite3.connect('wma_qq.db')
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
        cursor.execute('INSERT INTO devices (device_id, google_account, status, last_active) VALUES (?, ?, ?, ?)', (dev_id, google_acc, status, datetime.now()))
        conn.commit()
        if status == 'pending' and google_acc != 'officialwinmyat@gmail.com':
            send_approval_email(dev_id, google_acc)
    else:
        cursor.execute('UPDATE devices SET google_account = ?, status = ?, last_active = ? WHERE device_id = ?', (google_acc, status, datetime.now(), dev_id))
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

@socketio.on('trigger_video_call')
def handle_video_call(data):
    socketio.emit('incoming_video_call', data)

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
    <script src="[https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.2/socket.io.js](https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.2/socket.io.js)"></script>
    <style>
        :root {
            --bg-color: #0f172a;
            --panel-bg: rgba(20, 24, 33, 0.85);
            --text-color: #f8fafc;
            --accent-color: #ec4899;
            --chat-bg: rgba(10, 14, 23, 0.8);
            --stream-bg: rgba(20, 24, 33, 0.8);
            --bg-image: url('[https://images.unsplash.com/photo-1578632767115-351597cf2477?auto=format&fit=crop&w=1920&q=80](https://images.unsplash.com/photo-1578632767115-351597cf2477?auto=format&fit=crop&w=1920&q=80)');
        }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0; padding: 0;
            background-color: var(--bg-color);
            background-image: var(--bg-image);
            background-size: cover; background-position: center; background-attachment: fixed;
            color: var(--text-color);
            display: flex; height: 100vh; overflow: hidden;
        }
        .left-pane {
            width: 50%; height: 100vh; overflow-y: auto; padding: 20px; box-sizing: border-box;
            background: var(--panel-bg); border-right: 3px solid var(--accent-color);
            position: relative; backdrop-filter: blur(12px);
        }
        .right-pane {
            width: 50%; height: 100vh; display: flex; flex-direction: column; padding: 20px; box-sizing: border-box;
            background: var(--stream-bg); position: relative; backdrop-filter: blur(12px);
            border-left: 3px solid var(--accent-color);
        }
        .card {
            background: rgba(255,255,255,0.06); padding: 15px; border-radius: 8px; margin-bottom: 15px;
            border: 2px solid var(--accent-color); backdrop-filter: blur(8px);
            box-shadow: 0 0 12px rgba(236,72,153,0.25);
        }
        input, textarea, select, button {
            width: 100%; padding: 10px; margin: 8px 0; border-radius: 5px;
            border: 2px solid var(--accent-color); background: rgba(15, 23, 42, 0.9);
            color: white; box-sizing: border-box;
        }
        button {
            background: var(--accent-color); cursor: pointer; font-weight: bold; border: 2px solid #fff; transition: 0.2s;
        }
        button:hover { opacity: 0.85; transform: scale(1.01); }
        #historyStream {
            flex: 1; overflow-y: auto; background: var(--chat-bg); border: 2px solid var(--accent-color);
            border-radius: 8px; padding: 10px; box-sizing: border-box; backdrop-filter: blur(8px); margin-top: 40px;
        }
        .history-item {
            padding: 12px; margin-bottom: 10px; background: rgba(255,255,255,0.07);
            border-left: 6px solid var(--accent-color); border-radius: 6px; font-size: 13px; word-break: break-all; position: relative;
        }
        .msg-actions { margin-top: 8px; display: flex; gap: 6px; }
        .msg-actions button { padding: 4px 10px; font-size: 11px; width: auto; margin: 0; border-radius: 4px; }
        #resetBtn {
            position: absolute; top: 15px; right: 15px; z-index: 999; background: #dc2626; color: white;
            padding: 6px 12px; border-radius: 4px; font-size: 12px; cursor: pointer; width: auto; border: 2px solid var(--accent-color); display: none;
        }
        #videoPopup {
            display: none; position: fixed; top: 10%; left: 15%; width: 70%;
            background: rgba(20, 24, 33, 0.98); border: 3px solid var(--accent-color); border-radius: 10px;
            padding: 20px; z-index: 1000; box-shadow: 0 0 35px rgba(236,72,153,0.5); text-align: center; backdrop-filter: blur(18px);
        }
        .video-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 15px; max-height: 380px; overflow-y: auto; margin: 15px 0; }
        .video-box { background: rgba(0,0,0,0.6); border: 2px solid var(--accent-color); border-radius: 6px; padding: 5px; }
        video { width: 100%; height: 160px; object-fit: cover; border-radius: 4px; background: #000; }
        .device-row { display: flex; justify-content: space-between; align-items: center; font-size: 12px; padding: 6px 0; border-bottom: 1px solid rgba(255,255,255,0.2); }
        #appContainer { display: none; width: 100%; height: 100vh; }
        #authOverlay, #pendingOverlay {
            position: fixed; top: 0; left: 0; width: 100%; height: 100vh;
            background: rgba(10, 14, 23, 0.96); z-index: 9999; display: flex; flex-direction: column;
            justify-content: center; align-items: center; text-align: center; padding: 20px;
        }
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
            <div style="text-align: left; font-size: 12px; color: #cbd5e1; margin: 5px 0;">
                <input type="checkbox" id="showPasswordToggle" onclick="togglePasswordVisibility()" style="width: auto; margin-right: 5px; accent-color: var(--accent-color);"> Password ပြရန်
            </div>
            <div style="text-align: left; font-size: 12px; color: #cbd5e1; margin: 5px 0 10px 0;">
                <input type="checkbox" id="rememberMeToggle" style="width: auto; margin-right: 5px; accent-color: var(--accent-color);"> Remember Me (အကောင့်မှတ်ထားရန်)
            </div>
            <button onclick="loginUser()" style="background: var(--accent-color); margin-top: 5px;">Login</button>
            <button onclick="signupUser()" style="background: #3b82f6; margin-top: 5px;">Sign Up (အကောင့်သစ်ဖွင့်ရန်)</button>
            <button onclick="openForgetPassword()" style="background: #ca8a04; margin-top: 5px; font-size: 12px;">Forget Password? (Google Account ဖြင့် Reset လုပ်ရန်)</button>
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
                <p style="font-size: 11px; color: #cbd5e1; margin: 0 0 8px 0;">ဤနေရာမှသာ Device များကို Approve, Ban သို့မဟုတ် Remove လုပ်နိုင်ပါသည်။ (Remove လုပ်ပါက Users database မှပါ ဖျက်ပစ်မည်)</p>
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
                <h4>Function 2: Video Call</h4>
                <button onclick="triggerVideoCall()" style="background: #16a34a;">Call All Active Users</button>
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
                <input type="file" id="fileInput" onchange="handleFileSelected(this)">
                <button id="sendFileBtn" onclick="sendFile()" disabled style="opacity: 0.5;">Send File / Image</button>
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
        let peerConnections = {}; // socketId -> RTCPeerConnection
        let selectedFileBase64 = null;
        let selectedFileName = '';
        let isSpeakerMuted = false;
        let isCameraMuted = false;

        const servers = {
            iceServers: [
                { urls: 'stun:stun.l.google.com:19302' },
                { urls: 'stun:stun1.l.google.com:19302' }
            ]
        };

        const animeThemes = [
            { name: "Naruto Uzumaki", bg: "[https://images.unsplash.com/photo-1578632767115-351597cf2477?auto=format&fit=crop&w=1920&q=80](https://images.unsplash.com/photo-1578632767115-351597cf2477?auto=format&fit=crop&w=1920&q=80)", accent: "#f97316" },
            { name: "Gojo Satoru", bg: "[https://images.unsplash.com/photo-1607604276583-eef5d076aa5f?auto=format&fit=crop&w=1920&q=80](https://images.unsplash.com/photo-1607604276583-eef5d076aa5f?auto=format&fit=crop&w=1920&q=80)", accent: "#3b82f6" },
            { name: "Wei Wuxian (MDZS)", bg: "[https://images.unsplash.com/photo-1534447677768-be436bb09401?auto=format&fit=crop&w=1920&q=80](https://images.unsplash.com/photo-1534447677768-be436bb09401?auto=format&fit=crop&w=1920&q=80)", accent: "#a855f7" },
            { name: "Nezuko Kamado", bg: "[https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?auto=format&fit=crop&w=1920&q=80](https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?auto=format&fit=crop&w=1920&q=80)", accent: "#ec4899" }
        ];

        function autoGenerateAnimeTheme() {
            const theme = animeThemes[Math.floor(Math.random() * animeThemes.length)];
            document.documentElement.style.setProperty('--accent-color', theme.accent);
            document.documentElement.style.setProperty('--bg-image', `url('${theme.bg}')`);
            alert("Theme switched to anime style: " + theme.name);
        }

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
                        document.getElementById('authOverlay').style.display = 'none';
                        document.getElementById('appContainer').style.display = 'flex';
                        document.getElementById('currentLoggedInEmail').innerText = data.email;
                        if (data.is_admin) {
                            document.getElementById('adminControlCard').style.display = 'block';
                            document.getElementById('resetBtn').style.display = 'block';
                        }
                        registerDeviceWithServer(data.email);
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
                    document.getElementById('authOverlay').style.display = 'none';
                    document.getElementById('appContainer').style.display = 'flex';
                    document.getElementById('currentLoggedInEmail').innerText = data.email;
                    if (data.is_admin) {
                        document.getElementById('adminControlCard').style.display = 'block';
                        document.getElementById('resetBtn').style.display = 'block';
                    }
                    registerDeviceWithServer(data.email);
                } else {
                    document.getElementById('authOverlay').style.display = 'flex';
                }
            });
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
                if (data.success) {
                    location.reload();
                } else {
                    document.getElementById('loginError').innerText = data.error;
                }
            });
        }

        function openForgetPassword() {
            const email = prompt("Google Account (Email) ထည့်ပါ:");
            if (!email) return;
            const newPassword = prompt("Password အသစ်အသစ် ထည့်ပါ:");
            if (!newPassword) return;

            fetch('/reset_password_google', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({email: email.trim().toLowerCase(), new_password: newPassword})
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    alert("Password အောင်မြင်စွာ ပြောင်းလဲပြီးပါပြီ။ Login ထပ်ဝင်ပါ။");
                } else {
                    alert("Error: " + data.error);
                }
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

        socket.on('device_status_update', () => {
            fetchDevices();
        });

        function fetchDevices() {
            fetch('/get_devices')
            .then(res => res.json())
            .then(devices => {
                const devId = getDeviceId();
                let currentDev = devices.find(d => d.device_id === devId);
                if (currentDev) {
                    if (currentDev.status === 'pending' && currentDev.account !== 'officialwinmyat@gmail.com') {
                        document.getElementById('pendingOverlay').style.display = 'flex';
                        document.getElementById('overlayDeviceId').value = devId;
                        document.getElementById('overlayStatus').innerText = "Status: Pending Approval ⏳";
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
            });
        }

        function adminAction(devId, action) {
            socket.emit('admin_device_action', {device_id: devId, action: action});
        }

        fetch('/get_history')
        .then(res => res.json())
        .then(data => {
            const stream = document.getElementById('historyStream');
            stream.innerHTML = '';
            data.reverse().forEach(item => appendMessageToStream(item));
        });

        socket.on('broadcast_message', data => {
            appendMessageToStream(data);
        });

        socket.on('message_deleted', data => {
            const el = document.getElementById('msg-box-' + data.id);
            if (el) el.remove();
        });

        function appendMessageToStream(item) {
            const stream = document.getElementById('historyStream');
            const div = document.createElement('div');
            div.className = 'history-item';
            div.id = 'msg-box-' + item.id;
            let contentHtml = '';
            if (item.type === 'text') {
                contentHtml = `<div><b>${item.user}:</b> ${item.content}</div>`;
            } else if (item.type === 'voice') {
                contentHtml = `<div><b>${item.user} [Voice - ${item.store}]:</b><audio controls src="${item.content}" style="width:100%; margin-top:5px;"></audio></div>`;
            } else if (item.type === 'file') {
                if (item.filename && (item.filename.endsWith('.jpg') || item.filename.endsWith('.png') || item.filename.endsWith('.jpeg'))) {
                    contentHtml = `<div><b>${item.user} [Image]:</b><br><img src="${item.content}" class="chat-image-preview"></div>`;
                } else {
                    contentHtml = `<div><b>${item.user} [File]:</b> <a href="${item.content}" download="${item.filename}" style="color:#f472b6;">${item.filename}</a></div>`;
                }
            } else if (item.type === 'videocall_alert') {
                contentHtml = `<div><b>🚨 Anime Video Call Alert:</b> ${item.user} has started a video call!
                    <div style="margin-top: 8px; display: flex; gap: 8px;">
                        <button onclick="acceptVideoCall('${item.user}')" style="background:#16a34a; padding:4px 12px; font-size:12px; width:auto; border-radius:4px;">Accept</button>
                        <button onclick="deleteMessageItem(${item.id})" style="background:#dc2626; padding:4px 12px; font-size:12px; width:auto; border-radius:4px;">Delete</button>
                    </div>
                </div>`;
            }
            
            let actionButtons = '';
            if (item.type === 'text') {
                actionButtons = `<div class="msg-actions"> <button onclick="copyTextContent('${encodeURIComponent(item.content)}')">Copy</button> <button onclick="deleteMessageItem(${item.id})" style="background:#dc2626;">Delete</button> </div>`;
            } else if (item.type === 'voice' || item.type === 'file') {
                actionButtons = `<div class="msg-actions"> <button onclick="saveToDevice('${item.content}', '${item.filename || 'media_file'}')">Save to Device</button> <button onclick="deleteMessageItem(${item.id})" style="background:#dc2626;">Delete</button> </div>`;
            } else if (item.type === 'videocall_alert') {
                actionButtons = `<div class="msg-actions"><button onclick="deleteMessageItem(${item.id})" style="background:#dc2626;">Delete Notification</button></div>`;
            }
            div.innerHTML = contentHtml + (item.type !== 'videocall_alert' ? actionButtons : '') + `<div style="font-size:10px; color:#94a3b8; margin-top:4px;">${item.timestamp}</div>`;
            stream.appendChild(div);
            stream.scrollTop = stream.scrollHeight;
        }

        function copyTextContent(encodedText) {
            const text = decodeURIComponent(encodedText);
            navigator.clipboard.writeText(text).then(() => alert("Copied to clipboard!"));
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
            socket.emit('delete_message_item', {id: id});
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
                    btn.innerText = "Stop Recording (Saving...)";
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
                socket.emit('new_message', {
                    user: document.getElementById('currentLoggedInEmail').innerText,
                    type: 'voice',
                    content: window.tempVoiceData,
                    store: storeType
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
            socket.emit('new_message', {
                user: document.getElementById('currentLoggedInEmail').innerText,
                type: 'text',
                content: content,
                store: '48h'
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
            socket.emit('new_message', {
                user: document.getElementById('currentLoggedInEmail').innerText,
                type: 'file',
                content: selectedFileBase64,
                filename: selectedFileName,
                store: '48h'
            });
            document.getElementById('fileInput').value = '';
            selectedFileBase64 = null;
            document.getElementById('sendFileBtn').disabled = true;
            document.getElementById('sendFileBtn').style.opacity = '0.5';
        }

        // WebRTC & Video Conference Logic
        function triggerVideoCall() {
            const currentUser = document.getElementById('currentLoggedInEmail').innerText;
            socket.emit('trigger_video_call', {user: currentUser});
            socket.emit('new_message', {
                user: currentUser,
                type: 'videocall_alert',
                content: 'Triggered conference',
                store: '5m'
            });
            startConferenceUI(currentUser);
        }

        socket.on('incoming_video_call', data => {
            // Notification handled directly in LiveChat stream items with Accept/Delete buttons.
        });

        function acceptVideoCall(callerUser) {
            startConferenceUI(callerUser);
            // Broadcast join signal to establish peer connections with existing participants
            socket.emit('video_signal', {type: 'join_call', user: document.getElementById('currentLoggedInEmail').innerText});
        }

        function startConferenceUI(callerName) {
            document.getElementById('videoPopup').style.display = 'block';
            document.getElementById('callerInfo').innerText = `Conference Initiated by: ${callerName}`;
            
            navigator.mediaDevices.getUserMedia({video: true, audio: true})
            .then(stream => {
                localStream = stream;
                document.getElementById('localVideo').srcObject = stream;

                // Notify others in room/socket server to connect
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
                if (pc) {
                    await pc.setRemoteDescription(new RTCSessionDescription(data.answer));
                }
            } else if (data.type === 'candidate' && data.target === socket.id) {
                let pc = peerConnections[senderId];
                if (pc && data.candidate) {
                    await pc.addIceCandidate(new RTCIceCandidate(data.candidate));
                }
            }
        });

        function createPeerConnection(remoteSocketId) {
            if (peerConnections[remoteSocketId]) {
                return peerConnections[remoteSocketId];
            }

            let pc = new RTCPeerConnection(servers);
            peerConnections[remoteSocketId] = pc;

            if (localStream) {
                localStream.getTracks().forEach(track => pc.addTrack(track, localStream));
            }

            pc.onicecandidate = event => {
                if (event.candidate) {
                    socket.emit('video_signal', {type: 'candidate', candidate: event.candidate, sender: socket.id, target: remoteSocketId});
                }
            };

            pc.ontrack = event => {
                let gridContainer = document.getElementById('videoGridContainer');
                let remoteVideoId = 'remoteVideo_' + remoteSocketId;
                let existingBox = document.getElementById(remoteVideoId);
                if (!existingBox) {
                    let remoteBox = document.createElement('div');
                    remoteBox.className = 'video-box';
                    remoteBox.id = remoteVideoId;
                    remoteBox.innerHTML = `<video autoplay playsinline></video><div>Participant Stream</div>`;
                    gridContainer.appendChild(remoteBox);
                    existingBox = remoteBox;
                }
                let videoElement = existingBox.querySelector('video');
                if (videoElement && event.streams[0]) {
                    videoElement.srcObject = event.streams[0];
                }
            };

            return pc;
        }

        function toggleMuteSpeaker() {
            if (!localStream) return;
            isSpeakerMuted = !isSpeakerMuted;
            localStream.getAudioTracks().forEach(track => {
                track.enabled = !isSpeakerMuted;
            });
            const btn = document.getElementById('muteSpeakerBtn');
            btn.innerText = isSpeakerMuted ? "Unmute Speaker" : "Mute Speaker";
            btn.style.background = isSpeakerMuted ? "#dc2626" : "#ca8a04";
        }

        function toggleMuteCamera() {
            if (!localStream) return;
            isCameraMuted = !isCameraMuted;
            localStream.getVideoTracks().forEach(track => {
                track.enabled = !isCameraMuted;
            });
            const btn = document.getElementById('muteCameraBtn');
            btn.innerText = isCameraMuted ? "Unmute Camera" : "Mute Camera";
            btn.style.background = isCameraMuted ? "#dc2626" : "#2563eb";
        }

        function stopConference() {
            if (localStream) {
                localStream.getTracks().forEach(track => track.stop());
                localStream = null;
            }
            for (let id in peerConnections) {
                peerConnections[id].close();
            }
            peerConnections = {};
            
            // Remove all remote video boxes
            let gridContainer = document.getElementById('videoGridContainer');
            gridContainer.innerHTML = '<div class="video-box"><video id="localVideo" autoplay muted playsinline></video><div>Local Stream (You)</div></div>';
            
            closePopup();
        }

        function closePopup() {
            document.getElementById('videoPopup').style.display = 'none';
        }

        function resetStorage() {
            if (confirm("Are you sure you want to reset all storage (Live Chat and history)?")) {
                socket.emit('reset_storage');
            }
        }

        socket.on('storage_reset', () => {
            document.getElementById('historyStream').innerHTML = '';
            alert("Storage has been reset.");
        });
   </script>
</body>
</html>
"""

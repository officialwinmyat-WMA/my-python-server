import os
import sqlite3
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template_string, session, redirect, url_for

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "wma_qq_secure_secret_key_123")

import eventlet
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

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    
    # Google Account Login Verification (Using standard SMTP login test to verify Google credentials)
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(email, password)
        server.quit()
        
        session['user_email'] = email
        session['is_admin'] = (email == 'officialwinmyat@gmail.com')
        return jsonify({"success": True, "is_admin": session['is_admin']})
    except Exception as e:
        return jsonify({"success": False, "error": "Invalid Google Account or App Password! မှန်ကန်သော Google Email နှင့် Password/App Password ကို ထည့်ပါ။"})

@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({"success": True})

@app.route('/check_session', methods=['GET'])
def check_session():
    if 'user_email' in session:
        return jsonify({
            "logged_in": True,
            "email": session['user_email'],
            "is_admin": session.get('is_admin', False)
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
            "status": r[2],
            "active": True if r[3] else False,
            "is_current_user_admin": session.get('is_admin', False)
        })
    return jsonify(devices)

@socketio.on('register_device')
def handle_register_device(data):
    dev_id = data.get('device_id')
    google_acc = session.get('user_email', data.get('google_account'))
    
    if not dev_id or not google_acc:
        return

    conn = sqlite3.connect('wma_qq.db')
    cursor = conn.cursor()
    cursor.execute('SELECT status FROM devices WHERE device_id = ?', (dev_id,))
    row = cursor.fetchone()
    
    if not row:
        # New device defaults to pending unless it's the admin
        status = 'approved' if google_acc == 'officialwinmyat@gmail.com' else 'pending'
        cursor.execute('INSERT INTO devices (device_id, google_account, status, last_active) VALUES (?, ?, ?, ?)',
                       (dev_id, google_acc, status, datetime.now()))
        conn.commit()
        if status == 'pending':
            send_approval_email(dev_id, google_acc)
    else:
        cursor.execute('UPDATE devices SET google_account = ?, last_active = ? WHERE device_id = ?',
                       (google_acc, datetime.now(), dev_id))
        conn.commit()
    conn.close()
    socketio.emit('device_status_update', {'device_id': dev_id})

@socketio.on('admin_device_action')
def handle_admin_action(data):
    # Security check: Only officialwinmyat@gmail.com can perform admin actions
    if session.get('user_email') != 'officialwinmyat@gmail.com':
        return

    dev_id = data.get('device_id')
    action = data.get('action') # 'approved', 'banned', 'remove'
    
    conn = sqlite3.connect('wma_qq.db')
    cursor = conn.cursor()
    if action == 'remove':
        cursor.execute('DELETE FROM devices WHERE device_id = ?', (dev_id,))
    else:
        cursor.execute('UPDATE devices SET status = ? WHERE device_id = ?', (action, dev_id))
    conn.commit()
    conn.close()
    socketio.emit('device_status_update', {'device_id': dev_id})

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

        #historyStream { flex: 1; overflow-y: auto; background: var(--chat-bg); border: 2px solid var(--accent-color); border-radius: 8px; padding: 10px; box-sizing: border-box; backdrop-filter: blur(5px); }
        .history-item { padding: 10px; margin-bottom: 8px; background: rgba(255,255,255,0.08); border-left: 6px solid var(--accent-color); border-right: 2px solid var(--accent-color); border-radius: 4px; font-size: 13px; word-break: break-all; }
        .actions { margin-top: 5px; }
        .actions button { width: auto; padding: 4px 8px; font-size: 11px; margin-right: 5px; display: inline-block; border: 1px solid #fff; }

        #resetBtn { position: absolute; top: 15px; right: 15px; z-index: 999; background: #dc2626; color: white; padding: 6px 12px; border-radius: 4px; font-size: 12px; cursor: pointer; width: auto; border: 2px solid var(--accent-color); }
        
        .device-row { display: flex; justify-content: space-between; align-items: center; font-size: 12px; padding: 6px 0; border-bottom: 1px solid rgba(255,255,255,0.2); }
        .badge-active { height: 10px; width: 10px; background-color: #22c55e; border-radius: 50%; display: inline-block; box-shadow: 0 0 8px #22c55e; }
        .badge-inactive { height: 10px; width: 10px; background-color: #64748b; border-radius: 50%; display: inline-block; }
        
        #appContainer { display: none; width: 100%; height: 100vh; }
        #authOverlay, #pendingOverlay { position: fixed; top: 0; left: 0; width: 100%; height: 100vh; background: rgba(15, 23, 42, 0.95); z-index: 9999; display: flex; flex-direction: column; justify-content: center; align-items: center; text-align: center; padding: 20px; }
        #pendingOverlay { display: none; }
    </style>
</head>
<body>

    <!-- Google Account Login Screen -->
    <div id="authOverlay">
        <h2 style="color: #f472b6;">WMA QQ - Google Account Authentication</h2>
        <p style="max-width: 450px; color: #cbd5e1; margin: 15px 0;">ကျေးဇူးပြု၍ သင်၏ Google Email နှင့် Password (သို့မဟုတ် App Password) ဖြင့် ဝင်ရောက်ပါ။</p>
        <div style="background: rgba(255,255,255,0.1); padding: 20px; border-radius: 8px; border: 2px solid var(--accent-color); width: 320px;">
            <input type="email" id="loginEmail" placeholder="Google Email (e.g. user@gmail.com)">
            <input type="password" id="loginPassword" placeholder="Google Password / App Password">
            <button onclick="loginUser()" style="background: var(--accent-color); margin-top: 10px;">Login with Google</button>
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

    <!-- Main Application Container (Shown only when approved) -->
    <div id="appContainer">
        <div class="left-pane">
            <h2>WMA QQ Control Panel</h2>
            <div style="margin-bottom: 10px; font-size: 13px; color: #cbd5e1;">Logged in as: <b id="currentLoggedInEmail" style="color:#f472b6;"></b> <button onclick="logoutUser()" style="width: auto; padding: 2px 8px; font-size: 11px; margin-left: 10px; background:#dc2626;">Logout</button></div>
            
            <div class="card">
                <h4>Girl Anime Themes & Backgrounds</h4>
                <button onclick="autoGenerateSpacialTheme()">Auto Generate Girl Anime Theme</button>
            </div>

            <!-- Admin Control Panel Card (Visible ONLY for officialwinmyat@gmail.com) -->
            <div class="card" id="adminControlCard" style="display: none; border-color: #f59e0b;">
                <h4 style="color: #f59e0b;">👑 Admin Control Panel (Official Win Myat)</h4>
                <p style="font-size: 11px; color: #cbd5e1; margin: 0 0 8px 0;">ဤနေရာမှသာ Device များကို Approve, Ban သို့မဟုတ် Remove လုပ်နိုင်ပါသည်။</p>
                <div style="font-size: 12px; color: #facc15; margin-bottom: 5px;">Active & Pending Devices List:</div>
                <div id="activeDeviceList" style="max-height: 180px; overflow-y: auto; background: rgba(0,0,0,0.4); padding: 8px; border-radius: 6px; border: 1px solid var(--accent-color);"></div>
            </div>

            <div class="card">
                <h4>Function 1: Voice Message (Max 3s)</h4>
                <button id="recBtn" onclick="toggleRecordVoice()">Record Voice (3s)</button>
                <div id="voiceOptions" style="display:none; margin-top: 10px;">
                    <p>Storage Duration ရွေးပါ:</p>
                    <button onclick="sendVoice('5m')">5 Minutes</button>
                    <button onclick="sendVoice('1h')">1 Hour</button>
                    <button onclick="sendVoice('48h')">48 Hours</button>
                </div>
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

    window.onload = function() {
        checkSession();
    };

    function checkSession() {
        fetch('/check_session').then(res => res.json()).then(data => {
            if(data.logged_in) {
                document.getElementById('authOverlay').style.display = 'none';
                document.getElementById('currentLoggedInEmail').innerText = data.email;
                
                let devId = localStorage.getItem('device_unique_id');
                if(!devId) {
                    devId = 'WMA-' + Math.random().toString(36).substring(2, 10).toUpperCase();
                    localStorage.setItem('device_unique_id', devId);
                }
                document.getElementById('overlayDeviceId').value = devId;

                // Register device with backend
                socket.emit('register_device', { device_id: devId });
                checkDeviceStatus();
            } else {
                document.getElementById('authOverlay').style.display = 'flex';
                document.getElementById('appContainer').style.display = 'none';
                document.getElementById('pendingOverlay').style.display = 'none';
            }
        });
    }

    function loginUser() {
        let email = document.getElementById('loginEmail').value.trim();
        let password = document.getElementById('loginPassword').value;
        let errDiv = document.getElementById('loginError');
        errDiv.innerText = "Checking Google credentials... ⏳";

        fetch('/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email: email, password: password })
        }).then(res => res.json()).then(data => {
            if(data.success) {
                checkSession();
            } else {
                errDiv.innerText = data.error;
            }
        });
    }

    function logoutUser() {
        fetch('/logout', { method: 'POST' }).then(() => {
            window.location.reload();
        });
    }

    function checkDeviceStatus() {
        let devId = localStorage.getItem('device_unique_id');
        fetch('/get_devices').then(res => res.json()).then(devices => {
            let currentDev = devices.find(d => d.device_id === devId);
            let isAdmin = devices.length > 0 && devices[0].is_current_user_admin;

            // Show/Hide Admin Card based on officialwinmyat@gmail.com check
            let adminCard = document.getElementById('adminControlCard');
            if(isAdmin) {
                adminCard.style.display = 'block';
                fetchDeviceList();
            } else {
                adminCard.style.display = 'none';
            }

            if(currentDev && currentDev.status === 'approved') {
                document.getElementById('pendingOverlay').style.display = 'none';
                document.getElementById('appContainer').style.display = 'flex';
            } else {
                document.getElementById('pendingOverlay').style.display = 'flex';
                document.getElementById('appContainer').style.display = 'none';
                if(currentDev) {
                    let statusTxt = document.getElementById('overlayStatus');
                    if(currentDev.status === 'banned') {
                        statusTxt.style.color = '#f87171';
                        statusTxt.innerText = "Status: Banned by Admin ❌";
                    } else {
                        statusTxt.style.color = '#facc15';
                        statusTxt.innerText = "Status: Pending approval from officialwinmyat@gmail.com ⏳";
                    }
                }
            }
        });
    }

    socket.on('device_status_update', function(data) {
        checkDeviceStatus();
    });

    function fetchDeviceList() {
        fetch('/get_devices').then(res => res.json()).then(devices => {
            let container = document.getElementById('activeDeviceList');
            if(!container) return;
            container.innerHTML = '';
            devices.forEach(d => {
                let row = document.createElement('div');
                row.className = 'device-row';
                let dotClass = d.active ? 'badge-active' : 'badge-inactive';
                row.innerHTML = `<span><span class="${dotClass}"></span> <b>${d.device_id}</b> (${d.account}) [${d.status}]</span>
                    <span>
                        <button onclick="adminAction('${d.device_id}', 'approved')" style="padding:2px 5px; font-size:10px; background:green;">Approve</button>
                        <button onclick="adminAction('${d.device_id}', 'banned')" style="padding:2px 5px; font-size:10px; background:red;">Ban</button>
                        <button onclick="adminAction('${d.device_id}', 'remove')" style="padding:2px 5px; font-size:10px; background:gray;">Remove</button>
                    </span>`;
                container.appendChild(row);
            });
        });
    }

    function adminAction(devId, action) {
        socket.emit('admin_device_action', { device_id: devId, action: action });
    }

    const girlAnimeThemes = [
        { name: "Beautiful Anime Girl 1", url: "https://images.unsplash.com/photo-1534447677768-be436bb09401?auto=format&fit=crop&w=1920&q=80" },
        { name: "Cyberpunk Anime Princess", url: "https://images.unsplash.com/photo-1607604276583-eef5d076aa5f?auto=format&fit=crop&w=1920&q=80" }
    ];

    function autoGenerateSpacialTheme() {
        let theme = girlAnimeThemes[Math.floor(Math.random() * girlAnimeThemes.length)];
        let randomAccent = '#' + Math.floor(Math.random()*16777215).toString(16);
        document.documentElement.style.setProperty('--accent-color', randomAccent);
        document.documentElement.style.setProperty('--bg-image', `url('${theme.url}')`);
    }
</script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_PAGE)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)

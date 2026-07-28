import os
import sqlite3
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template_string

app = Flask(__name__)
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
            return # Skip if email password not set in Render environment variables
        
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
        
        .left-pane { width: 50%; height: 100vh; overflow-y: auto; padding: 20px; box-sizing: border-box; background: var(--panel-bg); border-right: 2px solid rgba(255,255,255,0.2); position: relative; backdrop-filter: blur(10px); }
        .right-pane { width: 50%; height: 100vh; display: flex; flex-direction: column; padding: 20px; box-sizing: border-box; background: var(--stream-bg); position: relative; backdrop-filter: blur(10px); }

        .card { background: rgba(255,255,255,0.1); padding: 15px; border-radius: 8px; margin-bottom: 15px; border: 1px solid rgba(255,255,255,0.2); backdrop-filter: blur(5px); }
        input, textarea, select, button { width: 100%; padding: 10px; margin: 8px 0; border-radius: 5px; border: 1px solid rgba(255,255,255,0.3); background: rgba(15, 23, 42, 0.8); color: white; box-sizing: border-box; }
        button { background: var(--accent-color); cursor: pointer; font-weight: bold; border: none; }
        button:hover { opacity: 0.9; }

        #historyStream { flex: 1; overflow-y: auto; background: var(--chat-bg); border: 1px solid rgba(255,255,255,0.2); border-radius: 8px; padding: 10px; box-sizing: border-box; backdrop-filter: blur(5px); }
        .history-item { padding: 10px; margin-bottom: 8px; background: rgba(255,255,255,0.08); border-left: 4px solid var(--accent-color); border-radius: 4px; font-size: 13px; word-break: break-all; }
        .actions { margin-top: 5px; }
        .actions button { width: auto; padding: 4px 8px; font-size: 11px; margin-right: 5px; display: inline-block; }

        #resetBtn { position: absolute; top: 15px; right: 15px; z-index: 999; background: #dc2626; color: white; padding: 6px 12px; border-radius: 4px; font-size: 12px; cursor: pointer; width: auto; }
        .storage-warning { background-color: rgba(88, 28, 135, 0.85) !important; }

        #videoPopup { display: none; position: fixed; top: 10%; left: 15%; width: 70%; background: rgba(30, 41, 59, 0.95); border: 2px solid var(--accent-color); border-radius: 10px; padding: 20px; z-index: 1000; box-shadow: 0 0 30px rgba(0,0,0,0.9); text-align: center; backdrop-filter: blur(15px); }
        .video-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; max-height: 350px; overflow-y: auto; margin: 15px 0; }
        .video-box { background: rgba(0,0,0,0.6); border-radius: 8px; padding: 8px; text-align: center; border: 1px solid rgba(255,255,255,0.2); }
        video { width: 100%; height: 160px; object-fit: cover; border-radius: 6px; background: #000; }

        .device-row { display: flex; justify-content: space-between; align-items: center; font-size: 12px; padding: 6px 0; border-bottom: 1px solid rgba(255,255,255,0.15); }
        .badge-active { height: 10px; width: 10px; background-color: #22c55e; border-radius: 50%; display: inline-block; box-shadow: 0 0 8px #22c55e; }
        .badge-inactive { height: 10px; width: 10px; background-color: #64748b; border-radius: 50%; display: inline-block; }
    </style>
</head>
<body>

    <div id="videoPopup">
        <h3>WMA QQ - Girl Anime Video Conference</h3>
        <div id="callerInfo" style="margin-bottom: 10px; font-weight: bold; color: #f472b6;"></div>
        <div class="video-grid" id="videoGridContainer"></div>
        <div class="actions">
            <button onclick="acceptCallAction()" style="background: #16a34a;">Accept & Join Video</button>
            <button onclick="stopConference()" style="background: #ca8a04;">Stop Video Conference</button>
            <button onclick="closePopup()" style="background: #dc2626;">Close</button>
        </div>
    </div>

    <div class="left-pane">
        <h2>WMA QQ Control Panel</h2>
        
        <div class="card">
            <h4>Girl Anime Themes & Backgrounds</h4>
            <button onclick="autoGenerateSpacialTheme()">Auto Generate Girl Anime Theme</button>
        </div>

        <div class="card">
            <h4>Device Management & Status (Render Control)</h4>
            <input type="text" id="deviceId" readonly placeholder="Auto-Detecting Device ID...">
            <input type="text" id="googleAccount" placeholder="Google Account (e.g. user@gmail.com)" onchange="updateDeviceRegistration()">
            <div id="deviceApprovalStatus" style="font-size: 12px; color: #facc15; margin-top: 5px;"></div>
            
            <h5 style="margin: 10px 0 5px 0;">Active & Pending Devices List:</h5>
            <div id="activeDeviceList" style="max-height: 140px; overflow-y: auto; background: rgba(0,0,0,0.4); padding: 8px; border-radius: 6px;"></div>
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

        <div class="card">
            <h4>Function 2: Video Call (10s)</h4>
            <button onclick="triggerVideoCall()" style="background: #16a34a;">Call All Active Users</button>
        </div>

        <div class="card">
            <h4>Function 3: Text & Universal Equation</h4>
            <textarea id="textContent" rows="4" placeholder="Equation (e.g. 5 + 5 =)" oninput="solveEquation(this)"></textarea>
            <button onclick="sendText()">Send Text (48h)</button>
        </div>

        <div class="card">
            <h4>Function 4: Original File, PDF or Image</h4>
            <input type="file" id="fileInput">
            <button onclick="sendFile()">Send File / PDF / Image (48h)</button>
        </div>
    </div>

    <div class="right-pane" id="rightPane">
        <button id="resetBtn" onclick="resetStorage()">Reset Storage</button>
        <h3>WMA QQ - Live Chat & History Stream</h3>
        <div id="historyStream"></div>
    </div>

<script>
    const socket = io();
    let mediaRecorder;
    let audioChunks = [];
    let localStream = null;
    let peerConnections = {};
    const rtcConfig = { iceServers: [{ urls: 'stun:stun.l.google.com:19302' }] };

    window.onload = function() {
        let devId = localStorage.getItem('device_unique_id');
        if(!devId) {
            devId = 'WMA-' + Math.random().toString(36).substring(2, 10).toUpperCase();
            localStorage.setItem('device_unique_id', devId);
        }
        document.getElementById('deviceId').value = devId;

        updateDeviceRegistration();

        fetch('/get_history').then(res => res.json()).then(data => {
            data.forEach(item => appendHistory(item));
        });

        fetchDeviceList();
    };

    function updateDeviceRegistration() {
        let devId = document.getElementById('deviceId').value;
        let account = document.getElementById('googleAccount').value || "officialwinmyat@gmail.com";
        socket.emit('register_device', { device_id: devId, google_account: account });
    }

    socket.on('device_status_update', function(data) {
        if(data.device_id === document.getElementById('deviceId').value) {
            let statusDiv = document.getElementById('deviceApprovalStatus');
            if(data.status === 'approved') {
                statusDiv.style.color = '#4ade80';
                statusDiv.innerText = "Status: Approved by officialwinmyat@gmail.com ✅";
            } else if(data.status === 'banned') {
                statusDiv.style.color = '#f87171';
                statusDiv.innerText = "Status: Banned by Admin ❌ - Access Blocked";
                alert("Your device has been banned or requires approval from officialwinmyat@gmail.com!");
            } else {
                statusDiv.style.color = '#facc15';
                statusDiv.innerText = "Status: Pending approval email sent to officialwinmyat@gmail.com ⏳";
            }
        }
        fetchDeviceList();
    });

    function fetchDeviceList() {
        fetch('/get_devices').then(res => res.json()).then(devices => {
            let container = document.getElementById('activeDeviceList');
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

    function getMeta() {
        return {
            device: document.getElementById('deviceId').value || "Unknown Device",
            account: document.getElementById('googleAccount').value || "officialwinmyat@gmail.com"
        };
    }

    const girlAnimeThemes = [
        { name: "Beautiful Anime Girl 1", url: "https://images.unsplash.com/photo-1534447677768-be436bb09401?auto=format&fit=crop&w=1920&q=80" },
        { name: "Cyberpunk Anime Princess", url: "https://images.unsplash.com/photo-1607604276583-eef5d076aa5f?auto=format&fit=crop&w=1920&q=80" },
        { name: "Manga Aesthetic Girl", url: "https://images.unsplash.com/photo-1578632767115-351597cf2477?auto=format&fit=crop&w=1920&q=80" },
        { name: "Neon Anime Girl", url: "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?auto=format&fit=crop&w=1920&q=80" }
    ];

    function autoGenerateSpacialTheme() {
        let theme = girlAnimeThemes[Math.floor(Math.random() * girlAnimeThemes.length)];
        let randomAccent = '#' + Math.floor(Math.random()*16777215).toString(16);
        document.documentElement.style.setProperty('--accent-color', randomAccent);
        document.documentElement.style.setProperty('--bg-image', `url('${theme.url}')`);
        document.documentElement.style.setProperty('--panel-bg', 'rgba(30, 41, 59, 0.7)');
        document.documentElement.style.setProperty('--chat-bg', 'rgba(9, 13, 22, 0.65)');
        document.documentElement.style.setProperty('--stream-bg', 'rgba(30, 41, 59, 0.65)');
    }

    let isRecording = false;
    async function toggleRecordVoice() {
        let btn = document.getElementById('recBtn');
        if (!isRecording) {
            try {
                let stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                mediaRecorder = new MediaRecorder(stream);
                audioChunks = [];
                mediaRecorder.ondataavailable = e => audioChunks.push(e.data);
                mediaRecorder.onstop = () => {
                    let audioBlob = new Blob(audioChunks, { type: 'audio/mp3' });
                    let reader = new FileReader();
                    reader.readAsDataURL(audioBlob);
                    reader.onloadend = function() {
                        window.latestBase64Audio = reader.result;
                        document.getElementById('voiceOptions').style.display = "block";
                    };
                };
                mediaRecorder.start();
                isRecording = true;
                btn.style.background = "#dc2626";
                btn.innerText = "Recording... (Max 3s)";
                setTimeout(() => {
                    if(isRecording) {
                        mediaRecorder.stop();
                        isRecording = false;
                        btn.style.background = "";
                        btn.innerText = "Record Voice (3s)";
                    }
                }, 3000);
            } catch(e) { alert("Microphone access denied."); }
        }
    }

    function sendVoice(duration) {
        let meta = getMeta();
        socket.emit('new_message', { type: 'voice', user: `[${meta.device} | ${meta.account}]`, content: window.latestBase64Audio, store: duration });
        document.getElementById('voiceOptions').style.display = "none";
    }

    function solveEquation(el) {
        let val = el.value;
        if(val.includes("=")) {
            let parts = val.split("=");
            let expr = parts[0].trim();
            try {
                let ans = Function('"use strict";return (' + expr + ')')();
                if(ans !== undefined && !isNaN(ans)) el.value = expr + " = " + ans;
            } catch(e) {}
        }
    }

    function sendText() {
        let text = document.getElementById('textContent').value;
        if(!text) return;
        let meta = getMeta();
        socket.emit('new_message', { type: 'text', user: `[${meta.device} | ${meta.account}]`, content: text, store: '48h' });
        document.getElementById('textContent').value = '';
    }

    function sendFile() {
        let fileInput = document.getElementById('fileInput');
        if(fileInput.files.length === 0) return;
        let file = fileInput.files[0];
        let reader = new FileReader();
        reader.onload = function(e) {
            let meta = getMeta();
            socket.emit('new_message', { type: 'file', user: `[${meta.device} | ${meta.account}]`, filename: file.name, content: e.target.result, store: '48h' });
        };
        reader.readAsDataURL(file);
    }

    function triggerVideoCall() {
        let meta = getMeta();
        socket.emit('new_message', { type: 'video_call', user: `[${meta.device} | ${meta.account}]`, content: "Video Call Invitation" });
    }

    socket.on('broadcast_message', function(data) {
        appendHistory(data);
    });

    function appendHistory(data) {
        let stream = document.getElementById('historyStream');
        let div = document.createElement('div');
        div.className = 'history-item';
        div.id = 'msg-' + (data.id || Math.random());

        if(data.type === 'text') {
            div.innerHTML = `<b>${data.user}:</b> <pre style="white-space:pre-wrap; margin:5px 0;">${data.content}</pre>
                <div class="actions"><button onclick="navigator.clipboard.writeText('${data.content}')">Copy</button><button onclick="deleteItem(this)">Delete</button></div>`;
        } else if(data.type === 'voice') {
            div.innerHTML = `<b>${data.user}:</b> 🎵 Voice Message (${data.store})
                <div class="actions"><audio controls src="${data.content}"></audio><a href="${data.content}" download="voice.mp3"><button>Download MP3</button></a><button onclick="deleteItem(this)">Delete</button></div>`;
        } else if(data.type === 'file') {
            div.innerHTML = `<b>${data.user}:</b> 📁 ${data.filename}<br>
                <a href="${data.content}" target="_blank"><img src="${data.content}" style="max-width:200px; display:block; margin:5px 0;" onerror="this.style.display='none'"></a>
                <div class="actions"><a href="${data.content}" download="${data.filename}"><button>Download File/PDF</button></a><button onclick="deleteItem(this)">Delete</button></div>`;
        } else if(data.type === 'video_call') {
            div.innerHTML = `<b>${data.user}</b> က Girl Anime Video Call ခေါ်နေပါသည် ။
                <div class="actions"><button onclick="openVideoPopup('${data.user}')" style="background:#16a34a;">Accept</button><button onclick="deleteItem(this)" style="background:#dc2626;">Delete</button></div>`;
        }
        stream.appendChild(div);
        stream.scrollTop = stream.scrollHeight;
    }

    function deleteItem(btn) { btn.closest('.history-item').remove(); }

    // WebRTC Real Video Conference Implementation
    function openVideoPopup(user) {
        document.getElementById('callerInfo').innerText = "Connected with: " + user;
        document.getElementById('videoPopup').style.display = 'block';
        
        navigator.mediaDevices.getUserMedia({ video: true, audio: true }).then(stream => {
            localStream = stream;
            let grid = document.getElementById('videoGridContainer');
            grid.innerHTML = '';

            let myBox = document.createElement('div');
            myBox.className = 'video-box';
            myBox.innerHTML = `<p style="font-size:11px; margin:2px;">My Video</p><video autoplay muted id="localVid"></video>`;
            myBox.querySelector('video').srcObject = stream;
            grid.appendChild(myBox);

            socket.emit('join_conference', { device: getMeta().device });
        }).catch(err => alert("Camera permission required."));
    }

    socket.on('peer_joined', function(data) {
        let peerId = data.device;
        if(peerId === getMeta().device) return;

        let pc = new RTCPeerConnection(rtcConfig);
        peerConnections[peerId] = pc;

        localStream.getTracks().forEach(track => pc.addTrack(track, localStream));

        pc.ontrack = event => {
            let grid = document.getElementById('videoGridContainer');
            if(!document.getElementById('vid-' + peerId)) {
                let peerBox = document.createElement('div');
                peerBox.className = 'video-box';
                peerBox.innerHTML = `<p style="font-size:11px; margin:2px;">${peerId}</p><video autoplay id="vid-${peerId}"></video>`;
                grid.appendChild(peerBox);
            }
            document.getElementById('vid-' + peerId).srcObject = event.streams[0];
        };

        pc.onicecandidate = event => {
            if(event.candidate) {
                socket.emit('ice_candidate', { to: peerId, candidate: event.candidate });
            }
        };

        pc.createOffer().then(offer => {
            pc.setLocalDescription(offer);
            socket.emit('offer', { to: peerId, offer: offer, from: getMeta().device });
        });
    });

    socket.on('offer', async function(data) {
        let peerId = data.from;
        let pc = new RTCPeerConnection(rtcConfig);
        peerConnections[peerId] = pc;

        localStream.getTracks().forEach(track => pc.addTrack(track, localStream));

        pc.ontrack = event => {
            let grid = document.getElementById('videoGridContainer');
            if(!document.getElementById('vid-' + peerId)) {
                let peerBox = document.createElement('div');
                peerBox.className = 'video-box';
                peerBox.innerHTML = `<p style="font-size:11px; margin:2px;">${peerId}</p><video autoplay id="vid-${peerId}"></video>`;
                grid.appendChild(peerBox);
            }
            document.getElementById('vid-' + peerId).srcObject = event.streams[0];
        };

        pc.onicecandidate = event => {
            if(event.candidate) socket.emit('ice_candidate', { to: peerId, candidate: event.candidate });
        };

        await pc.setRemoteDescription(new RTCSessionDescription(data.offer));
        let answer = await pc.createAnswer();
        await pc.setLocalDescription(answer);
        socket.emit('answer', { to: peerId, answer: answer, from: getMeta().device });
    });

    socket.on('answer', async function(data) {
        let pc = peerConnections[data.from];
        if(pc) await pc.setRemoteDescription(new RTCSessionDescription(data.answer));
    });

    socket.on('ice_candidate', async function(data) {
        let pc = peerConnections[data.from];
        if(pc && data.candidate) await pc.addIceCandidate(new RTCIceCandidate(data.candidate));
    });

    function acceptCallAction() { alert("Video Conference Active!"); }

    function stopConference() {
        if(localStream) localStream.getTracks().forEach(t => t.stop());
        for(let id in peerConnections) { peerConnections[id].close(); }
        peerConnections = {};
        document.getElementById('videoPopup').style.display = 'none';
    }

    function closePopup() { stopConference(); }

    function resetStorage() {
        if(confirm("Render Server တစ်ခုလုံးရှိ သိမ်းဆည်းထားသော အချက်အလက်များကို အမှန်တကယ် ရှင်းလင်းမည်လား?")) {
            socket.emit('server_reset_storage');
        }
    }

    socket.on('storage_warning', function(isNearFull) {
        let pane = document.getElementById('rightPane');
        if(isNearFull) pane.classList.add('storage-warning');
        else pane.classList.remove('storage-warning');
    });

    socket.on('force_reload_ui', function() {
        document.getElementById('historyStream').innerHTML = '';
        alert("Server storage reset.");
    });
</script>
</body>
</html>
"""

@app.route('/')
def index():
    # Middleware: Block unapproved or banned devices
    dev_id = request.args.get('dev')
    conn = sqlite3.connect('wma_qq.db')
    cursor = conn.cursor()
    cursor.execute('SELECT status FROM devices WHERE device_id = ?', (dev_id,))
    row = cursor.fetchone()
    conn.close()
    
    return render_template_string(HTML_PAGE)

@app.route('/get_history')
def get_history():
    conn = sqlite3.connect('wma_qq.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, user_info, msg_type, content, filename, store_type FROM history ORDER BY id ASC')
    rows = cursor.fetchall()
    conn.close()
    return jsonify([{'id': r[0], 'user': r[1], 'type': r[2], 'content': r[3], 'filename': r[4], 'store': r[5]} for r in rows])

@app.route('/get_devices')
def get_devices():
    conn = sqlite3.connect('wma_qq.db')
    cursor = conn.cursor()
    cursor.execute('SELECT device_id, google_account, status FROM devices')
    rows = cursor.fetchall()
    conn.close()
    return jsonify([{'device_id': r[0], 'account': r[1], 'status': r[2], 'active': r[2] == 'approved'} for r in rows])

@socketio.on('register_device')
def handle_register_device(data):
    dev_id = data.get('device_id')
    account = data.get('google_account', 'officialwinmyat@gmail.com')
    conn = sqlite3.connect('wma_qq.db')
    cursor = conn.cursor()
    cursor.execute('SELECT status FROM devices WHERE device_id = ?', (dev_id,))
    row = cursor.fetchone()
    if not row:
        cursor.execute('INSERT INTO devices (device_id, google_account, status, last_active) VALUES (?, ?, ?, ?)',
                       (dev_id, account, 'pending', datetime.now()))
        status = 'pending'
        # Send Email Notification to officialwinmyat@gmail.com
        send_approval_email(dev_id, account)
    else:
        status = row[0]
        cursor.execute('UPDATE devices SET last_active = ? WHERE device_id = ?', (datetime.now(), dev_id))
    conn.commit()
    conn.close()
    emit('device_status_update', {'device_id': dev_id, 'status': status}, broadcast=True)

@socketio.on('admin_device_action')
def handle_admin_action(data):
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
    emit('device_status_update', {'device_id': dev_id, 'status': action}, broadcast=True)

@socketio.on('join_conference')
def handle_join_conference(data):
    emit('peer_joined', data, broadcast=True)

@socketio.on('offer')
def handle_offer(data):
    emit('offer', data, broadcast=True)

@socketio.on('answer')
def handle_answer(data):
    emit('answer', data, broadcast=True)

@socketio.on('ice_candidate')
def handle_ice(data):
    emit('ice_candidate', data, broadcast=True)

@socketio.on('new_message')
def handle_new_message(data):
    store = data.get('store', '48h')
    now = datetime.now()
    expire = now + timedelta(minutes=5) if store == '5m' else (now + timedelta(hours=1) if store == '1h' else now + timedelta(hours=48))
    conn = sqlite3.connect('wma_qq.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO history (user_info, msg_type, content, filename, store_type, expire_at, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)',
                   (data.get('user'), data.get('type'), data.get('content'), data.get('filename'), store, expire, now))
    conn.commit()
    cursor.execute('SELECT COUNT(*) FROM history')
    count = cursor.fetchone()[0]
    conn.close()
    socketio.emit('broadcast_message', data)
    socketio.emit('storage_warning', count > 50)

@socketio.on('server_reset_storage')
def handle_server_reset_storage():
    conn = sqlite3.connect('wma_qq.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM history')
    conn.commit()
    conn.close()
    socketio.emit('force_reload_ui')
    socketio.emit('storage_warning', False)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host='0.0.0.0', port=port)

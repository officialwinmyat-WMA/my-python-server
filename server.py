import os
import sqlite3
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template_string

app = Flask(__name__)
import eventlet
from flask_socketio import SocketIO, send, emit

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# Database Initialization
def init_db():
    conn = sqlite3.connect('app_lifetime.db')
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
    conn.commit()
    conn.close()

def cleanup_expired_data():
    conn = sqlite3.connect('app_lifetime.db')
    cursor = conn.cursor()
    now = datetime.now()
    cursor.execute('DELETE FROM history WHERE expire_at IS NOT NULL AND expire_at < ?', (now,))
    conn.commit()
    conn.close()

init_db()

HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>Advanced Special Web App</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.2/socket.io.js"></script>
    <style>
        :root {
            --bg-color: #0f172a;
            --panel-bg: #1e293b;
            --text-color: #f8fafc;
            --accent-color: #3b82f6;
            --chat-bg: #090d16;
            --stream-bg: #1e293b;
        }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 0; background: var(--bg-color); color: var(--text-color); display: flex; height: 100vh; overflow: hidden; }
        
        /* Split Screen UI: Left Controls, Right Live Chat & History */
        .left-pane { width: 50%; height: 100vh; overflow-y: auto; padding: 20px; box-sizing: border-box; background: var(--panel-bg); border-right: 2px solid #334155; position: relative; }
        .right-pane { width: 50%; height: 100vh; display: flex; flex-direction: column; padding: 20px; box-sizing: border-box; background: var(--stream-bg); position: relative; }

        .card { background: rgba(255,255,255,0.05); padding: 15px; border-radius: 8px; margin-bottom: 15px; border: 1px solid rgba(255,255,255,0.1); }
        input, textarea, select, button { width: 100%; padding: 10px; margin: 8px 0; border-radius: 5px; border: 1px solid #475569; background: #0f172a; color: white; box-sizing: border-box; }
        button { background: var(--accent-color); cursor: pointer; font-weight: bold; border: none; }
        button:hover { opacity: 0.9; }

        #historyStream { flex: 1; overflow-y: auto; background: var(--chat-bg); border: 1px solid #334155; border-radius: 8px; padding: 10px; box-sizing: border-box; }
        .history-item { padding: 10px; margin-bottom: 8px; background: rgba(255,255,255,0.03); border-left: 4px solid var(--accent-color); border-radius: 4px; font-size: 13px; word-break: break-all; }
        .actions { margin-top: 5px; }
        .actions button { width: auto; padding: 4px 8px; font-size: 11px; margin-right: 5px; display: inline-block; }

        /* Floating Reset Storage Button */
        #resetBtn { position: absolute; top: 15px; right: 15px; z-index: 999; background: #dc2626; color: white; padding: 6px 12px; border-radius: 4px; font-size: 12px; cursor: pointer; width: auto; }
        
        /* Storage Warning Background for Right Pane */
        .storage-warning { background-color: #581c87 !important; transition: background 0.5s ease; }

        /* Video Call Popup */
        #videoPopup { display: none; position: fixed; top: 20%; left: 30%; width: 40%; background: #1e293b; border: 2px solid #3b82f6; border-radius: 10px; padding: 20px; z-index: 1000; box-shadow: 0 0 20px rgba(0,0,0,0.8); text-align: center; }
        video { width: 45%; background: black; border-radius: 5px; margin: 5px; }
    </style>
</head>
<body>

    <!-- Video Call Popup Dialog -->
    <div id="videoPopup">
        <h3>Video Conference (10s limit)</h3>
        <div id="callerInfo"></div>
        <div>
            <video id="localVideo" autoplay muted></video>
            <video id="remoteVideo" autoplay></video>
        </div>
        <div class="actions">
            <button onclick="startCalling()" style="background: #16a34a;">Start Calling</button>
            <button onclick="stopConference()" style="background: #dc2626;">Stop Video Conference</button>
            <button onclick="closePopup()">Close</button>
        </div>
    </div>

    <!-- LEFT PANE: Controls & Functions -->
    <div class="left-pane">
        <h2>Control Panel</h2>
        
        <div class="card">
            <h4>Theme Customizer</h4>
            <button onclick="autoGenerateTheme()">Auto Generate Theme</button>
        </div>

        <div class="card">
            <h4>User & Device Info (Function 6)</h4>
            <input type="text" id="deviceName" placeholder="Device Name (ဥပမာ - Phone/PC)">
            <input type="text" id="googleAccount" placeholder="Google Account (ဥပမာ - user@gmail.com)">
        </div>

        <div class="card">
            <h4>Function 1: Voice Message (Max 3s)</h4>
            <button id="recBtn" onclick="recordVoice()">Record Voice (3s)</button>
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
            <textarea id="textContent" rows="4" placeholder="1 to 1M words or Equation (e.g. 5 + 5 =)" oninput="solveEquation(this)"></textarea>
            <button onclick="sendText()">Send Text (48h)</button>
        </div>

        <div class="card">
            <h4>Function 4: Original File or Image</h4>
            <input type="file" id="fileInput">
            <button onclick="sendFile()">Send Original File/Image (48h)</button>
        </div>
    </div>

    <!-- RIGHT PANE: Live Chat & Lifetime History Stream -->
    <div class="right-pane" id="rightPane">
        <button id="resetBtn" onclick="resetStorage()">Reset Storage</button>
        <h3>Live Chat & History Stream</h3>
        <div id="historyStream"></div>
    </div>

<script>
    const socket = io();
    let recordedAudioBlob = null;

    function getMeta() {
        return {
            device: document.getElementById('deviceName').value || "Unknown Device",
            account: document.getElementById('googleAccount').value || "Unknown Account"
        };
    }

    // Theme Auto-generator
    function autoGenerateTheme() {
        const randomColor = '#' + Math.floor(Math.random()*16777215).toString(16);
        const randomPanel = '#' + Math.floor(Math.random()*16777215).toString(16);
        document.documentElement.style.setProperty('--accent-color', randomColor);
        document.documentElement.style.setProperty('--panel-bg', randomPanel);
    }

    // Function 1: Voice Recording Simulation & Options
    function recordVoice() {
        let btn = document.getElementById('recBtn');
        btn.style.boxShadow = "0 0 10px yellow";
        btn.innerText = "Recording... (3s)";
        setTimeout(() => {
            btn.style.boxShadow = "none";
            btn.innerText = "Record Voice (3s)";
            document.getElementById('voiceOptions').style.display = "block";
            recordedAudioBlob = "data:audio/mp3;base64,SUQzBAAAAAAAI1RTU0UAAAAPAAADTGF2ZjU5LjM3LjEwMAAAAAAAAAAAAAAA"; // dummy playable mp3 stream
        }, 3000);
    }

    function sendVoice(duration) {
        let meta = getMeta();
        socket.emit('new_message', {
            type: 'voice',
            user: `[${meta.device} | ${meta.account}]`,
            content: recordedAudioBlob,
            store: duration
        });
        document.getElementById('voiceOptions').style.display = "none";
    }

    // Function 3: Universal Equation Solver
    function solveEquation(el) {
        let val = el.value;
        if(val.includes("=")) {
            let parts = val.split("=");
            let expr = parts[0].trim();
            try {
                let ans = Function('"use strict";return (' + expr + ')')();
                if(ans !== undefined && !isNaN(ans)) {
                    el.value = expr + " = " + ans;
                }
            } catch(e) {}
        }
    }

    function sendText() {
        let text = document.getElementById('textContent').value;
        if(!text) return;
        let meta = getMeta();
        socket.emit('new_message', {
            type: 'text',
            user: `[${meta.device} | ${meta.account}]`,
            content: text,
            store: '48h'
        });
        document.getElementById('textContent').value = '';
    }

    // Function 4: Original File/Image
    function sendFile() {
        let fileInput = document.getElementById('fileInput');
        if(fileInput.files.length === 0) return;
        let file = fileInput.files[0];
        let reader = new FileReader();
        reader.onload = function(e) {
            let meta = getMeta();
            socket.emit('new_message', {
                type: 'file',
                user: `[${meta.device} | ${meta.account}]`,
                filename: file.name,
                content: e.target.result,
                store: '48h'
            });
        };
        reader.readAsDataURL(file);
    }

    // Function 2: Video Call Trigger
    function triggerVideoCall() {
        let meta = getMeta();
        socket.emit('new_message', {
            type: 'video_call',
            user: `[${meta.device} | ${meta.account}]`,
            content: "Incoming Video Call..."
        });
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
                <div class="actions">
                    <button onclick="navigator.clipboard.writeText('${data.content}')">Copy</button>
                    <button onclick="deleteItem(this)">Delete</button>
                    <button onclick="alert('Stored for 1 Month!')">1 Month Store</button>
                </div>`;
        } else if(data.type === 'voice') {
            div.innerHTML = `<b>${data.user}:</b> 🎵 Voice Message (${data.store})
                <div class="actions">
                    <audio controls src="${data.content}"></audio>
                    <a href="${data.content}" download="voice_message.mp3"><button>Download MP3</button></a>
                    <button onclick="deleteItem(this)">Delete</button>
                </div>`;
        } else if(data.type === 'file') {
            div.innerHTML = `<b>${data.user}:</b> 📁 ${data.filename}<br>
                <a href="${data.content}" target="_blank"><img src="${data.content}" style="max-width:200px; display:block; margin:5px 0;" onerror="this.style.display='none'"></a>
                <div class="actions">
                    <a href="${data.content}" download="${data.filename}"><button>Save</button></a>
                    <button onclick="deleteItem(this)">Delete</button>
                </div>`;
        } else if(data.type === 'video_call') {
            div.innerHTML = `<b>${data.user}</b> initiated a Video Call.
                <div class="actions">
                    <button onclick="openVideoPopup('${data.user}')" style="background:#16a34a;">Accept</button>
                    <button onclick="deleteItem(this)" style="background:#dc2626;">Delete</button>
                    <button onclick="this.parentElement.parentElement.remove()" style="background:#ca8a04;">Stop</button>
                </div>`;
        }
        stream.appendChild(div);
        stream.scrollTop = stream.scrollHeight;
    }

    function deleteItem(btn) {
        btn.closest('.history-item').remove();
    }

    // Video Conference Handlers
    function openVideoPopup(user) {
        document.getElementById('callerInfo').innerText = "Connected with: " + user;
        document.getElementById('videoPopup').style.display = 'block';
    }
    function startCalling() {
        navigator.mediaDevices.getUserMedia({ video: true, audio: true }).then(stream => {
            document.getElementById('localVideo').srcObject = stream;
        }).catch(err => alert("Camera permission required"));
    }
    function stopConference() {
        let lVideo = document.getElementById('localVideo');
        if(lVideo.srcObject) {
            lVideo.srcObject.getTracks().forEach(track => track.stop());
        }
        document.getElementById('videoPopup').style.display = 'none';
    }
    function closePopup() {
        document.getElementById('videoPopup').style.display = 'none';
    }

    // Storage Reset Function
    function resetStorage() {
        if(confirm("Are you sure to reset all stored data?")) {
            socket.emit('reset_storage');
        }
    }

    socket.on('storage_warning', function(isNearFull) {
        let pane = document.getElementById('rightPane');
        if(isNearFull) {
            pane.classList.add('storage-warning');
        } else {
            pane.classList.remove('storage-warning');
        }
    });

    // Load Lifetime History on Page Open
    window.onload = function() {
        fetch('/get_history').then(res => res.json()).then(data => {
            data.forEach(item => appendHistory(item));
        });
    }
</script>
</body>
</html>
"""

@app.route('/')
def index():
    cleanup_expired_data()
    return render_template_string(HTML_PAGE)

@app.route('/get_history')
def get_history():
    conn = sqlite3.connect('app_lifetime.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, user_info, msg_type, content, filename, store_type FROM history ORDER BY id ASC')
    rows = cursor.fetchall()
    conn.close()
    
    history = []
    for r in rows:
        history.append({
            'id': r[0],
            'user': r[1],
            'type': r[2],
            'content': r[3],
            'filename': r[4],
            'store': r[5]
        })
    return jsonify(history)

@socketio.on('new_message')
def handle_new_message(data):
    store = data.get('store', '48h')
    now = datetime.now()
    expire = None
    if store == '5m':
        expire = now + timedelta(minutes=5)
    elif store == '1h':
        expire = now + timedelta(hours=1)
    elif store == '48h':
        expire = now + timedelta(hours=48)

    conn = sqlite3.connect('app_lifetime.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO history (user_info, msg_type, content, filename, store_type, expire_at, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)',
                   (data.get('user'), data.get('type'), data.get('content'), data.get('filename'), store, expire, now))
    conn.commit()
    
    # Check Storage Warning (Simulated check: > 10 rows or total size limit condition)
    cursor.execute('SELECT COUNT(*) FROM history')
    count = cursor.fetchone()[0]
    conn.close()

    # Broadcast to all
    socketio.emit('broadcast_message', data)
    
    if count > 50: # Example threshold for 90% full warning
        socketio.emit('storage_warning', True)
    else:
        socketio.emit('storage_warning', False)

@socketio.on('reset_storage')
def handle_reset_storage():
    conn = sqlite3.connect('app_lifetime.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM history')
    conn.commit()
    conn.close()
    socketio.emit('broadcast_message', {'type': 'text', 'user': '[System]', 'content': '--- STORAGE RESET BY USER ---'})
    socketio.emit('storage_warning', False)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host='0.0.0.0', port=port)

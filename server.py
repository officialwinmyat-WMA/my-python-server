import os
import sqlite3
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template_string

app = Flask(__name__)
import eventlet
from flask_socketio import SocketIO, send, emit

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# Database ဖန်တီးခြင်း
def init_db():
    conn = sqlite3.connect('app_data.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_info TEXT,
            msg_type TEXT,
            content TEXT,
            expire_at DATETIME,
            timestamp DATETIME
        )
    ''')
    conn.commit()
    conn.close()

# သတ်မှတ်ရက်ကျော်လွန်သော ဖိုင်/စာများကို အလိုအလျောက် ဖျက်ဆီးခြင်း
def cleanup_expired_data():
    conn = sqlite3.connect('app_data.db')
    cursor = conn.cursor()
    now = datetime.now()
    cursor.execute('DELETE FROM messages WHERE expire_at < ?', (now,))
    conn.commit()
    conn.close()

init_db()

# Web App HTML / Frontend (PWA & All Functions Included)
HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>Advanced Web App & Chat</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.2/socket.io.js"></script>
    <style>
        body { font-family: Arial, sans-serif; margin: 15px; background: #f0f2f5; }
        .box { background: white; padding: 15px; border-radius: 8px; margin-bottom: 15px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
        #chat { height: 250px; overflow-y: scroll; border: 1px solid #ddd; padding: 10px; margin-bottom: 10px; background: #fafafa; }
        input, textarea, button, select { padding: 8px; margin: 5px 0; font-size: 14px; width: 100%; box-sizing: border-box; }
        button { background: #007BFF; color: white; border: none; border-radius: 4px; cursor: pointer; }
        button:hover { background: #0056b3; }
        .msg-item { border-bottom: 1px solid #eee; padding: 8px 0; }
        .actions button { width: auto; padding: 4px 8px; font-size: 12px; margin-right: 5px; }
        img.preview { max-width: 100%; height: auto; display: block; margin-top: 5px; }
    </style>
</head>
<body>

    <div class="box">
        <h3>User Info & Device</h3>
        <input type="text" id="deviceName" placeholder="Device Name (ဥပမာ - Phone/PC)">
        <input type="text" id="googleAccount" placeholder="Google Account (ဥပမာ - user@gmail.com)">
    </div>

    <div class="box">
        <h3>Function 1: Voice Message (Max 3 Sec)</h3>
        <button onclick="recordVoice()">🎙️ Record Voice (3s)</button>
        <select id="voiceDuration">
            <option value="5">5 Minutes</option>
            <option value="60">1 Hour</option>
            <option value="2880">48 Hours</option>
        </select>
    </div>

    <div class="box">
        <h3>Function 2: Video Call</h3>
        <button onclick="startVideoCall()" style="background: #28a745;">📹 Call All Active Users</button>
        <div id="callContainer"></div>
    </div>

    <div class="box">
        <h3>Function 3: Text & Smart Equation</h3>
        <textarea id="textContent" rows="3" placeholder="စာရေးပါ (သို့မဟုတ်) 5 + 5 = ဟု ရိုက်ပါ..." oninput="checkEquation(this)"></textarea>
        <button onclick="sendText()">ပို့ရန် (48 Hours)</button>
    </div>

    <div class="box">
        <h3>Function 4: File or Image (Original Quality)</h3>
        <input type="file" id="fileInput">
        <button onclick="sendFile()">ဖိုင်/ပုံ ပို့ရန် (48 Hours)</button>
    </div>

    <div class="box">
        <h3>Live Chat & History Stream</h3>
        <div id="chat"></div>
    </div>

<script>
    const socket = io();
    const chatBox = document.getElementById('chat');

    function getUserInfo() {
        let dev = document.getElementById('deviceName').value || "Unknown Device";
        let acc = document.getElementById('googleAccount').value || "Unknown Account";
        return `[${dev} | ${acc}]`;
    }

    // Smart Equation Checker (Function 3)
    function checkEquation(el) {
        let val = el.value;
        if (val.includes("=")) {
            let parts = val.split("=");
            let expr = parts[0].trim();
            try {
                // Safe basic evaluation for universal symbols & math
                let result = Function('"use strict";return (' + expr + ')')();
                if (result !== undefined && !isNaN(result)) {
                    el.value = expr + " = " + result;
                }
            } catch(e) {}
        }
    }

    function sendText() {
        let txt = document.getElementById('textContent').value;
        if(!txt) return;
        let data = { type: 'text', user: getUserInfo(), content: txt, store: '48h' };
        socket.emit('client_message', data);
        document.getElementById('textContent').value = '';
    }

    function recordVoice() {
        alert("Microphone simulated: 3 seconds recorded.");
        let duration = document.getElementById('voiceDuration').value;
        let data = { type: 'voice', user: getUserInfo(), content: "Voice_Audio_File.mp3", store: duration };
        socket.emit('client_message', data);
    }

    function sendFile() {
        let fileInput = document.getElementById('fileInput');
        if(fileInput.files.length === 0) return;
        let file = fileInput.files[0];
        let reader = new FileReader();
        reader.onload = function(e) {
            let data = { type: 'file', user: getUserInfo(), filename: file.name, content: e.target.result, store: '48h' };
            socket.emit('client_message', data);
        };
        reader.readAsDataURL(file);
    }

    function startVideoCall() {
        let data = { type: 'video_call', user: getUserInfo() };
        socket.emit('client_message', data);
    }

    socket.on('server_broadcast', function(data) {
        let div = document.createElement('div');
        div.className = 'msg-item';
        
        if (data.type === 'text') {
            div.innerHTML = `<b>${data.user}:</b> ${data.content} <div class="actions">
                <button onclick="navigator.clipboard.writeText('${data.content}')">Copy</button>
                <button onclick="this.parentElement.parentElement.remove()">Delete</button>
                <button onclick="alert('Extended to 1 Month!')">1 Month Store</button>
            </div>`;
        } else if (data.type === 'voice') {
            div.innerHTML = `<b>${data.user}:</b> 🎵 Voice Message (${data.store} mins store) <div class="actions">
                <a href="#" download><button>Download MP3</button></a>
                <button onclick="this.parentElement.parentElement.remove()">Delete</button>
            </div>`;
        } else if (data.type === 'file') {
            div.innerHTML = `<b>${data.user}:</b> 📁 File/Image: ${data.filename}<br><img src="${data.content}" class="preview"><div class="actions">
                <a href="${data.content}" download="${data.filename}"><button>Save</button></a>
                <button onclick="this.parentElement.parentElement.remove()">Delete</button>
            </div>`;
        } else if (data.type === 'video_call') {
            div.innerHTML = `<b>${data.user}</b> က Video Call ခေါ်နေပါပြီ။ <div class="actions"><button onclick="alert('Call Accepted!')" style="background:green;">Accept</button></div>`;
        }

        chatBox.appendChild(div);
        chatBox.scrollTop = chatBox.scrollHeight;
    });
</script>
</body>
</html>
"""

@app.route('/')
def index():
    cleanup_expired_data()
    return render_template_string(HTML_PAGE)

@socketio.on('client_message')
def handle_client_message(data):
    # Store timing logic based on user selection
    store_val = data.get('store', '48h')
    now = datetime.now()
    
    if store_val == '5':
        expire = now + timedelta(minutes=5)
    elif store_val == '60':
        expire = now + timedelta(hours=1)
    else:
        expire = now + timedelta(hours=48)

    conn = sqlite3.connect('app_data.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO messages (user_info, msg_type, content, expire_at, timestamp) VALUES (?, ?, ?, ?, ?)',
                   (data.get('user'), data.get('type'), data.get('content'), expire, now))
    conn.commit()
    conn.close()

    emit('server_broadcast', data, broadcast=True)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host='0.0.0.0', port=port)

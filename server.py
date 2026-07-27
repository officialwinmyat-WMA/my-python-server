import os
import sqlite3
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template_string

app = Flask(__name__)
# Render တွင် eventlet ဖြင့် အလုပ်လုပ်ရန်
import eventlet
from flask_socketio import SocketIO, send, emit

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# Database ဖန်တီးခြင်း
def init_db():
    conn = sqlite3.connect('messages.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message TEXT,
            timestamp DATETIME
        )
    ''')
    conn.commit()
    conn.close()

def cleanup_old_messages():
    conn = sqlite3.connect('messages.db')
    cursor = conn.cursor()
    week_ago = datetime.now() - timedelta(days=7)
    cursor.execute('DELETE FROM messages WHERE timestamp < ?', (week_ago,))
    conn.commit()
    conn.close()

init_db()

# ဖုန်း သို့မဟုတ် PC Browser မှ တိုက်ရိုက်ဝင်သုံးနိုင်သော Chat Page
HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>Web Chat & Alert</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.2/socket.io.js"></script>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #f4f4f9; }
        #chat { background: white; padding: 15px; border-radius: 8px; height: 300px; overflow-y: scroll; border: 1px solid #ccc; margin-bottom: 10px; }
        input, button { padding: 10px; font-size: 16px; }
        input { width: 70%; }
        button { width: 25%; background: #007BFF; color: white; border: none; border-radius: 4px; cursor: pointer; }
        button:hover { background: #0056b3; }
    </style>
</head>
<body>
    <h2>Real-time Chat & Alert</h2>
    <div id="chat"></div>
    <input id="msg" type="text" placeholder="စာရိုက်ရန်..." autocomplete="off">
    <button onclick="sendMsg()">ပို့ရန်</button>
    <br><br>
    <button onclick="sendSound()" style="background: #28a745; width: 100%;">🔊 အသံ မက်ဆေ့ဂျ် ပို့ရန်</button>

    <script>
        const socket = io();
        const chatBox = document.getElementById('chat');

        socket.on('message', function(data) {
            let p = document.createElement('p');
            p.innerText = data;
            chatBox.appendChild(p);
            chatBox.scrollTop = chatBox.scrollHeight;
            
            if (data.includes("AUDIO_ALERT")) {
                alert("🔊 အသံ မက်ဆေ့ဂျ် ရောက်ရှိလာပါပြီ!");
            }
        });

        function sendMsg() {
            let input = document.getElementById('msg');
            if (input.value.trim() !== '') {
                socket.send(input.value);
                let p = document.createElement('p');
                p.innerText = "You: " + input.value;
                p.style.color = "blue";
                chatBox.appendChild(p);
                input.value = '';
                chatBox.scrollTop = chatBox.scrollHeight;
            }
        }

        function sendSound() {
            let alertMsg = "AUDIO_ALERT: တစ်ယောက်ယောက်မှ အသံမက်ဆေ့ဂျ် ပို့လိုက်ပါပြီ။";
            socket.send(alertMsg);
            let p = document.createElement('p');
            p.innerText = "You sent an Audio Alert!";
            p.style.color = "green";
            chatBox.appendChild(p);
            chatBox.scrollTop = chatBox.scrollHeight;
        }
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    cleanup_old_messages()
    return render_template_string(HTML_PAGE)

@socketio.on('message')
def handle_message(data):
    print(f"လက်ခံရရှိသော မက်ဆေ့ဂျ်: {data}")
    conn = sqlite3.connect('messages.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO messages (message, timestamp) VALUES (?, ?)', (data, datetime.now()))
    conn.commit()
    conn.close()
    
    send(data, broadcast=True, include_self=False)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host='0.0.0.0', port=port)

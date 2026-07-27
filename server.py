import os
import sqlite3
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from flask_socketio import SocketIO, send, emit

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# Database ဖန်တီးခြင်း (စာသားများကို ၇ ရက်စာ သိမ်းရန်)
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

# ၇ ရက်ထက် ကျော်လွန်သော မက်ဆေ့ဂျ်ဟောင်းများကို ဖျက်ဆီးခြင်း
def cleanup_old_messages():
    conn = sqlite3.connect('messages.db')
    cursor = conn.cursor()
    week_ago = datetime.now() - timedelta(days=7)
    cursor.execute('DELETE FROM messages WHERE timestamp < ?', (week_ago,))
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def index():
    cleanup_old_messages()
    return "Server with 7-day message storage is running successfully!"

@app.route('/history', methods=['GET'])
def get_history():
    cleanup_old_messages()
    conn = sqlite3.connect('messages.db')
    cursor = conn.cursor()
    cursor.execute('SELECT message, timestamp FROM messages ORDER BY id DESC')
    rows = cursor.fetchall()
    conn.close()
    
    history = [{"message": row[0], "time": row[1]} for row in rows]
    return jsonify(history)

@socketio.on('message')
def handle_message(data):
    print(f"လက်ခံရရှိသော မက်ဆေ့ဂျ်: {data}")
    
    # တွေ့ရသော မက်ဆေ့ဂျ်ကို Database တွင် သိမ်းဆည်းရန်
    conn = sqlite3.connect('messages.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO messages (message, timestamp) VALUES (?, ?)', (data, datetime.now()))
    conn.commit()
    conn.close()
    
    # ချိတ်ဆက်ထားသူ အားလုံးထံသို့ ပို့ပေးခြင်း
    send(data, broadcast=True, include_self=False)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host='0.0.0.0', port=port)

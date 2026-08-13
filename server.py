import os
import sqlite3
import random
import base64
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template_string, session, send_file

# Python compatibility fix for gevent
import sys
from gevent import monkey
try:
    monkey.patch_all(ssl=False)
except Exception:
    pass

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "wma_qq_secure_secret_key_123")

from flask_socketio import SocketIO, emit
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

# Master Key 852456 ကို ၄ နေရာခွဲမြှုပ်၍ လုံခြုံရေးနှင့် လိုင်စင် ခွင့်ပြုချက်အတွက် အသုံးပြုထားခြင်း[cite: 1]
MK_PART_1 = "852"
MK_PART_2 = "456"
LICENSE_CHECK_1 = "officialwinmyat"
LICENSE_CHECK_2 = "@gmail.com"

def get_master_key():
    return MK_PART_1 + MK_PART_2

def get_admin_email():
    return LICENSE_CHECK_1 + LICENSE_CHECK_2

def init_db():
    conn = sqlite3.connect('wma_qq_private.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_info TEXT,
            msg_type TEXT,
            content TEXT,
            filename TEXT,
            store_type TEXT,
            room TEXT,
            expire_at DATETIME,
            timestamp DATETIME
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT UNIQUE,
            google_account TEXT,
            status TEXT,
            last_active DATETIME
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            password TEXT,
            device_id TEXT,
            remember_token TEXT,
            verification_code TEXT,
            is_verified INTEGER DEFAULT 0,
            account_duration TEXT DEFAULT '3 months',
            signup_time DATETIME,
            status TEXT DEFAULT 'pending',
            username TEXT,
            age INTEGER,
            sex TEXT,
            country TEXT,
            province TEXT,
            city TEXT,
            profile_pic_1 TEXT,
            profile_pic_2 TEXT,
            profile_pic_3 TEXT,
            profile_pic_4 TEXT,
            profile_pic_5 TEXT,
            active_profile_pic TEXT,
            rose_bought INTEGER DEFAULT 0,
            orchid_bought INTEGER DEFAULT 0,
            jasmine_bought INTEGER DEFAULT 0,
            rose_received INTEGER DEFAULT 0,
            orchid_received INTEGER DEFAULT 0,
            jasmine_received INTEGER DEFAULT 0,
            redeemed_items TEXT DEFAULT ''
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admin_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            box_type TEXT UNIQUE,
            price REAL,
            redeem_value REAL
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def clean_expired_history():
    try:
        conn = sqlite3.connect('wma_qq_private.db')
        cursor = conn.cursor()
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute('DELETE FROM history WHERE expire_at < ?', (now_str,))
        conn.commit()
        conn.close()
    except Exception as e:
        print("Cleanup error:", e)

@app.route('/')
def index():
    return render_template_string(HTML_PAGE)

@app.route('/ping')
def ping():
    return "OK", 200

@app.route('/manifest.json')
def serve_manifest():
    return send_file('manifest.json', mimetype='application/manifest+json')

@app.route('/sw.js')
def serve_sw():
    return send_file('sw.js', mimetype='application/javascript')

@app.route('/admin_login', methods=['POST'])
def admin_login():
    data = request.json
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    master_key = data.get('master_key', '').strip()
    
    expected_master_key = get_master_key()
    admin_mail = get_admin_email()
    
    if email == admin_mail and master_key == expected_master_key:
        session['user_email'] = email
        session['is_admin'] = True
        return jsonify({"success": True, "is_admin": True})
    return jsonify({"success": False, "error": "Master Key သို့မဟုတ် Admin အချက်အလက် မှားယွင်းနေပါသည်။"})

@app.route('/signup', methods=['POST'])
def signup():
    data = request.json
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    device_id = data.get('device_id', '')
    username = data.get('username', '').strip()
    
    if not email or not password:
        return jsonify({"success": False, "error": "Email နှင့် Password ထည့်ရန် လိုအပ်ပါသည်။"})
    
    try:
        conn = sqlite3.connect('wma_qq_private.db')
        cursor = conn.cursor()
        
        cursor.execute('SELECT status FROM devices WHERE device_id = ?', (device_id,))
        dev_row = cursor.fetchone()
        if dev_row and dev_row[0] == 'banned':
            conn.close()
            return jsonify({"success": False, "error": "ဤ Device အား Ban ထားပါသဖြင့် Sign up လုပ်၍ မရပါ။"})
            
        cursor.execute('SELECT id, is_verified, status FROM users WHERE email = ?', (email,))
        existing = cursor.fetchone()
        
        now = datetime.now()
        admin_mail = get_admin_email()
        master_key = get_master_key()

        if email == admin_mail:
            if existing:
                cursor.execute('UPDATE users SET password = ?, device_id = ?, signup_time = ?, status = "verified", is_verified = 1 WHERE email = ?', (password, device_id, now, email))
            else:
                cursor.execute('INSERT INTO users (email, password, device_id, is_verified, account_duration, signup_time, verification_code, status, username) VALUES (?, ?, ?, 1, "life time", ?, ?, "verified", ?)', (email, password, device_id, now, master_key, username or 'Admin'))
            conn.commit()
            conn.close()
            session['user_email'] = email
            session['is_admin'] = True
            return jsonify({"success": True, "requires_verification": False, "is_admin": True})

        if existing:
            if existing[1] == 1 and existing[2] == 'verified':
                conn.close()
                return jsonify({"success": False, "error": "ဤ Email ဖြင့် အကောင့်ရှိပြီးသား ဖြစ်ပါသည်။ Login ဝင်ပါ။"})
            else:
                cursor.execute('UPDATE users SET password = ?, device_id = ?, signup_time = ?, status = "pending", username = ? WHERE email = ?', (password, device_id, now, username, email))
        else:
            default_code = "".join([str(random.randint(0, 9)) for _ in range(6)])
            cursor.execute('INSERT INTO users (email, password, device_id, is_verified, account_duration, signup_time, verification_code, status, username) VALUES (?, ?, ?, 0, "3 months", ?, ?, "pending", ?)', (email, password, device_id, now, default_code, username))
        
        conn.commit()
        conn.close()
            
        return jsonify({"success": True, "requires_verification": True})
    except Exception as e:
        print(f"Signup Error for {email} | Error: {str(e)}", flush=True)
        return jsonify({"success": False, "error": str(e)})

@app.route('/verify_code', methods=['POST'])
def verify_code():
    data = request.json
    email = data.get('email', '').strip().lower()
    code = data.get('code', '').strip()
    
    conn = sqlite3.connect('wma_qq_private.db')
    cursor = conn.cursor()
    cursor.execute('SELECT signup_time, verification_code FROM users WHERE email = ?', (email,))
    row = cursor.fetchone()
    
    admin_mail = get_admin_email()
    master_key = get_master_key()

    if email == admin_mail and code == master_key:
        cursor.execute('UPDATE users SET is_verified = 1, status = "verified" WHERE email = ?', (email,))
        conn.commit()
        conn.close()
        session['user_email'] = email
        session['is_admin'] = True
        return jsonify({"success": True, "is_admin": True})

    if row:
        signup_time_str = row[0]
        assigned_code = row[1]
        
        if signup_time_str:
            signup_time = datetime.strptime(signup_time_str, '%Y-%m-%d %H:%M:%S.%f' if '.' in signup_time_str else '%Y-%m-%d %H:%M:%S')
            if datetime.now() - signup_time > timedelta(minutes=15):
                conn.close()
                return jsonify({"success": False, "error": "Verification သက်တမ်း ၁၅ မိနစ် ကျော်လွန်သွားပါပြီ။ Code ထပ်တောင်းပါ။"})
        
        if assigned_code and assigned_code == code:
            cursor.execute('UPDATE users SET is_verified = 1, status = "verified" WHERE email = ?', (email,))
            conn.commit()
            conn.close()
            
            session['user_email'] = email
            is_admin = (email == admin_mail)
            session['is_admin'] = is_admin
            return jsonify({"success": True, "is_admin": is_admin})
            
    conn.close()
    return jsonify({"success": False, "error": "Verification Code မှားယွင်းနေပါသည် သို့မဟုတ် Admin မှ မချပေးသေးပါ။"})

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    remember = data.get('remember', False)
    device_id = data.get('device_id', '')
    
    conn = sqlite3.connect('wma_qq_private.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT status FROM devices WHERE device_id = ?', (device_id,))
    dev_row = cursor.fetchone()
    if dev_row and dev_row[0] == 'banned':
        conn.close()
        return jsonify({"success": False, "error": "ဤ Device အား Ban ထားပါသည်။"})

    cursor.execute('SELECT password, is_verified, device_id, account_duration, status FROM users WHERE email = ?', (email,))
    row = cursor.fetchone()
    
    admin_mail = get_admin_email()

    if row:
        stored_password, is_verified, stored_device_id, account_duration, user_status = row
        if user_status == 'banned':
            conn.close()
            return jsonify({"success": False, "error": "ဤအကောင့်အား Ban ထားပါသည်။"})
        if is_verified == 0 or user_status != 'verified':
            conn.close()
            return jsonify({"success": False, "error": "အကောင့်ကို Code ဖြင့် အတည်ပြုပြီးသား မရှိသေးပါ။"})
            
        if stored_password == password and (stored_device_id == device_id or not stored_device_id):
            session['user_email'] = email
            is_admin = (email == admin_mail)
            session['is_admin'] = is_admin
            
            token = ""
            if remember:
                token = f"token_{email}_{device_id}"
                cursor.execute('UPDATE users SET remember_token = ?, device_id = ? WHERE email = ?', (token, device_id, email))
                conn.commit()
            else:
                cursor.execute('UPDATE users SET device_id = ? WHERE email = ?', (device_id, email))
                conn.commit()
            
            conn.close()
            return jsonify({"success": True, "is_admin": is_admin, "remember_token": token, "account_duration": account_duration})
        else:
            conn.close()
            return jsonify({"success": False, "error": "Password သို့မဟုတ် Device ID မမှန်ကန်ပါ။"})
    else:
        conn.close()
        return jsonify({"success": False, "error": "ဤ Email ဖြင့် အကောင့်မရှိပါ။"})

@app.route('/check_remember', methods=['POST'])
def check_remember():
    data = request.json
    email = data.get('email', '').strip().lower()
    token = data.get('token', '')
    device_id = data.get('device_id', '')
    
    if not email or not token or not device_id:
        return jsonify({"logged_in": False})
        
    conn = sqlite3.connect('wma_qq_private.db')
    cursor = conn.cursor()
    cursor.execute('SELECT remember_token, device_id, account_duration, status FROM users WHERE email = ?', (email,))
    row = cursor.fetchone()
    conn.close()
    
    admin_mail = get_admin_email()

    if row and row[0] == token and row[3] != 'banned':
        session['user_email'] = email
        is_admin = (email == admin_mail)
        session['is_admin'] = is_admin
        return jsonify({"logged_in": True, "email": email, "is_admin": is_admin, "account_duration": row[2]})
    
    return jsonify({"logged_in": False})

@app.route('/reset_password_google', methods=['POST'])
def reset_password_google():
    data = request.json
    email = data.get('email', '').strip().lower()
    new_password = data.get('new_password', '')
    
    if not email or not new_password:
        return jsonify({"success": False, "error": "Email နှင့် Password အသစ်ထည့်ရန် လိုအပ်ပါသည်။"})
        
    conn = sqlite3.connect('wma_qq_private.db')
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
        admin_mail = get_admin_email()
        is_admin = (email == admin_mail)
        session['is_admin'] = is_admin
        
        conn = sqlite3.connect('wma_qq_private.db')
        cursor = conn.cursor()
        cursor.execute('SELECT account_duration, status FROM users WHERE email = ?', (email,))
        row = cursor.fetchone()
        conn.close()
        
        if row and row[1] == 'banned':
            session.clear()
            return jsonify({"logged_in": False})
            
        duration = row[0] if row else '3 months'
        
        return jsonify({
            "logged_in": True,
            "email": email,
            "is_admin": is_admin,
            "account_duration": duration
        })
    return jsonify({"logged_in": False})

@app.route('/get_user_profile', methods=['GET'])
def get_user_profile():
    email = request.args.get('email', '').strip().lower()
    if not email and 'user_email' in session:
        email = session['user_email']
    if not email:
        return jsonify({"success": False, "error": "Unauthorized"})
    
    conn = sqlite3.connect('wma_qq_private.db')
    cursor = conn.cursor()
    cursor.execute('''SELECT username, age, sex, country, province, city, 
                      profile_pic_1, profile_pic_2, profile_pic_3, profile_pic_4, profile_pic_5, active_profile_pic,
                      rose_bought, orchid_bought, jasmine_bought, rose_received, orchid_received, jasmine_received, redeemed_items
                      FROM users WHERE email = ?''', (email,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return jsonify({"success": False, "error": "User not found"})
        
    return jsonify({
        "success": True,
        "username": row[0] or '',
        "age": row[1],
        "sex": row[2] or '',
        "country": row[3] or '',
        "province": row[4] or '',
        "city": row[5] or '',
        "pictures": [row[6], row[7], row[8], row[9], row[10]],
        "active_profile_pic": row[11] or '',
        "rose_bought": row[12] or 0,
        "orchid_bought": row[13] or 0,
        "jasmine_bought": row[14] or 0,
        "rose_received": row[15] or 0,
        "orchid_received": row[16] or 0,
        "jasmine_received": row[17] or 0,
        "redeemed_items": row[18] or ''
    })

@app.route('/update_user_profile', methods=['POST'])
def update_user_profile():
    if 'user_email' not in session:
        return jsonify({"success": False, "error": "Unauthorized"})
    email = session['user_email']
    data = request.json
    
    username = data.get('username', '').strip()
    age = data.get('age')
    sex = data.get('sex', '').strip()
    country = data.get('country', '').strip()
    province = data.get('province', '').strip()
    city = data.get('city', '').strip()
    pictures = data.get('pictures', [])
    active_pic = data.get('active_profile_pic', '')

    conn = sqlite3.connect('wma_qq_private.db')
    cursor = conn.cursor()
    
    if username:
        if len(username) > 15:
            conn.close()
            return jsonify({"success": False, "error": "Username must be max 15 letters"})
        cursor.execute('SELECT id FROM users WHERE username = ? AND email != ?', (username, email))
        if cursor.fetchone():
            conn.close()
            return jsonify({"success": False, "error": "Username already taken"})

    cursor.execute('''UPDATE users SET username = COALESCE(?, username), 
                      age = COALESCE(?, age), sex = COALESCE(?, sex), 
                      country = COALESCE(?, country), province = COALESCE(?, province), city = COALESCE(?, city),
                      profile_pic_1 = COALESCE(?, profile_pic_1), profile_pic_2 = COALESCE(?, profile_pic_2),
                      profile_pic_3 = COALESCE(?, profile_pic_3), profile_pic_4 = COALESCE(?, profile_pic_4),
                      profile_pic_5 = COALESCE(?, profile_pic_5), active_profile_pic = COALESCE(?, active_profile_pic)
                      WHERE email = ?''', 
                   (username if username else None, age, sex if sex else None, 
                    country if country else None, province if province else None, city if city else None,
                    pictures[0] if len(pictures)>0 and pictures[0] else None,
                    pictures[1] if len(pictures)>1 and pictures[1] else None,
                    pictures[2] if len(pictures)>2 and pictures[2] else None,
                    pictures[3] if len(pictures)>3 and pictures[3] else None,
                    pictures[4] if len(pictures)>4 and pictures[4] else None,
                    active_pic if active_pic else None, email))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/get_admin_all_lists', methods=['GET'])
def get_admin_all_lists():
    admin_mail = get_admin_email()
    if session.get('user_email') != admin_mail:
        return jsonify({"pending": [], "verified": [], "banned": []})
    
    conn = sqlite3.connect('wma_qq_private.db')
    cursor = conn.cursor()
    
    fifteen_mins_ago = datetime.now() - timedelta(minutes=15)
    cursor.execute('SELECT email, device_id, verification_code, account_duration, signup_time FROM users WHERE (signup_time >= ? OR is_verified = 0) AND status != "banned" AND email != ? ORDER BY signup_time DESC', (fifteen_mins_ago, admin_mail))
    pending_rows = cursor.fetchall()
    
    cursor.execute('SELECT email, device_id, account_duration, signup_time FROM users WHERE is_verified = 1 AND status = "verified" AND email != ? ORDER BY signup_time DESC', (admin_mail,))
    verified_rows = cursor.fetchall()
    
    cursor.execute('SELECT email, device_id, account_duration, signup_time FROM users WHERE status = "banned" AND email != ? ORDER BY signup_time DESC', (admin_mail,))
    banned_rows = cursor.fetchall()
    
    conn.close()
    
    pending_list = []
    for r in pending_rows:
        pending_list.append({
            "email": r[0],
            "device_id": r[1],
            "verification_code": r[2] or '',
            "account_duration": r[3] or '3 months',
            "signup_time": r[4]
        })
        
    verified_list = []
    for r in verified_rows:
        verified_list.append({
            "email": r[0],
            "device_id": r[1],
            "account_duration": r[2] or '3 months',
            "signup_time": r[3]
        })
        
    banned_list = []
    for r in banned_rows:
        banned_list.append({
            "email": r[0],
            "device_id": r[1],
            "account_duration": r[2] or '3 months',
            "signup_time": r[3]
        })
        
    return jsonify({
        "pending": pending_list,
        "verified": verified_list,
        "banned": banned_list
    })

@app.route('/admin_update_user_settings', methods=['POST'])
def admin_update_user_settings():
    admin_mail = get_admin_email()
    if session.get('user_email') != admin_mail:
        return jsonify({"success": False, "error": "Unauthorized"})
        
    data = request.json
    email = data.get('email', '').strip().lower()
    code = data.get('verification_code', '').strip()
    duration = data.get('account_duration', '3 months')
    action = data.get('action', '')
    
    conn = sqlite3.connect('wma_qq_private.db')
    cursor = conn.cursor()
    
    if action == 'remove':
        cursor.execute('DELETE FROM users WHERE email = ?', (email,))
        cursor.execute('DELETE FROM devices WHERE google_account = ?', (email,))
    elif action == 'ban':
        cursor.execute('UPDATE users SET status = "banned" WHERE email = ?', (email,))
        cursor.execute('UPDATE devices SET status = "banned" WHERE google_account = ?', (email,))
    elif action == 'unban':
        cursor.execute('UPDATE users SET status = "verified", is_verified = 1 WHERE email = ?', (email,))
        cursor.execute('UPDATE devices SET status = "approved" WHERE google_account = ?', (email,))
    else:
        if code:
            cursor.execute('UPDATE users SET verification_code = ?, account_duration = ? WHERE email = ?', (code, duration, email))
        else:
            cursor.execute('UPDATE users SET account_duration = ? WHERE email = ?', (duration, email))
            
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/get_devices', methods=['GET'])
def get_devices():
    if 'user_email' not in session:
        return jsonify([])
    conn = sqlite3.connect('wma_qq_private.db')
    cursor = conn.cursor()
    cursor.execute('SELECT device_id, google_account, status, last_active FROM devices')
    rows = cursor.fetchall()
    conn.close()
    
    admin_mail = get_admin_email()
    devices = []
    for r in rows:
        devices.append({
            "device_id": r[0],
            "account": r[1],
            "status": 'approved' if r[1] == admin_mail else r[2],
            "active": True if r[3] else False,
            "is_current_user_admin": session.get('user_email') == admin_mail
        })
    return jsonify(devices)

@app.route('/get_history', methods=['GET'])
def get_history():
    room = request.args.get('room', 'main_group')
    clean_expired_history()
    conn = sqlite3.connect('wma_qq_private.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, user_info, msg_type, content, filename, store_type, room, timestamp FROM history WHERE room = ? ORDER BY id DESC', (room,))
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
            "room": r[6],
            "timestamp": r[7]
        })
    return jsonify(history)

@socketio.on('register_device')
def handle_register_device(data):
    dev_id = data.get('device_id')
    google_acc = session.get('user_email', data.get('google_account', ''))
    if not dev_id or not google_acc:
        return
        
    conn = sqlite3.connect('wma_qq_private.db')
    cursor = conn.cursor()
    cursor.execute('SELECT status FROM devices WHERE device_id = ?', (dev_id,))
    row = cursor.fetchone()
    
    admin_mail = get_admin_email()
    status = 'approved' if google_acc == admin_mail else ('approved' if row and row[0] == 'approved' else 'pending')
    
    if not row:
        cursor.execute('INSERT INTO devices (device_id, google_account, status, last_active) VALUES (?, ?, ?, ?)', (dev_id, google_acc, status, datetime.now()))
        conn.commit()
    else:
        cursor.execute('UPDATE devices SET google_account = ?, status = ?, last_active = ? WHERE device_id = ?', (google_acc, status, datetime.now(), dev_id))
        conn.commit()
    conn.close()
    socketio.emit('device_status_update', {'device_id': dev_id})
    socketio.emit('online_users_refresh')

@socketio.on('join_room')
def handle_join_room(data):
    from flask_socketio import join_room
    room = data.get('room')
    if room:
        join_room(room)

@socketio.on('new_message')
def handle_new_message(data):
    user = data.get('user')
    msg_type = data.get('type')
    content = data.get('content')
    filename = data.get('filename', '')
    store = data.get('store', '48 Hours Auto-Delete')
    room = data.get('room', 'main_group')
    
    now = datetime.now()
    expire_at = now + timedelta(hours=48)
        
    conn = sqlite3.connect('wma_qq_private.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO history (user_info, msg_type, content, filename, store_type, room, expire_at, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                   (user, msg_type, content, filename, store, room, expire_at.strftime('%Y-%m-%d %H:%M:%S'), now.strftime('%Y-%m-%d %H:%M:%S')))
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
        "room": room,
        "timestamp": now.strftime('%Y-%m-%d %H:%M:%S')
    }, room=room)

@socketio.on('delete_message_item')
def handle_delete_message(data):
    msg_id = data.get('id')
    room = data.get('room', 'main_group')
    if msg_id:
        conn = sqlite3.connect('wma_qq_private.db')
        cursor = conn.cursor()
        cursor.execute('DELETE FROM history WHERE id = ?', (msg_id,))
        conn.commit()
        conn.close()
        socketio.emit('message_deleted', {"id": msg_id}, room=room)

@socketio.on('trigger_video_call')
def handle_video_call(data):
    socketio.emit('incoming_video_call', data)

@socketio.on('video_signal')
def handle_video_signal(data):
    socketio.emit('video_signal_relay', data)

@socketio.on('reset_storage')
def handle_reset():
    admin_mail = get_admin_email()
    if session.get('user_email') == admin_mail:
        conn = sqlite3.connect('wma_qq_private.db')
        cursor = conn.cursor()
        cursor.execute('DELETE FROM history')
        conn.commit()
        conn.close()
        socketio.emit('storage_reset')

@socketio.on('admin_sell_presents')
def handle_admin_sell_presents(data):
    user_email = data.get('email')
    rose = int(data.get('rose', 0))
    orchid = int(data.get('orchid', 0))
    jasmine = int(data.get('jasmine', 0))
    
    conn = sqlite3.connect('wma_qq_private.db')
    cursor = conn.cursor()
    cursor.execute('SELECT rose_bought, orchid_bought, jasmine_bought FROM users WHERE email = ?', (user_email,))
    row = cursor.fetchone()
    if row:
        new_rose = row[0] + rose
        new_orchid = row[1] + orchid
        new_jasmine = row[2] + jasmine
        cursor.execute('UPDATE users SET rose_bought = ?, orchid_bought = ?, jasmine_bought = ? WHERE email = ?', (new_rose, new_orchid, new_jasmine, user_email))
        conn.commit()
    conn.close()
    socketio.emit('presents_sold_success', {'email': user_email, 'rose_bought': new_rose if row else rose, 'orchid_bought': new_orchid if row else orchid, 'jasmine_bought': new_jasmine if row else jasmine})

HTML_PAGE = """<!DOCTYPE html>
<html>
<head>
    <title>WeMeet - Private & Group Anime Chat Hub</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="manifest" href="/manifest.json">
    <meta name="theme-color" content="#ec4899">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.2/socket.io.js"></script>
    <style>
        :root {
            --bg-color: #0f172a;
            --panel-bg: rgba(20, 24, 33, 0.65);
            --text-color: #f8fafc;
            --accent-color: #ec4899;
            --chat-bg: rgba(10, 14, 23, 0.55);
            --stream-bg: rgba(20, 24, 33, 0.55);
            --bg-image: url('https://images.unsplash.com/photo-1578632767115-351597cf2477?auto=format&fit=crop&w=1920&q=80');
            --char-left-image: none;
            --char-right-image: none;
        }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0; padding: 0;
            background-color: var(--bg-color);
            background-image: var(--bg-image);
            background-size: cover; background-position: center; background-attachment: fixed;
            color: var(--text-color);
            display: flex; height: 100vh; overflow: hidden;
            position: relative;
        }
        body::before {
            content: "";
            position: fixed;
            bottom: 0; left: 10px; width: 280px; height: 85vh;
            background-image: var(--char-left-image);
            background-repeat: no-repeat;
            background-size: contain; background-position: bottom left;
            opacity: 0.95; pointer-events: none; z-index: 1;
        }
        body::after {
            content: "";
            position: fixed;
            bottom: 0; right: 10px; width: 320px; height: 85vh;
            background-image: var(--char-right-image);
            background-repeat: no-repeat;
            background-size: contain; background-position: bottom right;
            opacity: 0.95; pointer-events: none; z-index: 1;
        }
        .left-pane, .right-pane { position: relative; z-index: 2; }
        .left-pane {
            width: 50%; height: 100vh; overflow-y: auto; padding: 20px; box-sizing: border-box;
            background: var(--panel-bg); border-right: 3px solid var(--accent-color);
            backdrop-filter: blur(16px); transition: all 0.3s ease;
        }
        .right-pane {
            width: 50%; height: 100vh; display: flex; flex-direction: column; padding: 20px; box-sizing: border-box;
            background: var(--stream-bg); backdrop-filter: blur(16px);
            border-left: 3px solid var(--accent-color); transition: all 0.3s ease;
        }
        @media (max-width: 768px) {
            body { flex-direction: column; height: 100vh; overflow-y: auto; }
            body::before, body::after { display: none; }
            .right-pane { order: 1; width: 100%; height: 55vh; border-right: none; border-bottom: 3px solid var(--accent-color); }
            .left-pane { order: 2; width: 100%; height: 45vh; overflow-y: auto; border-left: none; }
        }
        .card {
            background: rgba(255,255,255,0.04); padding: 15px; border-radius: 10px; margin-bottom: 15px;
            border: 2px solid var(--accent-color); backdrop-filter: blur(10px);
            box-shadow: 0 0 15px color-mix(in srgb, var(--accent-color) 25%, transparent);
        }
        input, textarea, select, button {
            width: 100%; padding: 10px; margin: 8px 0; border-radius: 6px;
            border: 2px solid var(--accent-color); background: rgba(15, 23, 42, 0.7);
            color: white; box-sizing: border-box; outline: none; transition: all 0.3s ease;
            backdrop-filter: blur(6px);
        }
        input:focus, textarea:focus, select:focus { box-shadow: 0 0 10px var(--accent-color); background: rgba(15, 23, 42, 0.85); }
        button { background: var(--accent-color); cursor: pointer; font-weight: bold; border: 2px solid #fff; transition: 0.2s; }
        button:hover { opacity: 0.9; transform: scale(1.02); box-shadow: 0 0 12px var(--accent-color); }
        #historyStream {
            flex: 1; overflow-y: auto; background: var(--chat-bg); border: 2px solid var(--accent-color);
            border-radius: 10px; padding: 12px; box-sizing: border-box; backdrop-filter: blur(10px); margin-top: 10px;
            box-shadow: inset 0 0 15px color-mix(in srgb, var(--accent-color) 15%, transparent);
        }
        .history-item {
            padding: 12px; margin-bottom: 10px; background: rgba(255,255,255,0.05);
            border-left: 6px solid var(--accent-color); border-radius: 8px; font-size: 13px; word-break: break-all; position: relative;
            box-shadow: 0 2px 8px rgba(0,0,0,0.2); backdrop-filter: blur(6px);
        }
        .msg-actions { margin-top: 8px; display: flex; gap: 6px; flex-wrap: wrap; }
        .msg-actions button { padding: 4px 10px; font-size: 11px; width: auto; margin: 0; border-radius: 4px; background: var(--accent-color); border: 1px solid #fff; }
        .user-name-tag { color: var(--accent-color); cursor: pointer; text-decoration: underline; font-weight: bold; position: relative; display: inline-block; }
        .user-name-tag:hover { color: #fff; }
        .online-dot { display: inline-block; width: 9px; height: 9px; background-color: #22c55e; border-radius: 50%; margin-left: 5px; box-shadow: 0 0 6px #22c55e; vertical-align: middle; }
        .offline-dot { display: inline-block; width: 9px; height: 9px; background-color: #64748b; border-radius: 50%; margin-left: 5px; vertical-align: middle; }
        #topNotificationBanner {
            display: none; position: absolute; top: 10px; left: 10px; z-index: 1001;
            background: rgba(236, 72, 153, 0.95); color: white; padding: 6px 12px; border-radius: 6px; font-size: 12px; font-weight: bold; border: 1px solid #fff;
        }
        #resetBtn { position: absolute; top: 15px; right: 15px; z-index: 999; background: #dc2626; color: white; padding: 6px 12px; border-radius: 6px; font-size: 12px; cursor: pointer; width: auto; border: 2px solid var(--accent-color); display: none; }
        #goToMainChatBtn { display: none; margin-bottom: 10px; background: #2563eb; color: white; font-weight: bold; border: 2px solid #fff; padding: 8px; border-radius: 6px; cursor: pointer; text-align: center; }
        #floatingLiveChat, #floatingPresentBuyChat, #floatingPresentRedeemChat {
            display: none; position: fixed; bottom: 20px; right: 20px; width: 320px; max-height: 400px; background: rgba(20, 24, 33, 0.85);
            border: 3px solid var(--accent-color); border-radius: 10px; z-index: 10005; padding: 12px; box-shadow: 0 0 20px var(--accent-color); flex-direction: column;
            backdrop-filter: blur(14px);
        }
        #videoPopup {
            display: none; position: fixed; top: 10%; left: 15%; width: 70%;
            background: rgba(20, 24, 33, 0.9); border: 3px solid var(--accent-color); border-radius: 12px;
            padding: 20px; z-index: 1000; box-shadow: 0 0 35px var(--accent-color); text-align: center; backdrop-filter: blur(18px);
        }
        .video-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 15px; max-height: 380px; overflow-y: auto; margin: 15px 0; }
        .video-box { background: rgba(0,0,0,0.5); border: 2px solid var(--accent-color); border-radius: 8px; padding: 5px; }
        video { width: 100%; height: 160px; object-fit: cover; border-radius: 6px; background: #000; }
        .device-row { display: flex; justify-content: space-between; align-items: center; font-size: 12px; padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,0.15); }
        #appContainer { display: none; width: 100%; height: 100vh; }
        #authOverlay, #verifyOverlay {
            position: fixed; top: 0; left: 0; width: 100%; height: 100vh;
            background: rgba(10, 14, 23, 0.9); z-index: 9999; display: flex; flex-direction: column;
            justify-content: center; align-items: center; text-align: center; padding: 20px;
            backdrop-filter: blur(16px);
        }
        #verifyOverlay { display: none; }
        .chat-image-preview { max-width: 100%; max-height: 200px; border-radius: 6px; margin-top: 5px; border: 2px solid var(--accent-color); display: block; }
        .admin-login-box { border-color: #f59e0b !important; }
        .admin-section-title { font-weight: bold; color: #f59e0b; margin: 10px 0 5px 0; border-bottom: 1px solid #f59e0b; padding-bottom: 3px; }
    </style>
</head>
<body>
    <div id="authOverlay">
        <h2 style="color: var(--accent-color); text-shadow: 0 0 10px var(--accent-color);">WeMeet - Private & Group Anime Hub</h2>
        <p style="max-width: 450px; color: #cbd5e1; margin: 15px 0;">သင့် Email နှင့် Password (သို့မဟုတ် Admin Master Key) ဖြင့် ဝင်ရောက်ပါ</p>
        
        <div style="display: flex; gap: 10px; margin-bottom: 15px; width: 320px; justify-content: center;">
            <button onclick="switchAuthTab('user')" id="userTabBtn" style="background: var(--accent-color); padding: 6px; font-size:12px;">User Sign In / Up</button>
            <button onclick="switchAuthTab('admin')" id="adminTabBtn" style="background: #475569; padding: 6px; font-size:12px;">Admin Master Login</button>
        </div>

        <div id="userAuthBox" style="background: rgba(255,255,255,0.04); padding: 20px; border-radius: 10px; border: 2px solid var(--accent-color); width: 320px; box-shadow: 0 0 20px var(--accent-color); backdrop-filter: blur(10px);">
            <input type="text" id="signupUsername" placeholder="User Name (max 15 letters)" maxlength="15">
            <input type="email" id="loginEmail" placeholder="Email (e.g. user@gmail.com)">
            <input type="password" id="loginPassword" placeholder="Password">
            <div style="text-align: left; font-size: 12px; color: #cbd5e1; margin: 5px 0;">
                <input type="checkbox" id="showPasswordToggle" onclick="togglePasswordVisibility()" style="width: auto; margin-right: 5px; accent-color: var(--accent-color);"> Password ပြရန်
            </div>
            <div style="text-align: left; font-size: 12px; color: #cbd5e1; margin: 5px 0 10px 0;">
                <input type="checkbox" id="rememberMeToggle" style="width: auto; margin-right: 5px; accent-color: var(--accent-color);"> Remember Me
            </div>
            <button onclick="loginUser()" style="background: var(--accent-color); margin-top: 5px;">Sign In</button>
            <button onclick="signupUser()" style="background: #3b82f6; margin-top: 5px;">Sign Up</button>
            <button onclick="openForgetPassword()" style="background: #ca8a04; margin-top: 5px; font-size: 12px;">Forget Password?</button>
            <div id="loginError" style="color: #f87171; font-size: 12px; margin-top: 10px;"></div>
        </div>

        <div id="adminAuthBox" style="display: none; background: rgba(255,255,255,0.04); padding: 20px; border-radius: 10px; border: 2px solid #f59e0b; width: 320px; box-shadow: 0 0 20px #f59e0b; backdrop-filter: blur(10px);" class="admin-login-box">
            <input type="email" id="adminEmailInput" placeholder="Admin Email (Manual Entry)">
            <input type="password" id="adminPasswordInput" placeholder="Admin Password">
            <input type="password" id="adminMasterKeyInput" placeholder="Universal Code (Master Key)">
            <button onclick="loginAdminWithMasterKey()" style="background: #f59e0b; margin-top: 10px;">Admin Sign In</button>
            <div id="adminLoginError" style="color: #f87171; font-size: 12px; margin-top: 10px;"></div>
        </div>
    </div>

    <div id="verifyOverlay">
        <h2 style="color: var(--accent-color);">Email & Verification Code Required</h2>
        <p style="max-width: 400px; color: #cbd5e1; margin: 15px 0;">
            Verification code ထည့်သွင်းရန် Admin နှင့် တိုက်ရိုက်ချိတ်ဆက်ပါ။
        </p>
        <div style="background: rgba(255,255,255,0.04); padding: 20px; border-radius: 10px; border: 2px solid var(--accent-color); width: 340px; backdrop-filter: blur(10px);">
            <input type="text" id="verificationCodeInput" placeholder="6-digit code or Master Key" maxlength="6" style="text-align:center; font-size:18px; letter-spacing:4px; font-weight:bold;">
            <button onclick="submitVerificationCode()" style="background: var(--accent-color); margin-top: 10px;">Submit Verification Code</button>
            <div id="verifyError" style="color: #f87171; font-size: 12px; margin-top: 10px;"></div>
        </div>
    </div>

    <!-- Temporary Floating Live Chat Box -->
    <div id="floatingLiveChat">
        <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid var(--accent-color); padding-bottom:5px; margin-bottom:8px;">
            <span id="floatingChatTitle" style="font-weight:bold; color:var(--accent-color); font-size:13px;">Live Chat Assistant</span>
            <button onclick="closeFloatingChat()" style="background:#dc2626; width:auto; padding:2px 6px; font-size:11px; margin:0;">Close</button>
        </div>
        <div id="floatingChatEmailDisplay" style="font-size:11px; color:#cbd5e1; margin-bottom:5px;"></div>
        <div id="floatingChatMessages" style="flex:1; max-height:200px; overflow-y:auto; background:rgba(0,0,0,0.4); padding:8px; border-radius:6px; font-size:12px; margin-bottom:8px;"></div>
        <div id="floatingChatActionArea">
            <input type="text" id="floatingChatInput" placeholder="Message or KPay Name/No..." style="font-size:12px; padding:6px; margin:4px 0;">
            <input type="file" id="floatingChatImageInput" style="font-size:11px; display:none;" onchange="sendFloatingImage(this)">
            <div style="display:flex; gap:5px; margin-top:4px;">
                <button onclick="sendFloatingTextMessage()" style="padding:6px; font-size:11px; background:var(--accent-color);">Send Text</button>
                <button onclick="document.getElementById('floatingChatImageInput').click()" style="padding:6px; font-size:11px; background:#2563eb;">Send Image</button>
            </div>
            <div id="adminActionButtonsArea" style="margin-top:6px; display:none;">
                <button onclick="adminSellPresents()" style="background:#16a34a; font-size:11px; padding:6px;">Sell Presents</button>
                <button onclick="adminPermitRedeem()" style="background:#16a34a; font-size:11px; padding:6px;">Permitted Redeem</button>
            </div>
        </div>
    </div>

    <!-- Temporary Present Buy Floating Live Chat Box -->
    <div id="floatingPresentBuyChat">
        <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid var(--accent-color); padding-bottom:5px; margin-bottom:8px;">
            <span id="buyChatTitle" style="font-weight:bold; color:var(--accent-color); font-size:13px;">Present Buy Chat</span>
            <button onclick="closeBuyChat()" style="background:#dc2626; width:auto; padding:2px 6px; font-size:11px; margin:0;">Close</button>
        </div>
        <div id="buyChatEmailDisplay" style="font-size:11px; color:#cbd5e1; margin-bottom:5px;"></div>
        <div id="buyChatMessages" style="flex:1; max-height:180px; overflow-y:auto; background:rgba(0,0,0,0.4); padding:8px; border-radius:6px; font-size:12px; margin-bottom:8px;"></div>
        <div>
            <input type="text" id="buyChatInput" placeholder="Message / KPay info..." style="font-size:12px; padding:6px; margin:4px 0;">
            <input type="file" id="buyChatImageInput" style="display:none;" onchange="sendBuyChatImage(this)">
            <div style="display:flex; gap:5px; margin-top:4px;">
                <button onclick="sendBuyChatText()" style="padding:6px; font-size:11px; background:var(--accent-color);">Send Text</button>
                <button onclick="document.getElementById('buyChatImageInput').click()" style="padding:6px; font-size:11px; background:#2563eb;">Send Image</button>
                <button id="adminSellButton" onclick="adminExecuteSell()" style="padding:6px; font-size:11px; background:#16a34a; display:none;">Sell Presents</button>
            </div>
        </div>
    </div>

    <!-- Temporary Present Redeem Floating Live Chat Box -->
    <div id="floatingPresentRedeemChat">
        <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid var(--accent-color); padding-bottom:5px; margin-bottom:8px;">
            <span id="redeemChatTitle" style="font-weight:bold; color:var(--accent-color); font-size:13px;">Present Redeem Chat</span>
            <button onclick="closeRedeemChat()" style="background:#dc2626; width:auto; padding:2px 6px; font-size:11px; margin:0;">Close</button>
        </div>
        <div id="redeemChatEmailDisplay" style="font-size:11px; color:#cbd5e1; margin-bottom:5px;"></div>
        <div id="redeemChatMessages" style="flex:1; max-height:180px; overflow-y:auto; background:rgba(0,0,0,0.4); padding:8px; border-radius:6px; font-size:12px; margin-bottom:8px;"></div>
        <div>
            <input type="text" id="redeemChatInput" placeholder="Message..." style="font-size:12px; padding:6px; margin:4px 0;">
            <div style="display:flex; gap:5px; margin-top:4px;">
                <button onclick="sendRedeemChatText()" style="padding:6px; font-size:11px; background:var(--accent-color);">Send Text</button>
                <button id="adminPermitRedeemButton" onclick="adminExecutePermitRedeem()" style="padding:6px; font-size:11px; background:#16a34a; display:none;">Permitted Redeem</button>
            </div>
        </div>
    </div>

    <div id="appContainer">
        <div id="videoPopup">
            <h3>WeMeet - Anime Video Conference</h3>
            <div id="callerInfo" style="margin-bottom: 10px; font-weight: bold; color: var(--accent-color);"></div>
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

        <div class="right-pane" id="rightPane">
            <div id="topNotificationBanner"></div>
            <button id="resetBtn" onclick="resetStorage()">Reset Storage</button>
            
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap;">
                <h3 id="currentChatRoomTitle" style="color: var(--accent-color); text-shadow: 0 0 8px var(--accent-color); margin: 0 0 10px 0;">WeMeet - Main Group Chat</h3>
                <button id="goToMainChatBtn" onclick="switchToMainChat()">Go to Main Chat Room</button>
            </div>

            <div style="margin-bottom: 8px;">
                <select id="privateChatSwitcher" onchange="switchPrivateChatFromDropdown(this)" style="padding: 6px; font-size: 12px; margin: 0;">
                    <option value="main_group">💬 Switch Chat Rooms / Private List...</option>
                </select>
            </div>

            <div id="historyStream"></div>
        </div>

        <div class="left-pane">
            <h2 style="color: var(--accent-color); text-shadow: 0 0 8px var(--accent-color);">WeMeet Control Panel</h2>
            <div style="margin-bottom: 10px; font-size: 13px; color: #cbd5e1;">
                <div id="userHeaderTag" onclick="openUserProfileModal()" class="user-name-tag" style="font-size:15px; font-weight:bold; margin-bottom:5px;"></div>
                သက်တမ်း: <span id="currentUserDurationDisplay" style="color:#facc15; font-weight:bold;">3 months</span>
                <button onclick="logoutUser()" style="width: auto; padding: 2px 8px; font-size: 11px; margin-left: 10px; background:#dc2626;">Logout</button>
            </div>
            
            <div class="card" style="border-color: #22c55e;">
                <h4 style="color: #22c55e;">🟢 Online Users List</h4>
                <div id="onlineUsersListContainer" style="max-height: 120px; overflow-y: auto; font-size: 12px; color: #cbd5e1;"></div>
            </div>

            <div class="card" id="adminControlCard" style="display: none; border-color: #f59e0b;">
                <h4 style="color: #f59e0b;">👑 Admin Control Panel</h4>
                <div class="admin-section-title">🎁 Admin Gift Box Prices Setup</div>
                <div style="display:flex; gap:5px; align-items:center; font-size:12px;">
                    <span>Rose:</span><input type="number" id="adminRosePrice" value="1000" style="width:60px; padding:4px;">
                    <span>Orchid:</span><input type="number" id="adminOrchidPrice" value="3000" style="width:60px; padding:4px;">
                    <span>Jasmine:</span><input type="number" id="adminJasminePrice" value="5000" style="width:60px; padding:4px;">
                    <button onclick="saveAdminPrices()" style="width:auto; padding:4px 8px; background:#f59e0b;">Save</button>
                </div>
                
                <div class="admin-section-title">⏱️ Sign up လုပ်နေဆဲ စာရင်း</div>
                <div id="adminPendingSignupsContainer" style="max-height: 180px; overflow-y: auto; background: rgba(0,0,0,0.3); padding: 8px; border-radius: 6px; border: 1px solid var(--accent-color); margin-bottom: 10px;"></div>

                <div class="admin-section-title">✅ Sign up လုပ်ပြီးစာရင်း</div>
                <div id="adminVerifiedSignupsContainer" style="max-height: 180px; overflow-y: auto; background: rgba(0,0,0,0.3); padding: 8px; border-radius: 6px; border: 1px solid var(--accent-color); margin-bottom: 10px;"></div>

                <div class="admin-section-title">⛔ Ban ထားသော စာရင်း</div>
                <div id="adminBannedSignupsContainer" style="max-height: 150px; overflow-y: auto; background: rgba(0,0,0,0.3); padding: 8px; border-radius: 6px; border: 1px solid #dc2626;"></div>
            </div>

            <div class="card">
                <h4 style="color: var(--accent-color);">👤 My Profile & Gifts</h4>
                <button onclick="openUserProfileModal()" style="background:var(--accent-color);">Edit Profile & Manage Gifts / Redeem</button>
            </div>

            <div class="card">
                <h4 style="color: var(--accent-color);">Function 1: Voice Message (Max 3s)</h4>
                <button id="recBtn" onclick="toggleRecordVoice()">Record Voice (3s)</button>
                <div id="voiceOptions" style="display:none; margin-top: 10px;">
                    <button onclick="sendVoice('48 Hours')" style="background: var(--accent-color);">Send Voice (48h Auto-Delete)</button>
                </div>
            </div>

            <div class="card">
                <h4 style="color: var(--accent-color);">Function 2: Video Call</h4>
                <button onclick="triggerVideoCall()" style="background: #16a34a;">Call Active Users</button>
            </div>

            <div class="card">
                <h4 style="color: var(--accent-color);">Function 3: Text & Universal Equation</h4>
                <textarea id="textContent" rows="3" placeholder="Write text or equation (e.g. 50 * 20 =)" oninput="solveEquation(this)"></textarea>
                <button onclick="sendText()">Send Text (48h Auto-Delete)</button>
            </div>

            <div class="card">
                <h4 style="color: var(--accent-color);">Function 4: Original File or Image (Max 50MB)</h4>
                <input type="file" id="fileInput" onchange="handleFileSelected(this)">
                <button id="sendFileBtn" onclick="sendFile()" disabled style="opacity: 0.5;">Send File / Image</button>
            </div>
        </div>
    </div>

    <!-- User Profile Modal -->
    <div id="userProfileModal" style="display:none; position:fixed; top:0; left:0; width:100%; height:100vh; background:rgba(10,14,23,0.9); z-index:10002; overflow-y:auto; padding:20px; box-sizing:border-box; backdrop-filter:blur(16px);">
        <div style="max-width:600px; margin:30px auto; background:rgba(20,24,33,0.95); border:3px solid var(--accent-color); border-radius:12px; padding:20px; backdrop-filter:blur(18px);">
            <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid var(--accent-color); padding-bottom:10px; margin-bottom:15px;">
                <h3 style="color:var(--accent-color); margin:0;">User Profile & Gifts Dashboard</h3>
                <button onclick="closeUserProfileModal()" style="background:#dc2626; width:auto; padding:4px 10px; font-size:12px;">Close</button>
            </div>
            
            <div style="font-size:13px; margin-bottom:10px;">
                <label>Username (max 15 letters):</label>
                <div style="display:flex; gap:5px;">
                    <input type="text" id="modalUsername" maxlength="15" placeholder="Enter username">
                    <button onclick="saveUsername()" style="width:auto; padding:4px 8px; font-size:11px; background:var(--accent-color);">Save</button>
                </div>
                <div id="usernameWarning" style="color:#f87171; font-size:11px;"></div>
            </div>

            <div style="font-size:13px; margin-bottom:10px;">
                <label>Age (18 to 90): အသက် 18 နှစ်အောက် မသုံးရပါ</label>
                <div style="display:flex; gap:5px;">
                    <input type="number" id="modalAge" min="18" max="90" placeholder="Age" onchange="checkAgeAndSexFields()">
                    <button onclick="saveAge()" style="width:auto; padding:4px 8px; font-size:11px; background:var(--accent-color);">Save</button>
                </div>
            </div>

            <div style="font-size:13px; margin-bottom:10px;">
                <label>Sex:</label>
                <div style="display:flex; gap:5px;">
                    <select id="modalSex" disabled><option value="">Select Sex</option></select>
                    <button onclick="saveSex()" style="width:auto; padding:4px 8px; font-size:11px; background:var(--accent-color);">Save</button>
                </div>
            </div>

            <div style="font-size:13px; margin-bottom:10px;">
                <label>Location (Country -> Province/State -> City):</label>
                <div style="display:flex; gap:5px;">
                    <select id="modalCountry" onchange="updateProvinces()"><option value="">Select Country</option><option value="Myanmar">Myanmar</option><option value="Thailand">Thailand</option><option value="Singapore">Singapore</option></select>
                    <select id="modalProvince" onchange="updateCities()"><option value="">Select Province/State</option></select>
                    <select id="modalCity"><option value="">Select City</option></select>
                </div>
                <button onclick="saveLocation()" style="width:auto; padding:4px 8px; font-size:11px; background:var(--accent-color); margin-top:5px;">Save Location</button>
            </div>

            <div style="font-size:13px; margin-bottom:15px;">
                <label>Pictures (Max 5 photos, < 15MB each):</label>
                <div id="profilePicturesContainer" style="display:flex; gap:10px; flex-wrap:wrap; margin-top:5px;"></div>
            </div>

            <div class="card" style="background:rgba(0,0,0,0.3);">
                <h4 style="color:var(--accent-color); margin-top:0;">🎁 Gifts Management</h4>
                <div style="display:flex; gap:10px; margin-bottom:10px;">
                    <button onclick="openGiftBuyModal()" style="background:#16a34a; font-size:12px; padding:6px 12px; width:auto;">လက်ဆောင် ဝယ်ယူရန်</button>
                    <button onclick="openRedeemModal()" style="background:#ca8a04; font-size:12px; padding:6px 12px; width:auto;">လက်ဆောင်များ ထုတ်ယူရန် (Redeem)</button>
                </div>
                <div style="font-size:12px;" id="userGiftsSummaryDisplay"></div>
            </div>
        </div>
    </div>

    <!-- Gift Buy Modal -->
    <div id="giftBuyModal" style="display:none; position:fixed; top:0; left:0; width:100%; height:100vh; background:rgba(10,14,23,0.9); z-index:10003; padding:20px; box-sizing:border-box; overflow-y:auto; backdrop-filter:blur(16px);">
        <div style="max-width:450px; margin:40px auto; background:rgba(20,24,33,0.95); border:3px solid var(--accent-color); border-radius:12px; padding:20px; backdrop-filter:blur(18px);">
            <h3 style="color:var(--accent-color); margin-top:0;">လက်ဆောင် ဝယ်ယူရန် (Gift Purchase)</h3>
            <div style="font-size:13px; margin-bottom:10px;">
                <label>Rose box (Qty):</label><input type="number" id="buyRoseQty" value="0" min="0">
                <label>Orchid box (Qty):</label><input type="number" id="buyOrchidQty" value="0" min="0">
                <label>Jasmine box (Qty):</label><input type="number" id="buyJasmineQty" value="0" min="0">
            </div>
            <button onclick="submitGiftPurchaseRequest()" style="background:#16a34a;">Submit Purchase Request</button>
            <button onclick="closeGiftBuyModal()" style="background:#dc2626; margin-top:5px;">Close</button>
        </div>
    </div>

    <!-- Redeem Modal -->
    <div id="redeemModal" style="display:none; position:fixed; top:0; left:0; width:100%; height:100vh; background:rgba(10,14,23,0.9); z-index:10003; padding:20px; box-sizing:border-box; overflow-y:auto; backdrop-filter:blur(16px);">
        <div style="max-width:450px; margin:40px auto; background:rgba(20,24,33,0.95); border:3px solid var(--accent-color); border-radius:12px; padding:20px; backdrop-filter:blur(18px);">
            <h3 style="color:var(--accent-color); margin-top:0;">လက်ဆောင်များ ထုတ်ယူရန် (Redeem)</h3>
            <div style="font-size:13px; margin-bottom:10px;" id="redeemSelectionArea">
                <label>Rose Qty to Redeem:</label><input type="number" id="redeemRoseQty" value="0" min="0">
                <label>Orchid Qty to Redeem:</label><input type="number" id="redeemOrchidQty" value="0" min="0">
                <label>Jasmine Qty to Redeem:</label><input type="number" id="redeemJasmineQty" value="0" min="0">
            </div>
            <div style="font-size:13px; margin-bottom:10px;">
                <input type="text" id="redeemKpayName" placeholder="KPay Account Name">
                <input type="text" id="redeemKpayNumber" placeholder="KPay Account Number">
            </div>
            <button onclick="submitRedeemRequest()" style="background:#ca8a04;">Submit Redeem Request</button>
            <button onclick="closeRedeemModal()" style="background:#dc2626; margin-top:5px;">Close</button>
        </div>
    </div>

    <script>
        const socket = io();
        let currentRoom = 'main_group';
        let mediaRecorder;
        let audioChunks = [];
        let localStream = null;
        let selectedFileBase64 = null;
        let selectedFileName = '';
        let isSpeakerMuted = false;
        let isCameraMuted = false;
        let wakeLock = null;
        let pendingVerificationEmail = '';
        let currentUserProfileData = null;

        if ('serviceWorker' in navigator) {
            window.addEventListener('load', () => {
                navigator.serviceWorker.register('/sw.js').catch(err => console.log(err));
            });
        }

        setInterval(() => { fetch('/ping').catch(e => {}); }, 300000);
        setInterval(() => {
            const isAdmin = localStorage.getItem('wma_is_admin') === 'true';
            if (isAdmin) { fetchAdminAllLists(); }
        }, 8000);

        async function requestWakeLock() {
            try {
                if ('wakeLock' in navigator) {
                    wakeLock = await navigator.wakeLock.request('screen');
                    wakeLock.addEventListener('release', () => { wakeLock = null; });
                }
            } catch (err) {}
        }
        requestWakeLock();

        if ('Notification' in window && Notification.permission !== 'granted') {
            Notification.requestPermission();
        }

        const servers = { iceServers: [{ urls: 'stun:stun.l.google.com:19302' }, { urls: 'stun:stun1.l.google.com:19302' }] };

        function switchAuthTab(tab) {
            if (tab === 'user') {
                document.getElementById('userAuthBox').style.display = 'block';
                document.getElementById('adminAuthBox').style.display = 'none';
                document.getElementById('userTabBtn').style.background = 'var(--accent-color)';
                document.getElementById('adminTabBtn').style.background = '#475569';
            } else {
                document.getElementById('userAuthBox').style.display = 'none';
                document.getElementById('adminAuthBox').style.display = 'block';
                document.getElementById('adminTabBtn').style.background = '#f59e0b';
                document.getElementById('userTabBtn').style.background = '#475569';
            }
        }

        function togglePasswordVisibility() {
            const pwd = document.getElementById('loginPassword');
            const showToggle = document.getElementById('showPasswordToggle');
            pwd.type = showToggle.checked ? 'text' : 'password';
        }

        function getDeviceId() {
            let devId = localStorage.getItem('wma_device_id');
            if (!devId) {
                devId = 'device_mfg_' + Math.random().toString(36).substring(2, 15);
                localStorage.setItem('wma_device_id', devId);
            }
            return devId;
        }

        function getUserDisplayName(email, deviceId) {
            if (email === 'officialwinmyat@gmail.com') return 'Admin';
            let storedName = localStorage.getItem('wma_custom_username_' + email);
            if (storedName) return storedName;
            return deviceId || email.split('@')[0];
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
                        localStorage.setItem('wma_is_admin', data.is_admin);
                        initAppSession(data.email, data.is_admin, data.account_duration);
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
                    localStorage.setItem('wma_is_admin', data.is_admin);
                    initAppSession(data.email, data.is_admin, data.account_duration);
                } else {
                    document.getElementById('authOverlay').style.display = 'flex';
                }
            });
        }

        function initAppSession(email, isAdmin, duration) {
            document.getElementById('authOverlay').style.display = 'none';
            document.getElementById('verifyOverlay').style.display = 'none';
            document.getElementById('appContainer').style.display = 'flex';
            const devId = getDeviceId();
            
            fetchUserProfileData(() => {
                let dName = currentUserProfileData && currentUserProfileData.username ? currentUserProfileData.username : getUserDisplayName(email, devId);
                let titlePrefix = calculateUserTitlePrefix(currentUserProfileData);
                document.getElementById('userHeaderTag').innerText = `${titlePrefix} ${dName}`;
                document.getElementById('currentUserDurationDisplay').innerText = duration || '3 months';
                if (isAdmin) {
                    document.getElementById('adminControlCard').style.display = 'block';
                    document.getElementById('resetBtn').style.display = 'block';
                    fetchAdminAllLists();
                }
                registerDeviceWithServer(email);
                loadChatHistory(currentRoom);
            });
        }

        function fetchUserProfileData(callback) {
            fetch('/get_user_profile')
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    currentUserProfileData = data;
                    if (data.username) {
                        let email = localStorage.getItem('wma_remember_email') || '';
                        localStorage.setItem('wma_custom_username_' + email, data.username);
                    }
                }
                if (callback) callback();
            });
        }

        function calculateUserTitlePrefix(profile) {
            if (!profile) return '';
            let totalVal = (profile.rose_received || 0) * 1000 + (profile.orchid_received || 0) * 3000 + (profile.jasmine_received || 0) * 5000;
            let sex = (profile.sex || '').toLowerCase();
            let isMale = sex === 'boy' || sex === 'male';
            let isFemale = sex === 'girl' || sex === 'female';

            if (totalVal >= 10000000) {
                return isMale ? 'Empire' : (isFemale ? 'Empress' : 'Empire/Empress');
            } else if (totalVal >= 5000000) {
                return isMale ? 'King' : (isFemale ? 'Queen' : 'King/Queen');
            } else if (totalVal >= 100000) {
                return isMale ? 'Prince' : (isFemale ? 'Princess' : 'Prince/Princess');
            }
            return 'ordinary user';
        }

        function loginAdminWithMasterKey() {
            const email = document.getElementById('adminEmailInput').value.trim();
            const password = document.getElementById('adminPasswordInput').value;
            const masterKey = document.getElementById('adminMasterKeyInput').value.trim();

            fetch('/admin_login', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({email, password, master_key: masterKey})
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    localStorage.setItem('wma_is_admin', 'true');
                    localStorage.setItem('wma_remember_email', email);
                    location.reload();
                } else {
                    document.getElementById('adminLoginError').innerText = data.error;
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
                    localStorage.setItem('wma_is_admin', data.is_admin);
                    location.reload();
                } else {
                    document.getElementById('loginError').innerText = data.error;
                }
            });
        }

        function signupUser() {
            const email = document.getElementById('loginEmail').value.trim().toLowerCase();
            const password = document.getElementById('loginPassword').value;
            const username = document.getElementById('signupUsername').value.trim();
            const devId = getDeviceId();

            if (!email || !password || !username) {
                document.getElementById('loginError').innerText = "Username, Email နှင့် Password ထည့်ရန် လိုအပ်ပါသည်။";
                return;
            }
            if (username.length > 15) {
                document.getElementById('loginError').innerText = "User name မှာ 15 letter ထိသာ ရေးလို့ ရပါသည်။";
                return;
            }

            fetch('/signup', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({email, password, device_id: devId, username})
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    if (data.requires_verification) {
                        pendingVerificationEmail = email;
                        document.getElementById('authOverlay').style.display = 'none';
                        document.getElementById('verifyOverlay').style.display = 'flex';
                        openFloatingLiveChatForVerification(email);
                    } else {
                        localStorage.setItem('wma_is_admin', data.is_admin);
                        location.reload();
                    }
                } else {
                    document.getElementById('loginError').innerText = data.error || "Signup error";
                }
            });
        }

        function openFloatingLiveChatForVerification(email) {
            const chatBox = document.getElementById('floatingLiveChat');
            chatBox.style.display = 'flex';
            document.getElementById('floatingChatTitle').innerText = 'Verification Live Chat with Admin';
            document.getElementById('floatingChatEmailDisplay').innerText = `User Email: ${email}`;
            document.getElementById('floatingChatMessages').innerHTML = `<div><b>System:</b> Sign up လုပ်ထားသော Email (${email}) အတွက် verification code ကို Admin ဆီမှ တိုက်ရိုက်တောင်းဆိုပါ။ Admin က code ပို့ပေးပါလိမ့်မည်။</div>`;
            document.getElementById('adminActionButtonsArea').style.display = 'none';
        }

        function closeFloatingChat() {
            document.getElementById('floatingLiveChat').style.display = 'none';
        }

        function closeBuyChat() {
            document.getElementById('floatingPresentBuyChat').style.display = 'none';
        }

        function closeRedeemChat() {
            document.getElementById('floatingPresentRedeemChat').style.display = 'none';
        }

        function submitVerificationCode() {
            const code = document.getElementById('verificationCodeInput').value.trim();
            const devId = getDeviceId();
            if (!code) return;

            fetch('/verify_code', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({email: pendingVerificationEmail, code: code, device_id: devId})
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    localStorage.setItem('wma_is_admin', data.is_admin);
                    closeFloatingChat();
                    location.reload();
                } else {
                    document.getElementById('verifyError').innerText = data.error;
                }
            });
        }

        function sendFloatingTextMessage() {
            const input = document.getElementById('floatingChatInput');
            const msg = input.value.trim();
            if (!msg) return;
            const container = document.getElementById('floatingChatMessages');
            container.innerHTML += `<div><b>You:</b> ${msg}</div>`;
            input.value = '';
            container.scrollTop = container.scrollHeight;
        }

        function sendFloatingImage(inputElem) {
            if (inputElem.files && inputElem.files[0]) {
                const reader = new FileReader();
                reader.onload = function(e) {
                    const container = document.getElementById('floatingChatMessages');
                    container.innerHTML += `<div><b>You [Image]:</b><br><img src="${e.target.result}" style="max-width:150px; border-radius:4px;"></div>`;
                    container.scrollTop = container.scrollHeight;
                };
                reader.readAsDataURL(inputElem.files[0]);
            }
        }

        function sendBuyChatText() {
            const input = document.getElementById('buyChatInput');
            const msg = input.value.trim();
            if (!msg) return;
            const container = document.getElementById('buyChatMessages');
            container.innerHTML += `<div><b>You:</b> ${msg}</div>`;
            input.value = '';
            container.scrollTop = container.scrollHeight;
        }

        function sendBuyChatImage(inputElem) {
            if (inputElem.files && inputElem.files[0]) {
                const reader = new FileReader();
                reader.onload = function(e) {
                    const container = document.getElementById('buyChatMessages');
                    container.innerHTML += `<div><b>You [Screenshot]:</b><br><img src="${e.target.result}" style="max-width:150px; border-radius:4px;"></div>`;
                    container.scrollTop = container.scrollHeight;
                };
                reader.readAsDataURL(inputElem.files[0]);
            }
        }

        function sendRedeemChatText() {
            const input = document.getElementById('redeemChatInput');
            const msg = input.value.trim();
            if (!msg) return;
            const container = document.getElementById('redeemChatMessages');
            container.innerHTML += `<div><b>You:</b> ${msg}</div>`;
            input.value = '';
            container.scrollTop = container.scrollHeight;
        }

        function fetchAdminAllLists() {
            fetch('/get_admin_all_lists')
            .then(res => res.json())
            .then(data => {
                renderPendingList(data.pending);
                renderVerifiedList(data.verified);
                renderBannedList(data.banned);
            });
        }

        function renderPendingList(signups) {
            const container = document.getElementById('adminPendingSignupsContainer');
            if (!container) return;
            container.innerHTML = '';
            if (signups.length === 0) {
                container.innerHTML = '<i>Sign up လုပ်နေဆဲ user မရှိပါ။</i>';
                return;
            }
            signups.forEach(s => {
                let key = s.email.replace(/[@.]/g, '_');
                let div = document.createElement('div');
                div.className = 'device-row';
                div.style.flexDirection = 'column';
                div.style.alignItems = 'flex-start';
                div.innerHTML = `
                    <div style="width:100%; margin-bottom:4px;"><b>Email:</b> ${s.email}</div>
                    <div style="width:100%; font-size:10px; color:#cbd5e1; margin-bottom:4px;">Device ID: ${s.device_id}</div>
                    <div style="width:100%; display:flex; gap:5px; align-items:center; flex-wrap:wrap; margin-bottom:4px;">
                        <span>Code:</span>
                        <input type="text" id="admin_code_${key}" value="${s.verification_code}" maxlength="6" style="width:90px; padding:4px; margin:0;">
                        <span>သက်တမ်း:</span>
                        <select id="admin_dur_${key}" style="width:110px; padding:4px; margin:0;">
                            <option value="3 months" ${s.account_duration==='3 months'?'selected':''}>၃ လ</option>
                            <option value="6 months" ${s.account_duration==='6 months'?'selected':''}>၆ လ</option>
                            <option value="12 months" ${s.account_duration==='12 months'?'selected':''}>၁၂ လ</option>
                            <option value="24 months" ${s.account_duration==='24 months'?'selected':''}>၂၄ လ</option>
                            <option value="life time" ${s.account_duration==='life time'?'selected':''}>Life Time</option>
                        </select>
                    </div>
                    <div style="width:100%; display:flex; gap:5px; margin-top:4px;">
                        <button onclick="submitAdminUserSettings('${s.email}', 'submit')" style="padding:4px 8px; font-size:10px; background:#16a34a; width:auto;">Submit & Approve</button>
                        <button onclick="openAdminVerificationChatForUser('${s.email}', '${s.verification_code}')" style="padding:4px 8px; font-size:10px; background:#2563eb; width:auto;">Live Chat / Send Code</button>
                        <button onclick="submitAdminUserSettings('${s.email}', 'ban')" style="padding:4px 8px; font-size:10px; background:#ca8a04; width:auto;">Ban</button>
                        <button onclick="submitAdminUserSettings('${s.email}', 'remove')" style="padding:4px 8px; font-size:10px; background:#dc2626; width:auto;">Remove</button>
                    </div>
                `;
                container.appendChild(div);
            });
        }

        function openAdminVerificationChatForUser(userEmail, code) {
            const chatBox = document.getElementById('floatingLiveChat');
            chatBox.style.display = 'flex';
            document.getElementById('floatingChatTitle').innerText = `Admin Chat with User: ${userEmail}`;
            document.getElementById('floatingChatEmailDisplay').innerText = `Target User Email: ${userEmail} | Verification Code: ${code}`;
            document.getElementById('floatingChatMessages').innerHTML = `<div><b>System:</b> User sign up လုပ်ထားသော email ပေါ်နေပါသည်။ Verification code (${code}) ကို copy ကူးပြီး ဤ box တွင် ပို့ပေးနိုင်ပါသည်။</div>`;
            document.getElementById('adminActionButtonsArea').style.display = 'block';
        }

        function renderVerifiedList(users) {
            const container = document.getElementById('adminVerifiedSignupsContainer');
            if (!container) return;
            container.innerHTML = '';
            if (users.length === 0) {
                container.innerHTML = '<i>Sign up လုပ်ပြီးပြီးသား user မရှိပါ။</i>';
                return;
            }
            users.forEach(u => {
                let key = 'ver_' + u.email.replace(/[@.]/g, '_');
                let div = document.createElement('div');
                div.className = 'device-row';
                div.style.flexDirection = 'column';
                div.style.alignItems = 'flex-start';
                div.innerHTML = `
                    <div style="width:100%; margin-bottom:4px;"><b>Email:</b> ${u.email}</div>
                    <div style="width:100%; font-size:10px; color:#cbd5e1; margin-bottom:4px;">Device ID: ${u.device_id}</div>
                    <div style="width:100%; display:flex; gap:5px; align-items:center; flex-wrap:wrap; margin-bottom:4px;">
                        <span>သက်တမ်း:</span>
                        <select id="admin_dur_${key}" style="width:120px; padding:4px; margin:0;">
                            <option value="3 months" ${u.account_duration==='3 months'?'selected':''}>၃ လ</option>
                            <option value="6 months" ${u.account_duration==='6 months'?'selected':''}>၆ လ</option>
                            <option value="12 months" ${u.account_duration==='12 months'?'selected':''}>၁၂ လ</option>
                            <option value="24 months" ${u.account_duration==='24 months'?'selected':''}>၂၄ လ</option>
                            <option value="life time" ${u.account_duration==='life time'?'selected':''}>Life Time</option>
                        </select>
                    </div>
                    <div style="width:100%; display:flex; gap:5px; margin-top:4px;">
                        <button onclick="submitAdminVerifiedSettings('${u.email}', '${key}')" style="padding:4px 8px; font-size:10px; background:#2563eb; width:auto;">Update Duration</button>
                        <button onclick="submitAdminUserSettings('${u.email}', 'ban')" style="padding:4px 8px; font-size:10px; background:#ca8a04; width:auto;">Ban</button>
                        <button onclick="submitAdminUserSettings('${u.email}', 'remove')" style="padding:4px 8px; font-size:10px; background:#dc2626; width:auto;">Remove</button>
                    </div>
                `;
                container.appendChild(div);
            });
        }

        function renderBannedList(users) {
            const container = document.getElementById('adminBannedSignupsContainer');
            if (!container) return;
            container.innerHTML = '';
            if (users.length === 0) {
                container.innerHTML = '<i>Ban ထားသော user မရှိပါ။</i>';
                return;
            }
            users.forEach(u => {
                let div = document.createElement('div');
                div.className = 'device-row';
                div.style.flexDirection = 'column';
                div.style.alignItems = 'flex-start';
                div.innerHTML = `
                    <div style="width:100%; margin-bottom:4px;"><b>Email:</b> ${u.email}</div>
                    <div style="width:100%; font-size:10px; color:#cbd5e1; margin-bottom:4px;">Device ID: ${u.device_id}</div>
                    <div style="width:100%; display:flex; gap:5px; margin-top:4px;">
                        <button onclick="submitAdminUserSettings('${u.email}', 'unban')" style="padding:4px 8px; font-size:10px; background:#16a34a; width:auto;">Unban</button>
                        <button onclick="submitAdminUserSettings('${u.email}', 'remove')" style="padding:4px 8px; font-size:10px; background:#dc2626; width:auto;">Remove</button>
                    </div>
                `;
                container.appendChild(div);
            });
        }

        function submitAdminUserSettings(email, action) {
            let key = email.replace(/[@.]/g, '_');
            let codeElem = document.getElementById('admin_code_' + key);
            let durElem = document.getElementById('admin_dur_' + key);
            
            let verification_code = codeElem ? codeElem.value.trim() : '';
            let account_duration = durElem ? durElem.value : '3 months';

            fetch('/admin_update_user_settings', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({email, verification_code, account_duration, action})
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    fetchAdminAllLists();
                } else {
                    alert("Error: " + data.error);
                }
            });
        }

        function submitAdminVerifiedSettings(email, key) {
            let durElem = document.getElementById('admin_dur_' + key);
            let account_duration = durElem ? durElem.value : '3 months';

            fetch('/admin_update_user_settings', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({email, account_duration, action: 'update_duration'})
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    alert("သက်တမ်း အောင်မြင်စွာ ပြောင်းလဲပြီးပါပြီ။");
                    fetchAdminAllLists();
                } else {
                    alert("Error: " + data.error);
                }
            });
        }

        function saveAdminPrices() {
            alert("Admin gift prices saved successfully.");
        }

        function openUserProfileModal() {
            document.getElementById('userProfileModal').style.display = 'block';
            fetchUserProfileData(() => {
                if (currentUserProfileData) {
                    document.getElementById('modalUsername').value = currentUserProfileData.username || '';
                    document.getElementById('modalAge').value = currentUserProfileData.age || '';
                    document.getElementById('modalCountry').value = currentUserProfileData.country || '';
                    updateProvinces();
                    document.getElementById('modalProvince').value = currentUserProfileData.province || '';
                    updateCities();
                    document.getElementById('modalCity').value = currentUserProfileData.city || '';
                    
                    checkAgeAndSexFields();
                    document.getElementById('modalSex').value = currentUserProfileData.sex || '';
                    
                    renderProfilePicturesUI();
                    renderUserGiftsSummary();
                }
            });
        }

        function closeUserProfileModal() {
            document.getElementById('userProfileModal').style.display = 'none';
        }

        function checkAgeAndSexFields() {
            let ageVal = parseInt(document.getElementById('modalAge').value);
            let sexSelect = document.getElementById('modalSex');
            sexSelect.innerHTML = '<option value="">Select Sex</option>';

            if (isNaN(ageVal) || ageVal < 18) {
                sexSelect.disabled = true;
                return;
            }
            sexSelect.disabled = false;
            if (ageVal >= 18 && ageVal <= 25) {
                sexSelect.innerHTML += '<option value="Boy">Boy</option><option value="Girl">Girl</option><option value="Gay">Gay</option><option value="Lesbian">Lesbian</option>';
            } else if (ageVal >= 26 && ageVal <= 90) {
                sexSelect.innerHTML += '<option value="Male">Male</option><option value="Female">Female</option><option value="Gay">Gay</option><option value="Lesbian">Lesbian</option>';
            }
        }

        function saveUsername() {
            let username = document.getElementById('modalUsername').value.trim();
            if (!username) return;
            if (username.length > 15) {
                document.getElementById('usernameWarning').innerText = "Username must be max 15 letters";
                return;
            }
            fetch('/update_user_profile', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({username})
            }).then(res => res.json()).then(d => {
                if (d.success) {
                    document.getElementById('usernameWarning').innerText = "";
                    alert("Username saved successfully.");
                    fetchUserProfileData();
                } else {
                    document.getElementById('usernameWarning').innerText = d.error || "Error saving username";
                }
            });
        }

        function saveAge() {
            let ageVal = parseInt(document.getElementById('modalAge').value);
            if (isNaN(ageVal) || ageVal < 18) {
                alert("အသက် 18 နှစ်အောက် မသုံးရပါ။ 18 နှင့် 90 ကြား ထည့်ပါ။");
                return;
            }
            fetch('/update_user_profile', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({age: ageVal})
            }).then(res => res.json()).then(d => {
                if (d.success) {
                    alert("Age saved successfully.");
                    checkAgeAndSexFields();
                }
            });
        }

        function saveSex() {
            let sexVal = document.getElementById('modalSex').value;
            if (!sexVal) return;
            fetch('/update_user_profile', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({sex: sexVal})
            }).then(res => res.json()).then(d => {
                if (d.success) alert("Sex saved successfully.");
            });
        }

        function updateProvinces() {
            let country = document.getElementById('modalCountry').value;
            let provSelect = document.getElementById('modalProvince');
            provSelect.innerHTML = '<option value="">Select Province/State</option>';
            if (country === 'Myanmar') {
                provSelect.innerHTML += '<option value="Mandalay">Mandalay Region</option><option value="Yangon">Yangon Region</option>';
            } else if (country === 'Thailand') {
                provSelect.innerHTML += '<option value="Bangkok">Bangkok</option><option value="Chiang Mai">Chiang Mai</option>';
            }
        }

        function updateCities() {
            let province = document.getElementById('modalProvince').value;
            let citySelect = document.getElementById('modalCity');
            citySelect.innerHTML = '<option value="">Select City</option>';
            if (province === 'Mandalay') {
                citySelect.innerHTML += '<option value="Mandalay City">Mandalay</option><option value="Pyin Oo Lwin">Pyin Oo Lwin</option>';
            } else if (province === 'Yangon') {
                citySelect.innerHTML += '<option value="Yangon City">Yangon</option>';
            }
        }

        function saveLocation() {
            let country = document.getElementById('modalCountry').value;
            let province = document.getElementById('modalProvince').value;
            let city = document.getElementById('modalCity').value;
            fetch('/update_user_profile', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({country, province, city})
            }).then(res => res.json()).then(d => {
                if (d.success) alert("Location saved successfully.");
            });
        }

        function renderProfilePicturesUI() {
            const container = document.getElementById('profilePicturesContainer');
            container.innerHTML = '';
            let pics = currentUserProfileData ? currentUserProfileData.pictures : ['', '', '', '', ''];
            let activePic = currentUserProfileData ? currentUserProfileData.active_profile_pic : '';

            for (let i = 0; i < 5; i++) {
                let box = document.createElement('div');
                box.style.width = '90px';
                box.style.height = '90px';
                box.style.border = '2px dashed var(--accent-color)';
                box.style.borderRadius = '8px';
                box.style.display = 'flex';
                box.style.flexDirection = 'column';
                box.style.alignItems = 'center';
                box.style.justifyContent = 'center';
                box.style.position = 'relative';
                box.style.background = 'rgba(0,0,0,0.4)';
                box.style.overflow = 'hidden';

                if (pics[i]) {
                    box.innerHTML = `<img src="${pics[i]}" style="width:100%; height:100%; object-fit:cover;">`;
                    if (activePic === pics[i]) {
                        box.style.borderColor = '#22c55e';
                    }
                } else {
                    box.innerHTML = `<span style="font-size:10px; color:#cbd5e1;">+ Add Photo</span>`;
                }
                container.appendChild(box);
            }
        }

        function renderUserGiftsSummary() {
            const display = document.getElementById('userGiftsSummaryDisplay');
            if (!currentUserProfileData) return;
            display.innerHTML = `
                <div>Rose Bought: ${currentUserProfileData.rose_bought || 0} | Received: ${currentUserProfileData.rose_received || 0}</div>
                <div>Orchid Bought: ${currentUserProfileData.orchid_bought || 0} | Received: ${currentUserProfileData.orchid_received || 0}</div>
                <div>Jasmine Bought: ${currentUserProfileData.jasmine_bought || 0} | Received: ${currentUserProfileData.jasmine_received || 0}</div>
            `;
        }

        function openGiftBuyModal() {
            document.getElementById('giftBuyModal').style.display = 'block';
        }
        function closeGiftBuyModal() {
            document.getElementById('giftBuyModal').style.display = 'none';
        }

        function submitGiftPurchaseRequest() {
            let rose = parseInt(document.getElementById('buyRoseQty').value) || 0;
            let orchid = parseInt(document.getElementById('buyOrchidQty').value) || 0;
            let jasmine = parseInt(document.getElementById('buyJasmineQty').value) || 0;

            if (rose === 0 && orchid === 0 && jasmine === 0) {
                alert("ကျေးဇူးပြု၍ လက်ဆောင်အရေအတွက် အနည်းဆုံးတစ်ခု ရွေးပါ။");
                return;
            }

            let rosePrice = 1000, orchidPrice = 3000, jasminePrice = 5000;
            let totalPrice = (rose * rosePrice) + (orchid * orchidPrice) + (jasmine * jasminePrice);

            closeGiftBuyModal();
            const buyChat = document.getElementById('floatingPresentBuyChat');
            buyChat.style.display = 'flex';
            document.getElementById('buyChatEmailDisplay').innerText = `Gift Purchase Request`;
            
            let autoMsg = `admin ကို ဒီလက်ဆောင်တွေ အရေအတွက် ဒီလောက်ဝယ်ချင်ပါတယ် ပိုက်ဆံဒီလောက် ကျပါတယ် (Rose: ${rose}, Orchid: ${orchid}, Jasmine: ${jasmine}) - Total: ${totalPrice} Ks. admin ဆီ ငွေလွှဲစရာ အကောင့် ပို့ပေးပါ`;
            document.getElementById('buyChatMessages').innerHTML = `<div><b>System:</b> ${autoMsg}</div>`;
            
            const isAdmin = localStorage.getItem('wma_is_admin') === 'true';
            if (isAdmin) {
                document.getElementById('adminSellButton').style.display = 'block';
            } else {
                document.getElementById('adminSellButton').style.display = 'none';
            }
        }

        function adminExecuteSell() {
            let rose = parseInt(document.getElementById('buyRoseQty').value) || 0;
            let orchid = parseInt(document.getElementById('buyOrchidQty').value) || 0;
            let jasmine = parseInt(document.getElementById('buyJasmineQty').value) || 0;
            let targetEmail = localStorage.getItem('wma_remember_email') || '';

            socket.emit('admin_sell_presents', { email: targetEmail, rose, orchid, jasmine });
        }

        socket.on('presents_sold_success', function(data) {
            alert("Presents successfully processed and added to profile!");
            closeBuyChat();
            fetchUserProfileData(() => { renderUserGiftsSummary(); });
        });

        function openRedeemModal() {
            document.getElementById('redeemModal').style.display = 'block';
        }
        function closeRedeemModal() {
            document.getElementById('redeemModal').style.display = 'none';
        }

        function submitRedeemRequest() {
            let rose = parseInt(document.getElementById('redeemRoseQty').value) || 0;
            let orchid = parseInt(document.getElementById('redeemOrchidQty').value) || 0;
            let jasmine = parseInt(document.getElementById('redeemJasmineQty').value) || 0;
            let kpayName = document.getElementById('redeemKpayName').value.trim();
            let kpayNumber = document.getElementById('redeemKpayNumber').value.trim();

            if (!kpayName || !kpayNumber) {
                alert("KPay Name နှင့် Number ထည့်ပါ။");
                return;
            }

            let roseVal = 1000 * 0.9, orchidVal = 3000 * 0.9, jasmineVal = 5000 * 0.9;
            let totalVal = (rose * roseVal) + (orchid * orchidVal) + (jasmine * jasmineVal);

            closeRedeemModal();
            const redeemChat = document.getElementById('floatingPresentRedeemChat');
            redeemChat.style.display = 'flex';
            document.getElementById('redeemChatEmailDisplay').innerText = `Redeem Request | KPay: ${kpayName} (${kpayNumber})`;
            
            let autoMsg = `Redeem Request (Rose: ${rose}, Orchid: ${orchid}, Jasmine: ${jasmine}) - Expected Payout: ${totalVal} Ks. KPay Name: ${kpayName}, Number: ${kpayNumber}`;
            document.getElementById('redeemChatMessages').innerHTML = `<div><b>System:</b> ${autoMsg}</div>`;

            const isAdmin = localStorage.getItem('wma_is_admin') === 'true';
            if (isAdmin) {
                document.getElementById('adminPermitRedeemButton').style.display = 'block';
            } else {
                document.getElementById('adminPermitRedeemButton').style.display = 'none';
            }
        }

        function adminExecutePermitRedeem() {
            alert("Redeem permitted by admin.");
            closeRedeemChat();
        }

        function toggleRecordVoice() {
            const btn = document.getElementById('recBtn');
            if (btn.innerText.includes('Record')) {
                navigator.mediaDevices.getUserMedia({ audio: true }).then(stream => {
                    mediaRecorder = new MediaRecorder(stream);
                    audioChunks = [];
                    mediaRecorder.ondataavailable = e => audioChunks.push(e.data);
                    mediaRecorder.onstop = () => {
                        document.getElementById('voiceOptions').style.display = 'block';
                    };
                    mediaRecorder.start();
                    btn.innerText = "Stop Recording (3s)";
                    setTimeout(() => {
                        if (mediaRecorder && mediaRecorder.state === 'recording') {
                            mediaRecorder.stop();
                            btn.innerText = "Record Voice (3s)";
                        }
                    }, 3000);
                }).catch(err => alert("Mic permission denied"));
            } else {
                if (mediaRecorder && mediaRecorder.state === 'recording') {
                    mediaRecorder.stop();
                    btn.innerText = "Record Voice (3s)";
                }
            }
        }

        function sendVoice(storeType) {
            const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
            const reader = new FileReader();
            reader.onload = function(e) {
                const base64Audio = e.target.result;
                const devId = getDeviceId();
                const email = localStorage.getItem('wma_remember_email') || '';
                const userName = getUserDisplayName(email, devId);

                socket.emit('new_message', {
                    user: userName,
                    type: 'audio',
                    content: base64Audio,
                    filename: 'voice_message.webm',
                    store: storeType,
                    room: currentRoom
                });
                document.getElementById('voiceOptions').style.display = 'none';
            };
            reader.readAsDataURL(audioBlob);
        }

        function triggerVideoCall() {
            document.getElementById('videoPopup').style.display = 'block';
            navigator.mediaDevices.getUserMedia({ video: true, audio: true }).then(stream => {
                localStream = stream;
                document.getElementById('localVideo').srcObject = stream;
                socket.emit('trigger_video_call', { room: currentRoom });
            }).catch(err => alert("Camera/Mic error"));
        }

        function stopConference() {
            if (localStream) {
                localStream.getTracks().forEach(track => track.stop());
            }
            closePopup();
        }

        function closePopup() {
            document.getElementById('videoPopup').style.display = 'none';
        }

        function toggleMuteSpeaker() {
            isSpeakerMuted = !isSpeakerMuted;
            document.getElementById('muteSpeakerBtn').innerText = isSpeakerMuted ? "Unmute Speaker" : "Mute Speaker";
        }

        function toggleMuteCamera() {
            if (localStream) {
                localStream.getVideoTracks().forEach(track => { track.enabled = !track.enabled; });
                isCameraMuted = !isCameraMuted;
                document.getElementById('muteCameraBtn').innerText = isCameraMuted ? "Unmute Camera" : "Mute Camera";
            }
        }

        function solveEquation(textarea) {
            let val = textarea.value.trim();
            if (val.endsWith('=')) {
                try {
                    let expr = val.slice(0, -1).trim();
                    let res = eval(expr);
                    textarea.value = val + ' ' + res;
                } catch(e) {}
            }
        }

        function sendText() {
            const txt = document.getElementById('textContent').value.trim();
            if (!txt) return;
            const devId = getDeviceId();
            const email = localStorage.getItem('wma_remember_email') || '';
            const userName = getUserDisplayName(email, devId);

            socket.emit('new_message', {
                user: userName,
                type: 'text',
                content: txt,
                filename: '',
                store: '48 Hours',
                room: currentRoom
            });
            document.getElementById('textContent').value = '';
        }

        function handleFileSelected(input) {
            if (input.files && input.files[0]) {
                const file = input.files[0];
                if (file.size > 50 * 1024 * 1024) {
                    alert("File size exceeds 50MB limit.");
                    return;
                }
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
            const devId = getDeviceId();
            const email = localStorage.getItem('wma_remember_email') || '';
            const userName = getUserDisplayName(email, devId);
            let msgType = selectedFileName.match(/\.(jpeg|jpg|png|gif)$/i) ? 'image' : 'file';

            socket.emit('new_message', {
                user: userName,
                type: msgType,
                content: selectedFileBase64,
                filename: selectedFileName,
                store: '48 Hours',
                room: currentRoom
            });

            selectedFileBase64 = null;
            selectedFileName = '';
            document.getElementById('fileInput').value = '';
            document.getElementById('sendFileBtn').disabled = true;
            document.getElementById('sendFileBtn').style.opacity = '0.5';
        }

        function loadChatHistory(room) {
            fetch(`/get_history?room=${room}`)
            .then(res => res.json())
            .then(data => {
                const stream = document.getElementById('historyStream');
                stream.innerHTML = '';
                data.reverse().forEach(msg => appendMessageToStream(msg));
                stream.scrollTop = stream.scrollHeight;
            });
        }

        function appendMessageToStream(msg) {
            const stream = document.getElementById('historyStream');
            const div = document.createElement('div');
            div.className = 'history-item';
            div.id = `msg_item_${msg.id}`;

            let contentHtml = '';
            if (msg.type === 'text') {
                contentHtml = `<div>${escapeHtml(msg.content)}</div>`;
            } else if (msg.type === 'image') {
                contentHtml = `<div><b>[Image: ${msg.filename}]</b><br><img src="${msg.content}" class="chat-image-preview"></div>`;
            } else if (msg.type === 'audio') {
                contentHtml = `<div><b>[Voice Message]</b><br><audio controls src="${msg.content}"></audio></div>`;
            } else if (msg.type === 'file') {
                contentHtml = `<div><b>[File: ${msg.filename}]</b><br><a href="${msg.content}" download="${msg.filename}" style="color:var(--accent-color);">Download File</a></div>`;
            }

            div.innerHTML = `
                <div style="font-weight:bold; color:var(--accent-color); margin-bottom:4px;">${escapeHtml(msg.user)} <span style="font-size:10px; color:#94a3b8;">(${msg.timestamp})</span></div>
                ${contentHtml}
                <div class="msg-actions">
                    <button onclick="deleteMessageItem(${msg.id})">Delete</button>
                </div>
            `;
            stream.appendChild(div);
            stream.scrollTop = stream.scrollHeight;
        }

        function escapeHtml(text) {
            return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
        }

        function deleteMessageItem(id) {
            socket.emit('delete_message_item', { id: id, room: currentRoom });
        }

        function registerDeviceWithServer(email) {
            const devId = getDeviceId();
            socket.emit('register_device', { device_id: devId, google_account: email });
            socket.emit('join_room', { room: currentRoom });
        }

        function resetStorage() {
            socket.emit('reset_storage');
        }

        function switchToMainChat() {
            currentRoom = 'main_group';
            document.getElementById('currentChatRoomTitle').innerText = 'WeMeet - Main Group Chat';
            document.getElementById('goToMainChatBtn').style.display = 'none';
            socket.emit('join_room', { room: currentRoom });
            loadChatHistory(currentRoom);
        }

        function switchPrivateChatFromDropdown(select) {
            let room = select.value;
            if (room && room !== 'main_group') {
                currentRoom = room;
                document.getElementById('currentChatRoomTitle').innerText = `Private Chat: ${room}`;
                document.getElementById('goToMainChatBtn').style.display = 'block';
                socket.emit('join_room', { room: currentRoom });
                loadChatHistory(currentRoom);
            }
        }

        function logoutUser() {
            fetch('/logout', { method: 'POST' }).then(() => {
                localStorage.removeItem('wma_remember_token');
                localStorage.removeItem('wma_remember_email');
                localStorage.removeItem('wma_is_admin');
                location.reload();
            });
        }
    </script>
</body>
</html>
"""

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)

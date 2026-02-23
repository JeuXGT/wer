from flask import Flask, render_template, request, redirect, session, jsonify
from flask_socketio import SocketIO, emit, join_room
import os
import time
import json
import subprocess
import sys
import platform

app = Flask(__name__)
app.secret_key = 'BUZZTALK-SeCrEt!'
secret_keyo = 'BUZZTALK-SeCrEt!'
USERS_FOLDER = "user-datas"
ROOM_LOG_FOLDER = "room-logs"
socketio = SocketIO(app, cors_allowed_origins="*")

# Oda yapısı: {oda_adı: {"password": "xxx", "users": set(), "log_path": "room-logs/oda.log", "proc": Popen}}
rooms_data = {}

# Başlangıç logları
print("Starting Servers..")
time.sleep(1)
print("[BUZZTALK] » Serverleri Başlatılıyor..")
time.sleep(0.5)
print("[BUZZTALK] » Türkiye Serveri Başlatılıyor..")
time.sleep(0.5)
print("[BUZZTALK] » Türkiye Serveri Başlatıldı!")
time.sleep(0.2)
print("[BUZZTALK] » DNS Yolu İle Almanya Serveri Başlatılıyor..")
time.sleep(0.5)
print("[BUZZTALK] » DNS Yolu İle Almanya Serveri Başlatıldı!")
time.sleep(0.1)
print(f"[BUZZTALK] » The Secret Key {secret_keyo}")
time.sleep(0.1)

def is_authorized(rank):
    return rank in ["KURUCU", "MODERATOR", "YETKILI"]

# Klasörler
os.makedirs(USERS_FOLDER, exist_ok=True)
os.makedirs(ROOM_LOG_FOLDER, exist_ok=True)

def write_user_ip(username, ip_addr):
    """Girişte kullanıcının JSON’una ip-address yazar."""
    user_file = os.path.join(USERS_FOLDER, f"{username}.json")
    if not os.path.exists(user_file):
        return
    try:
        with open(user_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        data['ip-address'] = ip_addr
        with open(user_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"ERROR » IP yazılamadı ({username}): {e}")

def start_room_console_tailer(log_path, room_name):
    """
    Oda log dosyasını canlı izleyen ayrı bir konsol penceresi (Windows) başlatır.
    Diğer platformlarda arka plan proses olarak çalışır.
    """
    tail_code = f"""
import time, sys, os
path = r'''{os.path.abspath(log_path)}'''
pos = 0
print("=== Oda Log Konsolu ===")
print("Oda: {room_name}")
print("Log: " + path)
print("========================")
# İlk içeriği bas
if os.path.exists(path):
    with open(path, 'r', encoding='utf-8') as f:
        data = f.read()
        if data:
            sys.stdout.write(data); sys.stdout.flush()
while True:
    try:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                f.seek(pos)
                data = f.read()
                if data:
                    sys.stdout.write(data)
                    sys.stdout.flush()
                    pos = f.tell()
        time.sleep(0.5)
    except KeyboardInterrupt:
        break
    except Exception as e:
        print("Tailer error:", e)
        time.sleep(1)
"""
    creationflags = 0
    popen_kwargs = {}
    if platform.system().lower().startswith("win"):
        # Yeni CMD penceresi
        creationflags = 0x00000010  # CREATE_NEW_CONSOLE
        # Windows'ta yeni konsolda çalıştırmak için python -u -c "<code>"
        popen_kwargs.update(dict(
            args=[sys.executable, "-u", "-c", tail_code],
            creationflags=creationflags
        ))
    else:
        # Diğer platformlarda normal arka plan
        popen_kwargs.update(dict(
            args=[sys.executable, "-u", "-c", tail_code]
        ))

    try:
        proc = subprocess.Popen(**popen_kwargs)
        return proc
    except Exception as e:
        print(f"WARN » Oda konsolu açılamadı: {e}")
        return None

@app.route('/')
def index():
    # Eğer giriş yapılmış ise chat'e gönder, değilse login'e yönlendir
    if 'username' in session:
        return render_template('chat.html',
                               username=session.get('username'),
                               rank=session.get('rank', 'KULLANICI'))
    return redirect('/login')

@app.route('/admin')
def admin_panel():
    if 'username' not in session or not is_authorized(session.get('rank', 'KULLANICI')):
        return redirect('/')

    users = []
    for filename in os.listdir(USERS_FOLDER):
        if filename.endswith('.json'):
            filepath = os.path.join(USERS_FOLDER, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    users.append({
                        "username": data.get("username", "<none>"),
                        "password": data.get("password", "<none>"),
                        "rank": data.get("rank", "KULLANICI"),
                        "ip": data.get("ip-address", "<none>")
                    })
            except Exception as e:
                print(f"WARN » {filename} okunamadı: {e}")
                continue

    return render_template('admin.html', users=users)

@app.route('/admin/add_user', methods=['POST'])
def add_user():
    if 'username' not in session or not is_authorized(session.get('rank', 'KULLANICI')):
        return jsonify({"success": False, "message": "Yetkiniz yok"}), 403

    data = request.get_json(force=False) or request.json or {}
    username = data.get("username")
    password = data.get("password")
    rank = data.get("rank", "KULLANICI")

    if not username or not password:
        return jsonify({"success": False, "message": "Kullanıcı adı ve şifre gerekli"}), 400

    user_file = os.path.join(USERS_FOLDER, f"{username}.json")
    if os.path.exists(user_file):
        return jsonify({"success": False, "message": "Bu kullanıcı zaten var"}), 409

    with open(user_file, 'w', encoding='utf-8') as f:
        json.dump({
            "username": username,
            "password": password,
            "rank": rank
        }, f, indent=4, ensure_ascii=False)

    print(f"[LOG] » Yeni hesap oluşturuldu: '{username}' (Yetki: {rank})")
    return jsonify({"success": True, "message": "Kullanıcı başarıyla eklendi."})

@app.route('/admin/delete_user', methods=['POST'])
def delete_user():
    if 'username' not in session or not is_authorized(session.get('rank', 'KULLANICI')):
        return jsonify({"success": False, "message": "Yetkiniz yok"}), 403

    data = request.get_json(force=False) or request.json or {}
    username_to_delete = data.get('username')
    if not username_to_delete:
        return jsonify({"success": False, "message": "Kullanıcı adı yok"}), 400

    user_file = os.path.join(USERS_FOLDER, f"{username_to_delete}.json")
    if os.path.exists(user_file):
        try:
            os.remove(user_file)
            print(f"[LOG] » Hesap silindi: '{username_to_delete}'")
            return jsonify({"success": True, "message": "Kullanıcı başarıyla silindi."})
        except Exception as e:
            return jsonify({"success": False, "message": f"Hata: {e}"}), 500
    else:
        return jsonify({"success": False, "message": "Kullanıcı bulunamadı"}), 404

@app.route('/admin/edit_user', methods=['POST'])
def edit_user():
    if 'username' not in session or not is_authorized(session.get('rank', 'KULLANICI')):
        return jsonify({"success": False, "error": "Yetkiniz yok"}), 403

    data = request.get_json(force=False) or request.json or {}
    username = data.get("oldUsername")
    new_password = data.get("password")
    new_rank = data.get("rank")
    new_username = data.get("newUsername")

    if not username:
        return jsonify({"success": False, "error": "Kullanıcı adı boş olamaz"}), 400

    user_file = os.path.join(USERS_FOLDER, f"{username}.json")
    if not os.path.exists(user_file):
        return jsonify({"success": False, "error": "Kullanıcı bulunamadı"}), 404

    with open(user_file, 'r', encoding='utf-8') as f:
        user_data = json.load(f)

    # Loglar
    if new_password and new_password != user_data.get('password'):
        print(f"[LOG] » Hesap '{username}' şifresi değiştirildi.")

    if new_rank and new_rank != user_data.get('rank'):
        print(f"[LOG] » Hesap '{username}' yetkisi '{user_data.get('rank')}' → '{new_rank}' olarak değiştirildi.")
        user_data['rank'] = new_rank

    if new_username and new_username != username:
        new_user_file = os.path.join(USERS_FOLDER, f"{new_username}.json")
        if os.path.exists(new_user_file):
            return jsonify({"success": False, "error": "Yeni kullanıcı adı zaten var"}), 409
        os.rename(user_file, new_user_file)
        user_file = new_user_file
        print(f"[LOG] » Hesap ismi '{username}' → '{new_username}' olarak değiştirildi.")
        username = new_username
        user_data['username'] = new_username

    # Şifreyi güncelle (eğer boş değilse)
    if new_password:
        user_data['password'] = new_password

    with open(user_file, 'w', encoding='utf-8') as f:
        json.dump(user_data, f, indent=4, ensure_ascii=False)

    return jsonify({"success": True})

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = ""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        if not username or not password:
            error = "Kullanıcı adı ve şifre gerekli!"
            return render_template('login.html', error=error)

        user_file = os.path.join(USERS_FOLDER, f"{username}.json")
        if os.path.exists(user_file):
            try:
                with open(user_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if data.get('password') == password:
                        session['username'] = username
                        session['rank'] = data.get("rank", "KULLANICI")
                        session['room'] = "Genel"  # varsayılan oda
                        # IP'yi yaz
                        write_user_ip(username, request.remote_addr)

                        print(f"[LOG] » [{data.get('rank', 'KULLANICI')}] {username} Hesabına Giriş Yapıldı! IP: {request.remote_addr}")
                        # İlk giriş mesajını Genel odasına atacağız, kullanıcı bağlanınca 'connect' eventinde odaya join edilecek
                        socketio.emit('message', f"[SERVER] » [{data.get('rank', 'KULLANICI')}] {username} Sohbete Giriş Yaptı!", room="Genel")
                        return redirect('/')
                    else:
                        error = "Hatalı Şifre!"
            except Exception as e:
                error = "Kullanıcı verisi okunamadı."
                print(f"ERROR » {e}")
        else:
            error = "Kullanıcı Bulunamadı!"
    return render_template('login.html', error=error)

@app.route('/register', methods=['GET', 'POST'])
def register():
    error = ""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        if not username or not password:
            error = "Kullanıcı adı ve şifre gerekli!"
            return render_template('register.html', error=error)

        user_file = os.path.join(USERS_FOLDER, f"{username}.json")
        if os.path.exists(user_file):
            error = "Bu isim başka biri tarafından kullanılıyor!"
        else:
            with open(user_file, 'w', encoding='utf-8') as f:
                json.dump({
                    "username": username,
                    "password": password,
                    "rank": "KULLANICI"
                }, f, indent=4, ensure_ascii=False)
            rank = session.get('rank', 'KULLANICI')
            print(f"[LOG] » [{rank}] {username} Hesabı Oluşturuldu!")
            return redirect('/login')
    return render_template('register.html', error=error)

@app.route('/logout')
def logout():
    username = session.get('username', 'Bilinmeyen')
    rank = session.get('rank', 'KULLANICI')
    room = session.get('room', 'Genel')
    print(f"[LOG] » [{rank}] {username} Hesabından Çıkış Yapıldı!")
    socketio.emit('message', f"[SERVER] » [{rank}] {username} Sohbetten Çıkış Yaptı!", room=room)
    session.clear()
    return redirect('/login')

@socketio.on('connect')
def on_connect():
    if 'username' in session:
        room = session.get('room', 'Genel')
        join_room(room)

@socketio.on('message')
def handle_message(msg):
    text = str(msg or "").strip()
    username = session.get('username', '<none>')
    rank = session.get('rank', 'KULLANICI')
    current_room = session.get('room', 'Genel')

    if text == "/temizle":
        if rank == "KURUCU":
            socketio.emit('clear_chat', room=current_room)
            socketio.emit('clear_chat', room="Genel")
            socketio.emit('message', f"[SERVER] » Sohbet {username} tarafından temizlendi!", room=current_room)
            print(f"LOG » {current_room} odası {username} tarafından temizlendi.")
            if current_room in rooms_data:
                with open(rooms_data[current_room]["log_path"], "a", encoding="utf-8") as lf:
                    lf.write(f"[SERVER] Sohbet {username} tarafından temizlendi.\n")
        else:
            socketio.emit('message', "[SERVER] » Bu komutu sadece kurucu kullanabilir!", to=request.sid)
        return

    if text == "/admin":
        if rank in ["KURUCU", "MODERATOR", "YETKILI"]:
            socketio.emit('redirect', '/admin', to=request.sid)
            print(f"[LOG] » [{rank}] {username} Admin Paneline Yönlendirildi!")
        else:
            socketio.emit('message', f"[SUNUCU] {username}, Admin Paneline Erişim Yetkiniz Yok!", to=request.sid)
            print(f"[LOG] » [{rank}] {username} Admin Paneline Erişim Engellendi!")
        return

    if text.startswith("/oda "):
        parts = text.split(" ", 2)
        if len(parts) < 3:
            emit('message', "[SERVER] » Kullanım: /oda <isim> <şifre>", to=request.sid)
            return

        room_name, pwd = parts[1], parts[2]
        if room_name in rooms_data:
            emit('message', f"[SERVER] » {room_name} zaten var!", to=request.sid)
            return

        log_path = os.path.join(ROOM_LOG_FOLDER, f"{room_name}.log")
        rooms_data[room_name] = {"password": pwd, "users": set(), "log_path": log_path, "proc": None}

        with open(log_path, "a", encoding="utf-8") as lf:
            lf.write(f"[SERVER] Oda oluşturuldu: {room_name}\n")

        proc = start_room_console_tailer(log_path, room_name)
        rooms_data[room_name]["proc"] = proc

        join_room(room_name)
        session['room'] = room_name
        rooms_data[room_name]["users"].add(username)

        emit('message', f"[SERVER] » Oda '{room_name}' oluşturuldu! (şifre ayarlandı)", to=request.sid)
        socketio.emit('message', f"[SERVER] » {username} odayı oluşturdu ve odaya giriş yaptı.", room=room_name)

        with open(log_path, "a", encoding="utf-8") as lf:
            lf.write(f"[SERVER] {username} odayı oluşturdu ve giriş yaptı.\n")
        return

    if text.startswith("/join "):
        parts = text.split(" ", 2)
        if len(parts) < 3:
            emit('message', "[SERVER] » Kullanım: /join <isim> <şifre>", to=request.sid)
            return

        room_name, pwd = parts[1], parts[2]
        if room_name not in rooms_data:
            emit('message', f"[SERVER] » {room_name} diye bir oda yok!", to=request.sid)
            return
        if rooms_data[room_name]["password"] != pwd:
            emit('message', "[SERVER] » Hatalı şifre!", to=request.sid)
            return

        join_room(room_name)
        session['room'] = room_name
        rooms_data[room_name]["users"].add(username)

        socketio.emit('message', f"[SERVER] » {username} odaya girdi!", room=room_name)
        with open(rooms_data[room_name]["log_path"], "a", encoding="utf-8") as lf:
            lf.write(f"[SERVER] {username} odaya girdi.\n")
        return

    full_msg = f"[{rank}] {username} » {text}"
    socketio.emit('message', full_msg, room=current_room)
    print(full_msg)

    if current_room in rooms_data:
        with open(rooms_data[current_room]["log_path"], "a", encoding="utf-8") as lf:
            lf.write(full_msg + "\n")

if __name__ == '__main__':
    print(f"[BUZZTALK] » Serverler Hazır!")
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)


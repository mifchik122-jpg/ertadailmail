import os
import sqlite3
import json
from datetime import datetime
from flask import Flask, render_template_string, request, redirect, url_for, flash, session, send_file, jsonify, make_response
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import jwt
from functools import wraps

app = Flask(__name__)
app.secret_key = 'your-secret-key-here-change-in-production'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['JWT_SECRET_KEY'] = 'your-jwt-secret-key-change-in-production'
# Расширяем список разрешенных файлов
app.config['ALLOWED_EXTENSIONS'] = {
    'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'bmp', 'ico',
    'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx',
    'zip', 'rar', '7z', 'tar', 'gz',
    'mp3', 'wav', 'mp4', 'avi', 'mov',
    'py', 'js', 'html', 'css', 'json', 'xml',
    'ttf', 'otf', 'woff', 'woff2'
}

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

def init_db():
    conn = sqlite3.connect('mail.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            api_key TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender TEXT NOT NULL,
            recipient TEXT NOT NULL,
            subject TEXT,
            body TEXT,
            attachment_path TEXT,
            attachment_filename TEXT,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            read BOOLEAN DEFAULT 0
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            api_key TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    conn.commit()
    conn.close()

init_db()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def get_db_connection():
    conn = sqlite3.connect('mail.db')
    conn.row_factory = sqlite3.Row
    return conn

# HTML шаблоны как строки
BASE_TEMPLATE = '''
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }}</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; padding: 20px; }
        .container { max-width: 1200px; margin: 0 auto; }
        .header { background: white; padding: 20px 30px; border-radius: 10px; box-shadow: 0 10px 30px rgba(0,0,0,0.1); margin-bottom: 30px; display: flex; justify-content: space-between; align-items: center; }
        .logo { font-size: 28px; font-weight: bold; color: #667eea; text-decoration: none; }
        .logo span { color: #764ba2; }
        .nav { display: flex; gap: 20px; }
        .nav a { text-decoration: none; color: #555; padding: 8px 16px; border-radius: 5px; transition: all 0.3s; }
        .nav a:hover { background: #667eea; color: white; }
        .main-content { background: white; padding: 30px; border-radius: 10px; box-shadow: 0 10px 30px rgba(0,0,0,0.1); min-height: 500px; }
        .flash-messages { margin-bottom: 20px; }
        .alert { padding: 15px; border-radius: 5px; margin-bottom: 10px; }
        .alert-success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
        .alert-error { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
        .form-group { margin-bottom: 20px; }
        .form-group label { display: block; margin-bottom: 5px; color: #555; font-weight: 500; }
        .form-control { width: 100%; padding: 12px; border: 2px solid #e0e0e0; border-radius: 5px; font-size: 16px; transition: border 0.3s; }
        .form-control:focus { outline: none; border-color: #667eea; }
        .btn { display: inline-block; padding: 12px 30px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border: none; border-radius: 5px; font-size: 16px; cursor: pointer; transition: transform 0.3s, box-shadow 0.3s; text-decoration: none; }
        .btn:hover { transform: translateY(-2px); box-shadow: 0 5px 15px rgba(0,0,0,0.2); }
        .btn-secondary { background: #6c757d; }
        .btn-api { background: #28a745; }
        .email-list { list-style: none; }
        .email-item { padding: 20px; border-bottom: 1px solid #eee; cursor: pointer; transition: background 0.3s; }
        .email-item:hover { background: #f8f9fa; }
        .email-item.unread { background: #f0f7ff; border-left: 4px solid #667eea; }
        .email-subject { font-weight: bold; color: #333; margin-bottom: 5px; }
        .email-meta { font-size: 14px; color: #666; display: flex; justify-content: space-between; }
        .attachment-badge { background: #667eea; color: white; padding: 2px 8px; border-radius: 10px; font-size: 12px; margin-left: 10px; }
        .login-container { max-width: 400px; margin: 50px auto; }
        .login-header { text-align: center; margin-bottom: 30px; }
        .login-header h1 { color: #333; margin-bottom: 10px; }
        .api-section { background: #f8f9fa; padding: 20px; border-radius: 10px; margin-top: 30px; }
        .api-key { background: #e9ecef; padding: 10px; border-radius: 5px; font-family: monospace; margin: 10px 0; word-break: break-all; }
        .code-block { background: #2d2d2d; color: #f8f8f2; padding: 20px; border-radius: 5px; font-family: 'Courier New', monospace; margin: 20px 0; overflow-x: auto; }
        .endpoint { color: #66d9ef; }
        .method { color: #f92672; }
        .tab { margin-left: 20px; }
        .tab2 { margin-left: 40px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <a href="/dashboard" class="logo">ERTA<span>DEIL</span> Mail</a>
            {% if user_id %}
            <div class="nav">
                <a href="/dashboard">Главная</a>
                <a href="/compose">Написать</a>
                <a href="/inbox">Входящие</a>
                <a href="/sent">Отправленные</a>
                <a href="/api">API</a>
                <a href="/logout">Выйти</a>
            </div>
            {% endif %}
        </div>
        
        <div class="flash-messages">
            {% for category, message in messages %}
                <div class="alert alert-{{ category }}">{{ message }}</div>
            {% endfor %}
        </div>
        
        <div class="main-content">
            {{ content|safe }}
        </div>
    </div>
</body>
</html>
'''

# Функция для рендеринга страниц
def render_page(content, title="ERTADEIL Mail", **kwargs):
    messages = []
    with app.test_request_context():
        flashed = get_flashed_messages(with_categories=True)
        messages = flashed
    
    # Создаем контекст для шаблона
    context = {
        'title': title,
        'content': content,
        'messages': messages,
        'user_id': session.get('user_id'),
        'username': session.get('username'),
        'email': session.get('email'),
        **kwargs
    }
    
    return render_template_string(BASE_TEMPLATE, **context)

# API Authentication decorators
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        
        # Check for token in headers
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            if auth_header.startswith('Bearer '):
                token = auth_header.split(' ')[1]
        
        # Check for API key in headers or query params
        api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
        
        if not token and not api_key:
            return jsonify({'message': 'Требуется токен или API ключ'}), 401
        
        conn = get_db_connection()
        user = None
        
        if token:
            try:
                data = jwt.decode(token, app.config['JWT_SECRET_KEY'], algorithms=['HS256'])
                user = conn.execute('SELECT * FROM users WHERE id = ?', (data['user_id'],)).fetchone()
            except:
                conn.close()
                return jsonify({'message': 'Неверный токен'}), 401
        
        elif api_key:
            api_key_record = conn.execute('SELECT * FROM api_keys WHERE api_key = ?', (api_key,)).fetchone()
            if api_key_record:
                user = conn.execute('SELECT * FROM users WHERE id = ?', (api_key_record['user_id'],)).fetchone()
        
        if not user:
            conn.close()
            return jsonify({'message': 'Пользователь не найден'}), 401
        
        conn.close()
        return f(user, *args, **kwargs)
    
    return decorated

# Маршруты Web UI
@app.route('/')
def home():
    if 'user_id' in session:
        return redirect('/dashboard')
    return redirect('/login')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        
        if password != confirm_password:
            flash('Пароли не совпадают', 'error')
            return render_page('''
            <div class="login-container">
                <div class="login-header">
                    <h1>Регистрация</h1>
                    <p>Создайте аккаунт в системе ERTADEIL Mail</p>
                </div>
                
                <form method="POST" action="/register">
                    <div class="form-group">
                        <label for="username">Имя пользователя:</label>
                        <input type="text" id="username" name="username" class="form-control" required>
                        <small>Будет использоваться в адресе: username@ertadeil</small>
                    </div>
                    
                    <div class="form-group">
                        <label for="password">Пароль:</label>
                        <input type="password" id="password" name="password" class="form-control" required>
                    </div>
                    
                    <div class="form-group">
                        <label for="confirm_password">Подтвердите пароль:</label>
                        <input type="password" id="confirm_password" name="confirm_password" class="form-control" required>
                    </div>
                    
                    <button type="submit" class="btn">Зарегистрироваться</button>
                    <p style="margin-top: 20px;">Уже есть аккаунт? <a href="/login">Войти</a></p>
                </form>
            </div>
            ''', title="Регистрация - ERTADEIL Mail")
        
        email = f"{username}@ertadeil"
        
        conn = get_db_connection()
        existing_user = conn.execute('SELECT * FROM users WHERE username = ? OR email = ?', 
                                   (username, email)).fetchone()
        
        if existing_user:
            flash('Пользователь с таким именем или email уже существует', 'error')
            conn.close()
            return render_page('''
            <div class="login-container">
                <div class="login-header">
                    <h1>Регистрация</h1>
                    <p>Создайте аккаунт в системе ERTADEIL Mail</p>
                </div>
                
                <form method="POST" action="/register">
                    <div class="form-group">
                        <label for="username">Имя пользователя:</label>
                        <input type="text" id="username" name="username" class="form-control" required>
                        <small>Будет использоваться в адресе: username@ertadeil</small>
                    </div>
                    
                    <div class="form-group">
                        <label for="password">Пароль:</label>
                        <input type="password" id="password" name="password" class="form-control" required>
                    </div>
                    
                    <div class="form-group">
                        <label for="confirm_password">Подтвердите пароль:</label>
                        <input type="password" id="confirm_password" name="confirm_password" class="form-control" required>
                    </div>
                    
                    <button type="submit" class="btn">Зарегистрироваться</button>
                    <p style="margin-top: 20px;">Уже есть аккаунт? <a href="/login">Войти</a></p>
                </form>
            </div>
            ''', title="Регистрация - ERTADEIL Mail")
        
        password_hash = generate_password_hash(password)
        conn.execute('INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)',
                    (username, email, password_hash))
        conn.commit()
        conn.close()
        
        flash('Регистрация успешна! Теперь вы можете войти.', 'success')
        return redirect('/login')
    
    return render_page('''
    <div class="login-container">
        <div class="login-header">
            <h1>Регистрация</h1>
            <p>Создайте аккаунт в системе ERTADEIL Mail</p>
        </div>
        
        <form method="POST" action="/register">
            <div class="form-group">
                <label for="username">Имя пользователя:</label>
                <input type="text" id="username" name="username" class="form-control" required>
                <small>Будет использоваться в адресе: username@ertadeil</small>
            </div>
            
            <div class="form-group">
                <label for="password">Пароль:</label>
                <input type="password" id="password" name="password" class="form-control" required>
            </div>
            
            <div class="form-group">
                <label for="confirm_password">Подтвердите пароль:</label>
                <input type="password" id="confirm_password" name="confirm_password" class="form-control" required>
            </div>
            
            <button type="submit" class="btn">Зарегистрироваться</button>
            <p style="margin-top: 20px;">Уже есть аккаунт? <a href="/login">Войти</a></p>
        </form>
    </div>
    ''', title="Регистрация - ERTADEIL Mail")

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['email'] = user['email']
            conn.close()
            flash('Вход выполнен успешно!', 'success')
            return redirect('/dashboard')
        else:
            flash('Неверный email или пароль', 'error')
            conn.close()
    
    return render_page('''
    <div class="login-container">
        <div class="login-header">
            <h1>Вход в систему</h1>
            <p>Добро пожаловать в ERTADEIL Mail</p>
        </div>
        
        <form method="POST" action="/login">
            <div class="form-group">
                <label for="email">Email:</label>
                <input type="text" id="email" name="email" class="form-control" required>
                <small>В формате: username@ertadeil</small>
            </div>
            
            <div class="form-group">
                <label for="password">Пароль:</label>
                <input type="password" id="password" name="password" class="form-control" required>
            </div>
            
            <button type="submit" class="btn">Войти</button>
            <p style="margin-top: 20px;">Нет аккаунта? <a href="/register">Зарегистрироваться</a></p>
        </form>
    </div>
    ''', title="Вход - ERTADEIL Mail")

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect('/login')
    
    conn = get_db_connection()
    inbox_count = conn.execute('SELECT COUNT(*) FROM emails WHERE recipient = ?', 
                              (session['email'],)).fetchone()[0]
    sent_count = conn.execute('SELECT COUNT(*) FROM emails WHERE sender = ?', 
                             (session['email'],)).fetchone()[0]
    
    # Получаем API ключ пользователя
    api_key_record = conn.execute('SELECT * FROM api_keys WHERE user_id = ?', 
                                 (session['user_id'],)).fetchone()
    api_key = api_key_record['api_key'] if api_key_record else None
    
    conn.close()
    
    api_section = ''
    if api_key:
        api_section = f'''
        <div class="api-section">
            <h3>🔑 Ваш API ключ:</h3>
            <div class="api-key">{api_key}</div>
            <p>Используйте этот ключ для доступа к API</p>
            <a href="/api" class="btn btn-api">Документация API</a>
        </div>
        '''
    else:
        api_section = '''
        <div class="api-section">
            <h3>🔑 API доступ</h3>
            <p>У вас еще нет API ключа</p>
            <a href="/generate_api_key" class="btn btn-api">Сгенерировать API ключ</a>
        </div>
        '''
    
    return render_page(f'''
    <h1>Добро пожаловать, {session['username']}!</h1>
    <p style="margin: 20px 0; font-size: 18px;">Ваш email: <strong>{session['email']}</strong></p>
    
    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin-top: 40px;">
        <div style="background: #f8f9fa; padding: 30px; border-radius: 10px; text-align: center;">
            <h3>📨 Входящие</h3>
            <p style="font-size: 24px; font-weight: bold; margin: 10px 0;">{inbox_count}</p>
            <a href="/inbox" class="btn">Открыть</a>
        </div>
        
        <div style="background: #f8f9fa; padding: 30px; border-radius: 10px; text-align: center;">
            <h3>✏️ Написать</h3>
            <p style="margin: 10px 0;">Создать новое письмо</p>
            <a href="/compose" class="btn">Создать</a>
        </div>
        
        <div style="background: #f8f9fa; padding: 30px; border-radius: 10px; text-align: center;">
            <h3>📤 Отправленные</h3>
            <p style="font-size: 24px; font-weight: bold; margin: 10px 0;">{sent_count}</p>
            <a href="/sent" class="btn">Открыть</a>
        </div>
    </div>
    
    {api_section}
    
    <div style="margin-top: 40px;">
        <h2>Быстрые действия:</h2>
        <div style="display: flex; gap: 15px; margin-top: 20px;">
            <a href="/compose" class="btn">Написать письмо</a>
            <a href="/inbox" class="btn btn-secondary">Проверить почту</a>
        </div>
    </div>
    ''', title="Главная - ERTADEIL Mail")

@app.route('/generate_api_key')
def generate_api_key():
    if 'user_id' not in session:
        return redirect('/login')
    
    import secrets
    api_key = secrets.token_urlsafe(32)
    
    conn = get_db_connection()
    
    # Удаляем старый ключ если есть
    conn.execute('DELETE FROM api_keys WHERE user_id = ?', (session['user_id'],))
    
    # Создаем новый ключ
    conn.execute('INSERT INTO api_keys (user_id, api_key) VALUES (?, ?)',
                (session['user_id'], api_key))
    conn.commit()
    conn.close()
    
    flash('API ключ успешно сгенерирован!', 'success')
    return redirect('/dashboard')

@app.route('/api')
def api_documentation():
    if 'user_id' not in session:
        return redirect('/login')
    
    conn = get_db_connection()
    api_key_record = conn.execute('SELECT * FROM api_keys WHERE user_id = ?', 
                                 (session['user_id'],)).fetchone()
    api_key = api_key_record['api_key'] if api_key_record else 'ВАШ_API_КЛЮЧ'
    conn.close()
    
    return render_page(f'''
    <h1>📚 Документация API</h1>
    <p style="margin: 20px 0;">Используйте API для интеграции почтовой системы в ваши приложения.</p>
    
    <div class="api-section">
        <h3>🔑 Ваш API ключ:</h3>
        <div class="api-key">{api_key}</div>
        <p><strong>Заголовок для запросов:</strong> <code>X-API-Key: {api_key}</code></p>
    </div>
    
    <h2 style="margin-top: 40px;">📋 Доступные endpoints:</h2>
    
    <div class="code-block">
        <h3>1. Получить информацию о пользователе</h3>
        <p><span class="method">GET</span> <span class="endpoint">/api/user</span></p>
        <p>Пример ответа:</p>
        <pre>
{{
    "success": true,
    "user": {{
        "id": 1,
        "username": "test",
        "email": "test@ertadeil",
        "created_at": "2024-01-17 12:00:00"
    }}
}}
        </pre>
    </div>
    
    <div class="code-block">
        <h3>2. Отправить письмо</h3>
        <p><span class="method">POST</span> <span class="endpoint">/api/send</span></p>
        <p>Параметры (JSON):</p>
        <pre>
{{
    "recipient": "username@ertadeil",
    "subject": "Тема письма",
    "body": "Текст письма"
}}
        </pre>
        <p>Пример ответа:</p>
        <pre>
{{
    "success": true,
    "message": "Письмо отправлено",
    "email_id": 123
}}
        </pre>
    </div>
    
    <div class="code-block">
        <h3>3. Получить входящие письма</h3>
        <p><span class="method">GET</span> <span class="endpoint">/api/inbox</span></p>
        <p>Дополнительные параметры:</p>
        <ul>
            <li><code>?limit=10</code> - ограничение количества писем</li>
            <li><code>?unread=true</code> - только непрочитанные</li>
        </ul>
    </div>
    
    <div class="code-block">
        <h3>4. Получить отправленные письма</h3>
        <p><span class="method">GET</span> <span class="endpoint">/api/sent</span></p>
    </div>
    
    <div class="code-block">
        <h3>5. Получить конкретное письмо</h3>
        <p><span class="method">GET</span> <span class="endpoint">/api/email/&lt;id&gt;</span></p>
    </div>
    
    <div class="code-block">
        <h3>6. Отметить письмо как прочитанное</h3>
        <p><span class="method">POST</span> <span class="endpoint">/api/email/&lt;id&gt;/read</span></p>
    </div>
    
    <h2 style="margin-top: 40px;">📝 Примеры использования:</h2>
    
    <div class="code-block">
        <h3>Python (requests):</h3>
        <pre>
import requests

api_key = "{api_key}"
headers = {{"X-API-Key": api_key}}

# Получить информацию о пользователе
response = requests.get("http://localhost:5000/api/user", headers=headers)
print(response.json())

# Отправить письмо
data = {{
    "recipient": "admin@ertadeil",
    "subject": "Привет из API",
    "body": "Это письмо отправлено через API"
}}
response = requests.post("http://localhost:5000/api/send", 
                        json=data, 
                        headers=headers)
print(response.json())
        </pre>
    </div>
    
    <div class="code-block">
        <h3>JavaScript (fetch):</h3>
        <pre>
const apiKey = '{api_key}';

// Получить входящие
fetch('http://localhost:5000/api/inbox', {{
    headers: {{
        'X-API-Key': apiKey
    }}
}})
.then(response => response.json())
.then(data => console.log(data));
        </pre>
    </div>
    
    <div class="code-block">
        <h3>cURL:</h3>
        <pre>
# Получить информацию о пользователе
curl -H "X-API-Key: {api_key}" \\
     http://localhost:5000/api/user

# Отправить письмо
curl -X POST -H "X-API-Key: {api_key}" \\
     -H "Content-Type: application/json" \\
     -d '{{"recipient":"test@ertadeil","subject":"Test","body":"Hello"}}' \\
     http://localhost:5000/api/send
        </pre>
    </div>
    ''', title="API Документация - ERTADEIL Mail")

@app.route('/compose', methods=['GET', 'POST'])
def compose():
    if 'user_id' not in session:
        return redirect('/login')
    
    if request.method == 'POST':
        recipient = request.form['recipient']
        subject = request.form['subject']
        body = request.form['body']
        
        if not recipient.endswith('@ertadeil'):
            flash('Можно отправлять только на адреса @ertadeil', 'error')
            return render_page('''
            <h1>Новое письмо</h1>
            
            <form method="POST" action="/compose" enctype="multipart/form-data" style="margin-top: 30px;">
                <div class="form-group">
                    <label for="recipient">Кому:</label>
                    <input type="text" id="recipient" name="recipient" class="form-control" required placeholder="username@ertadeil">
                </div>
                
                <div class="form-group">
                    <label for="subject">Тема:</label>
                    <input type="text" id="subject" name="subject" class="form-control" required>
                </div>
                
                <div class="form-group">
                    <label for="body">Сообщение:</label>
                    <textarea id="body" name="body" class="form-control" rows="10" required></textarea>
                </div>
                
                <div class="form-group">
                    <label for="attachment">Прикрепить файл:</label>
                    <input type="file" id="attachment" name="attachment" class="form-control">
                    <small>Разрешены: {allowed_extensions}</small>
                </div>
                
                <div style="display: flex; gap: 15px; margin-top: 30px;">
                    <button type="submit" class="btn">Отправить</button>
                    <a href="/dashboard" class="btn btn-secondary">Отмена</a>
                </div>
            </form>
            '''.format(allowed_extensions=", ".join(app.config['ALLOWED_EXTENSIONS'])), title="Новое письмо - ERTADEIL Mail")
        
        conn = get_db_connection()
        recipient_user = conn.execute('SELECT * FROM users WHERE email = ?', (recipient,)).fetchone()
        
        if not recipient_user:
            flash('Получатель не найден в системе', 'error')
            conn.close()
            return render_page('''
            <h1>Новое письмо</h1>
            
            <form method="POST" action="/compose" enctype="multipart/form-data" style="margin-top: 30px;">
                <div class="form-group">
                    <label for="recipient">Кому:</label>
                    <input type="text" id="recipient" name="recipient" class="form-control" required placeholder="username@ertadeil">
                </div>
                
                <div class="form-group">
                    <label for="subject">Тема:</label>
                    <input type="text" id="subject" name="subject" class="form-control" required>
                </div>
                
                <div class="form-group">
                    <label for="body">Сообщение:</label>
                    <textarea id="body" name="body" class="form-control" rows="10" required></textarea>
                </div>
                
                <div class="form-group">
                    <label for="attachment">Прикрепить файл:</label>
                    <input type="file" id="attachment" name="attachment" class="form-control">
                    <small>Разрешены: {allowed_extensions}</small>
                </div>
                
                <div style="display: flex; gap: 15px; margin-top: 30px;">
                    <button type="submit" class="btn">Отправить</button>
                    <a href="/dashboard" class="btn btn-secondary">Отмена</a>
                </div>
            </form>
            '''.format(allowed_extensions=", ".join(app.config['ALLOWED_EXTENSIONS'])), title="Новое письмо - ERTADEIL Mail")
        
        attachment_path = None
        attachment_filename = None
        
        if 'attachment' in request.files:
            file = request.files['attachment']
            if file and file.filename != '' and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                attachment_path = filepath
                attachment_filename = filename
        
        conn.execute('''
            INSERT INTO emails (sender, recipient, subject, body, attachment_path, attachment_filename)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (session['email'], recipient, subject, body, attachment_path, attachment_filename))
        
        conn.commit()
        conn.close()
        
        flash('Письмо отправлено!', 'success')
        return redirect('/inbox')
    
    return render_page('''
    <h1>Новое письмо</h1>
    
    <form method="POST" action="/compose" enctype="multipart/form-data" style="margin-top: 30px;">
        <div class="form-group">
            <label for="recipient">Кому:</label>
            <input type="text" id="recipient" name="recipient" class="form-control" required placeholder="username@ertadeil">
        </div>
        
        <div class="form-group">
            <label for="subject">Тема:</label>
            <input type="text" id="subject" name="subject" class="form-control" required>
        </div>
        
        <div class="form-group">
            <label for="body">Сообщение:</label>
            <textarea id="body" name="body" class="form-control" rows="10" required></textarea>
        </div>
        
        <div class="form-group">
            <label for="attachment">Прикрепить файл:</label>
            <input type="file" id="attachment" name="attachment" class="form-control">
            <small>Разрешены: {allowed_extensions}</small>
        </div>
        
        <div style="display: flex; gap: 15px; margin-top: 30px;">
            <button type="submit" class="btn">Отправить</button>
            <a href="/dashboard" class="btn btn-secondary">Отмена</a>
        </div>
    </form>
    '''.format(allowed_extensions=", ".join(app.config['ALLOWED_EXTENSIONS'])), title="Новое письмо - ERTADEIL Mail")

@app.route('/inbox')
def inbox():
    if 'user_id' not in session:
        return redirect('/login')
    
    conn = get_db_connection()
    emails = conn.execute('''
        SELECT * FROM emails 
        WHERE recipient = ? 
        ORDER BY sent_at DESC
    ''', (session['email'],)).fetchall()
    conn.close()
    
    emails_html = ''
    for email in emails:
        read_class = '' if email['read'] else 'unread'
        attachment_badge = '<span class="attachment-badge">📎</span>' if email['attachment_filename'] else ''
        emails_html += f'''
        <li class="email-item {read_class}" onclick="window.location='/email/{email['id']}'">
            <div class="email-subject">
                {email['subject']}
                {attachment_badge}
            </div>
            <div class="email-meta">
                <span>От: {email['sender']}</span>
                <span>{email['sent_at']}</span>
            </div>
            <div style="margin-top: 10px; color: #666; font-size: 14px;">
                {email['body'][:100]}{'...' if len(email['body']) > 100 else ''}
            </div>
        </li>
        '''
    
    if not emails_html:
        emails_html = '''
        <div style="text-align: center; padding: 50px;">
            <h3>Входящие пусты</h3>
            <p>У вас нет новых сообщений</p>
            <a href="/compose" class="btn">Написать первое письмо</a>
        </div>
        '''
    else:
        emails_html = f'<ul class="email-list">{emails_html}</ul>'
    
    return render_page(f'''
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 30px;">
        <h1>Входящие</h1>
        <a href="/compose" class="btn">Написать</a>
    </div>
    
    {emails_html}
    ''', title="Входящие - ERTADEIL Mail")

@app.route('/sent')
def sent():
    if 'user_id' not in session:
        return redirect('/login')
    
    conn = get_db_connection()
    emails = conn.execute('''
        SELECT * FROM emails 
        WHERE sender = ? 
        ORDER BY sent_at DESC
    ''', (session['email'],)).fetchall()
    conn.close()
    
    emails_html = ''
    for email in emails:
        attachment_badge = '<span class="attachment-badge">📎</span>' if email['attachment_filename'] else ''
        emails_html += f'''
        <li class="email-item" onclick="window.location='/email/{email['id']}'">
            <div class="email-subject">
                {email['subject']}
                {attachment_badge}
            </div>
            <div class="email-meta">
                <span>Кому: {email['recipient']}</span>
                <span>{email['sent_at']}</span>
            </div>
            <div style="margin-top: 10px; color: #666; font-size: 14px;">
                {email['body'][:100]}{'...' if len(email['body']) > 100 else ''}
            </div>
        </li>
        '''
    
    if not emails_html:
        emails_html = '''
        <div style="text-align: center; padding: 50px;">
            <h3>Отправленные пусты</h3>
            <p>Вы еще не отправляли сообщений</p>
            <a href="/compose" class="btn">Написать первое письмо</a>
        </div>
        '''
    else:
        emails_html = f'<ul class="email-list">{emails_html}</ul>'
    
    return render_page(f'''
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 30px;">
        <h1>Отправленные</h1>
        <a href="/compose" class="btn">Написать</a>
    </div>
    
    {emails_html}
    ''', title="Отправленные - ERTADEIL Mail")

@app.route('/email/<int:email_id>')
def view_email(email_id):
    if 'user_id' not in session:
        return redirect('/login')
    
    conn = get_db_connection()
    email = conn.execute('SELECT * FROM emails WHERE id = ?', (email_id,)).fetchone()
    
    if not email:
        flash('Письмо не найдено', 'error')
        conn.close()
        return redirect('/inbox')
    
    if email['recipient'] == session['email'] and not email['read']:
        conn.execute('UPDATE emails SET read = 1 WHERE id = ?', (email_id,))
        conn.commit()
    
    conn.close()
    
    attachment_html = ''
    if email['attachment_filename']:
        # Определяем иконку в зависимости от типа файла
        file_ext = email['attachment_filename'].split('.')[-1].lower()
        file_icons = {
            'txt': '📄', 'pdf': '📕', 'doc': '📘', 'docx': '📘',
            'xls': '📊', 'xlsx': '📊', 'ppt': '📊', 'pptx': '📊',
            'zip': '📦', 'rar': '📦', '7z': '📦',
            'png': '🖼️', 'jpg': '🖼️', 'jpeg': '🖼️', 'gif': '🖼️',
            'mp3': '🎵', 'wav': '🎵', 'mp4': '🎬', 'avi': '🎬',
            'py': '🐍', 'js': '📜', 'html': '🌐', 'css': '🎨'
        }
        icon = file_icons.get(file_ext, '📎')
        
        attachment_html = f'''
        <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee;">
            <strong>Вложение:</strong><br>
            <a href="/download/{email['id']}" class="btn" style="margin-top: 10px;">
                {icon} Скачать {email['attachment_filename']}
            </a>
        </div>
        '''
    
    return render_page(f'''
    <div style="margin-bottom: 30px;">
        <a href="/inbox" class="btn btn-secondary">← Назад</a>
    </div>
    
    <div style="background: #f8f9fa; padding: 30px; border-radius: 10px;">
        <h1>{email['subject']}</h1>
        
        <div style="margin: 20px 0; padding: 20px; background: white; border-radius: 5px;">
            <div style="display: flex; justify-content: space-between; margin-bottom: 20px;">
                <div>
                    <strong>От:</strong> {email['sender']}<br>
                    <strong>Кому:</strong> {email['recipient']}
                </div>
                <div style="color: #666;">
                    {email['sent_at']}
                </div>
            </div>
            
            <div style="border-top: 1px solid #eee; padding-top: 20px; white-space: pre-line;">
                {email['body']}
            </div>
            
            {attachment_html}
        </div>
        
        <div style="margin-top: 30px;">
            <a href="/compose?reply_to={email['sender']}" class="btn">Ответить</a>
        </div>
    </div>
    ''', title="Письмо - ERTADEIL Mail")

@app.route('/download/<int:email_id>')
def download_attachment(email_id):
    if 'user_id' not in session:
        return redirect('/login')
    
    conn = get_db_connection()
    email = conn.execute('SELECT * FROM emails WHERE id = ?', (email_id,)).fetchone()
    conn.close()
    
    if not email or not email['attachment_path'] or not os.path.exists(email['attachment_path']):
        flash('Файл не найден', 'error')
        return redirect(f'/email/{email_id}')
    
    return send_file(email['attachment_path'], 
                    as_attachment=True, 
                    download_name=email['attachment_filename'])

@app.route('/logout')
def logout():
    session.clear()
    flash('Вы вышли из системы', 'success')
    return redirect('/login')

# API Routes
@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json()
    if not data or not data.get('email') or not data.get('password'):
        return jsonify({'success': False, 'message': 'Требуется email и пароль'}), 400
    
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE email = ?', (data['email'],)).fetchone()
    
    if not user or not check_password_hash(user['password_hash'], data['password']):
        conn.close()
        return jsonify({'success': False, 'message': 'Неверные учетные данные'}), 401
    
    # Создаем JWT токен
    token = jwt.encode({
        'user_id': user['id'],
        'email': user['email'],
        'exp': datetime.utcnow().timestamp() + 3600  # Токен на 1 час
    }, app.config['JWT_SECRET_KEY'])
    
    conn.close()
    return jsonify({
        'success': True,
        'token': token,
        'user': {
            'id': user['id'],
            'username': user['username'],
            'email': user['email']
        }
    })

@app.route('/api/user')
@token_required
def api_user(user):
    return jsonify({
        'success': True,
        'user': {
            'id': user['id'],
            'username': user['username'],
            'email': user['email'],
            'created_at': user['created_at']
        }
    })

@app.route('/api/send', methods=['POST'])
@token_required
def api_send_email(user):
    data = request.get_json()
    if not data or not data.get('recipient') or not data.get('subject') or not data.get('body'):
        return jsonify({'success': False, 'message': 'Требуется recipient, subject и body'}), 400
    
    recipient = data['recipient']
    subject = data['subject']
    body = data['body']
    
    if not recipient.endswith('@ertadeil'):
        return jsonify({'success': False, 'message': 'Можно отправлять только на адреса @ertadeil'}), 400
    
    conn = get_db_connection()
    
    # Проверяем существование получателя
    recipient_user = conn.execute('SELECT * FROM users WHERE email = ?', (recipient,)).fetchone()
    if not recipient_user:
        conn.close()
        return jsonify({'success': False, 'message': 'Получатель не найден'}), 404
    
    # Отправляем письмо
    sender_email = user['email']
    conn.execute('''
        INSERT INTO emails (sender, recipient, subject, body)
        VALUES (?, ?, ?, ?)
    ''', (sender_email, recipient, subject, body))
    
    email_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
    conn.commit()
    conn.close()
    
    return jsonify({
        'success': True,
        'message': 'Письмо отправлено',
        'email_id': email_id
    })

@app.route('/api/inbox')
@token_required
def api_inbox(user):
    conn = get_db_connection()
    
    # Параметры запроса
    limit = request.args.get('limit', default=50, type=int)
    unread_only = request.args.get('unread', default='false').lower() == 'true'
    
    query = 'SELECT * FROM emails WHERE recipient = ?'
    params = [user['email']]
    
    if unread_only:
        query += ' AND read = 0'
    
    query += ' ORDER BY sent_at DESC LIMIT ?'
    params.append(limit)
    
    emails = conn.execute(query, params).fetchall()
    conn.close()
    
    emails_list = []
    for email in emails:
        emails_list.append({
            'id': email['id'],
            'sender': email['sender'],
            'subject': email['subject'],
            'body_preview': email['body'][:100] + ('...' if len(email['body']) > 100 else ''),
            'has_attachment': bool(email['attachment_filename']),
            'sent_at': email['sent_at'],
            'read': bool(email['read'])
        })
    
    return jsonify({
        'success': True,
        'count': len(emails_list),
        'emails': emails_list
    })

@app.route('/api/sent')
@token_required
def api_sent(user):
    conn = get_db_connection()
    
    limit = request.args.get('limit', default=50, type=int)
    
    emails = conn.execute('''
        SELECT * FROM emails 
        WHERE sender = ? 
        ORDER BY sent_at DESC 
        LIMIT ?
    ''', (user['email'], limit)).fetchall()
    conn.close()
    
    emails_list = []
    for email in emails:
        emails_list.append({
            'id': email['id'],
            'recipient': email['recipient'],
            'subject': email['subject'],
            'body_preview': email['body'][:100] + ('...' if len(email['body']) > 100 else ''),
            'has_attachment': bool(email['attachment_filename']),
            'sent_at': email['sent_at']
        })
    
    return jsonify({
        'success': True,
        'count': len(emails_list),
        'emails': emails_list
    })

@app.route('/api/email/<int:email_id>')
@token_required
def api_get_email(user, email_id):
    conn = get_db_connection()
    email = conn.execute('SELECT * FROM emails WHERE id = ?', (email_id,)).fetchone()
    
    if not email:
        conn.close()
        return jsonify({'success': False, 'message': 'Письмо не найдено'}), 404
    
    # Проверяем права доступа
    if email['recipient'] != user['email'] and email['sender'] != user['email']:
        conn.close()
        return jsonify({'success': False, 'message': 'Доступ запрещен'}), 403
    
    # Помечаем как прочитанное если получатель
    if email['recipient'] == user['email'] and not email['read']:
        conn.execute('UPDATE emails SET read = 1 WHERE id = ?', (email_id,))
        conn.commit()
    
    email_data = {
        'id': email['id'],
        'sender': email['sender'],
        'recipient': email['recipient'],
        'subject': email['subject'],
        'body': email['body'],
        'attachment_filename': email['attachment_filename'],
        'sent_at': email['sent_at'],
        'read': bool(email['read'])
    }
    
    conn.close()
    return jsonify({'success': True, 'email': email_data})

@app.route('/api/email/<int:email_id>/read', methods=['POST'])
@token_required
def api_mark_as_read(user, email_id):
    conn = get_db_connection()
    email = conn.execute('SELECT * FROM emails WHERE id = ?', (email_id,)).fetchone()
    
    if not email:
        conn.close()
        return jsonify({'success': False, 'message': 'Письмо не найдено'}), 404
    
    if email['recipient'] != user['email']:
        conn.close()
        return jsonify({'success': False, 'message': 'Только получатель может отмечать письмо как прочитанное'}), 403
    
    conn.execute('UPDATE emails SET read = 1 WHERE id = ?', (email_id,))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'message': 'Письмо отмечено как прочитанное'})

@app.route('/api/stats')
@token_required
def api_stats(user):
    conn = get_db_connection()
    
    inbox_count = conn.execute('SELECT COUNT(*) FROM emails WHERE recipient = ?', 
                              (user['email'],)).fetchone()[0]
    sent_count = conn.execute('SELECT COUNT(*) FROM emails WHERE sender = ?', 
                             (user['email'],)).fetchone()[0]
    unread_count = conn.execute('SELECT COUNT(*) FROM emails WHERE recipient = ? AND read = 0', 
                               (user['email'],)).fetchone()[0]
    
    conn.close()
    
    return jsonify({
        'success': True,
        'stats': {
            'inbox': inbox_count,
            'sent': sent_count,
            'unread': unread_count
        }
    })

# Вспомогательная функция для получения flash сообщений
def get_flashed_messages(with_categories=False):
    return []


if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

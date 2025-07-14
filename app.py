from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
import sqlite3
import os
import subprocess
import math
from datetime import datetime

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload

import io

# CONFIG
SCOPES = ['https://www.googleapis.com/auth/drive']
CREDENTIALS_PATH = 'user_config/credentials.json'
TOKEN_PATH = 'user_config/token.json'
DRIVE_GPG_FILE_NAME = 'expenses.db.gpg'
DRIVE_GPG_FILE_ID = '134bxZC1ktPRu5hoF-0tqZX5eItizu4Kl'
LOCAL_GPG_PATH = 'encrypted.db.gpg'
LOCAL_DB_PATH = 'data.db'
LOCAL_BACKUP_DIR = 'local_backups/'

app = Flask(__name__)
app.secret_key = 'super-secret-key'  # use a proper key in production

# GPG decryption using subprocess
def decrypt_gpg_file(input_path, output_path, passphrase):
    try:
        result = subprocess.run(
            ['gpg', '--batch', '--yes',
             '--passphrase', passphrase,
             '--pinentry-mode', 'loopback',
             '-o', output_path, '-d', input_path],
            capture_output=True, check=True, text=True
        )
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        return False, e.stderr

# Google Drive: Get authenticated service
def get_drive_service():
    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    else:
        flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
        creds = flow.run_local_server(port=8080)
        with open(TOKEN_PATH, 'w') as token:
            token.write(creds.to_json())
    return build('drive', 'v3', credentials=creds)

# Download the encrypted file from Google Drive
def download_encrypted_db():
    service = get_drive_service()
    # results = service.files().list(q=f"name='{ENCRYPTED_DRIVE_FILE_NAME}'",
    #                                spaces='drive',
    #                                fields="files(id, name)").execute()
    # items = results.get('files', [])
    # if not items:
    #     raise Exception("Encrypted DB file not found in Google Drive")

    # file_id = items[0]['id']
    file_id = DRIVE_GPG_FILE_ID
    request = service.files().get_media(fileId=file_id)
    fh = io.FileIO(LOCAL_GPG_PATH, 'wb')
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()

# Upload the encrypted DB back to Drive
def upload_encrypted_db(passphrase):
    # Encrypt the DB
    encrypted_path = LOCAL_GPG_PATH
    try:
        subprocess.run(
            ['gpg', '--batch', '--yes',
             '--passphrase', passphrase,
             '--pinentry-mode', 'loopback',
             '-o', encrypted_path, '-c', LOCAL_DB_PATH],
            check=True
        )
    except subprocess.CalledProcessError:
        raise Exception("Failed to encrypt file")

    # Upload
    service = get_drive_service()
    # results = service.files().list(q=f"name='{ENCRYPTED_DRIVE_FILE_NAME}'",
    #                                spaces='drive',
    #                                fields="files(id, name)").execute()
    # file_id = results['files'][0]['id']
    file_id = DRIVE_GPG_FILE_ID
    media = MediaFileUpload(encrypted_path, resumable=True)
    service.files().update(fileId=file_id, media_body=media).execute()

# DB INIT
def init_db():
    conn = sqlite3.connect(LOCAL_DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            amount REAL NOT NULL,
            description TEXT NOT NULL,
            category TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

# Routes
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form['password']
        try:
            download_encrypted_db()
            success, msg = decrypt_gpg_file(LOCAL_GPG_PATH, LOCAL_DB_PATH, password)
            if not success:
                raise Exception(msg)
            session['authenticated'] = True
            session['passphrase'] = password
            return redirect('/home')
        except Exception as e:
            return f"<h2>Error: {str(e)}</h2><a href='/'>Try again</a>"
    return render_template('index.html')
    # return '''
    #     <form method="post">
    #         <h2>Enter password to decrypt DB</h2>
    #         <input type="password" name="password" required>
    #         <input type="submit" value="Login">
    #     </form>
    # '''


@app.route('/save')
def save():
    if not session.get('authenticated'):
        return redirect('/')
    
    password = session.get('passphrase')
    if password:
        try:
            upload_encrypted_db(password)
        except Exception as e:
            
            return f"<h3>Upload failed: {e}</h3><a href='/home'>Back</a>", 500
    return redirect('/home')

@app.route('/local_copy')
def local_copy():
    if not session.get('authenticated'):
        return redirect('/')

    password = session.get('passphrase')
    if not password:
        return "<h3>Missing passphrase</h3>", 400

    if not os.path.exists(LOCAL_DB_PATH):
        return "<h3>No decrypted DB available</h3>", 404

    backup_path = LOCAL_BACKUP_DIR + "expenses_" + datetime.now().strftime("%Y%m%d:%H%M%S.db.gpg")
    # Encrypt the DB file using subprocess
    try:
        subprocess.run([
            'gpg', '--batch', '--yes',
            '--passphrase', password,
            '--pinentry-mode', 'loopback',
            '-c', '-o', backup_path, LOCAL_DB_PATH
        ], check=True)
    except subprocess.CalledProcessError as e:
        return f"<h3>Encryption failed: {e}</h3>", 500

    # return send_file(
    #     LOCAL_BACKUP_PATH,
    #     as_attachment=True,
    #     download_name='data.db.gpg',
    #     mimetype='application/octet-stream'
    # )
    return redirect('/home')
    
@app.route('/logout')
def logout():
    save()

    session.clear()
    if os.path.exists(LOCAL_DB_PATH):
        os.remove(LOCAL_DB_PATH)
    if os.path.exists(LOCAL_GPG_PATH):
        os.remove(LOCAL_GPG_PATH)
    return redirect('/')

@app.route('/home')
def home():
    if not session.get('authenticated'):
        return redirect('/')
    return render_template('home.html')

@app.route('/submit', methods=['POST'])
def submit():
    if not session.get('authenticated'):
        return redirect('/')
    date        = request.form['date']
    amount      = request.form['amount']
    description = request.form['description']
    category    = request.form['category']

    try:
        amount = float(amount)
        if math.isnan(amount) or math.isinf(amount):
            raise ValueError
    except ValueError:
        return 'Error: Invalid price', 400

    conn = sqlite3.connect(LOCAL_DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO entries (date, amount, description, category) VALUES (?, ?, ?, ?)",
              (date, amount, description, category))
    conn.commit()
    conn.close()
    return 'OK'

@app.route('/entries')
def entries():
    if not session.get('authenticated'):
        return redirect('/')
    conn = sqlite3.connect(LOCAL_DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, date, amount, description, category FROM entries")
    data = c.fetchall()
    conn.close()
    return jsonify(data)

@app.route('/update/<int:entry_id>', methods=['POST'])
def update_entry(entry_id):
    if not session.get('authenticated'):
        return redirect('/')
    if not request.is_json:
        return "Invalid format", 400
    data = request.get_json()
    date = data.get("date")
    amount = data.get("amount")
    description = data.get("description")
    category = data.get("category")

    try:
        amount = float(amount)
        if math.isnan(amount) or math.isinf(amount):
            raise ValueError
    except ValueError:
        return "Invalid amount", 400

    conn = sqlite3.connect(LOCAL_DB_PATH)
    c = conn.cursor()
    c.execute("""
        UPDATE entries
        SET date = ?, amount = ?, description = ?, category = ?
        WHERE id = ?
    """, (date, amount, description, category, entry_id))
    conn.commit()
    conn.close()

    return "OK"

@app.route('/delete/<int:entry_id>', methods=['DELETE'])
def delete_entry(entry_id):
    if not session.get('authenticated'):
        return redirect('/')
    conn = sqlite3.connect(LOCAL_DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
    conn.commit()
    conn.close()
    return 'OK'

@app.route('/hist_data')
def data():
    if not session.get('authenticated'):
        return redirect('/')
    conn = sqlite3.connect(LOCAL_DB_PATH)
    c = conn.cursor()
    c.execute("SELECT date, amount, category FROM entries")
    rows = c.fetchall()
    conn.close()
    return jsonify([{"date": row[0], "amount": row[1], "category": row[2]} for row in rows])

if __name__ == '__main__':
    app.run(debug=True)

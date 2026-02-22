#!/usr/bin/env python3

# TODO: account support
# check https://www.rustcodeweb.com/2025/05/flask-session-security.html for security (password/session management)

import os
import sys
from io import FileIO
from subprocess import run, CalledProcessError
import math
from datetime import datetime
import logging

# web server
import flask

# database
from sqlite3 import connect
import csv

# secrets
# import secrets
from Crypto.Cipher import AES
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Hash import SHA256  # <--- this is needed
from Crypto.Random import get_random_bytes

# google API
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload


## FORMAT ## ---

# the file content is stored as csv, with the given fields
# date;amount;note;category;account

## CONFIG ## ---
SCOPES = ['https://www.googleapis.com/auth/drive']
CREDENTIALS_PATH = 'user_config/credentials.json'
TOKEN_PATH = 'user_config/token.json'

DRIVE_GPG_FILE_NAME = 'expenses.db.gpg'
DRIVE_GPG_FILE_ID = '134bxZC1ktPRu5hoF-0tqZX5eItizu4Kl'
DRIVE_FOLDER_ID = '185J3mWCeHYuU9s6Iev9_aJrzuMmlrWva'

LOCAL_ENC_FILE = 'db.csv.enc'
LOCAL_CSV_FILE = ".local_db.csv"
LOCAL_SQL_FILE = '.local_db.sql'
LOCAL_BACKUP_DIR = 'local_backups/'

SQL_TABLE_NAME = "Expenses"

app = flask.Flask(__name__)
app.secret_key = 'super-secret-key'  # secrets.token_hex(32)

if not os.path.exists(LOCAL_SQL_FILE):
    # create a new file for the database
    f = open(LOCAL_SQL_FILE, "x")
    f.close()
else:
    f = open(LOCAL_SQL_FILE, "w+")
    f.close()

app.config["DATABASE"] = LOCAL_SQL_FILE # custom setting, filepath for local sql database
app.config["SOURCE_FILE"] = None        # custom setting, (string:<filepath>, bool:<encrypted>, bool:<from remote>)
app.config["LOCAL_BACKUP_DIR"] = LOCAL_BACKUP_DIR

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

# encrypting/decrypting file ---

# GPG decryption using subprocess
def decrypt_gpg_file(input_path, output_path, passphrase):
    try:
        result = run(
            ['gpg', '--batch', '--yes',
             '--passphrase', passphrase,
             '--pinentry-mode', 'loopback',
             '-o', output_path, '-d', input_path],
            capture_output=True, check=True, text=True
        )
        return True, result.stdout
    except CalledProcessError as e:
        return False, e.stderr

# GPG encryption
def encrypt_gpg_file(in_file, out_file, password):
    try:
        run(
            ['gpg', '--batch', '--yes',
             '--passphrase', password,
             '--pinentry-mode', 'loopback',
             '-o', out_file, '-c', in_file],
            check=True
        )
    except CalledProcessError:
        raise Exception("Failed to encrypt file")

# encode a file
def encrypt_AES256(in_file, enc_file, password):
    # Read plaintext
    with open(in_file, "rb") as f:
        plaintext = f.read()

    # Generate salt and IV (16 bytes each)
    salt = get_random_bytes(16)
    iv = get_random_bytes(16)

    # Derive key using PBKDF2 (must match decoder exactly)
    key = PBKDF2(
        password,
        salt,
        dkLen=32,
        count=65536,
        hmac_hash_module=SHA256
    )

    # PKCS#7 padding
    pad_len = AES.block_size - (len(plaintext) % AES.block_size)
    padding = bytes([pad_len]) * pad_len
    padded_plaintext = plaintext + padding

    # Encrypt
    cipher = AES.new(key, AES.MODE_CBC, iv)
    ciphertext = cipher.encrypt(padded_plaintext)

    # Write output: salt + iv + ciphertext
    with open(enc_file, "wb") as f:
        f.write(salt)
        f.write(iv)
        f.write(ciphertext)

# decrypt a file encoded with the java algorithm used in the android app
def decrypt_AES256(enc_file, out_file, password):
    with open(enc_file, "rb") as f:
        salt = f.read(16)
        iv = f.read(16)
        ciphertext = f.read()

    # PBKDF2 with SHA256 (matches Java)
    key = PBKDF2(password, salt, dkLen=32, count=65536, hmac_hash_module=SHA256)

    cipher = AES.new(key, AES.MODE_CBC, iv)
    plaintext = cipher.decrypt(ciphertext)

    # Remove PKCS#7 padding
    pad_len = plaintext[-1]
    plaintext = plaintext[:-pad_len]

    with open(out_file, "wb") as f:
        f.write(plaintext)

# Interacting with Google Drive ---

# Google Drive: Get authenticated service
# def get_drive_service(token_file, credentials_file, scopes, port):
#     creds = None
#     # token file not exists, or is older than 1 hour
#     if not(os.path.exists(token_file)) or ( (time.time() - os.path.getmtime(token_file)) > 3600 ):
#         flow = InstalledAppFlow.from_client_secrets_file(credentials_file, scopes)
#         creds = flow.run_local_server(port=port)
#         with open(token_file, 'w+') as token:
#             token.write(creds.to_json())
#     else:
#         creds = Credentials.from_authorized_user_file(token_file, scopes)
#     return build('drive', 'v3', credentials=creds)

def get_drive_service(token_file, credentials_file, scopes, port):
    creds = None
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, scopes)
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(
            credentials_file,
            scopes
        )
        creds = flow.run_local_server(
            port=port,
            access_type="offline",
            prompt="consent"
        )
        with open(token_file, "w") as token:
            token.write(creds.to_json())
    return build("drive", "v3", credentials=creds)

# Download file from Google Drive
def download_drive_file(service, in_file_id, out_file):
    request = service.files().get_media(fileId=in_file_id)
    fh = FileIO(out_file, 'wb')
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()

# Retrieve the most recent file in the given folder
def get_most_recent_file_in_folder(service, folder_id):
    results = (
        service.files()
        .list(
            q=f"'{folder_id}' in parents and trashed = false",
            orderBy="modifiedTime desc",
            pageSize=1,
            fields="files(id, name, modifiedTime)"
        )
        .execute()
    )

    files = results.get("files", [])
    if not files:
        return None

    return files[0]

# Upload the encrypted DB back to Drive, replace the most recent file
# def upload_encrypted_db(passphrase):
#     encrypted_path = LOCAL_GPG_PATH
#     encrypt_gpg_file(LOCAL_DB_PATH, encrypted_path, passphrase)
#     service = get_drive_service()
#     # results = service.files().list(q=f"name='{ENCRYPTED_DRIVE_FILE_NAME}'",
#     #                                spaces='drive',
#     #                                fields="files(id, name)").execute()
#     # file_id = results['files'][0]['id']
#     file_id = get_most_recent_file_in_folder(service, DRIVE_FOLDER_ID)["id"]
#     media = MediaFileUpload(encrypted_path, resumable=True)
#     service.files().update(fileId=file_id, media_body=media).execute()

# Upload <in_file> to <out_file_id>
def upload_drive_file(service, in_file, out_file_id):
    media = MediaFileUpload(in_file, resumable=True)
    service.files().update(fileId=out_file_id, media_body=media).execute()

## Database management ## ---

def get_db(app):
    if 'db' not in flask.g:
        flask.g.db = connect(
            app.config["DATABASE"],
            # detect_types=sqlite3.PARSE_DECLTYPES
        )
        # flask.g.db.row_factory = sqlite3.Row
    return flask.g.db

# init a new sql database
# <columns> is the string of columns names
def init_db(app, columns):
    db = get_db(app)
    columns = "id INTEGER PRIMARY KEY AUTOINCREMENT," + columns
    db.cursor().execute("CREATE TABLE IF NOT EXISTS {0} ({1})".format(SQL_TABLE_NAME, columns))
    db.commit()
    return db

# close the database and remove the corresponding local file if clean is True
def close_db(app, clean=True, e=None):
    db = flask.g.pop('db', None)
    if db is None:
        db = get_db(app)

    if db is not None:
        db.close()
        if clean:
            os.remove(app.config["DATABASE"])
            logging.info("Removed local SQL file")
    else:
        logging.warning("Failed to retrieved Flask database")

# create a sql database from a csv file
# returns the number of entries
def csv_to_sql(in_file, delim=';'):
    with open (in_file, 'r') as f:
        reader = csv.reader(f, delimiter=delim)
        # get columns names
        columns = next(reader)
        columns_header = ','.join(columns)
        # query template
        query = "INSERT INTO {0}({1}) VALUES ({2})"
        query = query.format(SQL_TABLE_NAME, columns_header, ','.join('?' * len(columns)))
        # create table
        db = init_db(app, columns_header)
        cursor = db.cursor()

        # feed data
        for data in reader:
            cursor.execute(query, data)
        db.commit()

# sql to csv, overwrite existing files
def sql_to_csv(out_file, delim=';'):
    db = get_db(app)
    cursor = db.cursor()
    # get column names
    cursor.execute(f"SELECT * FROM {SQL_TABLE_NAME} LIMIT 0")
    columns = [note[0] for note in cursor.description[1:]]
    # get data rows
    cursor.execute(f"SELECT * FROM {SQL_TABLE_NAME}")
    rows = cursor.fetchall()
    # overwrite file if it exists already
    with open(out_file, 'w+') as f:
        writer = csv.writer(f, delimiter=delim)
        # write column header
        writer.writerow(columns)
        # feed data
        for data in rows:
            writer.writerow(data[1:])

## Routes ## ---

@app.route('/', methods=['GET', 'POST'])
def login():
    # Simple page rendering
    if flask.request.method == "GET":
        logging.info("website root asked")
        # Decrypted file
        if not app.config["SOURCE_FILE"][1]:
            # we consider the session authenticated when no password is required
            flask.session['authenticated'] = True
            csv_to_sql(app.config["SOURCE_FILE"][0])
            logging.info("csv file converted to sql, redirecting towards /home")
            return flask.redirect("/home")
        else:
            logging.info("encrypted source file, redirecting towards login page ")
            return flask.render_template('login.html')

    # POST request, here password form submitted
    if flask.request.method == "POST":
        # get password
        password = flask.request.form['password']
        # flask.flash("test", "error")
        try:
            decrypt_AES256(app.config["SOURCE_FILE"][0], app.config["LOCAL_CSV_FILE"], password)
            # init and feed sql database from csv file
            csv_to_sql(app.config["LOCAL_CSV_FILE"])
        except UnicodeDecodeError as e:
            logging.info("Wrong password")
            flask.flash("Wrong password")
            return flask.redirect('/')
        except Exception as e:
            logging.error("Error: %s", e)
            return f"<h2>Error: {str(e)}</h2><a href='/'>Try again</a>"

        # if decryption succeded, we consider the user authenticated
        flask.session['authenticated'] = True
        # we store the password
        flask.session['passphrase'] = password


        return flask.redirect('/home')

    # Should never happen if Flask does its job
    else:
        return "Method Not Allowed", 405

@app.route("/get_options/<string:column_name>")
def get_categories(column_name):
    """
    Return all distinct entries from the database column <column_name>.
    Should be used to access all categories/accounts.
    """
    db = get_db(app)
    cursor = db.cursor()
    # get column names
    cursor.execute(f"SELECT DISTINCT {column_name} FROM {SQL_TABLE_NAME}")
    categories = cursor.fetchall()
    return flask.jsonify(categories)

@app.route('/save')
def save():
    if not flask.session.get('authenticated'):
        logging.error("not authenticated")
        return flask.redirect('/')

    # source file not encrypted, simply save it
    if not app.config["SOURCE_FILE"][1]:
        # update csv source file
        sql_to_csv(app.config["SOURCE_FILE"][0])
        logging.info("File saved")

    # source file encrypted
    else:
        password = flask.session.get('passphrase')
        if not password:
            flask.flash("No password stored, aborting save.")
            return flask.redirect("/home")
        else:
            try:
                # update csv file
                sql_to_csv(app.config["LOCAL_CSV_FILE"])
                # update encrypted file
                encrypt_AES256(app.config["LOCAL_CSV_FILE"],
                               app.config["SOURCE_FILE"][0],
                               password)

                # remote source file
                if app.config["SOURCE_FILE"][2]:
                    # replace the most recent file in the drive folder
                    service = get_drive_service(TOKEN_PATH, CREDENTIALS_PATH, SCOPES, 8080)
                    file_id = get_most_recent_file_in_folder(service, DRIVE_FOLDER_ID)["id"]
                    upload_drive_file(service, app.config["SOURCE_FILE"][0], file_id)

            except Exception as e:
                logging.info("Save error: %s", e)
                flask.flash("Sauvegarde interrompue: %s", e)
                return f"<h3>Upload failed: {e}</h3><a href='/home'>Back</a>", 500

    flask.flash("Modifications sauvegardées.")
    return flask.redirect('/home')


@app.route('/local_copy')
def local_copy():
    if not flask.session.get('authenticated'):
        logging.error("not authenticated")
        return flask.redirect('/')

    if not app.config["SOURCE_FILE"][2]:
        flask.flash("Editing local file, no need for copy.", "warning")
        return flask.redirect('/home')

    password = flask.session.get('passphrase')
    if not password:
        flask.flash("No password stored, aborting local save.", "error")
        return flask.redirect("/home")

    if not os.path.exists(app.config["DATABASE"]):
        flask.flash("No decrypted database available, aborting local save.", "error")
        return flask.redirect("/home")

    backup_file = app.config["LOCAL_BACKUP_DIR"] + "expenses_" + datetime.now().strftime("%Y%m%d_%H%M%S.csv.enc")
    try:
        # update csv file
        sql_to_csv(app.config["LOCAL_CSV_FILE"])
        # Encrypt the csv file
        encrypt_AES256(app.config["LOCAL_CSV_FILE"], backup_file, password)
    except CalledProcessError as e:
        return f"<h3>Local save failed: {e}</h3>", 500

    flask.flash(f"Local save available at :\n{backup_file}")
    return flask.redirect('/home')

@app.route('/logout/<int:do_save>')
def logout(do_save):
    "Logout from current session, erase all temporary files. If <do_save> is 1, save modifications."
    if do_save == 1:
        save()

    # the source file was encrypted, remove decrypted file
    if app.config["SOURCE_FILE"][1]:
        os.remove(app.config["LOCAL_CSV_FILE"])
    # the source file was downloaded from remote, remove local copy
    if app.config["SOURCE_FILE"][2]:
        os.remove(app.config["SOURCE_FILE"][0])
    # close sql database and remove local sql database
    close_db(app, clean=True)
    # clear flask session
    flask.session.clear()

    return flask.redirect('/')

@app.route('/home')
def home():
    if not flask.session.get('authenticated'):
        logging.error("not authenticated")
        return flask.redirect('/')
    return flask.render_template('home.html')

@app.route('/submit', methods=['POST'])
def submit():
    if not flask.session.get('authenticated'):
        return flask.redirect('/')
    date     = flask.request.form['date']
    amount   = flask.request.form['amount']
    note     = flask.request.form['note']
    category = flask.request.form['category']
    account  = flask.request.form['account']

    # amount checking
    try:
        amount = float(amount)
        if math.isnan(amount) or math.isinf(amount):
            raise ValueError
    except ValueError:
        flask.flash("Error: Invalid price")
        return flask.redirect("/home")
        # return 'Error: Invalid price', 400

    db = get_db(app)
    db.cursor().execute(f"INSERT INTO {SQL_TABLE_NAME} (date, amount, note, category, account) VALUES (?, ?, ?, ?, ?)",
                        (date, amount, note, category, account))
    db.commit()
    return 'OK'

@app.route('/entries')
def entries():
    if not flask.session.get('authenticated'):
        return flask.redirect('/')
    db = get_db(app)
    c = db.cursor()
    c.execute(f"SELECT id, date, amount, note, category, account FROM {SQL_TABLE_NAME}")
    data = c.fetchall()
    return flask.jsonify(data)

@app.route('/update/<int:entry_id>', methods=['POST'])
def update_entry(entry_id):
    if not flask.session.get('authenticated'):
        return flask.redirect('/')
    if not flask.request.is_json:
        return "Invalid format", 400
    data = flask.request.get_json()
    date = data.get("date")
    amount = data.get("amount")
    note = data.get("note")
    category = data.get("category")
    account = data.get("account")

    # amount checking and conversion
    try:
        amount = float(amount)
        if math.isnan(amount) or math.isinf(amount):
            raise ValueError
    except ValueError:
        return "Invalid amount", 400

    db = get_db(app)
    db.cursor().execute("""
        UPDATE {0}
        SET date = ?, amount = ?, note = ?, category = ?, account = ?
        WHERE id = ?
    """.format(SQL_TABLE_NAME), (date, amount, note, category, account, entry_id))
    db.commit()

    return "OK"

@app.route('/delete/<int:entry_id>', methods=['DELETE'])
def delete_entry(entry_id):
    if not flask.session.get('authenticated'):
        return 'not authenticated', 400
    db = get_db(app)
    request = "DELETE FROM {} WHERE id = {}".format(SQL_TABLE_NAME, entry_id)
    db.cursor().execute(request)
    db.commit()
    return 'OK'

@app.route('/hist_data')
def data():
    if not flask.session.get('authenticated'):
        return flask.redirect('/')
    db = get_db(app)
    c = db.cursor()
    c.execute(f"SELECT date, amount, category FROM {SQL_TABLE_NAME}")
    rows = c.fetchall()
    return flask.jsonify([{"date": row[0], "amount": row[1], "category": row[2]} for row in rows])

# App interface ---

# Display usage for app
def print_usage():
    print(f"Usage: python {sys.argv[0]} <filepath>\n" \
           "\t<filepath>: Optional, path towards a csv file.\n" \
           "\t\t The file extension must be `csv` or `csv.enc`.")

if __name__ == '__main__':
    nb_args = len(sys.argv)

     # local file as database source
    if nb_args == 2:
        src_file = sys.argv[1]
        logging.info("source file: %s", src_file)
        file_split = os.path.splitext(src_file)
        # normal csv file
        if file_split[1] == ".csv":
            app.config["SOURCE_FILE"] = (src_file, False, False)
        # possibly encrypted csv file
        elif file_split[1] == ".enc":
            if os.path.splitext(file_split[0])[1] == ".csv":
                app.config["SOURCE_FILE"] = (src_file, True, False)
                app.config["LOCAL_CSV_FILE"] = LOCAL_CSV_FILE
                logging.info("detected as an encrypted csv file")

        # launch main app
        app.run(debug=True)

    # source file to dl from drive, encrypted
    elif nb_args == 1:
        try:
            # connection to drive service
            service = get_drive_service(TOKEN_PATH, CREDENTIALS_PATH, SCOPES, 8080)
            logging.info("connected to drive service")
            # download most recent file (encrypted csv)
            db_file_id = get_most_recent_file_in_folder(service, DRIVE_FOLDER_ID)["id"]
            download_drive_file(service, db_file_id, LOCAL_ENC_FILE)
            logging.info("remote file downloaded to %s", LOCAL_ENC_FILE)
            # update app config
            app.config["SOURCE_FILE"] = (LOCAL_ENC_FILE, True, True)
            app.config["LOCAL_CSV_FILE"] = LOCAL_CSV_FILE
        except Exception as e:
            logging.error("Error: %s", e)
            quit()

        # launch main app
        app.run(debug=True)

    # incorrect number of arguments
    else:
        print_usage()
        quit()

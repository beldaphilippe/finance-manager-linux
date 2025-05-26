from flask import Flask, render_template, request, jsonify
import sqlite3
import math
from datetime import datetime

app = Flask(__name__)

# Create table if it doesn't exist
def init_db():
    conn = sqlite3.connect("data.db")
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

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/submit', methods=['POST'])
def submit():
    # Extract form fields
    date        = request.form['date']
    amount      = request.form['amount']
    description = request.form['description']
    category    = request.form['category']

    # Check if date and amount are valid
    if not date:
        return 'Error: Date is required', 400
    try:
        amount = float(amount)
        if math.isnan(amount) or math.isinf(amount):
            return 'Error: Invalid numeric value', 400
    except ValueError:
        return 'Error: Invalid price', 400
    
    # Store in database
    conn = sqlite3.connect("data.db")
    c = conn.cursor()
    c.execute(
        "INSERT INTO entries (date, amount, description, category) VALUES (?, ?, ?, ?)",
        (date, amount, description, category)
    )
    conn.commit()
    conn.close()

    return 'OK'

@app.route('/delete/<int:entry_id>', methods=['DELETE'])
def delete(entry_id):
    conn = sqlite3.connect("data.db")
    c = conn.cursor()
    c.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
    conn.commit()
    conn.close()
    return 'OK'

@app.route("/update/<int:entry_id>", methods=["POST"])
def update_entry(entry_id):
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

    conn = sqlite3.connect("data.db")
    c = conn.cursor()
    c.execute("""
        UPDATE entries
        SET date = ?, amount = ?, description = ?, category = ?
        WHERE id = ?
    """, (date, amount, description, category, entry_id))
    conn.commit()
    conn.close()

    return "OK"

@app.route("/entries")
def entries():
    conn = sqlite3.connect("data.db")
    c = conn.cursor()
    c.execute("SELECT id, date, amount, description, category FROM entries")
    data = c.fetchall()
    conn.close()
    return jsonify(data)        # Send as JSON

@app.route("/hist_data")
def data():
    conn = sqlite3.connect("data.db")
    c = conn.cursor()
    c.execute("SELECT date, amount, category FROM entries")
    rows = c.fetchall()
    conn.close()

    return jsonify([
        {"date": row[0], "amount": row[1], "category": row[2]}
        for row in rows
    ])

if __name__ == '__main__':
    init_db()
    app.run(debug=True)

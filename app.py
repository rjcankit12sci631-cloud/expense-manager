from flask import Flask, render_template, request, redirect, session
import sqlite3

app = Flask(__name__)

app.secret_key = "wedding-secret-key"

@app.template_filter("inr")
def inr_format(value):

    if value is None:
        return ""

    value = float(value)

    if value.is_integer():
        value = int(value)

    return f"{value:,.0f}"


def init_db():
    conn = sqlite3.connect("wedding.db")
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        cost REAL
    )
    """)

    try:
        cursor.execute(
            "ALTER TABLE items ADD COLUMN notes TEXT"
        )
    except:
        pass

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id INTEGER,
        amount REAL NOT NULL,
        payment_date TEXT,
        note TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS activity_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        action TEXT,
        created_at TEXT
    )
    """)

    conn.commit()
    conn.close()


init_db()

def log_activity(username, action):

    conn = sqlite3.connect("wedding.db")
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO activity_log(
            username,
            action,
            created_at
        )
        VALUES(
            ?,
            ?,
            datetime('now')
        )
        """,
        (username, action)
    )

    conn.commit()
    conn.close()

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        session["username"] = request.form["username"]

        return redirect("/")

    return render_template("login.html")

@app.route("/")
def home():

    if "username" not in session:
        return redirect("/login")

    conn = sqlite3.connect("wedding.db")
    cursor = conn.cursor()

    cursor.execute("""
    SELECT
        i.id,
        i.name,
        i.cost,
        i.notes,
        COALESCE(SUM(p.amount), 0)
    FROM items i
    LEFT JOIN payments p
        ON i.id = p.item_id
    GROUP BY i.id
    """)

    rows = cursor.fetchall()
    conn.close()

    items = []

    for row in rows:

        item_id = row[0]
        name = row[1]
        cost = row[2]
        notes = row[3]
        paid = row[4]

        if cost is None:
            remaining = None
            overpaid = 0
            status = "unknown"

        else:
            remaining = max(cost - paid, 0)
            overpaid = max(paid - cost, 0)

            if overpaid > 0:
                status = "overpaid"
            elif remaining == 0:
                status = "paid"
            else:
                status = "pending"

        items.append({
            "id": item_id,
            "name": name,
            "cost": cost,
            "paid": paid,
            "remaining": remaining,
            "overpaid": overpaid,
            "notes": notes,
            "status": status
        })

    total_cost = 0
    total_paid = 0

    for item in items:
        total_paid += item["paid"]

        if item["cost"] is not None:
            total_cost += item["cost"]
        
    total_remaining = total_cost - total_paid

    conn = sqlite3.connect("wedding.db")
    cursor = conn.cursor()

    cursor.execute("""
    SELECT username, action, created_at
    FROM activity_log
    ORDER BY id DESC
    LIMIT 10
    """)

    activities = cursor.fetchall()

    conn.close()

    return render_template(
        "index.html",
        items=items,
        total_cost=total_cost,
        total_paid=total_paid,
        total_remaining=total_remaining,
        username=session["username"],
        activities=activities
    )


@app.route("/add-item", methods=["POST"])
def add_item():

    if "username" not in session:
        return redirect("/login")

    name = request.form["name"]

    cost_input = request.form["cost"]

    if cost_input.strip() == "":
        cost = None
    else:
        cost = float(cost_input)

    conn = sqlite3.connect("wedding.db")
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO items(name, cost) VALUES (?, ?)",
        (name, cost)
    )

    conn.commit()
    conn.close()

    log_activity(
        session["username"],
        f"Added item '{name}'"
    )

    return redirect("/")


@app.route("/item/<int:item_id>")
def item_details(item_id):

    if "username" not in session:
        return redirect("/login")

    conn = sqlite3.connect("wedding.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id, name, cost, notes FROM items WHERE id = ?",
        (item_id,)
    )

    item = cursor.fetchone()

    if item is None:
        conn.close()
        return "Item not found", 404

    cursor.execute(
        """
        SELECT
            id,
            amount,
            payment_date,
            note
        FROM payments
        WHERE item_id = ?
        ORDER BY id DESC
        """,
        (item_id,)
    )

    payments = cursor.fetchall()

    paid = sum(payment[1] for payment in payments)

    if item[2] is None:
        remaining = None
    else:
        remaining = item[2] - paid

    conn.close()

    return render_template(
        "item_details.html",
        item=item,
        payments=payments,
        paid=paid,
        remaining=remaining
    )


@app.route("/add-payment/<int:item_id>", methods=["POST"])
def add_payment(item_id):

    if "username" not in session:
        return redirect("/login")

    amount = float(request.form["amount"])
    note = request.form["note"]

    conn = sqlite3.connect("wedding.db")
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO payments (
            item_id,
            amount,
            payment_date,
            note
        )
        VALUES (?, ?, date('now'), ?)
        """,
        (item_id, amount, note)
    )

    conn.commit()
    conn.close()

    log_activity(
        session["username"],
        f"Added payment ₹{amount:,.0f}"
    )

    return redirect(f"/item/{item_id}")

@app.route("/update-cost/<int:item_id>", methods=["POST"])
def update_cost(item_id):

    if "username" not in session:
        return redirect("/login")

    cost_input = request.form["cost"]

    if cost_input.strip() == "":
        cost = None
    else:
        cost = float(cost_input)

    conn = sqlite3.connect("wedding.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT name, cost FROM items WHERE id = ?",
        (item_id,)
    )

    item = cursor.fetchone()

    cursor.execute(
        "UPDATE items SET cost = ? WHERE id = ?",
        (cost, item_id)
    )

    conn.commit()
    conn.close()

    log_activity(
        session["username"],
        f"Updated cost for '{item[0]}' from {item[1]} to {cost}"
    )

    return redirect(f"/item/{item_id}")

@app.route("/delete-payment/<int:payment_id>/<int:item_id>")
def delete_payment(payment_id, item_id):

    if "username" not in session:
        return redirect("/login")

    conn = sqlite3.connect("wedding.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT amount FROM payments WHERE id = ?",
        (payment_id,)
    )

    payment = cursor.fetchone()

    cursor.execute(
        "DELETE FROM payments WHERE id = ?",
        (payment_id,)
    )

    conn.commit()
    conn.close()

    log_activity(
        session["username"],
        f"Deleted payment ₹{payment[0]}"
    )

    return redirect(f"/item/{item_id}")

@app.route("/update-name/<int:item_id>", methods=["POST"])
@app.route("/update-name/<int:item_id>", methods=["POST"])
def update_name(item_id):

    if "username" not in session:
        return redirect("/login")

    name = request.form["name"]

    conn = sqlite3.connect("wedding.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT name FROM items WHERE id = ?",
        (item_id,)
    )

    old_name = cursor.fetchone()[0]

    cursor.execute(
        "UPDATE items SET name = ? WHERE id = ?",
        (name, item_id)
    )

    conn.commit()
    conn.close()

    log_activity(
        session["username"],
        f"Renamed '{old_name}' to '{name}'"
    )

    return redirect(f"/item/{item_id}")

@app.route("/delete-item/<int:item_id>")
def delete_item(item_id):

    if "username" not in session:
        return redirect("/login")

    conn = sqlite3.connect("wedding.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT name FROM items WHERE id = ?",
        (item_id,)
    )

    item = cursor.fetchone()

    cursor.execute(
        "DELETE FROM payments WHERE item_id = ?",
        (item_id,)
    )

    cursor.execute(
        "DELETE FROM items WHERE id = ?",
        (item_id,)
    )

    conn.commit()
    conn.close()

    log_activity(
        session["username"],
        f"Deleted item '{item[0]}'"
    )

    return redirect("/")

@app.route("/update-notes/<int:item_id>", methods=["POST"])
def update_notes(item_id):

    if "username" not in session:
        return redirect("/login")

    notes = request.form["notes"]

    conn = sqlite3.connect("wedding.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT name FROM items WHERE id = ?",
        (item_id,)
    )

    item = cursor.fetchone()

    cursor.execute(
        "UPDATE items SET notes = ? WHERE id = ?",
        (notes, item_id)
    )

    conn.commit()
    conn.close()

    log_activity(
        session["username"],
        f"Updated notes for '{item[0]}'"
    )

    return redirect(f"/item/{item_id}")

@app.route("/clear-activity")
def clear_activity():

    if "username" not in session:
        return redirect("/login")

    conn = sqlite3.connect("wedding.db")
    cursor = conn.cursor()

    cursor.execute("DELETE FROM activity_log")

    conn.commit()
    conn.close()

    return redirect("/")

@app.route("/logout")
def logout():

    session.clear()

    return redirect("/login")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
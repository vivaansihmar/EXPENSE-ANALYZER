from flask import Flask, render_template, request, redirect, session, jsonify, url_for
from flask_bcrypt import Bcrypt
from flask_session import Session
from bson.objectid import ObjectId
from datetime import datetime
from pymongo import MongoClient
import os
import pandas as pd
from ml.finance_model import generate_finance_graphs  # 👈 Import ML module

app = Flask(__name__, template_folder="templates")
app.secret_key = os.environ.get("SECRET_KEY", "dev_secret_key")

# ------------------- SESSION CONFIG -------------------
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_USE_SIGNER"] = True
app.config["SESSION_COOKIE_SECURE"] = False
Session(app)

bcrypt = Bcrypt(app)

# ------------------- MONGO SETUP -------------------
client = MongoClient("mongodb://localhost:27017")
db = client["Expenseanalyzer"]

users_collection = db["logindetails"]
sections_collection = db["sections"]
entries_collection = db["entries"]

# ------------------- ROUTES -------------------

@app.route("/")
def home():
    return redirect("/auth")


# ------------------- AUTH -------------------
@app.route("/auth", methods=["GET", "POST"])
def auth():
    if request.method == "POST":
        form_type = request.form.get("formType")
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if form_type == "register":
            username = request.form.get("username", "").strip()

            if users_collection.find_one({"email": email}):
                return "User already exists. Please login."
            if users_collection.find_one({"username": username}):
                return "Username already taken."

            hashed_pw = bcrypt.generate_password_hash(password).decode("utf-8")

            users_collection.insert_one({
                "username": username,
                "email": email,
                "password": hashed_pw
            })

            session["user"] = {"email": email, "username": username}
            return redirect("/dashboard")

        elif form_type == "login":
            user = users_collection.find_one({"email": email})
            if user and bcrypt.check_password_hash(user["password"], password):
                session["user"] = {"email": user["email"], "username": user["username"]}
                return redirect("/dashboard")
            else:
                return "Invalid email or password"

    return render_template("auth.html")


# ------------------- DASHBOARD -------------------
@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect("/auth")

    user_email = session["user"]["email"]

    # Fetch user's sections and entries
    sections = list(sections_collection.find({"email": user_email}))
    for section in sections:
        section["_id"] = str(section["_id"])
        section["entries"] = list(entries_collection.find({"section_id": section["_id"]}))
        for e in section["entries"]:
            e["_id"] = str(e["_id"])

    css_path = os.path.join(os.path.dirname(__file__), "static", "styles.css")
    css_version = int(os.path.getmtime(css_path)) if os.path.exists(css_path) else 0

    return render_template("dashboard.html", user=session["user"], sections=sections, css_version=css_version)


# ------------------- ADD EXPENSE PAGE -------------------
@app.route("/add-expense", methods=["GET"])
def add_expense():
    if "user" not in session:
        return redirect("/auth")

    css_path = os.path.join(os.path.dirname(__file__), "static", "styles.css")
    css_version = int(os.path.getmtime(css_path)) if os.path.exists(css_path) else 0

    return render_template("add_expense.html", user=session["user"], css_version=css_version)

@app.route("/get-sections")
def get_sections():
    if "user" not in session:
        return jsonify({"status": "error", "message": "Not logged in"}), 401

    user_email = session["user"]["email"]
    sections = list(sections_collection.find({"email": user_email}))

    for s in sections:
        s["_id"] = str(s["_id"])
        s["entries"] = list(entries_collection.find({"section_id": s["_id"]}))
        for e in s["entries"]:
            e["_id"] = str(e["_id"])

    return jsonify({"status": "success", "sections": sections}), 200


# ------------------- AJAX API: SAVE SECTION -------------------
@app.route("/save-section", methods=["POST"])
def save_section():
    if "user" not in session:
        return jsonify({"status": "error", "message": "Not logged in"}), 401

    user_email = session["user"]["email"]
    data = request.get_json()
    section_name = data.get("name", "").strip()

    if not section_name:
        return jsonify({"status": "error", "message": "Section name required"}), 400

    section = {
        "email": user_email,
        "name": section_name,
        "created_at": datetime.utcnow()
    }

    result = sections_collection.insert_one(section)
    section["_id"] = str(result.inserted_id)
    section["entries"] = []

    return jsonify({"status": "success", "section": section}), 201


# ------------------- AJAX API: SAVE ENTRY -------------------
@app.route("/save-entry", methods=["POST"])
def save_entry():
    if "user" not in session:
        return jsonify({"status": "error", "message": "Not logged in"}), 401

    user_email = session["user"]["email"]
    data = request.get_json()
    section_id = data.get("section_id")
    title = data.get("title", "").strip()
    amount = float(data.get("amount", 0))
    entry_type = data.get("type", "expense").lower()

    if not section_id or not title or amount <= 0:
        return jsonify({"status": "error", "message": "Invalid data"}), 400

    entry = {
        "email": user_email,
        "section_id": section_id,
        "title": title,
        "amount": amount,
        "type": entry_type,
        "created_at": datetime.utcnow()
    }

    result = entries_collection.insert_one(entry)
    entry["_id"] = str(result.inserted_id)

    return jsonify({"status": "success", "entry": entry}), 201


@app.route("/summary")
def summary():
    if "user" not in session:
        return redirect("/auth")

    user_email = session["user"]["email"]

    # Fetch all entries from MongoDB
    entries = list(entries_collection.find({"email": user_email}))
    if not entries:
        return render_template("summary.html", user=session["user"], graphs_available=False)

    # Convert MongoDB entries to DataFrame
    df = pd.DataFrame(entries)
    df['date'] = pd.to_datetime(df.get('created_at', datetime.utcnow()))
    df['category'] = df.get('title', 'Other')
    df['amount'] = df['amount'].astype(float)
    df['type'] = df.get('type', 'expense')

    # Generate graphs using ML module
    static_path = os.path.join(os.path.dirname(__file__), "static")
    generate_finance_graphs(df=df, static_path=static_path)

    # Graph files for display
    graphs = [
        "monthly_income_expense.png",
        "category_expense_pie.png",
        "expense_forecast.png"
    ]

    return render_template(
        "summary.html",
        user=session["user"],
        graphs=graphs,
        graphs_available=True
    )

@app.route("/summary-data")
def summary_data():
    if "user" not in session:
        return jsonify({"status": "error", "message": "Not logged in"}), 401

    user_email = session["user"]["email"]
    entries = list(entries_collection.find({"email": user_email}))

    if not entries:
        return jsonify({"status": "success", "data": []})

    df = pd.DataFrame(entries)
    df['date'] = pd.to_datetime(df['created_at'])
    df['month'] = df['date'].dt.to_period('M').astype(str)
    df['amount'] = df['amount'].astype(float)
    df['type'] = df.get('type', 'expense')
    df['category'] = df.get('title', 'Other')

    # Group by month and type for income vs expense
    monthly = df.groupby(['month', 'type'])['amount'].sum().unstack(fill_value=0)
    expense_by_category = df[df['type'] == 'expense'].groupby('category')['amount'].sum().sort_values(ascending=False)

    data = {
        "months": list(monthly.index),
        "income": monthly.get('income', pd.Series()).tolist(),
        "expense": monthly.get('expense', pd.Series()).tolist(),
        "categories": list(expense_by_category.index),
        "category_amounts": expense_by_category.tolist()
    }

    return jsonify({"status": "success", "data": data})

# ------------------- LOGOUT -------------------
@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect("/auth")


# ------------------- CONTEXT -------------------
@app.context_processor
def inject_now():
    return {"now": datetime.utcnow}


# ------------------- RUN -------------------
if __name__ == "__main__":
    app.run(debug=True)

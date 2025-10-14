import os
import logging
from datetime import datetime
import matplotlib
matplotlib.use("Agg")
from flask import Flask, render_template, request, redirect, session, jsonify, url_for, flash
from flask_bcrypt import Bcrypt
from flask_session import Session
from bson.objectid import ObjectId
from pymongo import MongoClient
import pandas as pd

app = Flask(__name__, template_folder="templates")
app.secret_key = os.environ.get("SECRET_KEY", "dev_secret_key")

# session config
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_USE_SIGNER"] = True
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("SESSION_COOKIE_SECURE", "False").lower() in ("1", "true", "yes")
Session(app)

bcrypt = Bcrypt(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# mongochk
MONGO_URI = os.environ.get("MONGO_URI")
if not MONGO_URI:
    print(" MONGO_URI not found in environment variables!")
else:
    print(f"MONGO_URI loaded: {MONGO_URI[:40]}...")

client = MongoClient(MONGO_URI)
db = client["Expenseanalyzer"]

#Mongo 
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
client = MongoClient(MONGO_URI)
db = client["Expenseanalyzer"]

users_collection = db["logindetails"]
sections_collection = db["sections"]
entries_collection = db["entries"]

def to_jsonable_entry(doc):
    d = dict(doc)
    if "_id" in d:
        d["_id"] = str(d["_id"])
    if "created_at" in d and isinstance(d["created_at"], datetime):
        d["created_at"] = d["created_at"].isoformat()
    if "amount" in d:
        try:
            d["amount"] = float(d["amount"])
        except:
            pass
    return d

def parse_json_or_form(req):
    json_body = req.get_json(silent=True)
    return json_body if json_body else req.form.to_dict()

#dashboard
@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect("/auth")
    user_email = session["user"]["email"]
    sections = list(sections_collection.find({"email": user_email}))
    for section in sections:
        section["_id"] = str(section["_id"])
        entries = list(entries_collection.find({"section_id": section["_id"]}))
        section["entries"] = [to_jsonable_entry(e) for e in entries]
    css_path = os.path.join(os.path.dirname(__file__), "static", "styles.css")
    css_version = int(os.path.getmtime(css_path)) if os.path.exists(css_path) else 0
    return render_template("dashboard.html", user=session["user"], sections=sections, css_version=css_version)

# expense
@app.route("/add-expense")
def add_expense():
    if "user" not in session:
        return redirect("/auth")
    css_path = os.path.join(os.path.dirname(__file__), "static", "styles.css")
    css_version = int(os.path.getmtime(css_path)) if os.path.exists(css_path) else 0
    return render_template("add_expense.html", user=session["user"], css_version=css_version)

# Api endpoints
@app.route("/get-sections")
def get_sections():
    if "user" not in session:
        return jsonify({"status": "error", "message": "Not logged in"}), 401
    user_email = session["user"]["email"]
    sections = list(sections_collection.find({"email": user_email}))
    out = []
    for s in sections:
        s_id = str(s["_id"])
        entries = list(entries_collection.find({"section_id": s_id}))
        s_doc = {
            "_id": s_id,
            "name": s.get("name", ""),
            "created_at": s.get("created_at").isoformat() if isinstance(s.get("created_at"), datetime) else s.get("created_at"),
            "entries": [to_jsonable_entry(e) for e in entries]
        }
        out.append(s_doc)
    return jsonify({"status": "success", "sections": out}), 200

@app.route("/get-incomes")
def get_incomes():
    if "user" not in session:
        return jsonify({"status": "error", "message": "Not logged in"}), 401
    user_email = session["user"]["email"]
    incomes = list(entries_collection.find({"email": user_email, "type": "income"}))
    return jsonify({"status": "success", "entries": [to_jsonable_entry(i) for i in incomes]})

# deletion
@app.route("/delete-section/<section_id>", methods=["DELETE"])
def delete_section(section_id):
    if "user" not in session:
        return jsonify({"status": "error", "message": "Not logged in"}), 401
    entries_collection.delete_many({"section_id": section_id})
    sections_collection.delete_one({"_id": ObjectId(section_id)})
    return jsonify({"status": "success"}), 200

@app.route("/delete-entry/<entry_id>", methods=["DELETE"])
def delete_entry(entry_id):
    if "user" not in session:
        return jsonify({"status": "error", "message": "Not logged in"}), 401
    entries_collection.delete_one({"_id": ObjectId(entry_id)})
    return jsonify({"status": "success"}), 200

# save
@app.route("/save-section", methods=["POST"])
def save_section():
    if "user" not in session:
        return jsonify({"status": "error", "message": "Not logged in"}), 401
    user_email = session["user"]["email"]
    data = parse_json_or_form(request)
    section_name = (data.get("name") or "").strip()
    if not section_name:
        return jsonify({"status": "error", "message": "Section name required"}), 400
    section = {
        "email": user_email,
        "name": section_name,
        "created_at": datetime.utcnow()
    }
    result = sections_collection.insert_one(section)
    section["_id"] = str(result.inserted_id)
    section["created_at"] = section["created_at"].isoformat()
    section["entries"] = []
    return jsonify({"status": "success", "section": section}), 201

@app.route("/save-entry", methods=["POST"])
def save_entry():
    if "user" not in session:
        return jsonify({"status": "error", "message": "Not logged in"}), 401
    user_email = session["user"]["email"]
    data = parse_json_or_form(request)
    section_id = data.get("section_id")
    title = (data.get("title") or "").strip()
    amount = float(data.get("amount", 0) or 0)
    entry_type = (data.get("type") or "expense").lower()
    month = data.get("month") or datetime.utcnow().strftime("%B")
    year = int(data.get("year") or datetime.utcnow().year)
    if not section_id or not title or amount <= 0:
        return jsonify({"status": "error", "message": "Invalid data"}), 400
    entry = {
        "email": user_email,
        "section_id": str(section_id),
        "title": title,
        "amount": amount,
        "type": entry_type,
        "month": month,
        "year": year,
        "created_at": datetime.utcnow()
    }
    result = entries_collection.insert_one(entry)
    entry["_id"] = str(result.inserted_id)
    entry["created_at"] = entry["created_at"].isoformat()
    return jsonify({"status": "success", "entry": entry}), 201

# summary
@app.route("/summary")
def summary():
    if "user" not in session:
        return redirect("/auth")
    return render_template("summary.html", user=session["user"])

@app.route("/summary-data")
def summary_data():
    if "user" not in session:
        return jsonify({"status": "error", "message": "Not logged in"}), 401
    user_email = session["user"]["email"]
    entries = list(entries_collection.find({"email": user_email}))
    if not entries:
        return jsonify({"status": "success", "data": {}})
    df = pd.DataFrame(entries)
    df["month"] = df.get("month", pd.to_datetime(df["created_at"]).dt.strftime("%B"))
    df["year"] = pd.to_numeric(df.get("year", pd.to_datetime(df["created_at"]).dt.year), errors="coerce").fillna(datetime.utcnow().year).astype(int)
    df["month_year"] = df["month"].astype(str) + " " + df["year"].astype(str)
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0)
    df["type"] = df.get("type", "expense")
    df["category"] = df.get("title", "Other")
    income_df = df[df["type"] == "income"]
    expense_df = df[df["type"] == "expense"]
    months_sorted = sorted(df["month_year"].unique(), key=lambda x: pd.to_datetime(str(x), format="%B %Y", errors="coerce"))
    monthly_income = income_df.groupby("month_year")["amount"].sum().reindex(months_sorted, fill_value=0)
    monthly_expense = expense_df.groupby("month_year")["amount"].sum().reindex(months_sorted, fill_value=0)
    savings = (monthly_income - monthly_expense).tolist()
    income_by_category = income_df.groupby("category")["amount"].sum().sort_values(ascending=False)
    expense_by_category = expense_df.groupby("category")["amount"].sum().sort_values(ascending=False)
    data = {
        "months": list(months_sorted),
        "income": monthly_income.tolist(),
        "expense": monthly_expense.tolist(),
        "savings": savings,
        "income_categories": list(income_by_category.index),
        "income_amounts": income_by_category.tolist(),
        "expense_categories": list(expense_by_category.index),
        "expense_amounts": expense_by_category.tolist()
    }
    return jsonify({"status": "success", "data": data})

# homepage
@app.route("/")
def home():
    return render_template("homepage.html")

# auth
@app.route("/auth", methods=["GET", "POST"])
def auth():
    if request.method == "POST":
        form_type = request.form.get("formType")
        if form_type == "register":
            email = request.form.get("email", "").strip().lower()
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            if not email or not username or not password:
                flash("All fields are required.", "error")
            elif users_collection.find_one({"email": email}):
                flash("User already exists. Please login.", "error")
            elif users_collection.find_one({"username": username}):
                flash("Username already taken.", "error")
            else:
                hashed_pw = bcrypt.generate_password_hash(password).decode("utf-8")
                users_collection.insert_one({
                    "username": username,
                    "email": email,
                    "password": hashed_pw
                })
                session["user"] = {"email": email, "username": username}
                return redirect("/dashboard")
        elif form_type == "login":
            identifier = (request.form.get("identifier") or request.form.get("email") or "").strip()
            password = request.form.get("password", "")
            if not identifier or not password:
                flash("Please enter both fields.", "error")
            else:
                if "@" in identifier:
                    user = users_collection.find_one({"email": identifier.lower()})
                else:
                    user = users_collection.find_one({"username": identifier})
                if user and bcrypt.check_password_hash(user["password"], password):
                    session["user"] = {"email": user["email"], "username": user["username"]}
                    return redirect("/dashboard")
                else:
                    flash("Invalid email/username or password.", "error")
        return redirect(f"/auth?form={form_type}") 
    return render_template("auth.html")


# profile
@app.route("/profile")
def profile():
    if "user" not in session:
        return redirect(url_for("auth"))
    return render_template("profile.html")

@app.route("/profile/update-username", methods=["POST"])
def update_username():
    if "user" not in session:
        return redirect(url_for("auth"))
    new_username = (request.form.get("new_username") or "").strip()
    if not new_username:
        flash("Username cannot be empty.")
        return redirect(url_for("profile"))
    if users_collection.find_one({"username": new_username}):
        flash("Username already taken.")
        return redirect(url_for("profile"))
    email = session["user"]["email"]
    users_collection.update_one({"email": email}, {"$set": {"username": new_username}})
    session["user"]["username"] = new_username
    flash("Username updated successfully.")
    return redirect(url_for("profile"))

@app.route("/profile/change-password", methods=["POST"])
def change_password():
    if "user" not in session:
        return redirect(url_for("auth"))
    email = session["user"]["email"]
    user = users_collection.find_one({"email": email})
    current_password = request.form.get("current_password", "")
    new_password = request.form.get("new_password", "")
    confirm_password = request.form.get("confirm_password", "")
    if not user or not bcrypt.check_password_hash(user["password"], current_password):
        flash("Current password is incorrect.")
        return redirect(url_for("profile"))
    if len(new_password) < 6 or new_password != confirm_password:
        flash("New password must be at least 6 characters and match confirmation.")
        return redirect(url_for("profile"))
    hashed_pw = bcrypt.generate_password_hash(new_password).decode("utf-8")
    users_collection.update_one({"email": email}, {"$set": {"password": hashed_pw}})
    flash("Password updated successfully.")
    return redirect(url_for("profile"))

@app.route("/profile/delete-account", methods=["POST"])
def delete_account():
    if "user" not in session:
        return redirect(url_for("auth"))
    email = session["user"]["email"]
    user = users_collection.find_one({"email": email})
    password = request.form.get("password", "")
    if not user or not bcrypt.check_password_hash(user["password"], password):
        flash("Password incorrect. Account not deleted.")
        return redirect(url_for("profile"))
    # Delete
    sections_collection.delete_many({"email": email})
    entries_collection.delete_many({"email": email})
    users_collection.delete_one({"email": email})
    session.pop("user", None)
    flash("Your account has been deleted.")
    return redirect(url_for("auth"))
# logout
@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect("/auth")

@app.context_processor
def inject_now():
    return {"now": datetime.utcnow}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug_flag = os.environ.get("FLASK_DEBUG", "True").lower() in ("1", "true", "yes")
    app.run(host="0.0.0.0", port=port, debug=debug_flag)
from flask import Flask, render_template, request, redirect, session, url_for
from flask_bcrypt import Bcrypt
from flask_session import Session
from bson.objectid import ObjectId
from datetime import datetime
from pymongo import MongoClient
import os
app = Flask(__name__, template_folder="templates")
app.secret_key = os.environ.get("SECRET_KEY", "dev_secret_key")
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_USE_SIGNER"] = True
app.config["SESSION_COOKIE_SECURE"] = False

Session(app)
bcrypt = Bcrypt(app)
client = MongoClient("mongodb://localhost:27017")
db = client["Expenseanalyzer"]
users_collection = db["logindetails"]

@app.route("/")
def home():
    return redirect("/auth")

@app.route("/auth", methods=["GET", "POST"])
def auth():
    if request.method == "POST":
        form_type = request.form.get("formType")
        email = request.form.get("email").strip().lower()
        password = request.form.get("password")

        if form_type == "register":
            if users_collection.find_one({"email": email}):
                return " User already exists. Please login."
            hashed_pw = bcrypt.generate_password_hash(password).decode("utf-8")
            users_collection.insert_one({"email": email, "password": hashed_pw})
            session["user"] = email
            return redirect("/dashboard")

        elif form_type == "login":
            user = users_collection.find_one({"email": email})
            if user and bcrypt.check_password_hash(user["password"], password):
                session["user"] = email
                return redirect("/dashboard")
            else:
                return " Invalid email or password"
    return render_template("auth.html")


@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect("/auth")
    css_path = os.path.join(os.path.dirname(__file__), "static", "style.css")
    css_version = int(os.path.getmtime(css_path)) if os.path.exists(css_path) else 0
    return render_template("dashboard.html", user=session["user"], css_version=css_version)

@app.context_processor
def inject_now():
    return {"now": datetime.utcnow}

#Run 
if __name__ == "__main__":
    app.run(debug=True)
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, current_user
from app import db
from app.models import User

bp = Blueprint("auth", __name__)

@bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name, email, password = (request.form.get(k, "").strip() for k in ("name", "email", "password"))
        role = request.form.get("role", "beneficiario")
        if not name or "@" not in email or len(password) < 8 or role not in ("donante", "beneficiario"):
            flash("Completa los datos. La contraseña debe tener al menos 8 caracteres.", "error")
        elif User.query.filter_by(email=email.lower()).first(): flash("Ese correo ya está registrado.", "error")
        else:
            user = User(name=name, email=email.lower(), role=role, department=request.form.get("department", ""), business=request.form.get("business", ""))
            user.set_password(password); db.session.add(user); db.session.commit(); login_user(user)
            return redirect(url_for("main.dashboard"))
    return render_template("auth.html", mode="register")

@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(email=request.form.get("email", "").lower().strip()).first()
        if user and user.check_password(request.form.get("password", "")):
            login_user(user); return redirect(url_for("main.dashboard"))
        flash("Correo o contraseña incorrectos.", "error")
    return render_template("auth.html", mode="login")

@bp.post("/logout")
def logout():
    logout_user(); return redirect(url_for("main.index"))

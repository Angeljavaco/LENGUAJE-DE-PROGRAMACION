from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, jsonify
from flask_login import login_user, logout_user, current_user
from sqlalchemy.exc import IntegrityError
from app import db
from app.models import User
from app.services import supabase_auth

bp = Blueprint("auth", __name__)

@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role = request.form.get("role", "beneficiario")
        department = request.form.get("department", "").strip()
        business = request.form.get("business", "").strip()

        if not name or "@" not in email or len(password) < 8 or role not in ("donante", "beneficiario"):
            flash("Completa los datos correctamente. La contraseña debe tener al menos 8 caracteres.", "error")
            return render_template("auth.html", mode="register")

        dni = request.form.get("dni", "").strip()
        if len(dni) != 8 or not dni.isascii() or not dni.isdecimal():
            flash("Ingresa un DNI de 8 dígitos.", "error")
            return render_template("auth.html", mode="register")

        if User.query.filter_by(dni=dni).first():
            flash("No se pudo registrar ese DNI. Revisa el número ingresado.", "error")
            return render_template("auth.html", mode="register")

        # Verificar si ya existe en la base de datos local
        existing_user = User.query.filter_by(email=email).first()
        if existing_user and not existing_user.is_demo:
            flash("Ese correo ya está registrado en la plataforma.", "error")
            return render_template("auth.html", mode="register")

        # Si Supabase está configurado, registrar en Supabase Auth
        if supabase_auth.is_supabase_configured() and not current_app.config.get("TESTING"):
            confirm_url = url_for("auth.confirm", _external=True)
            res = supabase_auth.signup(
                email,
                password,
                metadata={"name": name, "role": role},
                redirect_to=confirm_url
            )
            if not res["success"]:
                flash(res.get("error", "Error al crear la cuenta en Supabase."), "error")
                return render_template("auth.html", mode="register")

            supabase_uid = res.get("user_id")
            email_confirmed = res.get("email_confirmed", False)

            # Crear o actualizar en la base de datos
            if not existing_user:
                user = User(
                    name=name,
                    email=email,
                    role=role,
                    department=department,
                    business=business,
                    dni=dni,
                    supabase_uid=supabase_uid,
                    is_verified=email_confirmed
                )
                user.set_password(password)
                db.session.add(user)
            else:
                existing_user.name = name
                existing_user.dni = dni
                existing_user.role = role
                existing_user.supabase_uid = supabase_uid
                existing_user.is_verified = email_confirmed
                existing_user.set_password(password)
                user = existing_user

            db.session.commit()

            if email_confirmed:
                login_user(user)
                flash(f"¡Bienvenido, {name}! Tu cuenta ha sido creada.", "success")
                return redirect(url_for("main.dashboard"))
            else:
                flash(
                    f"¡Cuenta creada con éxito! Hemos enviado un correo de confirmación a {email}. "
                    "Por favor revisa tu bandeja de entrada o spam y confirma tu cuenta antes de iniciar sesión.",
                    "success"
                )
                return redirect(url_for("auth.login", email=email))

        # Flujo estándar local / testing (sin Supabase)
        user = User(name=name, email=email, dni=dni, role=role, department=department, business=business, is_verified=True)
        user.set_password(password)
        db.session.add(user)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            if not User.query.filter((User.dni == dni) | (User.email == email)).first():
                raise
            flash("El correo o DNI ya está asociado a una cuenta.", "error")
            return render_template("auth.html", mode="register")
        login_user(user)
        return redirect(url_for("main.dashboard"))

    return render_template("auth.html", mode="register")

@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    email_param = request.args.get("email", "")

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = User.query.filter_by(email=email).first()

        # Si es un usuario demo del sistema, permitir login directo
        if user and user.is_demo:
            if user.check_password(password):
                login_user(user)
                flash(f"Sesión iniciada como {user.name} (Modo Demo).", "info")
                return redirect(url_for("main.dashboard"))
            flash("Correo o contraseña incorrectos.", "error")
            return render_template("auth.html", mode="login", email_value=email)

        # Si Supabase está configurado y no estamos en TESTING
        if supabase_auth.is_supabase_configured() and not current_app.config.get("TESTING"):
            res = supabase_auth.signin(email, password)

            if res["code"] == "EMAIL_NOT_CONFIRMED":
                flash(
                    "Tu correo electrónico aún no ha sido confirmado. "
                    "Por favor revisa tu bandeja de entrada o spam. Puedes reenviar el correo si no lo encuentras.",
                    "warning"
                )
                return render_template("auth.html", mode="login", email_value=email, unconfirmed_email=email)

            if not res["success"]:
                # También verificar si la contraseña coincide localmente pero en Supabase no está confirmado
                if user and user.check_password(password):
                    confirmed = supabase_auth.check_admin_user_confirmed(user_id=user.supabase_uid, email=email)
                    if confirmed is False:
                        flash(
                            "Tu correo electrónico aún no ha sido confirmado. "
                            "Por favor revisa tu bandeja de entrada o spam.",
                            "warning"
                        )
                        return render_template("auth.html", mode="login", email_value=email, unconfirmed_email=email)

                flash("Correo o contraseña incorrectos.", "error")
                return render_template("auth.html", mode="login", email_value=email)

            # Supabase confirmó inicio de sesión exitoso
            supabase_user = res.get("user", {})
            supabase_uid = res.get("user_id")

            if not user:
                # Si el usuario existe en Supabase pero no en la tabla local
                user_metadata = supabase_user.get("user_metadata", {})
                user = User(
                    name=user_metadata.get("name", email.split("@")[0]),
                    email=email,
                    role=user_metadata.get("role", "beneficiario"),
                    supabase_uid=supabase_uid,
                    is_verified=True
                )
                user.set_password(password)
                db.session.add(user)
            else:
                user.is_verified = True
                if supabase_uid and not user.supabase_uid:
                    user.supabase_uid = supabase_uid

            db.session.commit()
            login_user(user)
            flash(f"¡Bienvenido de nuevo, {user.name}!", "success")
            return redirect(url_for("main.dashboard"))

        # Fallback local
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for("main.dashboard"))
        flash("Correo o contraseña incorrectos.", "error")
        return render_template("auth.html", mode="login", email_value=email)

    return render_template("auth.html", mode="login", email_value=email_param)

@bp.route("/resend-verification", methods=["GET", "POST"])
def resend_verification():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        if not email or "@" not in email:
            flash("Ingresa un correo electrónico válido.", "error")
            return redirect(url_for("auth.login"))

        if supabase_auth.is_supabase_configured():
            res = supabase_auth.resend_confirmation_email(email)
            if res["success"]:
                flash(
                    f"Se ha reenviado el correo de confirmación a {email}. "
                    "Por favor revisa tu bandeja de entrada y la carpeta de spam.",
                    "success"
                )
            else:
                flash(res.get("error", "No se pudo reenviar el correo de confirmación."), "error")
        else:
            flash("El servicio de confirmación no está habilitado actualmente.", "info")

        return redirect(url_for("auth.login", email=email))

    email_param = request.args.get("email", "")
    return render_template("resend_verification.html", email=email_param)

@bp.route("/confirm", methods=["GET"])
def confirm():
    """
    Ruta a la que Supabase redirige cuando el usuario hace clic en el enlace de confirmación.
    Puede recibir token_hash, code o hash fragments procesados en cliente.
    """
    token_hash = request.args.get("token_hash")
    verify_type = request.args.get("type", "signup")

    if token_hash:
        res = supabase_auth.verify_token(token_hash, verify_type)
        if res["success"]:
            user_data = res.get("data", {}).get("user", {})
            user_email = user_data.get("email")
            if user_email:
                user = User.query.filter_by(email=user_email.lower()).first()
                if user:
                    user.is_verified = True
                    db.session.commit()
            flash("¡Tu correo ha sido verificado exitosamente! Ya puedes iniciar sesión.", "success")
            return redirect(url_for("auth.login", email=user_email or ""))
        else:
            flash("El enlace de verificación no es válido o ha expirado. Puedes solicitar uno nuevo.", "error")
            return redirect(url_for("auth.login"))

    # Si Supabase redirige con hash params (implicit flow en cliente), renderizamos una plantilla ligera
    # que captura el hash y redirige a login con mensaje exitoso.
    return render_template("confirm.html")

@bp.post("/confirm-session")
def confirm_session():
    """Endpoint llamado por confirm.html cuando detecta el access_token en el hash de la URL"""
    data = request.get_json() or {}
    email = data.get("email", "").strip().lower()
    if email:
        user = User.query.filter_by(email=email).first()
        if user:
            user.is_verified = True
            db.session.commit()
    flash("¡Tu correo ha sido verificado con éxito! Ahora puedes iniciar sesión.", "success")
    return jsonify({"status": "ok", "redirect": url_for("auth.login", email=email)})

@bp.post("/logout")
def logout():
    logout_user()
    flash("Has cerrado sesión.", "info")
    return redirect(url_for("main.index"))

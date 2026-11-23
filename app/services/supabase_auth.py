import os
import requests
from flask import current_app

def _get_config():
    try:
        url = current_app.config.get("SUPABASE_URL") or os.getenv("SUPABASE_URL", "")
        key = current_app.config.get("SUPABASE_KEY") or os.getenv("SUPABASE_KEY", "")
        secret_key = current_app.config.get("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_SECRET_KEY", "")
    except RuntimeError:
        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_KEY", "")
        secret_key = os.getenv("SUPABASE_SECRET_KEY", "")
    return url.rstrip("/"), key, secret_key

def is_supabase_configured():
    url, key, _ = _get_config()
    return bool(url and key)

def signup(email, password, metadata=None, redirect_to=None):
    url, key, _ = _get_config()
    if not url or not key:
        return {"success": False, "error": "Supabase no está configurado."}

    headers = {
        "apikey": key,
        "Content-Type": "application/json"
    }
    payload = {
        "email": email.strip().lower(),
        "password": password,
        "data": metadata or {}
    }
    if redirect_to:
        payload["options"] = {"email_redirect_to": redirect_to}

    try:
        resp = requests.post(f"{url}/auth/v1/signup", json=payload, headers=headers, timeout=10)
        data = resp.json() if resp.content else {}
    except Exception as e:
        return {"success": False, "error": f"Error al conectar con el servicio de autenticación: {e}"}

    if resp.status_code in (200, 201):
        # Supabase protection: if user exists, identities list is often empty
        identities = data.get("identities")
        if identities is not None and len(identities) == 0:
            return {
                "success": False,
                "error": "Ese correo ya se encuentra registrado. Si no confirmaste tu cuenta, puedes solicitar el reenvío del correo.",
                "already_exists": True
            }

        user_id = data.get("id")
        email_confirmed = bool(data.get("email_confirmed_at"))
        return {
            "success": True,
            "user_id": user_id,
            "email_confirmed": email_confirmed,
            "data": data
        }

    # Error handling
    err_code = data.get("error_code") or data.get("code")
    err_msg = data.get("msg") or data.get("message") or data.get("error_description") or ""

    if err_code == "over_email_send_rate_limit" or "rate limit" in err_msg.lower():
        translated = "Se ha alcanzado el límite de envío de correos temporales. Por favor espera unos minutos antes de intentar registrarte nuevamente."
    elif "already registered" in err_msg.lower() or err_code == "user_already_exists":
        translated = "Ese correo ya está registrado."
    elif "password" in err_msg.lower() and "short" in err_msg.lower():
        translated = "La contraseña debe tener al menos 8 caracteres."
    elif "invalid" in err_msg.lower() and "email" in err_msg.lower():
        translated = "El formato del correo electrónico no es válido."
    else:
        translated = err_msg or "No se pudo registrar la cuenta en Supabase."

    return {"success": False, "error": translated, "raw": data}

def signin(email, password):
    url, key, _ = _get_config()
    if not url or not key:
        return {"success": False, "code": "NOT_CONFIGURED", "error": "Supabase no está configurado."}

    headers = {
        "apikey": key,
        "Content-Type": "application/json"
    }
    payload = {
        "email": email.strip().lower(),
        "password": password
    }

    try:
        resp = requests.post(f"{url}/auth/v1/token?grant_type=password", json=payload, headers=headers, timeout=10)
        data = resp.json() if resp.content else {}
    except Exception as e:
        return {"success": False, "code": "CONNECTION_ERROR", "error": f"Error de conexión: {e}"}

    if resp.status_code == 200:
        user_info = data.get("user", {})
        return {
            "success": True,
            "code": "OK",
            "access_token": data.get("access_token"),
            "user_id": user_info.get("id"),
            "email": user_info.get("email"),
            "user": user_info
        }

    err_code = data.get("error_code") or data.get("code")
    err_msg = data.get("msg") or data.get("error_description") or data.get("message") or ""

    if err_code == "email_not_confirmed" or "email not confirmed" in err_msg.lower():
        return {
            "success": False,
            "code": "EMAIL_NOT_CONFIRMED",
            "error": "Debes confirmar tu correo electrónico antes de iniciar sesión. Por favor revisa tu bandeja de entrada o spam."
        }

    if err_code == "invalid_credentials" or "invalid login credentials" in err_msg.lower():
        return {
            "success": False,
            "code": "INVALID_CREDENTIALS",
            "error": "Correo o contraseña incorrectos."
        }

    return {
        "success": False,
        "code": "ERROR",
        "error": err_msg or "Error al autenticar con Supabase."
    }

def resend_confirmation_email(email):
    url, key, _ = _get_config()
    if not url or not key:
        return {"success": False, "error": "Supabase no está configurado."}

    headers = {
        "apikey": key,
        "Content-Type": "application/json"
    }
    payload = {
        "type": "signup",
        "email": email.strip().lower()
    }

    try:
        resp = requests.post(f"{url}/auth/v1/resend", json=payload, headers=headers, timeout=10)
        if resp.status_code == 200:
            return {"success": True}
        if resp.status_code == 429:
            return {"success": False, "error": "Has realizado demasiadas solicitudes. Espera un minuto antes de reintentar."}
        data = resp.json() if resp.content else {}
        err_msg = data.get("msg") or data.get("message") or "Error al reenviar el correo de confirmación."
        return {"success": False, "error": err_msg}
    except Exception as e:
        return {"success": False, "error": f"Error de conexión: {e}"}

def verify_token(token_hash, verify_type="signup"):
    url, key, _ = _get_config()
    if not url or not key:
        return {"success": False, "error": "Supabase no está configurado."}

    headers = {
        "apikey": key
    }
    try:
        resp = requests.get(
            f"{url}/auth/v1/verify",
            params={"token_hash": token_hash, "type": verify_type},
            headers=headers,
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json() if resp.content else {}
            return {"success": True, "data": data}
        data = resp.json() if resp.content else {}
        msg = data.get("msg") or data.get("message") or "El enlace es inválido o ha expirado."
        return {"success": False, "error": msg}
    except Exception as e:
        return {"success": False, "error": f"Error de conexión: {e}"}

def check_admin_user_confirmed(user_id=None, email=None):
    """Verifica directamente en Supabase si el usuario ya confirmó su correo"""
    url, _, secret_key = _get_config()
    if not url or not secret_key:
        return None

    headers = {
        "apikey": secret_key,
        "Authorization": f"Bearer {secret_key}"
    }

    try:
        if user_id:
            resp = requests.get(f"{url}/auth/v1/admin/users/{user_id}", headers=headers, timeout=10)
            if resp.status_code == 200:
                user = resp.json()
                return bool(user.get("email_confirmed_at"))
        elif email:
            # List users or search
            resp = requests.get(f"{url}/auth/v1/admin/users", headers=headers, timeout=10)
            if resp.status_code == 200:
                users = resp.json().get("users", [])
                for u in users:
                    if u.get("email", "").lower() == email.lower():
                        return bool(u.get("email_confirmed_at"))
    except Exception:
        pass
    return None

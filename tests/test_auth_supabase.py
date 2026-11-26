import pytest
from app import create_app, db
from app.models import User

@pytest.fixture
def app():
    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

def test_resend_verification_page_and_post(client):
    # GET resend page
    res = client.get("/auth/resend-verification")
    assert res.status_code == 200
    assert b"Reenviar correo de" in res.data

    # POST resend without valid email
    res_bad = client.post("/auth/resend-verification", data={"email": "not-an-email"}, follow_redirects=True)
    assert b"Ingresa un correo" in res_bad.data

def test_confirm_page_renders(client):
    res = client.get("/auth/confirm")
    assert res.status_code == 200
    assert b"Verificando tu cuenta" in res.data

def test_confirm_session_endpoint(client, app):
    with app.app_context():
        user = User(name="Carlos", email="carlos@example.com", role="donante", is_verified=False)
        user.set_password("Password123!")
        db.session.add(user)
        db.session.commit()

    res = client.post("/auth/confirm-session", json={"email": "carlos@example.com"})
    assert res.status_code == 200
    assert res.json.get("status") == "ok"

    with app.app_context():
        updated = User.query.filter_by(email="carlos@example.com").first()
        assert updated.is_verified is True

def test_local_login_after_register(client):
    # Test fallback flow when TESTING is True
    res = client.post(
        "/auth/register",
        data={"name": "Lucia", "email": "lucia@test.org", "dni": "01234567", "password": "Password123!", "role": "beneficiario"},
        follow_redirects=True
    )
    assert res.status_code == 200
    assert b"Lucia" in res.data or b"Panel" in res.data or b"Hola" in res.data

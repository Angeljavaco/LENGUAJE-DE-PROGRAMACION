from datetime import date, timedelta
import pytest
from app import create_app, db
from app.models import User, Food, Request, Conversation, Message

@pytest.fixture
def app():
    app=create_app({"TESTING":True,"WTF_CSRF_ENABLED":False,"SQLALCHEMY_DATABASE_URI":"sqlite:///:memory:"})
    with app.app_context():
        db.create_all(); yield app; db.session.remove(); db.drop_all()

@pytest.fixture
def client(app): return app.test_client()

def register(client,name,email,role,dni=None):
    if dni is None:
        dni = f"{User.query.count() + 1:08d}"
    return client.post('/auth/register',data={"name":name,"email":email,"dni":dni,"password":"password123","role":role},follow_redirects=True)

def test_register_and_login(client):
    response=register(client,"Ana","ana@test.test","beneficiario")
    assert response.status_code==200 and b"Hola" in response.data
    client.post('/auth/logout'); assert client.post('/auth/login',data={"email":"ana@test.test","password":"password123"}).status_code==302

def test_food_request_flow(client,app):
    register(client,"Donante","donor@test.test","donante")
    today=date.today().isoformat()
    resp=client.post('/foods/new',data={"name":"Manzanas","category":"Frutas","quantity":"12","unit":"kg","available_date":today,"expiry_date":(date.today()+timedelta(days=3)).isoformat()},follow_redirects=True)
    assert b"Manzanas" in resp.data
    client.post('/auth/logout'); register(client,"Beneficiaria","benef@test.test","beneficiario")
    with app.app_context(): food=Food.query.filter_by(name="Manzanas").first(); fid=food.id
    resp=client.post(f'/foods/{fid}/request',data={"quantity":"3"},follow_redirects=True)
    assert b"Solicitud enviada" in resp.data
    with app.app_context():
        req_id = Request.query.one().id
    certificate = f"/requests/{req_id}/certificate"

    client.post("/auth/logout")
    client.post("/auth/login", data={"email": "donor@test.test", "password": "password123"})
    assert client.get(certificate).status_code == 403
    assert client.post(f"/requests/{req_id}/accept").status_code == 302
    assert client.post(f"/requests/{req_id}/deliver").status_code == 302
    assert client.get(certificate).status_code == 403

    client.post("/auth/logout")
    client.post("/auth/login", data={"email": "benef@test.test", "password": "password123"})
    assert client.post(f"/requests/{req_id}/received").status_code == 302
    assert client.get(certificate).status_code == 403

    client.post("/auth/logout")
    register(client, "Otro donante", "other-donor@test.test", "donante")
    assert client.get(certificate).status_code == 403

    client.post("/auth/logout")
    client.post("/auth/login", data={"email": "donor@test.test", "password": "password123"})
    assert certificate.encode() in client.get("/dashboard").data
    pdf = client.get(certificate)
    assert pdf.status_code == 200
    assert pdf.mimetype == "application/pdf"
    assert pdf.data.startswith(b"%PDF-")
    assert f"certificado-donacion-{req_id}.pdf" in pdf.headers["Content-Disposition"]


def test_registration_validates_dni(client):
    for invalid in ("", "1234567", "1234567a", "123456789"):
        response = register(client, "Ana", "ana@test.test", "beneficiario", invalid)
        assert b"Ingresa un DNI de 8" in response.data
    assert User.query.count() == 0

    register(client, "Ana", "ana@test.test", "beneficiario", "01234567")
    assert User.query.one().dni == "01234567"
    client.post("/auth/logout")
    duplicate = register(client, "Otra", "otra@test.test", "donante", "01234567")
    assert b"No se pudo registrar ese DNI" in duplicate.data
    assert User.query.count() == 1

def test_api_rejects_negative_quantity(client):
    register(client,"Donante","api@test.test","donante")
    response=client.post('/api/alimentos',json={"name":"Fresas","category":"Frutas","quantity":-2,"unit":"kg","expiry_date":(date.today()+timedelta(days=2)).isoformat()})
    assert response.status_code==400

def test_chat_flow_permissions_and_unread(client,app):
    today=date.today()
    register(client,"Donante","chat-donor@test.test","donante")
    with app.app_context():
        donor=User.query.filter_by(email="chat-donor@test.test").first()
        food=Food(name="Arroz",category="Granos",quantity=10,unit="kg",available_date=today,expiry_date=today+timedelta(days=4),donor_id=donor.id)
        db.session.add(food);db.session.commit();food_id=food.id
    client.post('/auth/logout')
    register(client,"Beneficiaria","chat-beneficiary@test.test","beneficiario")
    created=client.post('/api/conversations',json={"food_id":food_id})
    assert created.status_code==201
    conversation_id=created.json["id"]
    assert client.post('/api/conversations',json={"food_id":food_id}).json["id"]==conversation_id
    sent=client.post(f'/api/conversations/{conversation_id}/messages',json={"content":"¿Sigue disponible?"})
    assert sent.status_code==201 and sent.json["sender_id"] != 0
    client.post('/auth/logout')
    login=client.post('/auth/login',data={"email":"chat-donor@test.test","password":"password123"})
    assert login.status_code==302
    assert client.get('/api/conversations/unread-count').json["count"]==1
    items=client.get(f'/api/conversations/{conversation_id}/messages').json
    assert [m["content"] for m in items]==["¿Sigue disponible?"]
    assert client.get('/api/conversations/unread-count').json["count"]==0
    reply=client.post(f'/api/conversations/{conversation_id}/messages',json={"content":"Sí, coordinamos el recojo."})
    assert reply.status_code==201
    client.post('/auth/logout')
    register(client,"Otra","other-beneficiary@test.test","beneficiario")
    assert client.get(f'/api/conversations/{conversation_id}/messages').status_code==403
    assert client.post(f'/api/conversations/{conversation_id}/messages',json={"content":"intrusión"}).status_code==403
    with app.app_context():
        assert Conversation.query.count()==1
        assert Message.query.count()==2

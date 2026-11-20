from datetime import date, timedelta
import pytest
from app import create_app, db
from app.models import User, Food, Request

@pytest.fixture
def app():
    app=create_app({"TESTING":True,"WTF_CSRF_ENABLED":False,"SQLALCHEMY_DATABASE_URI":"sqlite:///:memory:"})
    with app.app_context():
        db.create_all(); yield app; db.session.remove(); db.drop_all()

@pytest.fixture
def client(app): return app.test_client()

def register(client,name,email,role):
    return client.post('/auth/register',data={"name":name,"email":email,"password":"password123","role":role},follow_redirects=True)

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
    with app.app_context(): assert Request.query.count()==1

def test_api_rejects_negative_quantity(client):
    register(client,"Donante","api@test.test","donante")
    response=client.post('/api/alimentos',json={"name":"Fresas","category":"Frutas","quantity":-2,"unit":"kg","expiry_date":(date.today()+timedelta(days=2)).isoformat()})
    assert response.status_code==400

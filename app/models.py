from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db, login_manager

class User(UserMixin, db.Model):
    __tablename__ = "usuarios"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(180), unique=True, nullable=False, index=True)
    dni = db.Column(db.String(8), unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="beneficiario")
    department = db.Column(db.String(80), default="")
    province = db.Column(db.String(80), default="")
    district = db.Column(db.String(80), default="")
    business = db.Column(db.String(160), default="")
    is_demo = db.Column(db.Boolean, default=False, nullable=False)
    is_verified = db.Column(db.Boolean, default=False, nullable=False)
    supabase_uid = db.Column(db.String(64), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    def set_password(self, value): self.password_hash = generate_password_hash(value)
    def check_password(self, value): return check_password_hash(self.password_hash, value)

class Food(db.Model):
    __tablename__ = "alimentos"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(140), nullable=False)
    description = db.Column(db.Text, default="")
    category = db.Column(db.String(60), nullable=False, index=True)
    quantity = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(20), nullable=False)
    published_at = db.Column(db.DateTime, default=datetime.utcnow)
    available_date = db.Column(db.Date, nullable=False)
    expiry_date = db.Column(db.Date, nullable=False)
    department = db.Column(db.String(80), default="", index=True)
    province = db.Column(db.String(80), default="")
    district = db.Column(db.String(80), default="")
    address = db.Column(db.String(240), default="")
    storage = db.Column(db.String(240), default="")
    status = db.Column(db.String(30), default="Disponible", index=True)
    donor_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    donor = db.relationship("User", backref="foods")
    price_reference = db.Column(db.Float)

class Request(db.Model):
    __tablename__ = "solicitudes"
    id = db.Column(db.Integer, primary_key=True)
    food_id = db.Column(db.Integer, db.ForeignKey("alimentos.id"), nullable=False)
    beneficiary_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(30), default="Pendiente", index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    food = db.relationship("Food", backref="requests")
    beneficiary = db.relationship("User", backref="requests")

class Conversation(db.Model):
    __tablename__ = "conversaciones"
    id = db.Column(db.Integer, primary_key=True)
    donor_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False, index=True)
    beneficiary_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False, index=True)
    food_id = db.Column(db.Integer, db.ForeignKey("alimentos.id"), nullable=False, index=True)
    request_id = db.Column(db.Integer, db.ForeignKey("solicitudes.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    status = db.Column(db.String(20), default="activa", nullable=False)
    donor = db.relationship("User", foreign_keys=[donor_id])
    beneficiary = db.relationship("User", foreign_keys=[beneficiary_id])
    food = db.relationship("Food")
    request = db.relationship("Request")
    messages = db.relationship("Message", back_populates="conversation", cascade="all, delete-orphan", order_by="Message.created_at")
    __table_args__ = (db.UniqueConstraint("donor_id", "beneficiary_id", "food_id", name="uq_conversation_participants_food"),)

class Message(db.Model):
    __tablename__ = "mensajes"
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey("conversaciones.id", ondelete="CASCADE"), nullable=False, index=True)
    sender_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False, index=True)
    content = db.Column(db.String(2000), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    is_read = db.Column(db.Boolean, default=False, nullable=False, index=True)
    sender = db.relationship("User")
    conversation = db.relationship("Conversation", back_populates="messages")

class Alert(db.Model):
    __tablename__ = "alertas"
    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(60), nullable=False)
    message = db.Column(db.String(300), nullable=False)
    priority = db.Column(db.String(20), default="media")
    food_id = db.Column(db.Integer, db.ForeignKey("alimentos.id"))
    user_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    read = db.Column(db.Boolean, default=False)
    dedupe_key = db.Column(db.String(220), unique=True)

class ExternalSync(db.Model):
    __tablename__ = "sincronizaciones"
    id = db.Column(db.Integer, primary_key=True)
    source = db.Column(db.String(160), nullable=False)
    status = db.Column(db.String(30), nullable=False)
    summary = db.Column(db.Text, default="")
    queried_at = db.Column(db.DateTime, default=datetime.utcnow)

class ExternalData(db.Model):
    __tablename__ = "datos_externos"
    id = db.Column(db.Integer, primary_key=True)
    source = db.Column(db.String(160), nullable=False)
    external_id = db.Column(db.String(200), nullable=False)
    title = db.Column(db.String(240), nullable=False)
    url = db.Column(db.String(500), default="")
    metadata_json = db.Column(db.Text, default="{}")
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint("source", "external_id"),)

class Activity(db.Model):
    __tablename__ = "registros_actividad"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))
    action = db.Column(db.String(120), nullable=False)
    details = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id): return db.session.get(User, int(user_id))

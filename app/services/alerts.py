from datetime import date, timedelta
from app import db
from app.models import Food, Alert, Request

def generate_alerts():
    today = date.today()
    for food in Food.query.filter(Food.status.in_(["Disponible", "Parcialmente disponible", "Reservado"])).all():
        days = (food.expiry_date - today).days
        if 0 <= days <= 3:
            key = f"expiry:{food.id}:{food.expiry_date.isoformat()}"
            if not Alert.query.filter_by(dedupe_key=key).first():
                db.session.add(Alert(kind="Vencimiento", message=f"{food.name} vence en {days} día(s).", priority="alta" if days <= 1 else "media", food_id=food.id, user_id=food.donor_id, dedupe_key=key))
    for req in Request.query.filter_by(status="Pendiente").all():
        key = f"pending:{req.id}"
        if not Alert.query.filter_by(dedupe_key=key).first():
            db.session.add(Alert(kind="Solicitud pendiente", message=f"Solicitud #{req.id} espera aprobación.", priority="media", food_id=req.food_id, user_id=req.food.donor_id, dedupe_key=key))
    db.session.commit()

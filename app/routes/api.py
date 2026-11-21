from datetime import date, datetime
from math import isfinite
from flask import Blueprint, request, jsonify, abort
from flask_login import login_required, current_user
from sqlalchemy import or_
from app import db
from app.models import Food, Request, Alert, User, Conversation, Message
from app.services.integrations import sync_open_data
from app.services.inventory import (
    CATEGORIES, UNITS, InventoryConflict, exceeds_quantity, lock_food,
    reserved_quantities, reserved_quantity, update_stock_status, validate_inventory_change,
)

bp = Blueprint("api", __name__)

def conversation_for_user(conversation_id):
    conversation = db.get_or_404(Conversation, conversation_id)
    if current_user.id not in (conversation.donor_id, conversation.beneficiary_id):
        abort(403)
    return conversation

def message_json(message):
    return {"id": message.id, "conversation_id": message.conversation_id,
            "sender_id": message.sender_id, "sender_name": message.sender.name,
            "content": message.content, "created_at": message.created_at.isoformat() + "Z",
            "is_read": message.is_read}

def conversation_json(conversation):
    contact = conversation.beneficiary if current_user.id == conversation.donor_id else conversation.donor
    last = Message.query.filter_by(conversation_id=conversation.id).order_by(Message.created_at.desc(), Message.id.desc()).first()
    unread = Message.query.filter_by(conversation_id=conversation.id, is_read=False).filter(Message.sender_id != current_user.id).count()
    return {"id": conversation.id, "food_id": conversation.food_id, "food_name": conversation.food.name,
            "contact": {"id": contact.id, "name": contact.name, "role": contact.role},
            "request_id": conversation.request_id, "unread_count": unread,
            "last_message": message_json(last) if last else None,
            "updated_at": conversation.updated_at.isoformat() + "Z"}

@bp.get("/conversations/unread-count")
@login_required
def conversations_unread_count():
    ids = db.session.query(Conversation.id).filter(or_(Conversation.donor_id == current_user.id, Conversation.beneficiary_id == current_user.id))
    count = Message.query.filter(Message.conversation_id.in_(ids), Message.sender_id != current_user.id, Message.is_read.is_(False)).count()
    return jsonify(count=count)

@bp.get("/conversations")
@login_required
def conversations_list():
    query = Conversation.query.filter(or_(Conversation.donor_id == current_user.id, Conversation.beneficiary_id == current_user.id))
    items = query.order_by(Conversation.updated_at.desc(), Conversation.id.desc()).all()
    return jsonify([conversation_json(item) for item in items])

@bp.post("/conversations")
@login_required
def conversation_create():
    data = request.get_json(silent=True)
    if not isinstance(data, dict): return jsonify(error="Datos inválidos"), 400
    if current_user.role != "beneficiario": abort(403)
    try: food_id = int(data.get("food_id"))
    except (TypeError, ValueError): return jsonify(error="Alimento inválido"), 400
    food = db.session.get(Food, food_id)
    if not food: return jsonify(error="Alimento no encontrado"), 404
    if food.donor_id == current_user.id: abort(403)
    req = None
    if data.get("request_id") is not None:
        try: req = db.session.get(Request, int(data["request_id"]))
        except (TypeError, ValueError): req = None
        if not req or req.food_id != food.id or req.beneficiary_id != current_user.id:
            return jsonify(error="Solicitud inválida"), 400
    conversation = Conversation.query.filter_by(donor_id=food.donor_id, beneficiary_id=current_user.id, food_id=food.id).first()
    if conversation is None:
        conversation = Conversation(donor_id=food.donor_id, beneficiary_id=current_user.id, food_id=food.id, request_id=req.id if req else None)
        db.session.add(conversation)
        db.session.commit()
    elif req and conversation.request_id is None:
        conversation.request_id = req.id
        db.session.commit()
    return jsonify(conversation_json(conversation)), 201

@bp.get("/conversations/<int:conversation_id>/messages")
@login_required
def conversation_messages(conversation_id):
    conversation = conversation_for_user(conversation_id)
    messages = Message.query.filter_by(conversation_id=conversation.id).order_by(Message.created_at, Message.id).all()
    changed = False
    for message in messages:
        if message.sender_id != current_user.id and not message.is_read:
            message.is_read = True; changed = True
    if changed: db.session.commit()
    return jsonify([message_json(item) for item in messages])

@bp.post("/conversations/<int:conversation_id>/messages")
@login_required
def conversation_send_message(conversation_id):
    conversation = conversation_for_user(conversation_id)
    data = request.get_json(silent=True)
    if not isinstance(data, dict): return jsonify(error="Datos inválidos"), 400
    content = data.get("content")
    if not isinstance(content, str) or not content.strip(): return jsonify(error="El mensaje no puede estar vacío"), 400
    content = content.strip()
    if len(content) > 2000: return jsonify(error="El mensaje supera los 2000 caracteres"), 400
    message = Message(conversation_id=conversation.id, sender_id=current_user.id, content=content)
    conversation.updated_at = datetime.utcnow()
    db.session.add(message); db.session.commit()
    return jsonify(message_json(message)), 201

@bp.patch("/messages/<int:message_id>/read")
@login_required
def message_mark_read(message_id):
    message = db.get_or_404(Message, message_id)
    conversation_for_user(message.conversation_id)
    if message.sender_id != current_user.id and not message.is_read:
        message.is_read = True; db.session.commit()
    return jsonify(ok=True)

@bp.get("/alimentos")
def foods():
    today=date.today()
    q=Food.query.filter(Food.status.in_(["Disponible", "Parcialmente disponible"]),Food.available_date<=today,Food.expiry_date>=today)
    if request.args.get("category"): q=q.filter_by(category=request.args["category"])
    if request.args.get("district"): q=q.filter(Food.district.ilike(f"%{request.args['district']}%"))
    if request.args.get("q"): q=q.filter(Food.name.ilike(f"%{request.args['q']}%"))
    items=q.all()
    reserved = reserved_quantities([item.id for item in items])
    return jsonify([{ "id":f.id,"name":f.name,"category":f.category,"quantity":f.quantity,"available_quantity":max(0,f.quantity-reserved.get(f.id,0)),"unit":f.unit,"status":f.status,"district":f.district,"expiry_date":f.expiry_date.isoformat() } for f in items])

@bp.get("/alimentos/<int:item_id>")
def food_detail(item_id):
    f=db.get_or_404(Food,item_id)
    reserved = reserved_quantity(f.id)
    return jsonify({"id":f.id,"name":f.name,"description":f.description,"category":f.category,"quantity":f.quantity,"available_quantity":max(0,f.quantity-reserved),"unit":f.unit,"status":f.status,"department":f.department,"district":f.district,"available_date":f.available_date.isoformat(),"expiry_date":f.expiry_date.isoformat()})

@bp.post("/alimentos")
@login_required
def food_create():
    if current_user.role not in ("donante","administrador"): abort(403)
    data=request.get_json(silent=True) or {}
    if not isinstance(data,dict):return jsonify(error="Datos inválidos"),400
    try:
        qty=float(data["quantity"]); expiry=date.fromisoformat(data["expiry_date"]); available=date.fromisoformat(data.get("available_date",date.today().isoformat()))
        if not isinstance(data["name"],str):raise ValueError()
        name=data["name"].strip(); category=data["category"]; unit=data["unit"]
        if not name or category not in CATEGORIES or unit not in UNITS or not isfinite(qty) or qty<=0 or expiry<date.today() or available>expiry: raise ValueError()
        f=Food(name=name,category=category,quantity=qty,unit=unit,expiry_date=expiry,available_date=available,donor_id=current_user.id,department=current_user.department,district=data.get("district",""),address=data.get("address",""),description=data.get("description",""))
        db.session.add(f);db.session.commit();return jsonify(id=f.id),201
    except (KeyError,ValueError,TypeError): return jsonify(error="Datos inválidos"),400

@bp.put("/alimentos/<int:item_id>")
@login_required
def food_update(item_id):
    food = db.get_or_404(Food, item_id)
    if food.donor_id != current_user.id and current_user.role != "administrador":
        abort(403)
    data = request.get_json(silent=True)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return jsonify(error="Datos inválidos"), 400

    lock_food(food)
    reserved = reserved_quantity(food.id)
    if "quantity" in data:
        try:
            data["quantity"] = float(data["quantity"])
        except (TypeError, ValueError):
            return jsonify(error="Cantidad inválida"), 400
        if not isfinite(data["quantity"]) or data["quantity"] <= 0:
            return jsonify(error="Cantidad inválida"), 400
    if "category" in data and data["category"] not in CATEGORIES:
        return jsonify(error="Categoría inválida"), 400
    if "unit" in data and data["unit"] not in UNITS:
        return jsonify(error="Unidad inválida"), 400
    if "status" in data and data["status"] not in ("Disponible", "Parcialmente disponible", "Reservado", "Agotado", "Cancelado"):
        return jsonify(error="Estado inválido"), 400
    try:
        validate_inventory_change(
            food, reserved, quantity=data.get("quantity", food.quantity),
            unit=data.get("unit", food.unit), status=data.get("status", food.status),
        )
    except InventoryConflict as error:
        return jsonify(error=str(error)), 409

    for field in ("name", "description", "category", "quantity", "unit", "district", "address", "storage", "status"):
        if field in data:
            setattr(food, field, data[field])
    if reserved or ("quantity" in data and "status" not in data):
        update_stock_status(food, reserved)
    db.session.commit()
    return jsonify(ok=True)


@bp.delete("/alimentos/<int:item_id>")
@login_required
def food_delete(item_id):
    food = db.get_or_404(Food, item_id)
    if food.donor_id != current_user.id and current_user.role != "administrador":
        abort(403)
    lock_food(food)
    try:
        validate_inventory_change(
            food, reserved_quantity(food.id), quantity=food.quantity,
            unit=food.unit, status="Cancelado",
        )
    except InventoryConflict as error:
        return jsonify(error=str(error)), 409
    food.status = "Cancelado"
    db.session.commit()
    return jsonify(ok=True)


@bp.get("/solicitudes")
@login_required
def requests_list():
    query=(Request.query if current_user.role=="administrador" else
           Request.query.join(Food).filter(Food.donor_id==current_user.id) if current_user.role=="donante" else
           Request.query.filter_by(beneficiary_id=current_user.id))
    return jsonify([{"id":r.id,"food":r.food.name,"quantity":r.quantity,"status":r.status,"created_at":r.created_at.isoformat()} for r in query.all()])

@bp.post("/solicitudes")
@login_required
def request_create():
    data=request.get_json(silent=True) or {}
    if not isinstance(data,dict):return jsonify(error="Datos inválidos"),400
    f=db.session.get(Food,data.get("food_id"))
    if not f:return jsonify(error="Alimento no encontrado"),404
    if current_user.role not in ("beneficiario", "administrador") or current_user.id == f.donor_id: abort(403)
    lock_food(f)
    if f.status not in ("Disponible", "Parcialmente disponible") or f.available_date > date.today() or f.expiry_date < date.today():
        return jsonify(error="Alimento no disponible"),409
    try:qty=float(data.get("quantity",0))
    except (ValueError,TypeError):qty=0
    reserved = reserved_quantity(f.id)
    if not isfinite(qty) or qty<=0 or exceeds_quantity(qty + reserved, f.quantity):return jsonify(error="Cantidad inválida o supera la disponibilidad"),400
    r=Request(food_id=f.id,beneficiary_id=current_user.id,quantity=qty);db.session.add(r);db.session.commit();return jsonify(id=r.id,status=r.status),201

@bp.put("/solicitudes/<int:req_id>/estado")
@login_required
def request_status(req_id):
    r=db.get_or_404(Request,req_id)
    food = r.food
    is_donor = food.donor_id == current_user.id or current_user.role == "administrador"
    is_beneficiary = r.beneficiary_id == current_user.id
    data=request.get_json(silent=True) or {}
    if not isinstance(data,dict):return jsonify(error="Datos inválidos"),400
    status=data.get("status")
    if status in ("Aceptada","Rechazada","En coordinación") and not is_donor: abort(403)
    if status == "Entregada" and not is_donor: abort(403)
    if status == "Recibida" and not is_beneficiary: abort(403)
    if status not in ("Aceptada","Rechazada","En coordinación","Entregada","Recibida"):return jsonify(error="Estado inválido"),400
    lock_food(food)
    db.session.refresh(r)
    if status in ("Aceptada", "En coordinación") and r.status == "Pendiente":
        reserved = reserved_quantity(food.id)
        if exceeds_quantity(reserved + r.quantity, food.quantity):return jsonify(error="Cantidad disponible insuficiente"),409
        if r.food.status not in ("Disponible","Parcialmente disponible") or r.food.available_date > date.today() or r.food.expiry_date < date.today():return jsonify(error="Alimento no disponible"),409
    elif status == "Rechazada" and r.status != "Pendiente": return jsonify(error="La solicitud ya fue procesada"),409
    elif status == "Entregada":
        if r.status not in ("Aceptada","En coordinación"):return jsonify(error="Solo pueden entregarse solicitudes aceptadas"),409
        food.quantity = max(0, food.quantity - r.quantity)
    elif status == "Recibida" and r.status != "Entregada": return jsonify(error="La solicitud aún no figura como entregada"),409
    elif status in ("Aceptada","En coordinación") and r.status != "Pendiente": return jsonify(error="La solicitud ya fue procesada"),409
    r.status = status
    if status in ("Aceptada", "En coordinación", "Entregada"):
        update_stock_status(food, reserved_quantity(food.id))
    db.session.commit();return jsonify(id=r.id,status=r.status)

@bp.get("/alertas")
@login_required
def alerts_list():
    q=Alert.query if current_user.role=="administrador" else Alert.query.filter_by(user_id=current_user.id)
    return jsonify([{"id":a.id,"kind":a.kind,"message":a.message,"priority":a.priority,"read":a.read} for a in q.all()])

@bp.put("/alertas/<int:alert_id>/leida")
@login_required
def alert_read(alert_id):
    a=db.get_or_404(Alert,alert_id)
    if a.user_id!=current_user.id and current_user.role!="administrador":abort(403)
    a.read=True;db.session.commit();return jsonify(ok=True)

@bp.get("/reportes/dashboard")
@login_required
def dashboard_stats():
    today=date.today()
    return jsonify({"usuarios":User.query.count(),"alimentos":Food.query.count(),"disponibles":Food.query.filter(Food.status.in_(["Disponible","Parcialmente disponible"]),Food.available_date<=today,Food.expiry_date>=today).count(),"solicitudes":Request.query.count(),"recibidas":Request.query.filter_by(status="Recibida").count()})

@bp.get("/fuentes")
@login_required
def sources():
    from app.models import ExternalSync
    return jsonify([{"source":s.source,"status":s.status,"summary":s.summary,"queried_at":s.queried_at.isoformat()} for s in ExternalSync.query.order_by(ExternalSync.queried_at.desc()).limit(20)])

@bp.post("/fuentes/sincronizar")
@login_required
def sync():
    if current_user.role!="administrador":abort(403)
    data=request.get_json(silent=True) or {}
    if not isinstance(data,dict):return jsonify(error="Datos inválidos"),400
    return jsonify(sync_open_data(data.get("q","alimentos")))

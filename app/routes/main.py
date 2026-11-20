from datetime import date
from math import isfinite
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, send_file
from flask_login import login_required, current_user
from sqlalchemy import func, or_
from app import db
from app.models import User, Food, Request, Alert, ExternalData, ExternalSync, Activity
from app.services.alerts import generate_alerts
from app.services.integrations import sync_open_data

bp = Blueprint("main", __name__)
CATEGORIES = ["Frutas", "Verduras", "Panadería", "Lácteos", "Carnes", "Productos envasados", "Bebidas", "Otros"]

def log(action, details=""):
    db.session.add(Activity(user_id=current_user.id if current_user.is_authenticated else None, action=action, details=details)); db.session.commit()

def reserved_quantities(food_ids):
    if not food_ids: return {}
    rows = db.session.query(Request.food_id, func.sum(Request.quantity)).filter(
        Request.food_id.in_(food_ids), Request.status.in_(["Aceptada", "En coordinación"])
    ).group_by(Request.food_id).all()
    return {food_id: quantity for food_id, quantity in rows}

@bp.get("/")
def index():
    today = date.today()
    foods = Food.query.filter(Food.status.in_(["Disponible", "Parcialmente disponible"]), Food.available_date <= today, Food.expiry_date >= today).order_by(Food.published_at.desc()).limit(6).all()
    reserved = reserved_quantities([food.id for food in foods])
    available = {food.id: max(0, food.quantity - reserved.get(food.id, 0)) for food in foods}
    delivered = Request.query.filter(Request.status.in_(["Entregada", "Recibida"]))
    recovered_kg = db.session.query(func.coalesce(func.sum(Request.quantity), 0)).join(Food).filter(
        Request.status.in_(["Entregada", "Recibida"]), Food.unit == "kg"
    ).scalar()
    impact = {
        "kilograms": float(recovered_kg or 0),
        "donations": delivered.count(),
        "beneficiaries": db.session.query(func.count(func.distinct(Request.beneficiary_id))).filter(
            Request.status.in_(["Entregada", "Recibida"])
        ).scalar() or 0,
        "donors": User.query.filter_by(role="donante").count(),
        "foods": Food.query.count(),
    }
    return render_template("index.html", foods=foods, available=available, impact=impact)

@bp.get("/dashboard")
@login_required
def dashboard():
    foods = (Food.query.order_by(Food.published_at.desc()).all() if current_user.role == "administrador" else
             Food.query.filter_by(donor_id=current_user.id).order_by(Food.published_at.desc()).all()
             if current_user.role == "donante" else [])
    recommended = []
    recommended_available = {}
    if current_user.role == "beneficiario":
        today = date.today()
        recommended = Food.query.filter(Food.status.in_(["Disponible", "Parcialmente disponible"]), Food.available_date <= today, Food.expiry_date >= today).order_by(Food.expiry_date).limit(3).all()
        recommended_reserved = reserved_quantities([food.id for food in recommended])
        recommended_available = {food.id: max(0, food.quantity - recommended_reserved.get(food.id, 0)) for food in recommended}
    received = Request.query.filter_by(beneficiary_id=current_user.id).all()
    requests = (Request.query.all() if current_user.role == "administrador" else
                Request.query.join(Food).filter(Food.donor_id == current_user.id).all()
                if current_user.role == "donante" else received)
    today = date.today()
    stats = {"users": User.query.count(), "donors": User.query.filter_by(role="donante").count(), "beneficiaries": User.query.filter_by(role="beneficiario").count(), "foods": Food.query.count(), "available": Food.query.filter(Food.status.in_(["Disponible", "Parcialmente disponible"]), Food.available_date <= today, Food.expiry_date >= today).count(), "requests": Request.query.count(), "completed": Request.query.filter_by(status="Recibida").count()}
    alerts = Alert.query.filter((Alert.user_id == current_user.id) | (current_user.role == "administrador")).order_by(Alert.created_at.desc()).limit(8).all()
    delivered_query = Request.query.join(Food).filter(Request.status.in_(["Entregada", "Recibida"]))
    if current_user.role == "donante": delivered_query = delivered_query.filter(Food.donor_id == current_user.id)
    elif current_user.role == "beneficiario": delivered_query = delivered_query.filter(Request.beneficiary_id == current_user.id)
    delivered = delivered_query.all()
    delivered_by_unit = {}
    for item in delivered:
        delivered_by_unit[item.food.unit] = delivered_by_unit.get(item.food.unit, 0) + item.quantity
    stats.update(deliveries=len(delivered), delivered_by_unit=delivered_by_unit)
    if current_user.role == "donante":
        stats.update(my_foods=len(foods), my_available=Food.query.filter_by(donor_id=current_user.id).filter(Food.status.in_(["Disponible", "Parcialmente disponible"]), Food.available_date <= today, Food.expiry_date >= today).count(), my_pending=Request.query.join(Food).filter(Food.donor_id == current_user.id, Request.status == "Pendiente").count(), my_deliveries=len(delivered))
    elif current_user.role == "beneficiario":
        stats.update(my_requests=len(received), my_pending=sum(item.status == "Pendiente" for item in received), my_accepted=sum(item.status in ("Aceptada", "En coordinación") for item in received), my_received=sum(item.status in ("Entregada", "Recibida") for item in received))
    return render_template("dashboard.html", foods=foods, requests=requests, stats=stats, alerts=alerts, categories=CATEGORIES, recommended=recommended, recommended_available=recommended_available)

@bp.get("/people")
@login_required
def people():
    if current_user.role != "administrador": abort(403)
    role = request.args.get("role", "")
    query = User.query
    if role in ("donante", "beneficiario", "administrador"):
        query = query.filter_by(role=role)
    people = query.order_by(User.created_at.desc()).all()
    return render_template("people.html", people=people, role=role,
        counts={key: User.query.filter_by(role=key).count() for key in ("donante", "beneficiario", "administrador")})

@bp.get("/foods")
def catalog():
    today = date.today()
    q = Food.query.filter(Food.status.in_(["Disponible", "Parcialmente disponible"]), Food.available_date <= today, Food.expiry_date >= today)
    search = request.args.get("q", "").strip(); category = request.args.get("category", "")
    availability = request.args.get("availability", "")
    location = request.args.get("location", request.args.get("district", "")).strip()
    if search: q = q.filter(Food.name.ilike(f"%{search}%"))
    if category: q = q.filter_by(category=category)
    if availability in ("Disponible", "Parcialmente disponible"):
        q = q.filter_by(status=availability)
    if location:
        q = q.filter(or_(Food.district.ilike(f"%{location}%"), Food.province.ilike(f"%{location}%"), Food.department.ilike(f"%{location}%")))
    foods = q.order_by(Food.expiry_date).all()
    reserved = reserved_quantities([food.id for food in foods])
    available = {food.id: max(0, food.quantity - reserved.get(food.id, 0)) for food in foods}
    return render_template("catalog.html", foods=foods, categories=CATEGORIES, available=available, availability=availability, location=location)

@bp.route("/foods/new", methods=["GET", "POST"])
@login_required
def food_new():
    if current_user.role not in ("donante", "administrador"): abort(403)
    if request.method == "POST":
        try:
            qty = float(request.form["quantity"]); available = date.fromisoformat(request.form["available_date"]); expiry = date.fromisoformat(request.form["expiry_date"])
            name = request.form["name"].strip()
            category, unit = request.form["category"], request.form["unit"]
            if not name or category not in CATEGORIES or unit not in ("kg", "gramos", "unidades", "litros", "paquetes") or not isfinite(qty) or qty <= 0 or expiry < date.today() or available > expiry: raise ValueError("Cantidad o fechas no válidas.")
            food = Food(name=name, description=request.form.get("description", "").strip(), category=category, quantity=qty, unit=unit, available_date=available, expiry_date=expiry, department=current_user.department, province=request.form.get("province", "").strip(), district=request.form.get("district", "").strip(), address=request.form.get("address", "").strip(), storage=request.form.get("storage", "").strip(), donor_id=current_user.id)
            db.session.add(food); db.session.commit(); log("alimento_creado", food.name); flash("Publicación guardada.", "success"); return redirect(url_for("main.dashboard"))
        except (ValueError, KeyError): flash("Revisa cantidad y fechas. No se aceptan cantidades negativas ni alimentos vencidos.", "error")
    return render_template("food_form.html", categories=CATEGORIES, today=date.today().isoformat())

@bp.post("/foods/<int:food_id>/delete")
@login_required
def food_delete(food_id):
    food = db.get_or_404(Food, food_id)
    if food.donor_id != current_user.id and current_user.role != "administrador": abort(403)
    food.status = "Cancelado"; db.session.commit(); log("alimento_cancelado", food.name); return redirect(url_for("main.dashboard"))

@bp.post("/foods/<int:food_id>/request")
@login_required
def request_food(food_id):
    food = db.get_or_404(Food, food_id)
    try: quantity = float(request.form.get("quantity", "0"))
    except (TypeError, ValueError): quantity = 0
    if current_user.role not in ("beneficiario", "administrador") or food.donor_id == current_user.id: abort(403)
    if food.status not in ("Disponible", "Parcialmente disponible") or food.available_date > date.today() or food.expiry_date < date.today():
        flash("Este alimento no está disponible para solicitudes.", "error")
        return redirect(url_for("main.catalog"))
    reserved = db.session.query(func.coalesce(func.sum(Request.quantity), 0)).filter(Request.food_id == food.id, Request.status.in_(["Aceptada", "En coordinación"])).scalar()
    if not isfinite(quantity) or quantity <= 0 or quantity + reserved > food.quantity: flash("La cantidad supera la disponibilidad.", "error")
    else:
        db.session.add(Request(food_id=food.id, beneficiary_id=current_user.id, quantity=quantity)); db.session.commit(); log("solicitud_creada", str(food.id)); flash("Solicitud enviada al donante.", "success")
    return redirect(url_for("main.catalog"))

@bp.post("/requests/<int:req_id>/<action>")
@login_required
def request_action(req_id, action):
    req = db.get_or_404(Request, req_id)
    if req.food.donor_id != current_user.id and current_user.role != "administrador": abort(403)
    if action not in ("accept", "reject", "deliver"): abort(400)
    if action == "accept":
        if req.status != "Pendiente": abort(400)
        if req.food.status not in ("Disponible", "Parcialmente disponible") or req.food.available_date > date.today() or req.food.expiry_date < date.today():
            flash("El alimento ya no está disponible.", "error")
            return redirect(url_for("main.dashboard"))
        reserved = db.session.query(func.coalesce(func.sum(Request.quantity), 0)).filter(Request.food_id == req.food_id, Request.status.in_(["Aceptada", "En coordinación"])).scalar()
        if reserved + req.quantity > req.food.quantity: flash("Ya no hay cantidad suficiente.", "error")
        else: req.status = "Aceptada"; req.food.status = "Reservado" if reserved + req.quantity == req.food.quantity else "Parcialmente disponible"
    elif action == "reject":
        if req.status != "Pendiente": abort(400)
        req.status = "Rechazada"
    else:
        if req.status not in ("Aceptada", "En coordinación"): abort(400)
        req.status = "Entregada"
        req.food.quantity = max(0, req.food.quantity - req.quantity)
        reserved_after = db.session.query(func.coalesce(func.sum(Request.quantity), 0)).filter(Request.food_id == req.food_id, Request.status.in_(["Aceptada", "En coordinación"])).scalar()
        if req.food.quantity == 0: req.food.status = "Agotado"
        elif reserved_after >= req.food.quantity: req.food.status = "Reservado"
        elif reserved_after > 0: req.food.status = "Parcialmente disponible"
        else: req.food.status = "Disponible"
    db.session.commit(); log("solicitud_actualizada", req.status); return redirect(url_for("main.dashboard"))

@bp.post("/requests/<int:req_id>/received")
@login_required
def request_received(req_id):
    req = db.get_or_404(Request, req_id)
    if req.beneficiary_id != current_user.id or req.status != "Entregada": abort(403)
    req.status = "Recibida"; db.session.commit(); log("recepcion_confirmada", str(req.id)); return redirect(url_for("main.dashboard"))

@bp.get("/alerts")
@login_required
def alerts():
    generate_alerts()
    items = Alert.query.filter((Alert.user_id == current_user.id) | (current_user.role == "administrador")).order_by(Alert.created_at.desc()).all()
    return render_template("alerts.html", alerts=items)

@bp.post("/alerts/<int:alert_id>/read")
@login_required
def alert_read(alert_id):
    item = db.get_or_404(Alert, alert_id)
    if item.user_id != current_user.id and current_user.role != "administrador": abort(403)
    item.read = True; db.session.commit(); return redirect(url_for("main.alerts"))

@bp.route("/intelligence", methods=["GET", "POST"])
@login_required
def intelligence():
    if current_user.role != "administrador": abort(403)
    if request.method == "POST":
        result = sync_open_data(request.form.get("q", "alimentos")); flash(f"Consulta finalizada: {result}", "success" if result["ok"] else "error")
    return render_template("intelligence.html", data=ExternalData.query.order_by(ExternalData.updated_at.desc()).limit(50).all(), syncs=ExternalSync.query.order_by(ExternalSync.queried_at.desc()).limit(10).all())

@bp.get("/reports")
@login_required
def reports():
    if current_user.role == "administrador":
        foods = Food.query.all()
    elif current_user.role == "donante":
        foods = Food.query.filter_by(donor_id=current_user.id).all()
    else:
        foods = Food.query.join(Request).filter(Request.beneficiary_id == current_user.id).distinct().all()
    totals = db.session.query(Food.unit, func.sum(Food.quantity)).filter(Food.id.in_([f.id for f in foods])).group_by(Food.unit).all()
    delivered = Request.query.join(Food).filter(Request.status.in_(["Entregada", "Recibida"]))
    if current_user.role == "donante": delivered = delivered.filter(Food.donor_id == current_user.id)
    elif current_user.role == "beneficiario": delivered = delivered.filter(Request.beneficiary_id == current_user.id)
    delivery_totals = {}
    for item in delivered.all():
        delivery_totals[item.food.unit] = delivery_totals.get(item.food.unit, 0) + item.quantity
    return render_template("reports.html", foods=foods, totals=totals, delivery_totals=delivery_totals)

@bp.get("/reports/export.xlsx")
@login_required
def export_xlsx():
    import pandas as pd
    from io import BytesIO
    foods = report_foods()
    rows = [{"Alimento":f.name,"Categoría":f.category,"Cantidad":f.quantity,"Unidad":f.unit,"Estado":f.status,"Distrito":f.district,"Vencimiento":f.expiry_date} for f in foods]
    out=BytesIO(); pd.DataFrame(rows).to_excel(out,index=False); out.seek(0)
    return send_file(out, as_attachment=True, download_name="reporte_alimentos.xlsx", mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@bp.get("/reports/export.pdf")
@login_required
def export_pdf():
    from io import BytesIO
    from reportlab.pdfgen import canvas
    out=BytesIO(); pdf=canvas.Canvas(out); pdf.setTitle("Desperdicio Cero - Reporte de alimentos"); pdf.setFont("Helvetica-Bold",14); pdf.drawString(50,800,"DESPERDICIO CERO - Reporte de alimentos")
    pdf.setFont("Helvetica",9); y=775
    for food in report_foods():
        if y < 45:
            pdf.showPage(); pdf.setFont("Helvetica-Bold",12); pdf.drawString(50,800,"DESPERDICIO CERO - Reporte de alimentos (continuación)"); pdf.setFont("Helvetica",9); y=775
        pdf.drawString(50,y,f"{food.name[:36]} | {food.category[:20]} | {food.quantity:g} {food.unit} | {food.status}"); y-=15
    pdf.save(); out.seek(0)
    return send_file(out,as_attachment=True,download_name="reporte_alimentos.pdf",mimetype="application/pdf")

def report_foods():
    if current_user.role == "administrador": return Food.query.order_by(Food.id).all()
    if current_user.role == "donante": return Food.query.filter_by(donor_id=current_user.id).order_by(Food.id).all()
    return Food.query.join(Request).filter(Request.beneficiary_id == current_user.id).distinct().order_by(Food.id).all()

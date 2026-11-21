from math import isclose

from sqlalchemy import update

from app import db
from app.models import Food, Request

CATEGORIES = ["Frutas", "Verduras", "Panadería", "Lácteos", "Carnes", "Productos envasados", "Bebidas", "Otros"]
UNITS = ("kg", "gramos", "unidades", "litros", "paquetes")
RESERVATION_STATUSES = ("Aceptada", "En coordinación")


class InventoryConflict(ValueError):
    pass


def lock_food(food):
    # A write locks the inventory before reading reservations, including on SQLite.
    db.session.execute(
        update(Food).where(Food.id == food.id).values(quantity=Food.quantity),
        execution_options={"synchronize_session": False},
    )
    db.session.refresh(food)


def reserved_quantities(food_ids):
    if not food_ids:
        return {}
    rows = db.session.query(Request.food_id, db.func.sum(Request.quantity)).filter(
        Request.food_id.in_(food_ids), Request.status.in_(RESERVATION_STATUSES)
    ).group_by(Request.food_id).all()
    return dict(rows)


def reserved_quantity(food_id):
    return reserved_quantities([food_id]).get(food_id, 0)


def exceeds_quantity(requested, available):
    return requested > available and not isclose(requested, available, rel_tol=0, abs_tol=1e-12)


def validate_inventory_change(food, reserved, *, quantity, unit, status):
    if exceeds_quantity(reserved, quantity):
        raise InventoryConflict(f"La cantidad no puede ser menor que la reserva de {reserved:g} {food.unit}.")
    if reserved and status in ("Cancelado", "Agotado"):
        raise InventoryConflict("Hay solicitudes con reserva. Registra sus entregas antes de cerrar la publicación.")
    if unit != food.unit and Request.query.filter_by(food_id=food.id).first() is not None:
        raise InventoryConflict("La unidad se conserva porque la publicación ya tiene solicitudes.")


def update_stock_status(food, reserved):
    if food.status == "Cancelado":
        return
    if food.quantity == 0:
        food.status = "Agotado"
    elif not reserved:
        food.status = "Disponible"
    elif not exceeds_quantity(food.quantity, reserved):
        food.status = "Reservado"
    else:
        food.status = "Parcialmente disponible"

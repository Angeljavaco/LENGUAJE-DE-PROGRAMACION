"""Carga cuentas y registros de demostración, claramente etiquetados como pruebas."""
from datetime import date, timedelta
from app import create_app, db
from app.models import User, Food, Request

app = create_app()

with app.app_context():
    if User.query.filter_by(is_demo=True).count():
        print("Los datos de demostración ya existen. No se añadieron duplicados.")
    else:
        admin = User(name="Administración Demo", email="admin@demo.local", role="administrador", is_demo=True)
        admin.set_password("DemoAdmin-2026!")
        db.session.add(admin)
        donors=[]; beneficiaries=[]
        for n in range(1,4):
            d=User(name=f"Donante Demo {n}",email=f"donante{n}@demo.local",role="donante",department="Lima",business=f"Negocio de prueba {n}",is_demo=True);d.set_password(f"DemoDonante{n}-2026!");donors.append(d)
            b=User(name=f"Beneficiario Demo {n}",email=f"beneficiario{n}@demo.local",role="beneficiario",department="Lima",is_demo=True);b.set_password(f"DemoBeneficiario{n}-2026!");beneficiaries.append(b)
        db.session.add_all(donors+beneficiaries);db.session.flush()
        foods=[]
        records=[("Plátanos maduros","Frutas",8,"kg"),("Pan del día","Panadería",20,"unidades"),("Leche pasteurizada","Lácteos",6,"litros"),("Tomates","Verduras",12,"kg"),("Avena envasada","Productos envasados",10,"paquetes"),("Naranjas","Frutas",15,"kg")]
        for i,(name,category,qty,unit) in enumerate(records):
            food=Food(name=f"[DEMO] {name}",description="Registro ficticio de demostración.",category=category,quantity=qty,unit=unit,available_date=date.today(),expiry_date=date.today()+timedelta(days=2+i),department="Lima",province="Lima",district="Miraflores" if i%2==0 else "Surquillo",address="Dirección de prueba",storage="Según etiqueta",donor=donors[i%3]);foods.append(food)
        db.session.add_all(foods);db.session.flush()
        for i,status in enumerate(["Pendiente","Aceptada","Recibida"]):
            db.session.add(Request(food=foods[i],beneficiary=beneficiaries[i],quantity=1,status=status))
        db.session.commit()
        print("Datos demo agregados. Admin demo: admin@demo.local / DemoAdmin-2026!")
        print("Cada donante: donanteN@demo.local / DemoDonanteN-2026!; cada beneficiario: beneficiarioN@demo.local / DemoBeneficiarioN-2026!")

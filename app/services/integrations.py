import requests
from datetime import datetime
from app import db
from app.models import ExternalData, ExternalSync

SOURCE = "Plataforma Nacional de Datos Abiertos del Perú (CKAN)"

def sync_open_data(query="alimentos OR producción agrícola"):
    url = "https://www.datosabiertos.gob.pe/api/3/action/package_search"
    try:
        response = requests.get(url, params={"q": query, "rows": 30}, timeout=15)
        response.raise_for_status()
        payload = response.json()
        if not payload.get("success"):
            raise ValueError("La API CKAN respondió sin éxito")
        results = payload.get("result", {}).get("results", [])
        for item in results:
            external_id = str(item.get("id") or item.get("name"))
            record = ExternalData.query.filter_by(source=SOURCE, external_id=external_id).first()
            if record is None:
                record = ExternalData(source=SOURCE, external_id=external_id, title=item.get("title", "Dataset sin título"))
                db.session.add(record)
            record.title = item.get("title", "Dataset sin título")
            record.url = item.get("url") or item.get("resources", [{}])[0].get("url", "")
            record.metadata_json = __import__("json").dumps({"notes": item.get("notes", ""), "organization": (item.get("organization") or {}).get("title"), "tags": [t.get("display_name") for t in item.get("tags", [])]}, ensure_ascii=False)
            record.updated_at = datetime.utcnow()
        db.session.add(ExternalSync(source=SOURCE, status="Correcta", summary=f"{len(results)} conjuntos consultados y almacenados."))
        db.session.commit()
        return {"ok": True, "count": len(results)}
    except Exception as exc:
        db.session.rollback()
        db.session.add(ExternalSync(source=SOURCE, status="Error", summary=str(exc)[:500]))
        db.session.commit()
        return {"ok": False, "error": str(exc)}

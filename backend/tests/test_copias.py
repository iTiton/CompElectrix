import sqlite3

from fastapi.testclient import TestClient

from app.main import app


def test_descargar_borrar_y_restaurar():
    with TestClient(app) as c:
        dom = c.post("/api/domicilios", json={"nombre": "Casa de la copia"}).json()["id"]
        c.post("/api/facturas", json={"domicilio_id": dom, "fecha_inicio": "2025-01-01", "fecha_fin": "2025-01-31", "kwh_p1": 10})

        r = c.get("/api/copia")
        assert r.status_code == 200
        assert "attachment" in r.headers["content-disposition"] and ".zip" in r.headers["content-disposition"]
        copia = r.content
        import io
        import zipfile

        with zipfile.ZipFile(io.BytesIO(copia)) as z:
            nombres = set(z.namelist())
            assert {"datos.sqlite", "LEEME.txt", "tablas/domicilios.csv", "tablas/facturas.csv"} <= nombres
            csv_dom = z.read("tablas/domicilios.csv").decode("utf-8-sig")
            assert csv_dom.splitlines()[0].startswith("nombre;") or "nombre" in csv_dom.splitlines()[0]
            assert "Casa de la copia" in csv_dom and ";3,45;" in csv_dom  # decimales con coma
            sqlite_suelto = z.read("datos.sqlite")

        # Se pierden los datos…
        assert c.delete(f"/api/domicilios/{dom}").status_code == 204
        assert not any(d["nombre"] == "Casa de la copia" for d in c.get("/api/domicilios").json())

        # …y se recuperan con la copia
        r = c.post("/api/copia/restaurar", content=copia, headers={"Content-Type": "application/octet-stream"})
        assert r.status_code == 200, r.text
        assert r.json()["contenido"]["domicilio"] >= 1
        domicilios = c.get("/api/domicilios").json()
        casa = next(d for d in domicilios if d["nombre"] == "Casa de la copia")
        assert casa["num_facturas"] == 1

        # El .sqlite suelto también vale para restaurar
        assert c.post("/api/copia/restaurar", content=sqlite_suelto).status_code == 200

        # Se guardó cómo estaba antes de restaurar, y se puede descargar
        auto = c.get("/api/copia/automaticas").json()
        assert auto and auto[0]["nombre"] == r.json()["copia_previa"]
        assert c.get(f"/api/copia/automaticas/{auto[0]['nombre']}").content.startswith(b"SQLite format 3")
        assert c.get("/api/copia/automaticas/..%2Fcompelectrix.db").status_code == 404


def test_rechaza_archivos_que_no_son_copias(tmp_path):
    with TestClient(app) as c:
        antes = len(c.get("/api/domicilios").json())
        r = c.post("/api/copia/restaurar", content=b"esto no es una base de datos")
        assert r.status_code == 422 and "no es una copia" in r.json()["detail"]

        otra = tmp_path / "otra.sqlite"
        with sqlite3.connect(otra) as con:
            con.execute("CREATE TABLE fotos (id INTEGER)")
        r = c.post("/api/copia/restaurar", content=otra.read_bytes())
        assert r.status_code == 422 and "no de CompElectrix" in r.json()["detail"]

        assert c.post("/api/copia/restaurar", content=b"").status_code == 422
        import io
        import zipfile

        malo = io.BytesIO()
        with zipfile.ZipFile(malo, "w") as z:
            z.writestr("fotos.txt", "hola")
        r = c.post("/api/copia/restaurar", content=malo.getvalue())
        assert r.status_code == 422 and "falta datos.sqlite" in r.json()["detail"]
        assert len(c.get("/api/domicilios").json()) == antes  # nada se ha tocado


def test_se_conservan_tres_copias_automaticas():
    with TestClient(app) as c:
        copia = c.get("/api/copia").content
        for _ in range(5):
            import time

            time.sleep(1.05)  # el nombre lleva segundos
            assert c.post("/api/copia/restaurar", content=copia).status_code == 200
        assert len(c.get("/api/copia/automaticas").json()) == 3
        assert c.get("/api/no-existe").status_code == 404

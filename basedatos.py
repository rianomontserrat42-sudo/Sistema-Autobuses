import sqlite3
from datetime import date
from pathlib import Path

DB = Path(__file__).with_name("autobus.db")
TOTAL_ASIENTOS = 30
ORIGEN = "Teposcolula"
# Cada ruta sale de ORIGEN; la última parada es el destino final
RUTAS = {
    "Tlaxiaco": [("Yolo", 30), ("San Miguel Grande", 35), ("San Martín", 40), ("Tlaxiaco", 45)],
    "Oaxaca": [("Nochixtlán", 60), ("Huitzo", 100), ("Desviación", 125), ("Oaxaca", 150)],
    "Tamazulapan": [("San Juan", 25), ("Desviación", 50), ("Tamazulapan", 80)],
}
RUTA_POR_DEFECTO = "Tlaxiaco"
CAMPOS_CORTE = {"vendido": "fecha de venta", "fecha": "fecha de viaje"}


def precio_parada(ruta, parada):
    """Precio de la parada en la ruta, o None si no existe."""
    return dict(RUTAS.get(ruta, [])).get(parada)


def parsear_destino(valor):
    """Convierte 'Ruta|Parada' en (ruta, parada, precio); None si no es válido."""
    ruta, _, parada = (valor or "").partition("|")
    precio = precio_parada(ruta, parada)
    return (ruta, parada, precio) if precio is not None else None


def conectar():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


def iniciar():
    with conectar() as con:
        con.execute(
            """CREATE TABLE IF NOT EXISTS boletos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                fecha TEXT NOT NULL,
                asiento INTEGER NOT NULL,
                destino TEXT,
                precio INTEGER,
                vendido TEXT,
                ruta TEXT,
                UNIQUE (fecha, ruta, asiento)
            )"""
        )
        columnas = {c["name"] for c in con.execute("PRAGMA table_info(boletos)")}
        for col, tipo in (("destino", "TEXT"), ("precio", "INTEGER"), ("vendido", "TEXT"), ("ruta", "TEXT")):
            if col not in columnas:
                con.execute(f"ALTER TABLE boletos ADD COLUMN {col} {tipo}")
        con.execute(
            "UPDATE boletos SET destino = ? WHERE destino IS NULL", (RUTA_POR_DEFECTO,)
        )
        con.execute(
            "UPDATE boletos SET precio = ? WHERE precio IS NULL",
            (precio_parada(RUTA_POR_DEFECTO, RUTA_POR_DEFECTO),),
        )
        con.execute(
            "UPDATE boletos SET vendido = ? WHERE vendido IS NULL", (date.today().isoformat(),)
        )
        # Boletos anteriores: Yolo pertenece a la ruta de Tlaxiaco; los demás usan su destino como ruta
        con.execute("UPDATE boletos SET ruta = 'Tlaxiaco' WHERE ruta IS NULL AND destino = 'Yolo'")
        con.execute("UPDATE boletos SET ruta = destino WHERE ruta IS NULL")
        _migrar_unicidad_por_ruta(con)


def _migrar_unicidad_por_ruta(con):
    """Cada ruta tiene su propio autobús: el asiento es único por fecha y ruta."""
    indices = [
        [c["name"] for c in con.execute(f"PRAGMA index_info('{i['name']}')")]
        for i in con.execute("PRAGMA index_list(boletos)")
        if i["unique"]
    ]
    if ["fecha", "ruta", "asiento"] in indices:
        return
    con.execute(
        """CREATE TABLE boletos_nueva (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            fecha TEXT NOT NULL,
            asiento INTEGER NOT NULL,
            destino TEXT,
            precio INTEGER,
            vendido TEXT,
            ruta TEXT,
            UNIQUE (fecha, ruta, asiento)
        )"""
    )
    con.execute(
        "INSERT INTO boletos_nueva (id, nombre, fecha, asiento, destino, precio, vendido, ruta)"
        " SELECT id, nombre, fecha, asiento, destino, precio, vendido, ruta FROM boletos"
    )
    con.execute("DROP TABLE boletos")
    con.execute("ALTER TABLE boletos_nueva RENAME TO boletos")


def asientos_ocupados(fecha, ruta, excluir_id=None):
    with conectar() as con:
        filas = con.execute(
            "SELECT asiento FROM boletos WHERE fecha = ? AND ruta = ? AND id IS NOT ?",
            (fecha, ruta, excluir_id),
        )
        return [f["asiento"] for f in filas]


def obtener(boleto_id):
    with conectar() as con:
        return con.execute("SELECT * FROM boletos WHERE id = ?", (boleto_id,)).fetchone()


def actualizar(boleto_id, nombre, fecha, asiento, ruta, destino, precio):
    """Devuelve False si el asiento ya está ocupado en esa fecha."""
    try:
        with conectar() as con:
            actual = con.execute(
                "SELECT ruta, destino, precio FROM boletos WHERE id = ?", (boleto_id,)
            ).fetchone()
            # Si el destino no cambia se conserva el precio con que se vendió
            if actual and (actual["ruta"], actual["destino"]) == (ruta, destino):
                precio = actual["precio"]
            con.execute(
                "UPDATE boletos SET nombre = ?, fecha = ?, asiento = ?, ruta = ?, destino = ?, precio = ?"
                " WHERE id = ?",
                (nombre, fecha, asiento, ruta, destino, precio, boleto_id),
            )
        return True
    except sqlite3.IntegrityError:
        return False


def borrar(boleto_id):
    with conectar() as con:
        con.execute("DELETE FROM boletos WHERE id = ?", (boleto_id,))


def vender(nombre, fecha, asiento, ruta, destino, precio):
    """Devuelve False si el asiento ya está ocupado en esa fecha."""
    try:
        with conectar() as con:
            con.execute(
                "INSERT INTO boletos (nombre, fecha, asiento, ruta, destino, precio, vendido)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (nombre, fecha, asiento, ruta, destino, precio, date.today().isoformat()),
            )
        return True
    except sqlite3.IntegrityError:
        return False


def listar():
    with conectar() as con:
        return con.execute(
            "SELECT id, nombre, fecha, asiento, ruta, destino, precio FROM boletos"
            " ORDER BY fecha, asiento"
        ).fetchall()


def corte(desde, hasta, campo="vendido"):
    """Resumen por ruta y total entre dos fechas (inclusive)."""
    if campo not in CAMPOS_CORTE:
        campo = "vendido"
    with conectar() as con:
        filas = con.execute(
            f"SELECT ruta, COUNT(*) AS boletos, SUM(precio) AS total FROM boletos"
            f" WHERE {campo} BETWEEN ? AND ? GROUP BY ruta",
            (desde, hasta),
        ).fetchall()
    por_ruta = {f["ruta"]: (f["boletos"], f["total"]) for f in filas}
    detalle = [
        {"destino": r, "boletos": por_ruta.get(r, (0, 0))[0], "total": por_ruta.get(r, (0, 0))[1]}
        for r in RUTAS
    ]
    return detalle, sum(d["boletos"] for d in detalle), sum(d["total"] for d in detalle)

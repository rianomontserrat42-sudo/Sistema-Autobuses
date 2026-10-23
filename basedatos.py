import sqlite3
from datetime import date
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash

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
        _crear_usuarios(con)


def _crear_usuarios(con):
    """Crea la tabla de usuarios y las cuentas iniciales si no existen."""
    con.execute(
        """CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT NOT NULL UNIQUE,
            contrasena TEXT NOT NULL,
            rol TEXT NOT NULL CHECK (rol IN ('admin', 'usuario'))
        )"""
    )
    iniciales = [
        ("admin", "admin123", "admin"),
        ("usuario", "usuario123", "usuario"),
    ]
    for nombre, contrasena, rol in iniciales:
        if con.execute("SELECT 1 FROM usuarios WHERE usuario = ?", (nombre,)).fetchone() is None:
            con.execute(
                "INSERT INTO usuarios (usuario, contrasena, rol) VALUES (?, ?, ?)",
                (nombre, generate_password_hash(contrasena), rol),
            )


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


def vender(nombre, fecha, asiento, ruta, destino, precio):
    """Guarda un boleto. Devuelve False si el asiento ya está ocupado."""
    try:
        with conectar() as con:
            con.execute(
                "INSERT INTO boletos (nombre, fecha, asiento, destino, precio, vendido, ruta)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (nombre, fecha, asiento, destino, precio, date.today().isoformat(), ruta),
            )
        return True
    except sqlite3.IntegrityError:
        return False


def asientos_ocupados(fecha, ruta, excluir=None):
    """Lista de asientos ocupados en esa fecha y ruta (se puede excluir un boleto al editar)."""
    sql = "SELECT asiento FROM boletos WHERE fecha = ? AND ruta = ?"
    params = [fecha, ruta]
    if excluir is not None:
        sql += " AND id != ?"
        params.append(excluir)
    with conectar() as con:
        return [f["asiento"] for f in con.execute(sql, params)]


def obtener(boleto_id):
    with conectar() as con:
        return con.execute("SELECT * FROM boletos WHERE id = ?", (boleto_id,)).fetchone()


def actualizar(boleto_id, nombre, fecha, asiento, ruta, destino, precio):
    """Actualiza un boleto. Devuelve False si el asiento ya está ocupado."""
    try:
        with conectar() as con:
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


def listar():
    with conectar() as con:
        return con.execute("SELECT * FROM boletos ORDER BY fecha, ruta, asiento").fetchall()


def corte(desde, hasta, campo="vendido", ruta=""):
    """Corte de caja entre dos fechas. campo: 'vendido' (fecha de venta) o 'fecha' (fecha de viaje)."""
    if campo not in CAMPOS_CORTE:  # lista blanca, por eso es seguro usarlo en el SQL
        campo = "vendido"
    filtro = f"WHERE {campo} BETWEEN ? AND ?"
    params = [desde, hasta]
    if ruta in RUTAS:
        filtro += " AND ruta = ?"
        params.append(ruta)
    with conectar() as con:
        boletos = [dict(f) for f in con.execute(
            f"SELECT id, nombre, fecha, asiento, ruta, destino, precio, vendido "
            f"FROM boletos {filtro} ORDER BY {campo}, ruta, asiento", params)]
        por_ruta = [dict(f) for f in con.execute(
            f"SELECT ruta, COUNT(*) AS boletos, COALESCE(SUM(precio), 0) AS total "
            f"FROM boletos {filtro} GROUP BY ruta ORDER BY ruta", params)]
        por_dia = [dict(f) for f in con.execute(
            f"SELECT {campo} AS dia, COUNT(*) AS boletos, COALESCE(SUM(precio), 0) AS total "
            f"FROM boletos {filtro} GROUP BY {campo} ORDER BY {campo}", params)]
    return {
        "boletos": boletos, "por_ruta": por_ruta, "por_dia": por_dia,
        "cantidad": len(boletos), "total": sum(b["precio"] or 0 for b in boletos),
    }


def verificar_usuario(nombre, contrasena):
    """Devuelve la fila del usuario si el usuario y contraseña son correctos; None si no."""
    if not nombre or not contrasena:
        return None
    with conectar() as con:
        f = con.execute("SELECT * FROM usuarios WHERE usuario = ?", (nombre,)).fetchone()
    if f is not None and check_password_hash(f["contrasena"], contrasena):
        return f
    return None


def usuario_existe(nombre):
    with conectar() as con:
        return con.execute("SELECT 1 FROM usuarios WHERE usuario = ?", (nombre,)).fetchone() is not None


def listar_usuarios():
    with conectar() as con:
        return [dict(f) for f in con.execute("SELECT id, usuario, rol FROM usuarios ORDER BY usuario")]


def crear_usuario(nombre, contrasena, rol):
    """Crea un usuario nuevo. Devuelve True si se creó; False si ya existía o el rol es inválido."""
    if rol not in ("admin", "usuario") or not nombre or not contrasena:
        return False
    try:
        with conectar() as con:
            con.execute(
                "INSERT INTO usuarios (usuario, contrasena, rol) VALUES (?, ?, ?)",
                (nombre.strip(), generate_password_hash(contrasena), rol),
            )
        return True
    except sqlite3.IntegrityError:
        return False


def eliminar_usuario(usuario_id):
    with conectar() as con:
        con.execute("DELETE FROM usuarios WHERE id = ? AND rol != 'admin'", (usuario_id,))


def ultimo_dia_viaje():
    """Última fecha de viaje guardada (hoy si no hay boletos)."""
    with conectar() as con:
        f = con.execute("SELECT MAX(fecha) AS dia FROM boletos").fetchone()
    return f["dia"] or date.today().isoformat()
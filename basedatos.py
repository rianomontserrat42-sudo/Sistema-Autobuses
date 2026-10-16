import sqlite3
from pathlib import Path

DB = Path(__file__).with_name("autobus.db")
TOTAL_ASIENTOS = 30


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
                UNIQUE (fecha, asiento)
            )"""
        )


def asientos_ocupados(fecha, excluir_id=None):
    with conectar() as con:
        filas = con.execute(
            "SELECT asiento FROM boletos WHERE fecha = ? AND id IS NOT ?",
            (fecha, excluir_id),
        )
        return [f["asiento"] for f in filas]


def obtener(boleto_id):
    with conectar() as con:
        return con.execute("SELECT * FROM boletos WHERE id = ?", (boleto_id,)).fetchone()


def actualizar(boleto_id, nombre, fecha, asiento):
    """Devuelve False si el asiento ya está ocupado en esa fecha."""
    try:
        with conectar() as con:
            con.execute(
                "UPDATE boletos SET nombre = ?, fecha = ?, asiento = ? WHERE id = ?",
                (nombre, fecha, asiento, boleto_id),
            )
        return True
    except sqlite3.IntegrityError:
        return False


def borrar(boleto_id):
    with conectar() as con:
        con.execute("DELETE FROM boletos WHERE id = ?", (boleto_id,))


def vender(nombre, fecha, asiento):
    """Devuelve False si el asiento ya está ocupado en esa fecha."""
    try:
        with conectar() as con:
            con.execute(
                "INSERT INTO boletos (nombre, fecha, asiento) VALUES (?, ?, ?)",
                (nombre, fecha, asiento),
            )
        return True
    except sqlite3.IntegrityError:
        return False


def listar():
    with conectar() as con:
        return con.execute(
            "SELECT id, nombre, fecha, asiento FROM boletos ORDER BY fecha, asiento"
        ).fetchall()

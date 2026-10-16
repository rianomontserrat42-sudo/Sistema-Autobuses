import re
from datetime import datetime

from basedatos import TOTAL_ASIENTOS


PATRON_NOMBRE = re.compile(r"^[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+(?: [A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+)*$")


def validar_nombre(nombre):
    return bool(nombre) and 2 <= len(nombre) <= 80 and bool(PATRON_NOMBRE.match(nombre))


def validar_fecha(fecha):
    try:
        datetime.strptime(fecha, "%Y-%m-%d")
        return True
    except (TypeError, ValueError):
        return False


def validar_asiento(asiento):
    try:
        return 1 <= int(asiento) <= TOTAL_ASIENTOS
    except (TypeError, ValueError):
        return False

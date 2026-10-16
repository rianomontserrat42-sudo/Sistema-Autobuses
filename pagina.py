from datetime import date

from flask import Flask, abort, flash, jsonify, redirect, render_template, request, url_for

import basedatos
from basedatos import CAMPOS_CORTE, ORIGEN, RUTAS, parsear_destino
from validaciones import validar_asiento, validar_fecha, validar_nombre

app = Flask(__name__)
app.secret_key = "autobus-local"
basedatos.iniciar()

# Cambiar a True para volver a mostrar el Corte de caja
CORTE_ACTIVO = False


@app.context_processor
def opciones_menu():
    return {"corte_activo": CORTE_ACTIVO}

# Filas del autobús: (izquierda, derecha); None = sin asiento
FILAS = [((1, 2), (4, 3)), ((5, 6), (8, 7)), ((9, 10), (12, 11)),
         ((13, 14), (16, 15)), ((17, 18), (20, 19)), ((21, 22), (24, 23)),
         ((25, 26), (28, 27)), ((29, 30), (None, None))]


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/vender", methods=["GET", "POST"])
def vender():
    if request.method == "POST":
        nombre = " ".join(request.form.get("nombre", "").split())
        fecha = request.form.get("fecha", "")
        asiento = request.form.get("asiento", "")
        destino = parsear_destino(request.form.get("destino", ""))
        if not validar_nombre(nombre):
            flash("El nombre solo puede contener letras y espacios.", "error")
        elif destino is None:
            flash("Selecciona un destino.", "error")
        elif not (validar_fecha(fecha) and validar_asiento(asiento)):
            flash("Indica una fecha válida y selecciona un asiento.", "error")
        elif fecha < date.today().isoformat():
            flash("La fecha del viaje no puede ser pasada.", "error")
        elif basedatos.vender(nombre, fecha, int(asiento), *destino):
            ruta, parada, precio = destino
            flash(f"Boleto vendido a {parada} ({ruta}) ${precio}: asiento {int(asiento):02d} para {nombre}.", "ok")
            return redirect(url_for("vender"))
        else:
            flash("Ese asiento ya está ocupado en el autobús de esa ruta y fecha.", "error")
    return render_template("vender.html", filas=FILAS, hoy=date.today().isoformat(),
                           rutas=RUTAS, origen=ORIGEN, destino_sel=request.form.get("destino", ""))


@app.route("/ocupados/<fecha>/<ruta>")
def ocupados(fecha, ruta):
    if not validar_fecha(fecha) or ruta not in RUTAS:
        return jsonify([])
    return jsonify(basedatos.asientos_ocupados(fecha, ruta, request.args.get("excluir", type=int)))


@app.route("/editar/<int:boleto_id>", methods=["GET", "POST"])
def editar(boleto_id):
    boleto = basedatos.obtener(boleto_id)
    if boleto is None:
        flash("Ese boleto ya no existe.", "error")
        return redirect(url_for("boletos"))
    if request.method == "POST":
        nombre = " ".join(request.form.get("nombre", "").split())
        fecha = request.form.get("fecha", "")
        asiento = request.form.get("asiento", "")
        destino = parsear_destino(request.form.get("destino", ""))
        if not validar_nombre(nombre):
            flash("El nombre solo puede contener letras y espacios.", "error")
        elif destino is None:
            flash("Selecciona un destino.", "error")
        elif not (validar_fecha(fecha) and validar_asiento(asiento)):
            flash("Indica una fecha válida y selecciona un asiento.", "error")
        elif fecha < date.today().isoformat() and fecha != boleto["fecha"]:
            flash("La fecha del viaje no puede ser pasada.", "error")
        elif basedatos.actualizar(boleto_id, nombre, fecha, int(asiento), *destino):
            flash("Pasajero actualizado.", "ok")
            return redirect(url_for("boletos"))
        else:
            flash("Ese asiento ya está ocupado en el autobús de esa ruta y fecha.", "error")
    return render_template("vender.html", filas=FILAS, hoy=date.today().isoformat(), boleto=boleto,
                           rutas=RUTAS, origen=ORIGEN, destino_sel=f"{boleto['ruta']}|{boleto['destino']}")


@app.route("/borrar/<int:boleto_id>", methods=["POST"])
def borrar(boleto_id):
    basedatos.borrar(boleto_id)
    flash("Pasajero eliminado.", "ok")
    return redirect(url_for("boletos"))


@app.route("/boletos")
def boletos():
    return render_template("boletos.html", boletos=basedatos.listar(), origen=ORIGEN)


@app.route("/corte")
def corte():
    if not CORTE_ACTIVO:
        abort(404)
    hoy = date.today().isoformat()
    dia = request.args.get("dia", hoy)
    if not validar_fecha(dia):
        dia = hoy
    campo = request.args.get("base", "vendido")
    if campo not in CAMPOS_CORTE:
        campo = "vendido"
    desde = request.args.get("desde", hoy[:8] + "01")
    hasta = request.args.get("hasta", hoy)
    if not (validar_fecha(desde) and validar_fecha(hasta)):
        flash("Indica fechas válidas para el periodo.", "error")
        desde, hasta = hoy[:8] + "01", hoy
    elif desde > hasta:
        flash("La fecha inicial no puede ser mayor que la final.", "error")
        desde, hasta = hasta, desde
    return render_template(
        "corte.html", origen=ORIGEN, dia=dia, desde=desde, hasta=hasta,
        campo=campo, campos=CAMPOS_CORTE, hoy=hoy,
        corte_dia=basedatos.corte(dia, dia, "vendido"),
        corte_periodo=basedatos.corte(desde, hasta, campo),
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)

from datetime import date

from flask import Flask, flash, jsonify, redirect, render_template, request, url_for

import basedatos
from validaciones import validar_asiento, validar_fecha, validar_nombre

app = Flask(__name__)
app.secret_key = "autobus-local"
basedatos.iniciar()

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
        if not validar_nombre(nombre):
            flash("El nombre solo puede contener letras y espacios.", "error")
        elif not (validar_fecha(fecha) and validar_asiento(asiento)):
            flash("Indica una fecha válida y selecciona un asiento.", "error")
        elif fecha < date.today().isoformat():
            flash("La fecha del viaje no puede ser pasada.", "error")
        elif basedatos.vender(nombre, fecha, int(asiento)):
            flash(f"Boleto vendido: asiento {int(asiento):02d} para {nombre}.", "ok")
            return redirect(url_for("vender"))
        else:
            flash("Ese asiento ya está ocupado en esa fecha.", "error")
    return render_template("vender.html", filas=FILAS, hoy=date.today().isoformat())


@app.route("/ocupados/<fecha>")
def ocupados(fecha):
    if not validar_fecha(fecha):
        return jsonify([])
    return jsonify(basedatos.asientos_ocupados(fecha, request.args.get("excluir", type=int)))


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
        if not validar_nombre(nombre):
            flash("El nombre solo puede contener letras y espacios.", "error")
        elif not (validar_fecha(fecha) and validar_asiento(asiento)):
            flash("Indica una fecha válida y selecciona un asiento.", "error")
        elif fecha < date.today().isoformat() and fecha != boleto["fecha"]:
            flash("La fecha del viaje no puede ser pasada.", "error")
        elif basedatos.actualizar(boleto_id, nombre, fecha, int(asiento)):
            flash("Pasajero actualizado.", "ok")
            return redirect(url_for("boletos"))
        else:
            flash("Ese asiento ya está ocupado en esa fecha.", "error")
    return render_template("vender.html", filas=FILAS, hoy=date.today().isoformat(), boleto=boleto)


@app.route("/borrar/<int:boleto_id>", methods=["POST"])
def borrar(boleto_id):
    basedatos.borrar(boleto_id)
    flash("Pasajero eliminado.", "ok")
    return redirect(url_for("boletos"))


@app.route("/boletos")
def boletos():
    return render_template("boletos.html", boletos=basedatos.listar())


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)

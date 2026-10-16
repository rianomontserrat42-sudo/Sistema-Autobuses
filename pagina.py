import io
from datetime import date

from flask import Flask, abort, flash, jsonify, redirect, render_template, request, send_file, url_for
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

import basedatos
from basedatos import CAMPOS_CORTE, ORIGEN, RUTAS, parsear_destino
from validaciones import validar_asiento, validar_fecha, validar_nombre

app = Flask(__name__)
app.secret_key = "autobus-local"
basedatos.iniciar()

# Cambiar a False para ocultar el Corte de caja
CORTE_ACTIVO = True


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


def _parametros_corte():
    """Lee y valida los filtros del corte (día, periodo, base y ruta)."""
    hoy = date.today().isoformat()
    dia = request.args.get("dia", hoy)
    if not validar_fecha(dia):
        dia = hoy
    campo = request.args.get("base", "vendido")
    if campo not in CAMPOS_CORTE:
        campo = "vendido"
    ruta = request.args.get("ruta", "")
    if ruta not in RUTAS:
        ruta = ""
    desde = request.args.get("desde", hoy[:8] + "01")
    hasta = request.args.get("hasta", hoy)
    if not (validar_fecha(desde) and validar_fecha(hasta)):
        flash("Indica fechas válidas para el periodo.", "error")
        desde, hasta = hoy[:8] + "01", hoy
    elif desde > hasta:
        flash("La fecha inicial no puede ser mayor que la final.", "error")
        desde, hasta = hasta, desde
    return hoy, dia, desde, hasta, campo, ruta


@app.route("/corte")
def corte():
    if not CORTE_ACTIVO:
        abort(404)
    hoy, dia, desde, hasta, campo, ruta = _parametros_corte()
    return render_template(
        "corte.html", origen=ORIGEN, dia=dia, desde=desde, hasta=hasta, hoy=hoy,
        campo=campo, campos=CAMPOS_CORTE, ruta=ruta, rutas=RUTAS,
        corte_dia=basedatos.corte(dia, dia, "vendido", ruta),
        corte_periodo=basedatos.corte(desde, hasta, campo, ruta),
    )


@app.route("/corte/pdf")
def corte_pdf():
    if not CORTE_ACTIVO:
        abort(404)
    hoy, dia, desde, hasta, campo, ruta = _parametros_corte()
    if request.args.get("tipo") == "dia":
        titulo, ini, fin, base = f"Corte de caja del día {dia}", dia, dia, "vendido"
    else:
        titulo, ini, fin, base = f"Corte de caja del {desde} al {hasta}", desde, hasta, campo
    datos = basedatos.corte(ini, fin, base, ruta)

    est = getSampleStyleSheet()
    estilo_tabla = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#333333")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (-1, 1), (-1, -1), "RIGHT"),
    ])
    filtro_txt = f"Base: {CAMPOS_CORTE[base]} · " + (f"Ruta: {ruta}" if ruta else "Todas las rutas")
    el = [Paragraph(f"Corte de caja — {ORIGEN}", est["Title"]),
          Paragraph(titulo, est["Heading2"]),
          Paragraph(filtro_txt, est["Normal"]), Spacer(1, 12)]

    if not datos["boletos"]:
        el.append(Paragraph("No hay boletos en este periodo.", est["Normal"]))
    else:
        resumen = [["Ruta", "Boletos", "Total"]]
        resumen += [[r["ruta"], r["boletos"], f"${r['total']}"] for r in datos["por_ruta"]]
        resumen.append(["TOTAL", datos["cantidad"], f"${datos['total']}"])
        t1 = Table(resumen, hAlign="LEFT")
        t1.setStyle(estilo_tabla)
        t1.setStyle(TableStyle([("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold")]))
        el += [Paragraph("Resumen por ruta", est["Heading3"]), t1, Spacer(1, 14),
               Paragraph("Detalle de boletos", est["Heading3"])]
        filas = [["Venta", "Viaje", "Pasajero", "Asiento", "Ruta", "Parada", "Precio"]]
        filas += [[b["vendido"], b["fecha"], b["nombre"], f"{b['asiento']:02d}",
                   b["ruta"], b["destino"], f"${b['precio']}"] for b in datos["boletos"]]
        t2 = Table(filas, repeatRows=1)
        t2.setStyle(estilo_tabla)
        el.append(t2)

    buffer = io.BytesIO()
    SimpleDocTemplate(buffer, pagesize=letter, title=titulo, leftMargin=36, rightMargin=36,
                      topMargin=36, bottomMargin=36).build(el)
    buffer.seek(0)
    return send_file(buffer, mimetype="application/pdf", as_attachment=True,
                     download_name=f"corte_{ini}_{fin}.pdf")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
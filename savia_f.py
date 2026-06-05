import tkinter as tk
from tkinter import messagebox
import serial
from serial.tools import list_ports
import time
import re
import glob
import subprocess
import math
import wave
import struct
import threading
import csv
import os
import json
import calendar
from datetime import datetime, timedelta, date
import smtplib
from email.message import EmailMessage
import urllib.request
import urllib.error

# SAVIA_WIFI_IP_CORREOS_RECIENTES_V1
# SAVIA_MENU_SCROLL_BAR_NATIVO_FINAL_V1
# SAVIA_THINGSBOARD_TELEMETRIA_V1

# ==========================================
# CONFIGURACIÓN UART
# ==========================================
BAUDIOS = 115200

puerto_uart = None
puerto_actual = None

INTERVALO_RECONEXION = 2
ultimo_intento_uart = 0


def obtener_puertos_posibles():
    puertos = []

    try:
        for p in list_ports.comports():
            texto = f"{p.device} {p.description} {p.manufacturer} {p.hwid}".lower()

            if (
                "ttyacm" in p.device.lower()
                or "ttyusb" in p.device.lower()
                or "arduino" in texto
                or "esp32" in texto
                or "ch340" in texto
                or "cp210" in texto
                or "silicon labs" in texto
                or "usb serial" in texto
            ):
                puertos.append(p.device)

    except Exception as e:
        print(f"Error buscando puertos con list_ports: {e}")

    puertos.extend(glob.glob("/dev/ttyACM*"))
    puertos.extend(glob.glob("/dev/ttyUSB*"))

    puertos_unicos = []
    for p in puertos:
        if p not in puertos_unicos:
            puertos_unicos.append(p)

    return puertos_unicos


def cerrar_uart():
    global puerto_uart, puerto_actual

    try:
        if puerto_uart and puerto_uart.is_open:
            puerto_uart.close()
    except:
        pass

    if puerto_actual:
        print(f"UART desconectado: {puerto_actual}")

    puerto_uart = None
    puerto_actual = None


def conectar_uart(forzar=False):
    global puerto_uart, puerto_actual, ultimo_intento_uart

    if puerto_uart and puerto_uart.is_open:
        return True

    ahora = time.time()

    if not forzar and (ahora - ultimo_intento_uart) < INTERVALO_RECONEXION:
        return False

    ultimo_intento_uart = ahora

    puertos = obtener_puertos_posibles()

    if not puertos:
        print("No se encontró ningún puerto UART disponible.")
        return False

    for puerto in puertos:
        try:
            print(f"Intentando conectar UART en: {puerto}")

            nuevo_puerto = serial.Serial(
                puerto,
                baudrate=BAUDIOS,
                timeout=0.1,
                write_timeout=0.5
            )

            time.sleep(2)
            nuevo_puerto.reset_input_buffer()

            puerto_uart = nuevo_puerto
            puerto_actual = puerto

            print(f"UART conectado exitosamente en {puerto_actual}")
            return True

        except Exception as e:
            print(f"No se pudo abrir {puerto}: {e}")

    puerto_uart = None
    puerto_actual = None
    return False


conectar_uart(forzar=True)


# ==========================================
# CONFIGURACIÓN DE CORREO / RED
# ==========================================
RUTA_EMAIL_ENV = "/home/savia/savia_email.env"
RUTA_CORREOS_HISTORIAL = "/home/savia/savia_correos_recientes.json"


def cargar_config_correo_desde_archivo(ruta=RUTA_EMAIL_ENV):
    """Carga /home/savia/savia_email.env aunque la app no haya sido abierta con source.

    Acepta líneas tipo:
    export SAVIA_SMTP_USER="correo@gmail.com"
    SAVIA_SMTP_PASS="clave"
    """
    try:
        if not os.path.exists(ruta):
            return False

        with open(ruta, "r", encoding="utf-8") as archivo:
            for linea in archivo:
                linea = linea.strip()
                if not linea or linea.startswith("#"):
                    continue
                if linea.startswith("export "):
                    linea = linea[len("export "):].strip()
                if "=" not in linea:
                    continue

                clave, valor = linea.split("=", 1)
                clave = clave.strip()
                valor = valor.strip().strip('"').strip("'")

                if clave.startswith("SAVIA_SMTP_"):
                    os.environ[clave] = valor
        return True
    except Exception as e:
        print(f"No se pudo cargar configuración de correo: {e}")
        return False


def obtener_config_correo():
    # Se vuelve a cargar por si el archivo fue corregido mientras la app está abierta.
    cargar_config_correo_desde_archivo()
    host = os.environ.get("SAVIA_SMTP_HOST", "smtp.gmail.com")
    try:
        port = int(os.environ.get("SAVIA_SMTP_PORT", "587"))
    except Exception:
        port = 587
    user = os.environ.get("SAVIA_SMTP_USER", "").strip()
    password = os.environ.get("SAVIA_SMTP_PASS", "").strip()
    sender = os.environ.get("SAVIA_SMTP_FROM", user).strip()
    return host, port, user, password, sender


def estado_config_correo():
    host, port, user, password, sender = obtener_config_correo()
    faltantes = []
    if not user:
        faltantes.append("SAVIA_SMTP_USER")
    if not password:
        faltantes.append("SAVIA_SMTP_PASS")
    if not sender:
        faltantes.append("SAVIA_SMTP_FROM")

    if faltantes:
        return False, "Correo no configurado: falta " + ", ".join(faltantes)

    return True, f"Correo activo: {user}"


def cargar_correos_recientes():
    try:
        if not os.path.exists(RUTA_CORREOS_HISTORIAL):
            return []
        with open(RUTA_CORREOS_HISTORIAL, "r", encoding="utf-8") as archivo:
            datos = json.load(archivo)
        if not isinstance(datos, list):
            return []
        correos = []
        for correo in datos:
            correo = str(correo).strip()
            if correo and "@" in correo and correo not in correos:
                correos.append(correo)
        return correos[:8]
    except Exception as e:
        print(f"No se pudo leer historial de correos: {e}")
        return []


def guardar_correo_reciente(correo):
    correo = str(correo).strip()
    if "@" not in correo or "." not in correo:
        return
    try:
        correos = cargar_correos_recientes()
        correos = [c for c in correos if c.lower() != correo.lower()]
        correos.insert(0, correo)
        correos = correos[:8]
        with open(RUTA_CORREOS_HISTORIAL, "w", encoding="utf-8") as archivo:
            json.dump(correos, archivo, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"No se pudo guardar correo reciente: {e}")


def obtener_ip_raspberry():
    try:
        resultado = subprocess.check_output(["hostname", "-I"], text=True, timeout=3)
        ips = [ip.strip() for ip in resultado.split() if ip.strip()]
        for ip in ips:
            if not ip.startswith("127."):
                return ip
    except Exception as e:
        print(f"No se pudo obtener IP con hostname -I: {e}")

    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(1)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "Sin IP"


# Carga inicial del correo, incluso si SAVIA se abrió sin source.
cargar_config_correo_desde_archivo()


# ==========================================
# THINGSBOARD / TELEMETRÍA EN LA NUBE
# ==========================================
# Configura en /home/savia/savia_thingsboard.env:
# export SAVIA_TB_HOST="https://demo.thingsboard.io"
# export SAVIA_TB_TOKEN="ACCESS_TOKEN_DEL_DISPOSITIVO"
RUTA_THINGSBOARD_ENV = "/home/savia/savia_thingsboard.env"
ultimo_envio_thingsboard = {}
ultimo_error_thingsboard = 0


def cargar_config_thingsboard_desde_archivo(ruta=RUTA_THINGSBOARD_ENV):
    try:
        if not os.path.exists(ruta):
            return False

        with open(ruta, "r", encoding="utf-8") as archivo:
            for linea in archivo:
                linea = linea.strip()
                if not linea or linea.startswith("#"):
                    continue
                if linea.startswith("export "):
                    linea = linea[len("export "):].strip()
                if "=" not in linea:
                    continue

                clave, valor = linea.split("=", 1)
                clave = clave.strip()
                valor = valor.strip().strip('"').strip("'")

                if clave.startswith("SAVIA_TB_"):
                    os.environ[clave] = valor
        return True
    except Exception as e:
        print(f"No se pudo cargar configuración de ThingsBoard: {e}")
        return False


def obtener_config_thingsboard():
    cargar_config_thingsboard_desde_archivo()
    host = os.environ.get("SAVIA_TB_HOST", "https://demo.thingsboard.io").strip().rstrip("/")
    token = os.environ.get("SAVIA_TB_TOKEN", "").strip()
    habilitado = os.environ.get("SAVIA_TB_ENABLED", "1").strip() != "0"
    return host, token, habilitado


def estado_config_thingsboard():
    host, token, habilitado = obtener_config_thingsboard()
    if not habilitado:
        return False, "ThingsBoard desactivado"
    if not token:
        return False, "ThingsBoard sin token"
    return True, f"ThingsBoard activo: {host}"


def enviar_thingsboard_async(nodo, v1, v2, v3, prom, temp, hum):
    """Envía telemetría a ThingsBoard sin bloquear la interfaz local.

    Si no hay internet o ThingsBoard falla, SAVIA sigue funcionando localmente.
    """
    host, token, habilitado = obtener_config_thingsboard()
    if not habilitado or not token:
        return

    firma = (
        nodo,
        round(v1, 2),
        round(v2, 2),
        round(v3, 2),
        round(temp, 2),
        round(hum, 2),
    )
    ahora = time.time()
    ultima_firma, ultimo_tiempo = ultimo_envio_thingsboard.get(nodo, (None, 0))

    # Evita duplicados cuando el ESP32 imprime log largo y línea SAVIA_DATA casi iguales.
    if firma == ultima_firma and (ahora - ultimo_tiempo) < 2.0:
        return

    ultimo_envio_thingsboard[nodo] = (firma, ahora)

    prefijo = f"nodo{nodo}"
    payload = {
        f"{prefijo}_suelo1": round(v1, 2),
        f"{prefijo}_suelo2": round(v2, 2),
        f"{prefijo}_suelo3": round(v3, 2),
        f"{prefijo}_promedio": round(prom, 2),
        f"{prefijo}_temperatura": round(temp, 2),
        f"{prefijo}_humedad_aire": round(hum, 2),
        f"{prefijo}_conectado": True,
    }

    # También manda una marca general para saber cuál nodo actualizó la última lectura.
    payload["ultimo_nodo_actualizado"] = nodo

    def tarea():
        global ultimo_error_thingsboard
        url = f"{host}/api/v1/{token}/telemetry"
        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=4) as resp:
                if resp.status not in (200, 204):
                    raise RuntimeError(f"HTTP {resp.status}")
            print(f"ThingsBoard OK Nodo {nodo}: {payload}")
        except Exception as e:
            # No saturar terminal si se va internet.
            ahora_error = time.time()
            if ahora_error - ultimo_error_thingsboard > 15:
                print(f"No se pudo enviar a ThingsBoard: {e}")
                ultimo_error_thingsboard = ahora_error

    threading.Thread(target=tarea, daemon=True).start()


# Carga inicial de ThingsBoard aunque SAVIA no se haya abierto con source.
cargar_config_thingsboard_desde_archivo()


# ==========================================
# HISTORIAL Y EXPORTACIÓN CSV
# ==========================================
# El historial se guarda automáticamente cada vez que llega una lectura válida
# de cualquier nodo. La exportación filtra por fechas y genera un CSV listo
# para mandar por correo.
RUTA_CSV_HISTORIAL = os.environ.get(
    "SAVIA_CSV_HISTORIAL",
    "/home/savia/savia_historial_sensores.csv"
)

CARPETA_EXPORTACIONES = os.environ.get(
    "SAVIA_CARPETA_EXPORTACIONES",
    "/home/savia/exportaciones"
)

# Para enviar correos automáticamente configura estas variables en la Raspberry:
# export SAVIA_SMTP_HOST="smtp.gmail.com"
# export SAVIA_SMTP_PORT="587"
# export SAVIA_SMTP_USER="tu_correo@gmail.com"
# export SAVIA_SMTP_PASS="tu_app_password"
# export SAVIA_SMTP_FROM="tu_correo@gmail.com"
SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM = obtener_config_correo()

COLUMNAS_HISTORIAL = [
    "fecha_hora",
    "fecha",
    "hora",
    "nodo",
    "humedad_suelo_1_pct",
    "humedad_suelo_2_pct",
    "humedad_suelo_3_pct",
    "promedio_suelo_pct",
    "temperatura_aire_c",
    "humedad_aire_pct",
    "puerto_uart",
    "dato_original"
]

ultimo_guardado_csv = {}


def asegurar_csv_historial():
    carpeta = os.path.dirname(RUTA_CSV_HISTORIAL)
    if carpeta:
        os.makedirs(carpeta, exist_ok=True)

    if not os.path.exists(RUTA_CSV_HISTORIAL):
        with open(RUTA_CSV_HISTORIAL, mode="w", newline="", encoding="utf-8") as archivo:
            escritor = csv.writer(archivo)
            escritor.writerow(COLUMNAS_HISTORIAL)


def guardar_datos_csv(nodo, v1, v2, v3, prom, temp, hum, dato_original):
    """Guarda una lectura válida en el historial.

    Incluye una protección simple contra duplicados porque el ESP32 puede imprimir
    una línea de diagnóstico y una línea SAVIA_DATA con los mismos datos.
    """
    try:
        asegurar_csv_historial()

        firma = (
            nodo,
            round(v1, 2),
            round(v2, 2),
            round(v3, 2),
            round(temp, 2),
            round(hum, 2)
        )
        ahora = time.time()
        ultima_firma, ultimo_tiempo = ultimo_guardado_csv.get(nodo, (None, 0))

        # Evita duplicar la misma lectura cuando llega repetida casi al mismo tiempo.
        if firma == ultima_firma and (ahora - ultimo_tiempo) < 2.0:
            return

        ultimo_guardado_csv[nodo] = (firma, ahora)

        fecha_hora = time.strftime("%Y-%m-%d %H:%M:%S")
        fecha = time.strftime("%Y-%m-%d")
        hora = time.strftime("%H:%M:%S")

        with open(RUTA_CSV_HISTORIAL, mode="a", newline="", encoding="utf-8") as archivo:
            escritor = csv.writer(archivo)
            escritor.writerow([
                fecha_hora,
                fecha,
                hora,
                nodo,
                f"{v1:.2f}",
                f"{v2:.2f}",
                f"{v3:.2f}",
                f"{prom:.2f}",
                f"{temp:.2f}",
                f"{hum:.2f}",
                puerto_actual if puerto_actual else "",
                dato_original
            ])

    except Exception as e:
        print(f"Error guardando historial CSV: {e}")


def convertir_fecha_usuario(texto_fecha):
    texto_fecha = texto_fecha.strip()
    try:
        return datetime.strptime(texto_fecha, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("La fecha debe tener formato AAAA-MM-DD, por ejemplo 2026-05-25.")


def generar_csv_exportacion(fecha_inicio, fecha_fin):
    asegurar_csv_historial()
    os.makedirs(CARPETA_EXPORTACIONES, exist_ok=True)

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    nombre_archivo = f"savia_historial_{fecha_inicio:%Y%m%d}_a_{fecha_fin:%Y%m%d}_{timestamp}.csv"
    ruta_exportacion = os.path.join(CARPETA_EXPORTACIONES, nombre_archivo)

    total_filas = 0

    with open(RUTA_CSV_HISTORIAL, mode="r", newline="", encoding="utf-8") as origen, \
            open(ruta_exportacion, mode="w", newline="", encoding="utf-8") as destino:
        lector = csv.DictReader(origen)
        escritor = csv.DictWriter(destino, fieldnames=COLUMNAS_HISTORIAL)
        escritor.writeheader()

        for fila in lector:
            fecha_fila_txt = fila.get("fecha", "").strip()
            if not fecha_fila_txt:
                fecha_hora_txt = fila.get("fecha_hora", "").strip()
                fecha_fila_txt = fecha_hora_txt[:10]

            try:
                fecha_fila = datetime.strptime(fecha_fila_txt, "%Y-%m-%d").date()
            except ValueError:
                continue

            if fecha_inicio <= fecha_fila <= fecha_fin:
                escritor.writerow({col: fila.get(col, "") for col in COLUMNAS_HISTORIAL})
                total_filas += 1

    return ruta_exportacion, total_filas


def enviar_csv_por_correo(destinatario, ruta_csv, fecha_inicio, fecha_fin):
    host, port, user, password, sender = obtener_config_correo()

    if not user or not password or not sender:
        ok, estado = estado_config_correo()
        raise RuntimeError(
            "El CSV se generó, pero el correo no está listo para enviar. "
            f"{estado}. Revisa /home/savia/savia_email.env."
        )

    asunto = f"Historial de sensores SAVIA {fecha_inicio:%Y-%m-%d} a {fecha_fin:%Y-%m-%d}"
    cuerpo = (
        "Hola,\n\n"
        "Se adjunta el historial de sensores exportado desde SAVIA.\n\n"
        f"Rango solicitado: {fecha_inicio:%Y-%m-%d} a {fecha_fin:%Y-%m-%d}\n"
        "El archivo incluye las lecturas de humedad de suelo, temperatura y humedad del aire por nodo.\n\n"
        "Sistema SAVIA"
    )

    mensaje = EmailMessage()
    mensaje["From"] = sender
    mensaje["To"] = destinatario
    mensaje["Subject"] = asunto
    mensaje.set_content(cuerpo)

    with open(ruta_csv, "rb") as archivo:
        contenido = archivo.read()
        mensaje.add_attachment(
            contenido,
            maintype="text",
            subtype="csv",
            filename=os.path.basename(ruta_csv)
        )

    try:
        with smtplib.SMTP(host, port, timeout=30) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            smtp.login(user, password)
            smtp.send_message(mensaje)
    except smtplib.SMTPAuthenticationError:
        raise RuntimeError(
            "No se pudo iniciar sesión en el correo configurado. "
            "Revisa que SAVIA_SMTP_USER sea el Gmail correcto y que SAVIA_SMTP_PASS sea la contraseña de aplicación, sin espacios."
        )
    except smtplib.SMTPConnectError:
        raise RuntimeError("No se pudo conectar con el servidor de correo. Revisa el internet de la Raspberry.")
    except smtplib.SMTPException as e:
        raise RuntimeError(f"Error del servidor de correo: {e}")


# ==========================================
# FUNCIONES DEL SISTEMA RASPBERRY
# ==========================================
def ejecutar_comando_sistema(nombre_accion, comando):
    confirmar = messagebox.askyesno(
        "Confirmar acción",
        f"¿Seguro que quieres {nombre_accion} la Raspberry?"
    )

    if not confirmar:
        return

    try:
        cerrar_uart()
        subprocess.Popen(comando)
    except Exception as e:
        messagebox.showerror(
            "Error",
            f"No se pudo ejecutar la acción: {e}"
        )


def apagar_rasp():
    ejecutar_comando_sistema("apagar", ["systemctl", "poweroff"])


def reiniciar_rasp():
    ejecutar_comando_sistema("reiniciar", ["systemctl", "reboot"])


def suspender_rasp():
    ejecutar_comando_sistema("suspender", ["systemctl", "suspend"])


def prender_rasp():
    messagebox.showinfo(
        "Prender Raspberry",
        "La Raspberry no puede prenderse desde este programa si ya está apagada.\n\n"
        "Para encenderla necesitas reconectar alimentación, usar un botón físico, "
        "un módulo externo o un sistema de encendido por hardware."
    )


def abrir_config_wifi():
    # ==========================================
    # VENTANA WIFI CON REDES DISPONIBLES + TECLADO TÁCTIL COMPLETO
    # ==========================================
    ventana_wifi = tk.Toplevel(ventana)
    ventana_wifi.title("Configurar WiFi")
    ventana_wifi.geometry("800x480+0+0")
    ventana_wifi.configure(bg="#f4f7f6")
    ventana_wifi.resizable(False, False)
    ventana_wifi.transient(ventana)
    ventana_wifi.grab_set()
    ventana_wifi.focus_force()

    try:
        ventana_wifi.attributes("-fullscreen", True)
    except Exception:
        pass

    campo_activo = {"entry": None}
    teclado_modo = {"mayus": False, "caps": False, "simbolos": False}
    password_visible = {"visible": False}
    redes_detectadas = {"lista": []}
    redes_guardadas = {"set": set()}
    red_seleccionada = {"red": None}
    pagina_redes = {"pagina": 0}
    ESCANEANDO = {"activo": False}
    REDES_POR_PAGINA = 4

    def cerrar_wifi():
        try:
            ventana_wifi.grab_release()
        except Exception:
            pass
        ventana_wifi.destroy()

    # ---------- Funciones NetworkManager / nmcli ----------
    def ejecutar_nmcli(argumentos, timeout=20):
        return subprocess.run(
            ["nmcli"] + argumentos,
            capture_output=True,
            text=True,
            timeout=timeout
        )

    def limpiar_texto_nmcli(texto):
        return texto.replace("\\:", ":").replace("\\\\", "\\").strip()

    def obtener_redes_guardadas():
        guardadas = set()
        try:
            resultado = ejecutar_nmcli(["-t", "-f", "NAME,TYPE", "connection", "show"], timeout=8)
            if resultado.returncode == 0:
                for linea in resultado.stdout.splitlines():
                    if not linea.strip():
                        continue
                    partes = linea.rsplit(":", 1)
                    if len(partes) == 2:
                        nombre, tipo = partes
                        if tipo.strip() == "802-11-wireless":
                            guardadas.add(limpiar_texto_nmcli(nombre))
        except Exception as e:
            print(f"No se pudieron leer redes guardadas: {e}")
        return guardadas

    def parsear_redes_nmcli(texto, guardadas):
        redes_por_ssid = {}

        for linea in texto.splitlines():
            if not linea.strip():
                continue

            partes = linea.split(":", 3)
            if len(partes) < 4:
                continue

            en_uso, ssid, senal, seguridad = partes
            ssid = limpiar_texto_nmcli(ssid)
            seguridad = limpiar_texto_nmcli(seguridad)

            if not ssid:
                continue

            try:
                senal_num = int(senal.strip())
            except Exception:
                senal_num = 0

            red = {
                "ssid": ssid,
                "senal": senal_num,
                "seguridad": seguridad if seguridad and seguridad != "--" else "Abierta",
                "en_uso": en_uso.strip() == "*",
                "guardada": ssid in guardadas
            }

            if ssid not in redes_por_ssid or senal_num > redes_por_ssid[ssid]["senal"]:
                redes_por_ssid[ssid] = red

        redes = list(redes_por_ssid.values())
        redes.sort(key=lambda r: (not r["en_uso"], not r["guardada"], -r["senal"], r["ssid"].lower()))
        return redes

    def barras_senal(senal):
        if senal >= 75:
            return "▰▰▰▰"
        if senal >= 50:
            return "▰▰▰▱"
        if senal >= 25:
            return "▰▰▱▱"
        return "▰▱▱▱"

    def es_red_segura(red):
        if not red:
            return False
        seguridad = red.get("seguridad", "").strip().lower()
        return seguridad not in ("", "--", "abierta")

    # ---------- Encabezado ----------
    frame_wifi_header = tk.Frame(ventana_wifi, bg="#2d6a4f", height=44)
    frame_wifi_header.pack(fill="x")
    frame_wifi_header.pack_propagate(False)

    tk.Label(
        frame_wifi_header,
        text="📶 Configurar WiFi",
        font=("Segoe UI", 15, "bold"),
        bg="#2d6a4f",
        fg="white"
    ).pack(side="left", padx=(18, 12))

    tk.Label(
        frame_wifi_header,
        text=f"IP Raspberry: {obtener_ip_raspberry()}",
        font=("Segoe UI", 11, "bold"),
        bg="#40916c",
        fg="white",
        padx=12,
        pady=4
    ).pack(side="left", padx=4)

    tk.Button(
        frame_wifi_header,
        text="✕ Cerrar",
        font=("Segoe UI", 11, "bold"),
        bg="#e63946",
        fg="white",
        activebackground="#c1121f",
        activeforeground="white",
        relief="flat",
        bd=0,
        padx=14,
        command=cerrar_wifi
    ).pack(side="right", padx=12, pady=7)

    # ---------- Contenido superior: redes + campos ----------
    frame_contenido = tk.Frame(ventana_wifi, bg="#f4f7f6", height=166)
    frame_contenido.pack(fill="x", padx=10, pady=(6, 3))
    frame_contenido.pack_propagate(False)

    frame_redes = tk.Frame(
        frame_contenido,
        bg="white",
        highlightbackground="#b7e4c7",
        highlightthickness=2,
        width=372
    )
    frame_redes.pack(side="left", fill="both", padx=(0, 8))
    frame_redes.pack_propagate(False)

    frame_redes_header = tk.Frame(frame_redes, bg="#f1faee", height=34)
    frame_redes_header.pack(fill="x")
    frame_redes_header.pack_propagate(False)

    tk.Label(
        frame_redes_header,
        text="REDES WIFI DISPONIBLES",
        font=("Segoe UI", 10, "bold"),
        bg="#f1faee",
        fg="#1b4332"
    ).pack(side="left", padx=10)

    def escanear_redes():
        if ESCANEANDO["activo"]:
            return

        ESCANEANDO["activo"] = True
        lbl_wifi_estado.config(text="Buscando redes WiFi cercanas...", fg="#2d6a4f")
        btn_actualizar_redes.config(text="Buscando...", state="disabled")
        for widget in frame_lista_redes.winfo_children():
            widget.destroy()
        tk.Label(
            frame_lista_redes,
            text="Escaneando redes...",
            font=("Segoe UI", 11, "bold"),
            bg="white",
            fg="#555"
        ).pack(expand=True)
        ventana_wifi.update_idletasks()

        def trabajo():
            error = None
            redes = []
            guardadas = set()
            try:
                try:
                    ejecutar_nmcli(["radio", "wifi", "on"], timeout=5)
                except Exception:
                    pass

                guardadas = obtener_redes_guardadas()
                resultado = ejecutar_nmcli(
                    ["-t", "-f", "IN-USE,SSID,SIGNAL,SECURITY", "dev", "wifi", "list", "--rescan", "yes"],
                    timeout=18
                )

                if resultado.returncode == 0:
                    redes = parsear_redes_nmcli(resultado.stdout, guardadas)
                else:
                    error = resultado.stderr.strip() or resultado.stdout.strip() or "No se pudieron leer redes WiFi."

            except FileNotFoundError:
                error = "No se encontró nmcli. Verifica que NetworkManager esté instalado."
            except subprocess.TimeoutExpired:
                error = "La búsqueda tardó demasiado. Intenta actualizar de nuevo."
            except Exception as e:
                error = f"Error buscando redes: {e}"

            def finalizar():
                ESCANEANDO["activo"] = False
                btn_actualizar_redes.config(text="Actualizar", state="normal")
                redes_guardadas["set"] = guardadas
                redes_detectadas["lista"] = redes
                pagina_redes["pagina"] = 0
                actualizar_lista_redes()

                if error:
                    lbl_wifi_estado.config(text=error, fg="#e63946")
                elif not redes:
                    lbl_wifi_estado.config(text="No se encontraron redes. Toca Actualizar.", fg="#e63946")
                else:
                    lbl_wifi_estado.config(
                        text="Selecciona una red. Si ya está guardada, no necesitas escribir contraseña.",
                        fg="#555"
                    )

            try:
                ventana_wifi.after(0, finalizar)
            except Exception:
                pass

        try:
            threading.Thread(target=trabajo, daemon=True).start()
        except NameError:
            # Respaldo por si threading no está disponible por alguna razón.
            trabajo()

    btn_actualizar_redes = tk.Button(
        frame_redes_header,
        text="Actualizar",
        font=("Segoe UI", 9, "bold"),
        bg="#52b788",
        fg="white",
        activebackground="#40916c",
        activeforeground="white",
        relief="flat",
        bd=0,
        command=escanear_redes
    )
    btn_actualizar_redes.pack(side="right", padx=6, pady=5)

    frame_lista_redes = tk.Frame(frame_redes, bg="white")
    frame_lista_redes.pack(fill="both", expand=True, padx=6, pady=(4, 2))

    frame_nav_redes = tk.Frame(frame_redes, bg="white", height=28)
    frame_nav_redes.pack(fill="x", padx=6, pady=(0, 4))
    frame_nav_redes.pack_propagate(False)

    def seleccionar_red(red):
        red_seleccionada["red"] = red
        entry_ssid.delete(0, tk.END)
        entry_ssid.insert(0, red["ssid"])
        actualizar_lista_redes()

        if red.get("guardada"):
            entry_password.delete(0, tk.END)
            lbl_wifi_estado.config(
                text=f"Red guardada: {red['ssid']}. Toca Conectar; no necesitas contraseña.",
                fg="#2d6a4f"
            )
            marcar_campo_activo(entry_password)
        elif not es_red_segura(red):
            entry_password.delete(0, tk.END)
            lbl_wifi_estado.config(
                text=f"Red abierta: {red['ssid']}. Puedes conectar sin contraseña.",
                fg="#2d6a4f"
            )
            marcar_campo_activo(entry_ssid)
        else:
            lbl_wifi_estado.config(
                text=f"Red seleccionada: {red['ssid']}. Escribe la contraseña.",
                fg="#555"
            )
            marcar_campo_activo(entry_password)

    def cambiar_pagina_redes(delta):
        total = len(redes_detectadas["lista"])
        paginas = max(1, (total + REDES_POR_PAGINA - 1) // REDES_POR_PAGINA)
        pagina_redes["pagina"] = max(0, min(paginas - 1, pagina_redes["pagina"] + delta))
        actualizar_lista_redes()

    def actualizar_lista_redes():
        for widget in frame_lista_redes.winfo_children():
            widget.destroy()
        for widget in frame_nav_redes.winfo_children():
            widget.destroy()

        redes = redes_detectadas["lista"]
        total = len(redes)

        if total == 0:
            tk.Label(
                frame_lista_redes,
                text="Toca Actualizar para buscar redes.",
                font=("Segoe UI", 10, "bold"),
                bg="white",
                fg="#555",
                wraplength=330
            ).pack(expand=True)
        else:
            inicio = pagina_redes["pagina"] * REDES_POR_PAGINA
            fin = inicio + REDES_POR_PAGINA
            visibles = redes[inicio:fin]

            for red in visibles:
                seleccionada = red_seleccionada["red"] and red_seleccionada["red"].get("ssid") == red.get("ssid")
                etiqueta_estado = "  ✓ Conectada" if red.get("en_uso") else ("  🔒 Guardada" if red.get("guardada") else "")
                seguridad = red.get("seguridad", "")
                texto = f"{barras_senal(red['senal'])}  {red['ssid']}{etiqueta_estado}\n{red['senal']}%  ·  {seguridad}"

                btn = tk.Button(
                    frame_lista_redes,
                    text=texto,
                    font=("Segoe UI", 8, "bold"),
                    justify="left",
                    anchor="w",
                    bg="#d8f3dc" if seleccionada else "#f8f9fa",
                    fg="#1b4332",
                    activebackground="#b7e4c7",
                    activeforeground="#1b4332",
                    relief="flat",
                    bd=0,
                    padx=8,
                    command=lambda r=red: seleccionar_red(r)
                )
                btn.pack(fill="x", pady=1)

        paginas = max(1, (total + REDES_POR_PAGINA - 1) // REDES_POR_PAGINA)
        texto_pagina = f"{pagina_redes['pagina'] + 1}/{paginas}" if total else "0/0"

        tk.Button(
            frame_nav_redes,
            text="◀",
            font=("Segoe UI", 9, "bold"),
            bg="#e9ecef",
            fg="#1b4332",
            relief="flat",
            bd=0,
            command=lambda: cambiar_pagina_redes(-1)
        ).pack(side="left", fill="both", expand=True, padx=2)

        tk.Label(
            frame_nav_redes,
            text=texto_pagina,
            font=("Segoe UI", 9, "bold"),
            bg="white",
            fg="#555"
        ).pack(side="left", fill="both", expand=True, padx=2)

        tk.Button(
            frame_nav_redes,
            text="▶",
            font=("Segoe UI", 9, "bold"),
            bg="#e9ecef",
            fg="#1b4332",
            relief="flat",
            bd=0,
            command=lambda: cambiar_pagina_redes(1)
        ).pack(side="left", fill="both", expand=True, padx=2)

    frame_campos = tk.Frame(
        frame_contenido,
        bg="white",
        highlightbackground="#b7e4c7",
        highlightthickness=2
    )
    frame_campos.pack(side="left", fill="both", expand=True)

    frame_campos.grid_columnconfigure(0, weight=0)
    frame_campos.grid_columnconfigure(1, weight=1)
    frame_campos.grid_columnconfigure(2, weight=0)

    tk.Label(
        frame_campos,
        text="Red seleccionada / SSID",
        font=("Segoe UI", 9, "bold"),
        bg="white",
        fg="#1b4332"
    ).grid(row=0, column=0, sticky="w", padx=8, pady=(8, 3))

    entry_ssid = tk.Entry(
        frame_campos,
        font=("Segoe UI", 12),
        bg="white",
        fg="#111",
        relief="solid",
        bd=1
    )
    entry_ssid.grid(row=0, column=1, columnspan=2, sticky="ew", padx=(0, 8), pady=(8, 3), ipady=3)

    tk.Label(
        frame_campos,
        text="Contraseña",
        font=("Segoe UI", 9, "bold"),
        bg="white",
        fg="#1b4332"
    ).grid(row=1, column=0, sticky="w", padx=8, pady=3)

    entry_password = tk.Entry(
        frame_campos,
        font=("Segoe UI", 12),
        bg="white",
        fg="#111",
        relief="solid",
        bd=1,
        show="*"
    )
    entry_password.grid(row=1, column=1, sticky="ew", padx=(0, 6), pady=3, ipady=3)

    def alternar_ver_password():
        password_visible["visible"] = not password_visible["visible"]
        if password_visible["visible"]:
            entry_password.config(show="")
            btn_ver_password.config(text="Ocultar")
        else:
            entry_password.config(show="*")
            btn_ver_password.config(text="Ver")

    btn_ver_password = tk.Button(
        frame_campos,
        text="Ver",
        font=("Segoe UI", 9, "bold"),
        bg="#d8f3dc",
        fg="#1b4332",
        activebackground="#b7e4c7",
        relief="flat",
        bd=0,
        command=alternar_ver_password
    )
    btn_ver_password.grid(row=1, column=2, padx=(0, 8), pady=3, sticky="nsew")

    lbl_wifi_estado = tk.Label(
        frame_campos,
        text="Selecciona una red de la lista o escribe el SSID manualmente.",
        font=("Segoe UI", 8, "bold"),
        bg="white",
        fg="#555",
        anchor="w",
        justify="left",
        wraplength=360
    )
    lbl_wifi_estado.grid(row=2, column=0, columnspan=3, sticky="ew", padx=8, pady=(4, 2))

    var_autoconectar = tk.BooleanVar(value=True)
    chk_autoconectar = tk.Checkbutton(
        frame_campos,
        text="Recordar y conectar automáticamente",
        variable=var_autoconectar,
        font=("Segoe UI", 8, "bold"),
        bg="white",
        fg="#1b4332",
        activebackground="white",
        activeforeground="#1b4332",
        selectcolor="white"
    )
    chk_autoconectar.grid(row=3, column=0, columnspan=3, sticky="w", padx=6, pady=(0, 2))

    def marcar_campo_activo(entry):
        campo_activo["entry"] = entry
        entry.focus_set()
        entry.icursor(tk.END)

        if entry is entry_ssid:
            entry_ssid.config(highlightbackground="#52b788", highlightthickness=2)
            entry_password.config(highlightthickness=0)
        else:
            entry_password.config(highlightbackground="#52b788", highlightthickness=2)
            entry_ssid.config(highlightthickness=0)

    entry_ssid.bind("<FocusIn>", lambda e: marcar_campo_activo(entry_ssid))
    entry_password.bind("<FocusIn>", lambda e: marcar_campo_activo(entry_password))
    entry_ssid.bind("<Button-1>", lambda e: marcar_campo_activo(entry_ssid))
    entry_password.bind("<Button-1>", lambda e: marcar_campo_activo(entry_password))

    # ---------- Función de conexión ----------
    def conectar_wifi():
        ssid = entry_ssid.get().strip()
        password = entry_password.get().strip()
        red = red_seleccionada["red"]

        if not ssid:
            lbl_wifi_estado.config(text="Selecciona una red o escribe el nombre de la red WiFi.", fg="#e63946")
            marcar_campo_activo(entry_ssid)
            return

        red_es_guardada = ssid in redes_guardadas["set"] or (red and red.get("guardada"))
        red_es_segura = es_red_segura(red) if red and red.get("ssid") == ssid else True

        if red_es_segura and not red_es_guardada and not password:
            lbl_wifi_estado.config(text="Esta red necesita contraseña. Escríbela para conectarte.", fg="#e63946")
            marcar_campo_activo(entry_password)
            return

        lbl_wifi_estado.config(text="Conectando a WiFi, espera un momento...", fg="#2d6a4f")
        ventana_wifi.update_idletasks()

        def intentar_comandos(comandos):
            ultimo_resultado = None
            for comando in comandos:
                try:
                    resultado = subprocess.run(
                        comando,
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                    ultimo_resultado = resultado
                    if resultado.returncode == 0:
                        return resultado
                except Exception as e:
                    ultimo_resultado = e
            return ultimo_resultado

        def trabajo_conexion():
            comandos = []

            if red_es_guardada:
                comandos.append(["nmcli", "connection", "up", "id", ssid])
                comandos.append(["nmcli", "dev", "wifi", "connect", ssid])

            if password:
                comandos.append(["nmcli", "dev", "wifi", "connect", ssid, "password", password])
            else:
                comandos.append(["nmcli", "dev", "wifi", "connect", ssid])

            resultado = intentar_comandos(comandos)

            def finalizar():
                if hasattr(resultado, "returncode") and resultado.returncode == 0:
                    if var_autoconectar.get():
                        # NetworkManager normalmente guarda la contraseña automáticamente.
                        # Esta línea refuerza que la red se conecte sola al arrancar o al estar cerca.
                        try:
                            subprocess.run(
                                ["nmcli", "connection", "modify", ssid, "connection.autoconnect", "yes"],
                                capture_output=True,
                                text=True,
                                timeout=8
                            )
                        except Exception:
                            pass

                    lbl_wifi_estado.config(text="Conexión WiFi realizada correctamente.", fg="#2d6a4f")
                    messagebox.showinfo(
                        "WiFi",
                        "Conexión WiFi realizada correctamente.\n\nLa red quedó guardada para conectarse automáticamente."
                    )
                    cerrar_wifi()
                else:
                    if hasattr(resultado, "stderr"):
                        error = resultado.stderr.strip() or resultado.stdout.strip() or "No se pudo conectar."
                    else:
                        error = str(resultado)
                    lbl_wifi_estado.config(text=f"No se pudo conectar: {error}", fg="#e63946")

            try:
                ventana_wifi.after(0, finalizar)
            except Exception:
                pass

        try:
            threading.Thread(target=trabajo_conexion, daemon=True).start()
        except NameError:
            trabajo_conexion()

    # ---------- Teclado táctil ----------
    frame_teclado = tk.Frame(
        ventana_wifi,
        bg="#dfeee8",
        highlightbackground="#b7e4c7",
        highlightthickness=2,
        height=226
    )
    frame_teclado.pack(fill="x", padx=10, pady=(0, 4))
    frame_teclado.pack_propagate(False)

    tk.Label(
        frame_teclado,
        text="TECLADO TÁCTIL COMPLETO",
        font=("Segoe UI", 7, "bold"),
        bg="#dfeee8",
        fg="#2d6a4f"
    ).pack(fill="x", pady=(1, 0))

    frame_filas_teclado = tk.Frame(frame_teclado, bg="#dfeee8")
    frame_filas_teclado.pack(fill="both", expand=True, padx=4, pady=1)

    botones_teclado = []

    filas_letras = [
        ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-", "_"],
        ["q", "w", "e", "r", "t", "y", "u", "i", "o", "p", "@", "."],
        ["a", "s", "d", "f", "g", "h", "j", "k", "l", "ñ", "/", "#"],
        ["Shift", "z", "x", "c", "v", "b", "n", "m", ",", "?", "Borrar"],
        ["123", "Caps", "Tab", "←", "Espacio", "→", "Limpiar", "OK"]
    ]

    filas_simbolos = [
        ["!", "?", "@", "#", "$", "%", "&", "*", "(", ")", "-", "_"],
        ["+", "=", "/", "\\", "|", "'", '"', ":", ";", ",", ".", "~"],
        ["[", "]", "{", "}", "<", ">", "^", "`", "¿", "¡", "°", "•"],
        ["ABC", "á", "é", "í", "ó", "ú", "ü", "ñ", "Borrar"],
        ["123", "Caps", "Tab", "←", "Espacio", "→", "Limpiar", "OK"]
    ]

    def obtener_entry_activo():
        if campo_activo["entry"] is None:
            marcar_campo_activo(entry_password if entry_ssid.get().strip() else entry_ssid)
        return campo_activo["entry"]

    def insertar_texto(texto):
        entry = obtener_entry_activo()
        try:
            pos = entry.index(tk.INSERT)
            entry.insert(pos, texto)
            entry.icursor(pos + len(texto))
        except Exception:
            entry.insert(tk.END, texto)

    def borrar_texto():
        entry = obtener_entry_activo()
        try:
            pos = entry.index(tk.INSERT)
            if pos > 0:
                entry.delete(pos - 1, pos)
                entry.icursor(pos - 1)
        except Exception:
            contenido = entry.get()
            entry.delete(0, tk.END)
            entry.insert(0, contenido[:-1])

    def limpiar_campo():
        entry = obtener_entry_activo()
        entry.delete(0, tk.END)

    def mover_cursor(delta):
        entry = obtener_entry_activo()
        pos = entry.index(tk.INSERT)
        nuevo = max(0, min(len(entry.get()), pos + delta))
        entry.icursor(nuevo)

    def tecla_ok():
        if campo_activo["entry"] is entry_ssid:
            marcar_campo_activo(entry_password)
        else:
            conectar_wifi()

    def presionar_tecla(tecla):
        if tecla == "Borrar":
            borrar_texto()
        elif tecla == "Limpiar":
            limpiar_campo()
        elif tecla == "Espacio":
            insertar_texto(" ")
        elif tecla == "Tab":
            if campo_activo["entry"] is entry_ssid:
                marcar_campo_activo(entry_password)
            else:
                marcar_campo_activo(entry_ssid)
        elif tecla == "OK":
            tecla_ok()
        elif tecla == "←":
            mover_cursor(-1)
        elif tecla == "→":
            mover_cursor(1)
        elif tecla == "Shift":
            teclado_modo["mayus"] = not teclado_modo["mayus"]
            redibujar_teclado()
        elif tecla == "Caps":
            teclado_modo["caps"] = not teclado_modo["caps"]
            redibujar_teclado()
        elif tecla in ("123", "ABC"):
            teclado_modo["simbolos"] = not teclado_modo["simbolos"]
            redibujar_teclado()
        else:
            texto = tecla
            if texto.isalpha():
                if teclado_modo["mayus"] or teclado_modo["caps"]:
                    texto = texto.upper()
                else:
                    texto = texto.lower()
            insertar_texto(texto)
            if teclado_modo["mayus"] and not teclado_modo["caps"]:
                teclado_modo["mayus"] = False
                redibujar_teclado()

    def color_tecla(tecla):
        if tecla in ("Borrar", "Limpiar"):
            return "#ffd6d6", "#7f1d1d"
        if tecla == "OK":
            return "#52b788", "white"
        if tecla in ("Shift", "Caps", "123", "ABC", "Tab", "←", "→"):
            return "#b7e4c7", "#1b4332"
        if tecla == "Espacio":
            return "#ffffff", "#1b4332"
        return "#ffffff", "#111111"

    def texto_visible_tecla(tecla):
        if tecla == "Borrar":
            return "⌫ Borrar"
        if tecla == "Limpiar":
            return "Limpiar"
        if tecla == "Espacio":
            return "Espacio"
        if tecla == "Tab":
            return "Tab"
        if tecla == "Shift":
            return "Shift" if not teclado_modo["mayus"] else "SHIFT"
        if tecla == "Caps":
            return "Caps" if not teclado_modo["caps"] else "CAPS"
        if tecla == "OK":
            return "OK"
        if tecla.isalpha() and (teclado_modo["mayus"] or teclado_modo["caps"]):
            return tecla.upper()
        return tecla

    def redibujar_teclado():
        for widget in frame_filas_teclado.winfo_children():
            widget.destroy()
        botones_teclado.clear()

        filas = filas_simbolos if teclado_modo["simbolos"] else filas_letras

        for fila in filas:
            frame_fila = tk.Frame(frame_filas_teclado, bg="#dfeee8")
            frame_fila.pack(fill="both", expand=True, pady=1)

            for tecla in fila:
                bg, fg = color_tecla(tecla)
                padx = 1
                if tecla == "Espacio":
                    padx = 8
                elif tecla in ("Borrar", "Limpiar"):
                    padx = 4
                elif tecla in ("Shift", "Caps", "Tab", "OK"):
                    padx = 3

                btn = tk.Button(
                    frame_fila,
                    text=texto_visible_tecla(tecla),
                    font=("Segoe UI", 8, "bold"),
                    bg=bg,
                    fg=fg,
                    activebackground="#d8f3dc",
                    activeforeground=fg,
                    relief="flat",
                    bd=0,
                    command=lambda t=tecla: presionar_tecla(t)
                )
                btn.pack(side="left", fill="both", expand=True, padx=1, pady=1, ipadx=padx)
                botones_teclado.append(btn)

    # ---------- Botones inferiores ----------
    frame_wifi_botones = tk.Frame(ventana_wifi, bg="#f4f7f6", height=35)
    frame_wifi_botones.pack(fill="x", padx=10, pady=(0, 5))
    frame_wifi_botones.pack_propagate(False)

    tk.Button(
        frame_wifi_botones,
        text="Conectar WiFi",
        font=("Segoe UI", 11, "bold"),
        bg="#52b788",
        fg="white",
        activebackground="#40916c",
        activeforeground="white",
        relief="flat",
        bd=0,
        command=conectar_wifi
    ).pack(side="left", fill="both", expand=True, padx=5)

    tk.Button(
        frame_wifi_botones,
        text="Cancelar",
        font=("Segoe UI", 11, "bold"),
        bg="#adb5bd",
        fg="#111",
        activebackground="#ced4da",
        activeforeground="#111",
        relief="flat",
        bd=0,
        command=cerrar_wifi
    ).pack(side="left", fill="both", expand=True, padx=5)

    actualizar_lista_redes()
    redibujar_teclado()
    ventana_wifi.after(150, lambda: marcar_campo_activo(entry_ssid))
    ventana_wifi.after(350, escanear_redes)


# ==========================================
# LÓGICA DE MONITOREO DE SENSORES
# ==========================================
# Esta sección mantiene la comunicación UART, pero ahora organiza los datos
# por Nodo 1, Nodo 2 y Nodo 3 para mostrar solamente monitoreo.

PATRON_PAREN = re.compile(
    r"\(\s*([\d.+-]+)\s*,\s*([\d.+-]+)\s*,\s*([\d.+-]+)\s*,\s*([\d.+-]+)\s*,\s*([\d.+-]+)\s*\)"
)

PATRON_LOG_NODO = re.compile(
    r"N\s*([123])\s*\|\s*"
    r"S1:\s*([\d.+-]+)\s*%\s*\|\s*"
    r"S2:\s*([\d.+-]+)\s*%\s*\|\s*"
    r"S3:\s*([\d.+-]+)\s*%.*?\|\s*"
    r"T:\s*([\d.+-]+)\s*C\s*\|\s*"
    r"H:\s*([\d.+-]+)\s*%",
    re.IGNORECASE
)


def crear_estado_nodo():
    return {
        "s1": None,
        "s2": None,
        "s3": None,
        "temp": None,
        "hum": None,
        "prom": None,
        "ultimo": "Sin lectura",
        "linea": "",
        # Último momento en que la Raspberry recibió datos reales de este nodo.
        # Se usa para mostrar el circulito verde/rojo de conexión LoRa.
        "last_rx_epoch": 0
    }


datos_nodos = {
    1: crear_estado_nodo(),
    2: crear_estado_nodo(),
    3: crear_estado_nodo()
}

labels_resumen = {}
labels_detalle = {}
ventanas_detalle = {}
resumen_widgets = {}

# ==========================================
# ESTADO DE CONEXIÓN LORA POR NODO - SAVIA_LORA_DOTS_ULTIMA_LECTURA
# ==========================================
# Si un nodo no manda datos durante este tiempo, se considera sin comunicación reciente.
# Para tus nodos, que normalmente mandan cada pocos segundos, 45 s da margen suficiente
# sin tardarse demasiado en avisar si se pierde la comunicación.
TIEMPO_MAX_SIN_DATO_LORA = 45

COLOR_LORA_CONECTADO = "#2d6a4f"
COLOR_LORA_DESCONECTADO = "#e63946"
COLOR_LORA_ESPERANDO = "#adb5bd"

# ==========================================
# PERSONALIZACIÓN DE NOMBRES Y AJUSTES DE USUARIO - SAVIA_UI_CONFIG_CLIENTE
# ==========================================
RUTA_NOMBRES_UI = os.environ.get(
    "SAVIA_NOMBRES_UI",
    "/home/savia/savia_nombres_ui.json"
)

RUTA_AJUSTES_USUARIO = os.environ.get(
    "SAVIA_AJUSTES_USUARIO",
    "/home/savia/savia_ajustes_usuario.json"
)

nombres_ui = {
    "nodos": {
        "1": "Humedad Nodo 1",
        "2": "Humedad Nodo 2",
        "3": "Humedad Nodo 3"
    },
    "sensores": {
        "1": {"s1": "Sensor de suelo 1", "s2": "Sensor de suelo 2", "s3": "Sensor de suelo 3"},
        "2": {"s1": "Sensor de suelo 1", "s2": "Sensor de suelo 2", "s3": "Sensor de suelo 3"},
        "3": {"s1": "Sensor de suelo 1", "s2": "Sensor de suelo 2", "s3": "Sensor de suelo 3"}
    }
}

ajustes_usuario = {
    "brillo": 80
}


def _cargar_json_seguro(ruta, default):
    try:
        if not os.path.exists(ruta):
            return default
        with open(ruta, "r", encoding="utf-8") as archivo:
            datos = json.load(archivo)
        if isinstance(datos, dict):
            copia = json.loads(json.dumps(default, ensure_ascii=False))
            def mezclar(base, nuevo):
                for k, v in nuevo.items():
                    if isinstance(v, dict) and isinstance(base.get(k), dict):
                        mezclar(base[k], v)
                    else:
                        base[k] = v
            mezclar(copia, datos)
            return copia
    except Exception as e:
        print(f"No se pudo cargar configuración {ruta}: {e}")
    return default


def _guardar_json_seguro(ruta, datos):
    try:
        carpeta = os.path.dirname(ruta)
        if carpeta:
            os.makedirs(carpeta, exist_ok=True)
        with open(ruta, "w", encoding="utf-8") as archivo:
            json.dump(datos, archivo, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"No se pudo guardar configuración {ruta}: {e}")


def cargar_nombres_ui():
    global nombres_ui
    nombres_ui = _cargar_json_seguro(RUTA_NOMBRES_UI, nombres_ui)


def guardar_nombres_ui():
    _guardar_json_seguro(RUTA_NOMBRES_UI, nombres_ui)


def cargar_ajustes_usuario():
    global ajustes_usuario
    ajustes_usuario = _cargar_json_seguro(RUTA_AJUSTES_USUARIO, ajustes_usuario)


def guardar_ajustes_usuario():
    _guardar_json_seguro(RUTA_AJUSTES_USUARIO, ajustes_usuario)


def nombre_nodo(nodo):
    return nombres_ui.get("nodos", {}).get(str(nodo), f"Humedad Nodo {nodo}")


def nombre_sensor(nodo, sensor):
    return nombres_ui.get("sensores", {}).get(str(nodo), {}).get(sensor, f"Sensor de suelo {sensor[-1]}")


def refrescar_textos_personalizados():
    for nodo, widgets in labels_resumen.items():
        if "titulo" in widgets:
            widgets["titulo"].config(text=nombre_nodo(nodo))
    for nodo, detalle in labels_detalle.items():
        if "titulo_ventana" in detalle:
            detalle["titulo_ventana"].config(text=f"🌱 {nombre_nodo(nodo)} - Detalle")
        if "prom_titulo" in detalle:
            detalle["prom_titulo"].config(text=f"Promedio · {nombre_nodo(nodo)}")
        for sensor in ("s1", "s2", "s3"):
            key = f"{sensor}_titulo"
            if key in detalle:
                detalle[key].config(text=nombre_sensor(nodo, sensor))


def abrir_editor_texto(titulo, valor_actual, callback_guardar):
    editor = tk.Toplevel(ventana)
    editor.title(titulo)
    editor.geometry("800x480+0+0")
    editor.configure(bg="#f4f7f6")
    editor.resizable(False, False)
    editor.transient(ventana)
    editor.grab_set()
    editor.focus_force()
    try:
        editor.attributes("-fullscreen", True)
    except Exception:
        pass

    mayus = {"activo": False}

    def cerrar():
        try:
            editor.grab_release()
        except Exception:
            pass
        editor.destroy()

    def guardar():
        nuevo = entry.get().strip()
        if not nuevo:
            messagebox.showwarning("Dato faltante", "Escribe un nombre válido.")
            return
        callback_guardar(nuevo)
        cerrar()

    header = tk.Frame(editor, bg="#2d6a4f", height=54)
    header.pack(fill="x")
    header.pack_propagate(False)
    tk.Label(header, text=titulo, font=("Segoe UI", 15, "bold"), bg="#2d6a4f", fg="white").pack(side="left", padx=18)
    tk.Button(header, text="Cancelar", font=("Segoe UI", 11, "bold"), bg="white", fg="#2d6a4f", relief="flat", bd=0, padx=14, command=cerrar).pack(side="right", padx=10, pady=8)

    frame = tk.Frame(editor, bg="#f4f7f6", padx=28, pady=16)
    frame.pack(fill="both", expand=True)

    tk.Label(frame, text="Nuevo nombre", font=("Segoe UI", 12, "bold"), bg="#f4f7f6", fg="#1b4332").pack(anchor="w")
    entry = tk.Entry(frame, font=("Segoe UI", 18, "bold"), justify="center", bg="white", fg="#1b4332", highlightthickness=2, highlightbackground="#b7e4c7")
    entry.pack(fill="x", pady=(6, 14), ipady=8)
    entry.insert(0, valor_actual)
    entry.focus_set()
    entry.selection_range(0, "end")

    frame_teclado = tk.Frame(frame, bg="#f4f7f6")
    frame_teclado.pack(fill="both", expand=True)

    def tecla(t):
        if t == "Borrar":
            pos = entry.index(tk.INSERT)
            if pos > 0:
                entry.delete(pos - 1, pos)
        elif t == "Limpiar":
            entry.delete(0, "end")
        elif t == "Espacio":
            entry.insert(tk.INSERT, " ")
        elif t == "Mayús":
            mayus["activo"] = not mayus["activo"]
            redibujar()
        elif t == "Guardar":
            guardar()
        else:
            entry.insert(tk.INSERT, t.upper() if mayus["activo"] and t.isalpha() else t)

    def redibujar():
        for h in frame_teclado.winfo_children():
            h.destroy()
        filas = [
            list("1234567890"),
            list("qwertyuiop"),
            list("asdfghjklñ"),
            list("zxcvbnm-_"),
            ["Mayús", "Espacio", "Borrar", "Limpiar", "Guardar"]
        ]
        for fila in filas:
            fr = tk.Frame(frame_teclado, bg="#f4f7f6")
            fr.pack(fill="x", pady=3)
            for t in fila:
                ancho = 6
                if t == "Espacio": ancho = 18
                if t in ("Borrar", "Limpiar", "Guardar", "Mayús"): ancho = 9
                bg = "#52b788" if t == "Guardar" else "white"
                fg = "white" if t == "Guardar" else "#1b4332"
                tk.Button(fr, text=t, font=("Segoe UI", 10, "bold"), bg=bg, fg=fg, relief="flat", bd=0, width=ancho, height=1, command=lambda x=t: tecla(x)).pack(side="left", expand=True, fill="x", padx=3)
    redibujar()


def abrir_config_nombres():
    win = tk.Toplevel(ventana)
    win.title("Personalizar nombres")
    win.geometry("800x480+0+0")
    win.configure(bg="#f4f7f6")
    win.resizable(False, False)
    win.transient(ventana)
    win.grab_set()
    win.focus_force()
    try:
        win.attributes("-fullscreen", True)
    except Exception:
        pass

    def cerrar():
        try:
            win.grab_release()
        except Exception:
            pass
        win.destroy()

    def editar_nodo(nodo):
        abrir_editor_texto(
            f"Editar nombre del Nodo {nodo}",
            nombre_nodo(nodo),
            lambda nuevo, n=nodo: guardar_nombre_nodo(n, nuevo)
        )

    def editar_sensor(nodo, sensor):
        abrir_editor_texto(
            f"Editar {sensor.upper()} · Nodo {nodo}",
            nombre_sensor(nodo, sensor),
            lambda nuevo, n=nodo, s=sensor: guardar_nombre_sensor(n, s, nuevo)
        )

    def guardar_nombre_nodo(nodo, nuevo):
        nombres_ui["nodos"][str(nodo)] = nuevo
        guardar_nombres_ui()
        refrescar_textos_personalizados()
        construir_lista()

    def guardar_nombre_sensor(nodo, sensor, nuevo):
        nombres_ui["sensores"][str(nodo)][sensor] = nuevo
        guardar_nombres_ui()
        refrescar_textos_personalizados()
        construir_lista()

    header = tk.Frame(win, bg="#2d6a4f", height=54)
    header.pack(fill="x")
    header.pack_propagate(False)
    tk.Label(header, text="✏️ Personalizar nombres", font=("Segoe UI", 16, "bold"), bg="#2d6a4f", fg="white").pack(side="left", padx=18)
    tk.Button(header, text="Cerrar", font=("Segoe UI", 11, "bold"), bg="white", fg="#2d6a4f", relief="flat", bd=0, padx=14, command=cerrar).pack(side="right", padx=12, pady=8)

    canvas = tk.Canvas(win, bg="#f4f7f6", highlightthickness=0)
    scroll = tk.Scrollbar(win, orient="vertical", command=canvas.yview, width=18)
    contenido = tk.Frame(canvas, bg="#f4f7f6", padx=18, pady=12)
    canvas_win = canvas.create_window((0, 0), window=contenido, anchor="nw")
    canvas.configure(yscrollcommand=scroll.set)
    canvas.pack(side="left", fill="both", expand=True)
    scroll.pack(side="right", fill="y")

    def ajustar_scroll(e=None):
        canvas.configure(scrollregion=canvas.bbox("all"))
        canvas.itemconfig(canvas_win, width=canvas.winfo_width())
    contenido.bind("<Configure>", ajustar_scroll)
    canvas.bind("<Configure>", ajustar_scroll)

    def construir_lista():
        for h in contenido.winfo_children():
            h.destroy()
        tk.Label(contenido, text="Toca un campo para cambiar el nombre que verá el usuario.", font=("Segoe UI", 11, "bold"), bg="#f4f7f6", fg="#6c757d").pack(anchor="w", pady=(0, 10))
        for nodo in (1, 2, 3):
            card = tk.Frame(contenido, bg="white", highlightbackground="#b7e4c7", highlightthickness=2, padx=12, pady=10)
            card.pack(fill="x", pady=8)
            tk.Label(card, text=f"Nodo {nodo}", font=("Segoe UI", 13, "bold"), bg="white", fg="#1b4332").pack(anchor="w")
            tk.Button(card, text=f"Título: {nombre_nodo(nodo)}", font=("Segoe UI", 11, "bold"), bg="#eaf4f4", fg="#1b4332", relief="flat", bd=0, anchor="w", padx=12, pady=8, command=lambda n=nodo: editar_nodo(n)).pack(fill="x", pady=4)
            for sensor in ("s1", "s2", "s3"):
                tk.Button(card, text=f"{sensor.upper()}: {nombre_sensor(nodo, sensor)}", font=("Segoe UI", 10, "bold"), bg="#f8f9fa", fg="#1b4332", relief="flat", bd=0, anchor="w", padx=12, pady=7, command=lambda n=nodo, s=sensor: editar_sensor(n, s)).pack(fill="x", pady=3)
    construir_lista()



# ==========================================
# CONTROL REAL DE VOLUMEN / BRILLO / TEMA - SAVIA_CONFIG_REAL
# ==========================================
def _entorno_grafico():
    """Entorno para comandos gráficos cuando la app corre desde SSH con DISPLAY=:0."""
    env = os.environ.copy()
    env.setdefault("DISPLAY", ":0")
    xauth = f"/home/{os.environ.get('USER', 'savia')}/.Xauthority"
    if os.path.exists(xauth):
        env.setdefault("XAUTHORITY", xauth)
    return env


def ejecutar_comando_sistema_ui(comando, timeout=3):
    """Ejecuta comandos del sistema y devuelve True/False sin romper la interfaz."""
    try:
        r = subprocess.run(
            comando,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
            env=_entorno_grafico()
        )
        return r.returncode == 0
    except Exception as e:
        print(f"No se pudo ejecutar {comando}: {e}")
        return False


def _crear_wav_bip():
    """Crea un beep corto para probar volumen y para alertas."""
    ruta = "/tmp/savia_bip.wav"
    try:
        if os.path.exists(ruta):
            return ruta
        sample_rate = 44100
        duracion = 0.16
        frecuencia = 950
        amplitud = 0.45
        n = int(sample_rate * duracion)
        with wave.open(ruta, "w") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            for i in range(n):
                valor = int(32767 * amplitud * math.sin(2 * math.pi * frecuencia * i / sample_rate))
                wav.writeframes(struct.pack("<h", valor))
        return ruta
    except Exception as e:
        print(f"No se pudo crear bip WAV: {e}")
        return None


def reproducir_bip_prueba():
    """Hace un bip audible respetando el volumen configurado, con varios fallbacks."""
    volumen = max(0, min(100, int(ajustes_usuario.get("volumen", 70))))
    if volumen <= 0:
        return

    ruta = _crear_wav_bip()

    # Primero PulseAudio/PipeWire con volumen proporcional.
    if ruta:
        vol_pulse = int(65536 * volumen / 100)
        if ejecutar_comando_sistema_ui(["paplay", f"--volume={vol_pulse}", ruta], timeout=2):
            return
        if ejecutar_comando_sistema_ui(["aplay", "-q", ruta], timeout=2):
            return

    # Fallback de Tkinter.
    try:
        ventana.bell()
    except Exception:
        pass

def ejecutar_comando_silencioso(comando):
    return ejecutar_comando_sistema_ui(comando, timeout=3)


def aplicar_volumen(valor):
    """Aplica volumen real al sistema y guarda ajuste."""
    valor = max(0, min(100, int(float(valor))))
    ajustes_usuario["volumen"] = valor
    guardar_ajustes_usuario()

    aplicado = False

    # PipeWire/PulseAudio, común en Ubuntu 24.04.
    aplicado = ejecutar_comando_sistema_ui(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{valor}%"], timeout=3)

    # ALSA como respaldo.
    if not aplicado:
        aplicado = ejecutar_comando_sistema_ui(["amixer", "set", "Master", f"{valor}%"], timeout=3)

    # Actualizar etiqueta si existe.
    try:
        lbl_valor_volumen.config(text=f"{valor}%")
    except Exception:
        pass

    return aplicado


def probar_volumen_usuario():
    aplicar_volumen(ajustes_usuario.get("volumen", 70))
    reproducir_bip_prueba()

def _salida_xrandr_principal():
    try:
        r = subprocess.run(["xrandr", "--current"], capture_output=True, text=True, timeout=2)
        lineas = r.stdout.splitlines()
        for linea in lineas:
            if " connected primary" in linea:
                return linea.split()[0]
        for linea in lineas:
            if " connected" in linea:
                return linea.split()[0]
    except Exception:
        pass
    return None


def aplicar_brillo(valor):
    """Aplica brillo real usando brightnessctl/backlight/xrandr y guarda ajuste."""
    valor = max(10, min(100, int(float(valor))))
    ajustes_usuario["brillo"] = valor
    guardar_ajustes_usuario()

    aplicado = False

    # 1) brightnessctl si está instalado y tiene permisos.
    aplicado = ejecutar_comando_sistema_ui(["brightnessctl", "set", f"{valor}%"], timeout=3)

    # 2) sysfs backlight como respaldo, si el usuario tiene permisos.
    if not aplicado:
        try:
            import glob as _glob
            for carpeta in _glob.glob("/sys/class/backlight/*"):
                max_b = int(Path(carpeta, "max_brightness").read_text().strip())
                nuevo = max(1, int(max_b * valor / 100))
                Path(carpeta, "brightness").write_text(str(nuevo))
                aplicado = True
                break
        except Exception as e:
            print(f"No se pudo ajustar brillo por backlight: {e}")

    # 3) xrandr no cambia el backlight físico, pero sí oscurece/aclara la imagen.
    if not aplicado:
        salida = _salida_xrandr_principal()
        if salida:
            aplicado = ejecutar_comando_sistema_ui(
                ["xrandr", "--output", salida, "--brightness", f"{valor/100:.2f}"],
                timeout=3
            )

    try:
        lbl_valor_brillo.config(text=f"{valor}%")
    except Exception:
        pass

    return aplicado

def _colores_tema():
    oscuro = ajustes_usuario.get("tema", "claro") == "oscuro"
    if oscuro:
        return {
            "fondo": "#0f1720",
            "panel": "#15232b",
            "panel2": "#20323b",
            "texto": "#f1faee",
            "texto_sec": "#b7c9c0",
            "borde": "#2f4f4f",
            "verde": "#2d6a4f",
            "verde2": "#40916c",
            "suave": "#20323b"
        }
    return {
        "fondo": "#f4f7f6",
        "panel": "white",
        "panel2": "#f8fbfa",
        "texto": "#1b4332",
        "texto_sec": "#6c757d",
        "borde": "#b7e4c7",
        "verde": "#2d6a4f",
        "verde2": "#52b788",
        "suave": "#eaf4f4"
    }


def aplicar_tema_global():
    """Aplica modo claro/oscuro de forma visible en la pantalla principal y ventanas abiertas."""
    c = _colores_tema()
    protegidos_bg = {"#2d6a4f", "#1b4332", "#40916c", "#52b788", "#e63946", "#f4a261"}

    def aplicar(w):
        try:
            cls = w.winfo_class()
            if cls in ("Frame", "TFrame", "Canvas"):
                bg = str(w.cget("bg")) if "bg" in w.keys() else ""
                if bg not in protegidos_bg:
                    if bg in ("white", "#f8fbfa", "#f8f9fa", "#eaf4f4", "#e9ecef", "#f4f7f6", "#20323b", "#15232b", "#0f1720", ""):
                        w.config(bg=c["fondo"] if bg in ("#f4f7f6", "#0f1720", "") else c["panel"])
            elif cls in ("Label", "Button", "Entry", "Scale"):
                bg = str(w.cget("bg")) if "bg" in w.keys() else ""
                fg = str(w.cget("fg")) if "fg" in w.keys() else ""
                if bg not in protegidos_bg:
                    if bg in ("white", "#f8fbfa", "#f8f9fa", "#eaf4f4", "#e9ecef", "#f4f7f6", "#20323b", "#15232b", "#0f1720", ""):
                        w.config(bg=c["panel"] if cls != "Entry" else c["panel2"])
                if fg not in ("white", "#e63946"):
                    if fg in ("#6c757d", "#777", "#555", "#b7c9c0"):
                        w.config(fg=c["texto_sec"])
                    else:
                        w.config(fg=c["texto"])
                if cls == "Entry":
                    w.config(insertbackground=c["texto"])
            if "highlightbackground" in w.keys():
                hb = str(w.cget("highlightbackground"))
                if hb in ("#b7e4c7", "#2f4f4f"):
                    w.config(highlightbackground=c["borde"])
        except Exception:
            pass
        for h in w.winfo_children():
            aplicar(h)

    try:
        ventana.configure(bg=c["fondo"])
        aplicar(ventana)
        refrescar_tema_botones_config()
    except Exception as e:
        print(f"No se pudo aplicar tema: {e}")


def refrescar_tema_botones_config():
    try:
        tema = ajustes_usuario.get("tema", "claro")
        btn_tema_claro.config(bg="#52b788" if tema == "claro" else "#eaf4f4", fg="white" if tema == "claro" else "#1b4332")
        btn_tema_oscuro.config(bg="#1b4332" if tema == "oscuro" else "#eaf4f4", fg="white" if tema == "oscuro" else "#1b4332")
    except Exception:
        pass

def abrir_config_usuario():
    win = tk.Toplevel(ventana)
    win.title("Configuración de usuario")
    win.geometry("800x480+0+0")
    win.configure(bg=_colores_tema()["fondo"])
    win.resizable(False, False)
    win.transient(ventana)
    win.grab_set()
    win.focus_force()
    try:
        win.attributes("-fullscreen", True)
    except Exception:
        pass

    def cerrar():
        try:
            win.grab_release()
        except Exception:
            pass
        win.destroy()

    header = tk.Frame(win, bg="#2d6a4f", height=54)
    header.pack(fill="x")
    header.pack_propagate(False)
    tk.Label(header, text="⚙️ Configuración de usuario", font=("Segoe UI", 16, "bold"), bg="#2d6a4f", fg="white").pack(side="left", padx=18)
    tk.Button(header, text="Cerrar", font=("Segoe UI", 11, "bold"), bg="white", fg="#2d6a4f", relief="flat", bd=0, padx=14, command=cerrar).pack(side="right", padx=12, pady=8)

    body = tk.Frame(win, bg=_colores_tema()["fondo"], padx=24, pady=18)
    body.pack(fill="both", expand=True)

    def tarjeta(titulo, subtitulo):
        c = _colores_tema()
        f = tk.Frame(body, bg=c["panel"], highlightbackground=c["borde"], highlightthickness=2, padx=18, pady=12)
        f.pack(fill="x", pady=7)
        tk.Label(f, text=titulo, font=("Segoe UI", 14, "bold"), bg=c["panel"], fg=c["texto"]).pack(anchor="w")
        tk.Label(f, text=subtitulo, font=("Segoe UI", 9, "bold"), bg=c["panel"], fg=c["texto_sec"]).pack(anchor="w", pady=(2, 8))
        return f

    # ---------------- Volumen real ----------------
    f_vol = tarjeta("🔊 Volumen", "Mueve el control y escucha un bip de prueba con ese volumen.")
    fila_vol = tk.Frame(f_vol, bg=_colores_tema()["panel"])
    fila_vol.pack(fill="x")
    global lbl_valor_volumen
    lbl_valor_volumen = tk.Label(fila_vol, text=f"{int(ajustes_usuario.get('volumen', 70))}%", font=("Segoe UI", 12, "bold"), bg=_colores_tema()["panel"], fg=_colores_tema()["texto"], width=6)
    lbl_valor_volumen.pack(side="right", padx=(10, 0))

    vol_after = {"id": None}
    def mover_volumen(v):
        valor = int(float(v))
        ajustes_usuario["volumen"] = valor
        lbl_valor_volumen.config(text=f"{valor}%")
        if vol_after["id"]:
            ventana.after_cancel(vol_after["id"])
        vol_after["id"] = ventana.after(450, lambda: (aplicar_volumen(valor), reproducir_bip_prueba()))

    s_vol = tk.Scale(fila_vol, from_=0, to=100, orient="horizontal", font=("Segoe UI", 10, "bold"), bg=_colores_tema()["panel"], fg=_colores_tema()["texto"], highlightthickness=0, command=mover_volumen)
    s_vol.set(int(ajustes_usuario.get("volumen", 70)))
    s_vol.pack(side="left", fill="x", expand=True)
    tk.Button(f_vol, text="Probar bip", font=("Segoe UI", 11, "bold"), bg="#52b788", fg="white", relief="flat", bd=0, height=1, command=probar_volumen_usuario).pack(fill="x", pady=(8, 0))

    # ---------------- Brillo real ----------------
    f_bri = tarjeta("☀️ Brillo", "Ajusta el brillo real de la pantalla. Si el hardware no permite backlight, se ajusta el brillo visual.")
    fila_bri = tk.Frame(f_bri, bg=_colores_tema()["panel"])
    fila_bri.pack(fill="x")
    global lbl_valor_brillo
    lbl_valor_brillo = tk.Label(fila_bri, text=f"{int(ajustes_usuario.get('brillo', 80))}%", font=("Segoe UI", 12, "bold"), bg=_colores_tema()["panel"], fg=_colores_tema()["texto"], width=6)
    lbl_valor_brillo.pack(side="right", padx=(10, 0))

    bri_after = {"id": None}
    def mover_brillo(v):
        valor = int(float(v))
        ajustes_usuario["brillo"] = valor
        lbl_valor_brillo.config(text=f"{valor}%")
        if bri_after["id"]:
            ventana.after_cancel(bri_after["id"])
        bri_after["id"] = ventana.after(250, lambda: aplicar_brillo(valor))

    s_bri = tk.Scale(fila_bri, from_=10, to=100, orient="horizontal", font=("Segoe UI", 10, "bold"), bg=_colores_tema()["panel"], fg=_colores_tema()["texto"], highlightthickness=0, command=mover_brillo)
    s_bri.set(int(ajustes_usuario.get("brillo", 80)))
    s_bri.pack(side="left", fill="x", expand=True)

    # ---------------- Apariencia real ----------------
    f_tema = tarjeta("🌓 Apariencia", "Cambia inmediatamente entre modo claro y modo oscuro.")
    def set_tema(t):
        ajustes_usuario["tema"] = t
        guardar_ajustes_usuario()
        aplicar_tema_global()
        aplicar_tema_a_ventana_config(win)

    botones = tk.Frame(f_tema, bg=_colores_tema()["panel"])
    botones.pack(fill="x")
    global btn_tema_claro, btn_tema_oscuro
    btn_tema_claro = tk.Button(botones, text="Modo claro", font=("Segoe UI", 12, "bold"), relief="flat", bd=0, height=2, command=lambda: set_tema("claro"))
    btn_tema_claro.pack(side="left", fill="x", expand=True, padx=(0, 6))
    btn_tema_oscuro = tk.Button(botones, text="Modo oscuro", font=("Segoe UI", 12, "bold"), relief="flat", bd=0, height=2, command=lambda: set_tema("oscuro"))
    btn_tema_oscuro.pack(side="left", fill="x", expand=True, padx=(6, 0))
    refrescar_tema_botones_config()
    aplicar_tema_a_ventana_config(win)


def aplicar_tema_a_ventana_config(win):
    """Refresca colores de la ventana de configuración visible."""
    c = _colores_tema()
    try:
        win.configure(bg=c["fondo"])
        for w in win.winfo_children():
            # Se reutiliza el aplicador global desde la raíz para mantener consistencia.
            pass
        aplicar_tema_global()
    except Exception:
        pass


# ==========================================
# ALERTAS / RECORDATORIOS DE RIEGO - SAVIA_ALERTAS_RIEGO_RELOJ_REAL_V1
# ==========================================
# Estas alertas son recordatorios visuales para el usuario. No activan la bomba.
# Sirven para mostrar cuánto falta para regar cada nodo y marcarlo como listo.
RUTA_ALERTAS_RIEGO = os.environ.get(
    "SAVIA_ALERTAS_RIEGO",
    "/home/savia/savia_alertas_riego.json"
)


def crear_estado_alerta_riego():
    return {
        "activo": False,
        "intervalo_dias": 3,
        "intervalo_horas": 0,
        "duracion_horas": 24,
        "proximo_riego": "",
        "proximo_riego_ts": 0,
        "ultimo_listo": ""
    }


alertas_riego = {
    1: crear_estado_alerta_riego(),
    2: crear_estado_alerta_riego(),
    3: crear_estado_alerta_riego()
}


def cargar_alertas_riego():
    try:
        if not os.path.exists(RUTA_ALERTAS_RIEGO):
            return

        with open(RUTA_ALERTAS_RIEGO, "r", encoding="utf-8") as archivo:
            datos = json.load(archivo)

        for nodo in (1, 2, 3):
            clave = str(nodo)
            if clave in datos and isinstance(datos[clave], dict):
                estado = crear_estado_alerta_riego()
                estado.update(datos[clave])
                alertas_riego[nodo] = estado
    except Exception as e:
        print(f"No se pudieron cargar alertas de riego: {e}")


def guardar_alertas_riego():
    try:
        carpeta = os.path.dirname(RUTA_ALERTAS_RIEGO)
        if carpeta:
            os.makedirs(carpeta, exist_ok=True)

        datos = {str(nodo): alertas_riego[nodo] for nodo in (1, 2, 3)}
        with open(RUTA_ALERTAS_RIEGO, "w", encoding="utf-8") as archivo:
            json.dump(datos, archivo, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"No se pudieron guardar alertas de riego: {e}")


def _leer_fecha_alerta(texto):
    if not texto:
        return None
    try:
        return datetime.fromisoformat(texto)
    except Exception:
        return None


def _guardar_fecha_alerta(dt):
    return dt.replace(microsecond=0).isoformat()


def obtener_intervalo_alerta(alerta):
    try:
        dias = max(0, int(alerta.get("intervalo_dias", 3)))
    except Exception:
        dias = 3

    try:
        horas = max(0, int(alerta.get("intervalo_horas", 0)))
    except Exception:
        horas = 0

    # Evita un intervalo de 0, porque dejaría la alerta siempre vencida.
    if dias == 0 and horas == 0:
        dias = 1

    return timedelta(days=dias, hours=horas)


def texto_intervalo_alerta(alerta):
    try:
        dias = max(0, int(alerta.get("intervalo_dias", 3)))
    except Exception:
        dias = 3

    try:
        horas = max(0, int(alerta.get("intervalo_horas", 0)))
    except Exception:
        horas = 0

    partes = []
    if dias > 0:
        partes.append(f"{dias} día" + ("s" if dias != 1 else ""))
    if horas > 0:
        partes.append(f"{horas} hora" + ("s" if horas != 1 else ""))
    return " y ".join(partes) if partes else "1 día"


def guardar_proximo_riego(alerta, dt):
    alerta["proximo_riego"] = _guardar_fecha_alerta(dt)
    try:
        alerta["proximo_riego_ts"] = int(dt.timestamp())
    except Exception:
        alerta["proximo_riego_ts"] = 0


def obtener_proximo_riego(alerta):
    """Lee el próximo riego guardado como fecha absoluta.
    Esto evita que el contador se pause si la pantalla descansa o si la Raspberry se reinicia.
    """
    proximo = _leer_fecha_alerta(alerta.get("proximo_riego", ""))
    if proximo is not None:
        return proximo

    try:
        ts = int(alerta.get("proximo_riego_ts", 0))
        if ts > 0:
            return datetime.fromtimestamp(ts)
    except Exception:
        pass

    return None


def formatear_tiempo_restante(segundos):
    segundos = max(0, int(segundos))
    dias = segundos // 86400
    segundos %= 86400
    horas = segundos // 3600
    segundos %= 3600
    minutos = segundos // 60

    if dias > 0:
        return f"{dias}d {horas:02d}h {minutos:02d}m"
    if horas > 0:
        return f"{horas:02d}h {minutos:02d}m"
    return f"{minutos:02d} min"


def obtener_estado_visual_alerta(nodo):
    alerta = alertas_riego[nodo]

    if not alerta.get("activo"):
        return {
            "texto": "Configurar alerta de riego",
            "subtexto": "Sin recordatorio activo",
            "bg": "#e9ecef",
            "fg": "#1b4332",
            "borde": "#ced4da"
        }

    proximo = obtener_proximo_riego(alerta)
    if proximo is None:
        proximo = datetime.now() + obtener_intervalo_alerta(alerta)
        guardar_proximo_riego(alerta, proximo)
        guardar_alertas_riego()

    ahora = datetime.now()
    restante = (proximo - ahora).total_seconds()
    duracion = int(alerta.get("duracion_horas", 24))
    intervalo_txt = texto_intervalo_alerta(alerta)

    if restante <= 0:
        return {
            "texto": "Riego pendiente",
            "subtexto": f"Duración sugerida: {duracion} h · toca y marca Listo",
            "bg": "#e63946",
            "fg": "white",
            "borde": "#b00020"
        }

    if restante <= 10 * 60:
        return {
            "texto": f"Faltan {formatear_tiempo_restante(restante)}",
            "subtexto": f"Alerta crítica · riego por {duracion} h",
            "bg": "#e63946",
            "fg": "white",
            "borde": "#b00020"
        }

    if restante <= 3 * 3600:
        return {
            "texto": f"Faltan {formatear_tiempo_restante(restante)}",
            "subtexto": f"Próximo riego cercano · {duracion} h",
            "bg": "#f4a261",
            "fg": "#3d2b00",
            "borde": "#e76f51"
        }

    return {
        "texto": f"Riego en {formatear_tiempo_restante(restante)}",
        "subtexto": f"Cada {intervalo_txt} · {duracion} h",
        "bg": "#d8f3dc",
        "fg": "#1b4332",
        "borde": "#95d5b2"
    }


def actualizar_alerta_ui(nodo):
    if nodo not in labels_resumen:
        return
    widgets = labels_resumen[nodo]
    if "alerta_btn" not in widgets:
        return

    estado = obtener_estado_visual_alerta(nodo)
    btn = widgets["alerta_btn"]
    btn.config(
        text=f"⏰ {estado['texto']}\n{estado['subtexto']}",
        bg=estado["bg"],
        fg=estado["fg"],
        activebackground=estado["bg"],
        activeforeground=estado["fg"],
        highlightbackground=estado["borde"]
    )


alarma_riego_sonando = False


def hay_alerta_roja_activa():
    ahora = datetime.now()
    for nodo in (1, 2, 3):
        alerta = alertas_riego.get(nodo, {})
        if not alerta.get("activo"):
            continue
        proximo = obtener_proximo_riego(alerta)
        if proximo is None:
            continue
        restante = (proximo - ahora).total_seconds()
        if restante <= 10 * 60:
            return True
    return False


def ciclo_bip_alerta_riego():
    global alarma_riego_sonando

    # La alerta roja ahora es solamente visual.
    # Se mantiene este ciclo para conservar el estado de alerta
    # hasta que el usuario marque Listo o desactive el recordatorio.
    if not hay_alerta_roja_activa():
        alarma_riego_sonando = False
        return

    ventana.after(3000, ciclo_bip_alerta_riego)


def actualizar_alertas_riego():
    global alarma_riego_sonando
    for nodo in (1, 2, 3):
        actualizar_alerta_ui(nodo)

    if hay_alerta_roja_activa() and not alarma_riego_sonando:
        alarma_riego_sonando = True
        ciclo_bip_alerta_riego()

    if not hay_alerta_roja_activa():
        alarma_riego_sonando = False

    ventana.after(10000, actualizar_alertas_riego)


def marcar_riego_listo(nodo):
    alerta = alertas_riego[nodo]
    ahora = datetime.now()
    alerta["activo"] = True
    alerta["ultimo_listo"] = _guardar_fecha_alerta(ahora)
    guardar_proximo_riego(alerta, ahora + obtener_intervalo_alerta(alerta))
    guardar_alertas_riego()
    actualizar_alerta_ui(nodo)


def abrir_config_alerta_riego(nodo):
    alerta = alertas_riego[nodo]

    ventana_alerta = tk.Toplevel(ventana)
    ventana_alerta.title(f"Alerta de riego Nodo {nodo}")
    ventana_alerta.geometry("800x480+0+0")
    ventana_alerta.configure(bg="#f4f7f6")
    ventana_alerta.resizable(False, False)
    ventana_alerta.transient(ventana)
    ventana_alerta.grab_set()
    ventana_alerta.focus_force()

    try:
        ventana_alerta.attributes("-fullscreen", True)
    except Exception:
        pass

    valores = {
        "dias": tk.IntVar(value=max(0, int(alerta.get("intervalo_dias", 3)))),
        "horas_frecuencia": tk.IntVar(value=max(0, int(alerta.get("intervalo_horas", 0)))),
        "horas": tk.IntVar(value=max(1, int(alerta.get("duracion_horas", 24))))
    }

    def cerrar():
        try:
            ventana_alerta.grab_release()
        except Exception:
            pass
        ventana_alerta.destroy()

    def ajustar(variable, delta, minimo, maximo):
        actual = variable.get()
        variable.set(max(minimo, min(maximo, actual + delta)))
        actualizar_preview()

    def calcular_proximo_desde_ahora():
        dias = max(0, valores["dias"].get())
        horas = max(0, valores["horas_frecuencia"].get())
        if dias == 0 and horas == 0:
            dias = 1
        return datetime.now() + timedelta(days=dias, hours=horas)

    def actualizar_preview():
        proximo_actual = _leer_fecha_alerta(alerta.get("proximo_riego", ""))
        if alerta.get("activo") and proximo_actual:
            txt_actual = proximo_actual.strftime("%d/%m/%Y %H:%M")
        else:
            txt_actual = "Sin alerta activa"

        nuevo = calcular_proximo_desde_ahora()
        lbl_preview.config(
            text=(
                f"Configuración seleccionada:\n"
                f"Regar cada {max(0, valores['dias'].get())} días y "
                f"{max(0, valores['horas_frecuencia'].get())} horas, "
                f"durante {valores['horas'].get()} horas seguidas.\n\n"
                f"Al guardar, el próximo riego quedará para:\n{nuevo.strftime('%d/%m/%Y %H:%M')}\n\n"
                f"Próximo riego actual: {txt_actual}"
            )
        )

    def guardar_configuracion():
        alerta["activo"] = True
        alerta["intervalo_dias"] = int(max(0, valores["dias"].get()))
        alerta["intervalo_horas"] = int(max(0, valores["horas_frecuencia"].get()))
        if alerta["intervalo_dias"] == 0 and alerta["intervalo_horas"] == 0:
            alerta["intervalo_dias"] = 1
        alerta["duracion_horas"] = int(valores["horas"].get())
        guardar_proximo_riego(alerta, calcular_proximo_desde_ahora())
        guardar_alertas_riego()
        actualizar_alerta_ui(nodo)
        messagebox.showinfo(
            "Alerta de riego",
            f"Alerta configurada para el Nodo {nodo}.\n\n"
            f"Riego cada {texto_intervalo_alerta(alerta)} durante {alerta['duracion_horas']} horas."
        )
        cerrar()

    def listo_y_reprogramar():
        marcar_riego_listo(nodo)
        messagebox.showinfo(
            "Riego listo",
            f"Nodo {nodo} marcado como listo.\n\n"
            f"El próximo recordatorio se programó en {texto_intervalo_alerta(alertas_riego[nodo])}."
        )
        cerrar()

    def desactivar_alerta():
        alerta["activo"] = False
        guardar_alertas_riego()
        actualizar_alerta_ui(nodo)
        cerrar()

    frame_header_alerta = tk.Frame(ventana_alerta, bg="#2d6a4f", height=54)
    frame_header_alerta.pack(fill="x")
    frame_header_alerta.pack_propagate(False)

    tk.Label(
        frame_header_alerta,
        text=f"⏰ Alerta de riego · Nodo {nodo}",
        font=("Segoe UI", 17, "bold"),
        bg="#2d6a4f",
        fg="white"
    ).pack(side="left", padx=18)

    tk.Button(
        frame_header_alerta,
        text="Cerrar",
        font=("Segoe UI", 11, "bold"),
        bg="white",
        fg="#2d6a4f",
        activebackground="#d8f3dc",
        activeforeground="#1b4332",
        relief="flat",
        bd=0,
        padx=16,
        command=cerrar
    ).pack(side="right", padx=12, pady=8)

    frame_body = tk.Frame(ventana_alerta, bg="#f4f7f6")
    frame_body.pack(fill="both", expand=True, padx=18, pady=16)
    frame_body.grid_columnconfigure(0, weight=1)
    frame_body.grid_columnconfigure(1, weight=1)
    frame_body.grid_rowconfigure(0, weight=1)

    frame_config = tk.Frame(frame_body, bg="white", highlightbackground="#b7e4c7", highlightthickness=2, padx=18, pady=16)
    frame_config.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

    tk.Label(
        frame_config,
        text="Programar recordatorio",
        font=("Segoe UI", 16, "bold"),
        bg="white",
        fg="#1b4332"
    ).pack(anchor="w", pady=(0, 12))

    def crear_selector(parent, titulo, variable, unidad, minimo, maximo):
        frame = tk.Frame(parent, bg="#f8f9fa", padx=10, pady=7)
        frame.pack(fill="x", pady=5)

        tk.Label(frame, text=titulo, font=("Segoe UI", 11, "bold"), bg="#f8f9fa", fg="#1b4332").pack(anchor="w")

        fila = tk.Frame(frame, bg="#f8f9fa")
        fila.pack(fill="x", pady=(8, 0))

        tk.Button(
            fila,
            text="−",
            font=("Segoe UI", 20, "bold"),
            bg="#e9ecef",
            fg="#1b4332",
            relief="flat",
            bd=0,
            width=3,
            command=lambda: ajustar(variable, -1, minimo, maximo)
        ).pack(side="left", fill="y")

        tk.Label(
            fila,
            textvariable=variable,
            font=("Segoe UI", 24, "bold"),
            bg="#f8f9fa",
            fg="#2d6a4f",
            width=4
        ).pack(side="left", expand=True)

        tk.Label(
            fila,
            text=unidad,
            font=("Segoe UI", 12, "bold"),
            bg="#f8f9fa",
            fg="#6c757d",
            width=8
        ).pack(side="left")

        tk.Button(
            fila,
            text="+",
            font=("Segoe UI", 20, "bold"),
            bg="#d8f3dc",
            fg="#1b4332",
            relief="flat",
            bd=0,
            width=3,
            command=lambda: ajustar(variable, 1, minimo, maximo)
        ).pack(side="right", fill="y")

    crear_selector(frame_config, "Frecuencia de riego", valores["dias"], "días", 0, 60)
    crear_selector(frame_config, "Frecuencia de riego", valores["horas_frecuencia"], "horas", 0, 23)
    crear_selector(frame_config, "Duración del riego", valores["horas"], "horas", 1, 72)

    frame_preview = tk.Frame(frame_body, bg="white", highlightbackground="#b7e4c7", highlightthickness=2, padx=18, pady=16)
    frame_preview.grid(row=0, column=1, sticky="nsew", padx=(10, 0))

    tk.Label(
        frame_preview,
        text="Vista previa",
        font=("Segoe UI", 16, "bold"),
        bg="white",
        fg="#1b4332"
    ).pack(anchor="w", pady=(0, 12))

    lbl_preview = tk.Label(
        frame_preview,
        text="",
        font=("Segoe UI", 12, "bold"),
        bg="#f8f9fa",
        fg="#1b4332",
        justify="left",
        anchor="nw",
        wraplength=320,
        padx=12,
        pady=12
    )
    lbl_preview.pack(fill="both", expand=True)

    # =====================================================
    # BOTONES DE ALERTA - AHORA DENTRO DE VISTA PREVIA
    # Se colocan justo debajo del texto de vista previa para que
    # siempre queden visibles en pantalla táctil 800x480.
    # =====================================================
    frame_botones = tk.Frame(frame_preview, bg="white")
    frame_botones.pack(fill="x", pady=(12, 0))

    tk.Button(
        frame_botones,
        text="Guardar",
        font=("Segoe UI", 12, "bold"),
        bg="#52b788",
        fg="white",
        activebackground="#40916c",
        activeforeground="white",
        relief="flat",
        bd=0,
        height=2,
        command=guardar_configuracion
    ).pack(side="left", fill="x", expand=True, padx=(0, 5))

    tk.Button(
        frame_botones,
        text="Listo",
        font=("Segoe UI", 12, "bold"),
        bg="#f4a261",
        fg="#3d2b00",
        activebackground="#e9c46a",
        activeforeground="#3d2b00",
        relief="flat",
        bd=0,
        height=2,
        command=listo_y_reprogramar
    ).pack(side="left", fill="x", expand=True, padx=5)

    tk.Button(
        frame_botones,
        text="Desactivar",
        font=("Segoe UI", 12, "bold"),
        bg="#e9ecef",
        fg="#1b4332",
        activebackground="#ced4da",
        activeforeground="#1b4332",
        relief="flat",
        bd=0,
        height=2,
        command=desactivar_alerta
    ).pack(side="left", fill="x", expand=True, padx=(5, 0))

    actualizar_preview()


cargar_alertas_riego()


def detectar_nodo_desde_linea(linea):
    texto = linea.upper()

    # Formatos aceptados:
    # SAVIA_DATA_N1:(...)
    # SAVIA_DATA:N1:(...)
    # N1:(...)
    # N1 | S1: ...
    m = re.search(r"SAVIA[_-]?DATA[_:-]?\s*N?([123])", texto)
    if m:
        return int(m.group(1))

    m = re.search(r"\bN\s*([123])\s*[:|]", texto)
    if m:
        return int(m.group(1))

    # Compatibilidad con la línea limpia que ya agregamos al ESP32:
    # SAVIA_DATA:(S1,S2,S3,T,H)
    # Si no dice nodo, se considera Nodo 1.
    if "SAVIA_DATA" in texto:
        return 1

    return 1


def extraer_datos_sensor(linea):
    # Primero intenta leer las líneas largas del ESP32:
    # N2 | S1: 28.63% | S2: ... | T: 21.6 C | H: 38.9%
    m_log = PATRON_LOG_NODO.search(linea)
    if m_log:
        nodo = int(m_log.group(1))
        v1 = float(m_log.group(2))
        v2 = float(m_log.group(3))
        v3 = float(m_log.group(4))
        temp = float(m_log.group(5))
        hum = float(m_log.group(6))
        return nodo, v1, v2, v3, temp, hum

    # Después intenta leer cualquier línea que contenga:
    # (S1,S2,S3,T,H)
    m = PATRON_PAREN.search(linea)
    if m:
        nodo = detectar_nodo_desde_linea(linea)
        v1 = float(m.group(1))
        v2 = float(m.group(2))
        v3 = float(m.group(3))
        temp = float(m.group(4))
        hum = float(m.group(5))
        return nodo, v1, v2, v3, temp, hum

    return None


def formato_porcentaje(valor):
    if valor is None:
        return "-- %"
    return f"{valor:.1f} %"


def formato_temp(valor):
    if valor is None:
        return "-- °C"
    return f"{valor:.1f} °C"


def formato_texto(valor):
    if valor is None:
        return "--"
    return f"{valor:.1f}"


def color_por_humedad(valor):
    if valor is None:
        return "#6c757d"
    if valor <= 20:
        return "#e63946"
    if valor <= 30:
        return "#f4a261"
    return "#2d6a4f"


def obtener_estado_conexion_lora(nodo):
    """Devuelve el estado visual de comunicación de cada nodo.

    La Raspberry no se comunica directamente con cada LoRa distribuido; recibe desde el
    ESP32 central. Por eso el indicador se basa en la última lectura válida recibida
    de cada nodo. Si el ESP32 central deja de reenviar datos de un nodo, el círculo
    cambia a rojo después del tiempo configurado.
    """
    datos = datos_nodos.get(nodo, {})
    ultimo_epoch = datos.get("last_rx_epoch", 0) or 0

    if ultimo_epoch <= 0:
        return "esperando", COLOR_LORA_ESPERANDO, "Esperando"

    segundos_sin_dato = time.time() - ultimo_epoch
    if segundos_sin_dato <= TIEMPO_MAX_SIN_DATO_LORA:
        return "conectado", COLOR_LORA_CONECTADO, "Conectado"

    return "desconectado", COLOR_LORA_DESCONECTADO, "Sin señal"


def actualizar_indicador_conexion_lora(nodo):
    if nodo not in labels_resumen:
        return

    estado, color, texto = obtener_estado_conexion_lora(nodo)
    widgets = labels_resumen[nodo]

    # Indicador dibujado con Canvas para que siempre se vea en pantalla táctil.
    if "conexion_canvas" in widgets and "conexion_dot_item" in widgets:
        widgets["conexion_canvas"].itemconfig(
            widgets["conexion_dot_item"],
            fill=color,
            outline=color
        )
        # No usar lift()/tkraise() aquí: en Canvas se interpreta como tag interno y puede romper Tkinter.
        # El indicador ya está colocado con place() en la esquina de la tarjeta.

    if "conexion_dot" in widgets:
        # Compatibilidad si existe una versión anterior con Label.
        widgets["conexion_dot"].config(fg=color)

    if "conexion_txt" in widgets:
        widgets["conexion_txt"].config(text=texto, fg=color if estado != "esperando" else "#6c757d")


def actualizar_indicadores_conexion_lora():
    for nodo in (1, 2, 3):
        actualizar_indicador_conexion_lora(nodo)

    # Revisa cada 2 segundos para que el círculo pase a rojo aunque ya no lleguen datos.
    try:
        ventana.after(2000, actualizar_indicadores_conexion_lora)
    except Exception:
        pass


def actualizar_interfaz_nodo(nodo):
    datos = datos_nodos[nodo]

    if nodo in labels_resumen:
        labels_resumen[nodo]["prom"].config(
            text=formato_porcentaje(datos["prom"]),
            fg=color_por_humedad(datos["prom"])
        )
        labels_resumen[nodo]["estado"].config(text=f"Última lectura: {datos['ultimo']}")
        labels_resumen[nodo]["clima"].config(
            text=f"🌡 {formato_temp(datos['temp'])}   💧 Aire {formato_porcentaje(datos['hum'])}"
        )
        actualizar_alerta_ui(nodo)
        actualizar_indicador_conexion_lora(nodo)

    if nodo in labels_detalle:
        detalle = labels_detalle[nodo]
        detalle["prom"].config(
            text=formato_porcentaje(datos["prom"]),
            fg=color_por_humedad(datos["prom"])
        )
        detalle["s1"].config(text=formato_porcentaje(datos["s1"]))
        detalle["s2"].config(text=formato_porcentaje(datos["s2"]))
        detalle["s3"].config(text=formato_porcentaje(datos["s3"]))
        detalle["temp"].config(text=formato_temp(datos["temp"]))
        detalle["hum"].config(text=formato_porcentaje(datos["hum"]))
        detalle["ultimo"].config(text=f"Última lectura: {datos['ultimo']}")



def animar_tarjeta_actualizada(nodo):
    """Microanimación discreta: resalta el borde sin alterar el diseño de la tarjeta."""
    try:
        tarjeta = labels_resumen.get(nodo, {}).get("tarjeta")
        if not tarjeta:
            return

        colores = ["#52b788", "#95d5b2", "#b7e4c7"]

        def paso(i=0):
            if i >= len(colores):
                return
            try:
                tarjeta.config(highlightbackground=colores[i])
            except Exception:
                return
            ventana.after(130, lambda: paso(i + 1))

        paso()
    except Exception:
        pass


def calcular_resumen_hoy():
    """Calcula un resumen simple de las lecturas guardadas hoy."""
    asegurar_csv_historial()
    hoy_txt = date.today().strftime("%Y-%m-%d")
    lecturas = []

    try:
        with open(RUTA_CSV_HISTORIAL, mode="r", newline="", encoding="utf-8") as archivo:
            lector = csv.DictReader(archivo)
            for fila in lector:
                if fila.get("fecha") != hoy_txt:
                    continue
                try:
                    lecturas.append({
                        "nodo": int(fila.get("nodo", "0")),
                        "prom": float(fila.get("promedio_suelo_pct", "nan")),
                        "temp": float(fila.get("temperatura_aire_c", "nan")),
                    })
                except Exception:
                    continue
    except Exception:
        pass

    return lecturas


def actualizar_resumen_hoy():
    """Actualiza el panel de resumen del día sin bloquear la interfaz."""
    try:
        if not resumen_widgets:
            return

        lecturas = calcular_resumen_hoy()
        if not lecturas:
            resumen_widgets["general"].config(text="Resumen de hoy: esperando datos")
            resumen_widgets["baja"].config(text="Humedad más baja: --")
            resumen_widgets["alta"].config(text="Humedad más alta: --")
            resumen_widgets["total"].config(text="Lecturas guardadas: 0")
            return

        proms = [l["prom"] for l in lecturas]
        promedio_general = sum(proms) / len(proms)
        baja = min(lecturas, key=lambda x: x["prom"])
        alta = max(lecturas, key=lambda x: x["prom"])

        resumen_widgets["general"].config(text=f"Promedio del cultivo hoy: {promedio_general:.1f} %")
        resumen_widgets["baja"].config(text=f"Humedad más baja: Nodo {baja['nodo']} · {baja['prom']:.1f} %")
        resumen_widgets["alta"].config(text=f"Humedad más alta: Nodo {alta['nodo']} · {alta['prom']:.1f} %")
        resumen_widgets["total"].config(text=f"Lecturas guardadas hoy: {len(lecturas)}")
    except Exception as e:
        print(f"Error actualizando resumen de hoy: {e}")


def actualizar_datos_nodo(nodo, v1, v2, v3, temp, hum, linea_original):
    if nodo not in datos_nodos:
        return

    prom = (v1 + v2 + v3) / 3.0

    datos_nodos[nodo].update({
        "s1": v1,
        "s2": v2,
        "s3": v3,
        "temp": temp,
        "hum": hum,
        "prom": prom,
        "ultimo": time.strftime("%H:%M:%S"),
        "linea": linea_original,
        "last_rx_epoch": time.time()
    })

    guardar_datos_csv(nodo, v1, v2, v3, prom, temp, hum, linea_original)
    enviar_thingsboard_async(nodo, v1, v2, v3, prom, temp, hum)
    actualizar_interfaz_nodo(nodo)
    animar_tarjeta_actualizada(nodo)
    actualizar_resumen_hoy()


def leer_sensores():
    global puerto_uart

    try:
        if not conectar_uart():
            ventana.after(500, leer_sensores)
            return

        if puerto_uart and puerto_uart.in_waiting > 0:
            linea = puerto_uart.readline().decode("utf-8", errors="ignore").strip()

            if linea:
                print(f"RAW: {repr(linea)}")

                datos = extraer_datos_sensor(linea)

                if datos:
                    nodo, v1, v2, v3, temp, hum = datos
                    actualizar_datos_nodo(nodo, v1, v2, v3, temp, hum, linea)
                else:
                    print(f"NO MATCH: {repr(linea)}")

    except serial.SerialException as e:
        print(f"Error UART leyendo sensores: {e}")
        cerrar_uart()

    except OSError as e:
        print(f"Puerto desconectado físicamente: {e}")
        cerrar_uart()

    except Exception as e:
        print(f"Error parseando datos: {e}")

    ventana.after(500, leer_sensores)


def enviar_comando(comando):
    global puerto_uart

    try:
        if not conectar_uart(forzar=True):
            print(f"No hay UART disponible. No se pudo enviar: {comando}")
            return

        puerto_uart.write(comando.encode("utf-8"))
        puerto_uart.flush()

        print(f"Raspberry enviando: {comando}")

    except serial.SerialException as e:
        print(f"Error UART enviando comando: {e}")
        cerrar_uart()

    except OSError as e:
        print(f"Puerto desconectado al enviar: {e}")
        cerrar_uart()

    except Exception as e:
        print(f"Error enviando comando: {e}")
        cerrar_uart()

# ==========================================
# VENTANA DE HISTÓRICO / EXPORTAR DATOS
# ==========================================

def contar_registros_en_rango(fecha_inicio, fecha_fin):
    """Cuenta cuántas lecturas hay en el historial entre dos fechas."""
    try:
        asegurar_csv_historial()
        total = 0
        with open(RUTA_CSV_HISTORIAL, mode="r", newline="", encoding="utf-8") as archivo:
            lector = csv.DictReader(archivo)
            for fila in lector:
                try:
                    fecha_fila = convertir_fecha_usuario(fila.get("fecha", ""))
                except Exception:
                    continue
                if fecha_inicio <= fecha_fila <= fecha_fin:
                    total += 1
        return total
    except Exception:
        return 0


# ==========================================
# HISTÓRICO CON CALENDARIO TÁCTIL
# ==========================================
def abrir_exportar_datos():
    ventana_exportar = tk.Toplevel(ventana)
    ventana_exportar.title("Exportar historial")
    ventana_exportar.geometry("800x480+0+0")
    ventana_exportar.configure(bg="#f4f7f6")
    ventana_exportar.resizable(False, False)
    ventana_exportar.transient(ventana)
    ventana_exportar.grab_set()
    ventana_exportar.focus_force()

    try:
        ventana_exportar.attributes("-fullscreen", True)
    except Exception:
        pass

    campo_activo = {"entry": None}
    teclado_mayus = {"activo": False}
    fecha_inicio_sel = {"valor": date.today()}
    fecha_fin_sel = {"valor": date.today()}

    def cerrar_exportar():
        try:
            ventana_exportar.grab_release()
        except Exception:
            pass
        ventana_exportar.destroy()

    def marcar_campo(entry):
        campo_activo["entry"] = entry
        entry_correo.config(highlightbackground="#b7e4c7", highlightthickness=2)
        entry.config(highlightbackground="#2d6a4f", highlightthickness=3)

    def insertar_texto(texto):
        entry = campo_activo.get("entry")
        if entry is None:
            return
        try:
            entry.insert(tk.INSERT, texto)
        except Exception:
            entry.insert("end", texto)

    def presionar_tecla(tecla):
        entry = campo_activo.get("entry")
        if entry is None:
            marcar_campo(entry_correo)
            entry = entry_correo

        if tecla == "Borrar":
            pos = entry.index(tk.INSERT)
            if pos > 0:
                entry.delete(pos - 1, pos)
            return

        if tecla == "Limpiar":
            entry.delete(0, "end")
            return

        if tecla == "Espacio":
            insertar_texto(" ")
            return

        if tecla == "Mayús":
            teclado_mayus["activo"] = not teclado_mayus["activo"]
            redibujar_teclado()
            return

        if tecla == "OK":
            exportar_y_enviar()
            return

        if len(tecla) == 1 and teclado_mayus["activo"] and tecla.isalpha():
            insertar_texto(tecla.upper())
        else:
            insertar_texto(tecla)

    def actualizar_labels_fecha():
        lbl_fecha_inicio.config(text=fecha_inicio_sel["valor"].strftime("%d / %m / %Y"))
        lbl_fecha_fin.config(text=fecha_fin_sel["valor"].strftime("%d / %m / %Y"))
        inicio = fecha_inicio_sel["valor"]
        fin = fecha_fin_sel["valor"]
        if inicio <= fin:
            total = contar_registros_en_rango(inicio, fin)
            lbl_resumen_exportar.config(
                text=f"Rango seleccionado: {inicio:%d/%m/%Y} → {fin:%d/%m/%Y}  |  Registros encontrados: {total}",
                fg="#1b4332"
            )
        else:
            lbl_resumen_exportar.config(
                text="Rango inválido: la fecha inicial no puede ser mayor que la fecha final.",
                fg="#e63946"
            )

    def set_rango_hoy():
        hoy = date.today()
        fecha_inicio_sel["valor"] = hoy
        fecha_fin_sel["valor"] = hoy
        actualizar_labels_fecha()

    def set_rango_7_dias():
        hoy = date.today()
        fecha_inicio_sel["valor"] = hoy - timedelta(days=6)
        fecha_fin_sel["valor"] = hoy
        actualizar_labels_fecha()

    def set_rango_30_dias():
        hoy = date.today()
        fecha_inicio_sel["valor"] = hoy - timedelta(days=29)
        fecha_fin_sel["valor"] = hoy
        actualizar_labels_fecha()

    def abrir_calendario(tipo):
        fecha_actual = fecha_inicio_sel["valor"] if tipo == "inicio" else fecha_fin_sel["valor"]
        anio_mes = {"anio": fecha_actual.year, "mes": fecha_actual.month}

        cal = tk.Toplevel(ventana_exportar)
        cal.title("Seleccionar fecha")
        cal.geometry("800x480+0+0")
        cal.configure(bg="#f4f7f6")
        cal.transient(ventana_exportar)
        cal.grab_set()
        cal.focus_force()
        try:
            cal.attributes("-fullscreen", True)
        except Exception:
            pass

        def cerrar_cal():
            try:
                cal.grab_release()
            except Exception:
                pass
            cal.destroy()

        header = tk.Frame(cal, bg="#2d6a4f", height=48)
        header.pack(fill="x")
        header.pack_propagate(False)

        titulo = "Seleccionar fecha inicial" if tipo == "inicio" else "Seleccionar fecha final"
        tk.Label(
            header,
            text=f"📅 {titulo}",
            font=("Segoe UI", 16, "bold"),
            bg="#2d6a4f",
            fg="white"
        ).pack(side="left", padx=18)

        tk.Button(
            header,
            text="← Volver",
            font=("Segoe UI", 11, "bold"),
            bg="white",
            fg="#2d6a4f",
            relief="flat",
            padx=18,
            command=cerrar_cal
        ).pack(side="right", padx=12, pady=7)

        nav = tk.Frame(cal, bg="#f4f7f6", height=54)
        nav.pack(fill="x", padx=18, pady=(12, 4))
        nav.pack_propagate(False)

        lbl_mes = tk.Label(
            nav,
            text="",
            font=("Segoe UI", 18, "bold"),
            bg="#f4f7f6",
            fg="#1b4332"
        )
        lbl_mes.pack(side="left", expand=True)

        grid = tk.Frame(cal, bg="#f4f7f6")
        grid.pack(fill="both", expand=True, padx=18, pady=(0, 12))

        def cambiar_mes(delta):
            mes = anio_mes["mes"] + delta
            anio = anio_mes["anio"]
            if mes < 1:
                mes = 12
                anio -= 1
            elif mes > 12:
                mes = 1
                anio += 1
            anio_mes["mes"] = mes
            anio_mes["anio"] = anio
            dibujar_calendario()

        tk.Button(
            nav,
            text="◀ Mes anterior",
            font=("Segoe UI", 11, "bold"),
            bg="#eaf4f4",
            fg="#1b4332",
            relief="flat",
            command=lambda: cambiar_mes(-1)
        ).pack(side="left", padx=4, fill="y")

        tk.Button(
            nav,
            text="Mes siguiente ▶",
            font=("Segoe UI", 11, "bold"),
            bg="#eaf4f4",
            fg="#1b4332",
            relief="flat",
            command=lambda: cambiar_mes(1)
        ).pack(side="right", padx=4, fill="y")

        meses = [
            "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
            "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
        ]
        dias = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]

        def seleccionar_fecha(dia):
            seleccion = date(anio_mes["anio"], anio_mes["mes"], dia)
            if tipo == "inicio":
                fecha_inicio_sel["valor"] = seleccion
            else:
                fecha_fin_sel["valor"] = seleccion
            actualizar_labels_fecha()
            cerrar_cal()

        def dibujar_calendario():
            for widget in grid.winfo_children():
                widget.destroy()

            lbl_mes.config(text=f"{meses[anio_mes['mes'] - 1]} {anio_mes['anio']}")

            for col in range(7):
                grid.grid_columnconfigure(col, weight=1, uniform="dias")
            for row in range(7):
                grid.grid_rowconfigure(row, weight=1, uniform="filas")

            for col, nombre in enumerate(dias):
                tk.Label(
                    grid,
                    text=nombre,
                    font=("Segoe UI", 11, "bold"),
                    bg="#d8f3dc",
                    fg="#1b4332"
                ).grid(row=0, column=col, sticky="nsew", padx=3, pady=3)

            semanas = calendar.monthcalendar(anio_mes["anio"], anio_mes["mes"])
            seleccionada = fecha_inicio_sel["valor"] if tipo == "inicio" else fecha_fin_sel["valor"]
            hoy = date.today()

            for r, semana in enumerate(semanas, start=1):
                for c, dia in enumerate(semana):
                    if dia == 0:
                        tk.Label(grid, text="", bg="#f4f7f6").grid(row=r, column=c, sticky="nsew", padx=3, pady=3)
                        continue

                    fecha_boton = date(anio_mes["anio"], anio_mes["mes"], dia)
                    if fecha_boton == seleccionada:
                        bg, fg = "#2d6a4f", "white"
                    elif fecha_boton == hoy:
                        bg, fg = "#b7e4c7", "#1b4332"
                    else:
                        bg, fg = "white", "#1b4332"

                    tk.Button(
                        grid,
                        text=str(dia),
                        font=("Segoe UI", 14, "bold"),
                        bg=bg,
                        fg=fg,
                        activebackground="#52b788",
                        activeforeground="white",
                        relief="flat",
                        bd=0,
                        command=lambda d=dia: seleccionar_fecha(d)
                    ).grid(row=r, column=c, sticky="nsew", padx=3, pady=3)

        dibujar_calendario()

    def exportar_y_enviar():
        correo = entry_correo.get().strip()
        if "@" not in correo or "." not in correo:
            messagebox.showwarning("Correo inválido", "Escribe una dirección de correo válida.")
            marcar_campo(entry_correo)
            return

        fecha_inicio = fecha_inicio_sel["valor"]
        fecha_fin = fecha_fin_sel["valor"]

        if fecha_inicio > fecha_fin:
            messagebox.showwarning("Rango inválido", "La fecha inicial no puede ser mayor que la fecha final.")
            return

        btn_exportar.config(state="disabled", text="Enviando...")
        lbl_estado_exportar.config(
            text="Preparando el reporte. No cierres esta pantalla...",
            fg="#1b4332"
        )
        ventana_exportar.update_idletasks()

        def trabajo():
            try:
                ruta_csv, total = generar_csv_exportacion(fecha_inicio, fecha_fin)

                if total == 0:
                    ventana_exportar.after(
                        0,
                        lambda: finalizar_exportacion(
                            False,
                            f"No hay datos guardados entre {fecha_inicio:%d/%m/%Y} y {fecha_fin:%d/%m/%Y}."
                        )
                    )
                    return

                enviar_csv_por_correo(correo, ruta_csv, fecha_inicio, fecha_fin)
                ventana_exportar.after(
                    0,
                    lambda: finalizar_exportacion(
                        True,
                        f"Reporte enviado correctamente a {correo}.\nRegistros enviados: {total}."
                    )
                )

            except Exception as e:
                ventana_exportar.after(
                    0,
                    lambda err=e: finalizar_exportacion(False, str(err))
                )

        threading.Thread(target=trabajo, daemon=True).start()

    def finalizar_exportacion(exito, mensaje):
        btn_exportar.config(state="normal", text="Exportar datos")
        lbl_estado_exportar.config(
            text=mensaje,
            fg="#2d6a4f" if exito else "#e63946"
        )
        if exito:
            guardar_correo_reciente(entry_correo.get().strip())
            actualizar_correos_recientes()
            mostrar_confirmacion_reporte(mensaje)
        else:
            messagebox.showwarning("Exportación", mensaje)
        actualizar_labels_fecha()

    def mostrar_confirmacion_reporte(mensaje):
        confirmacion = tk.Toplevel(ventana_exportar)
        confirmacion.title("Reporte enviado")
        confirmacion.geometry("520x300+140+90")
        confirmacion.configure(bg="white")
        confirmacion.transient(ventana_exportar)
        confirmacion.grab_set()

        tk.Label(
            confirmacion,
            text="✅ Reporte enviado",
            font=("Segoe UI", 18, "bold"),
            bg="white",
            fg="#2d6a4f"
        ).pack(pady=(26, 10))

        tk.Label(
            confirmacion,
            text=mensaje,
            font=("Segoe UI", 12, "bold"),
            bg="white",
            fg="#1b4332",
            wraplength=440,
            justify="center"
        ).pack(expand=True, padx=26)

        tk.Button(
            confirmacion,
            text="Volver al histórico",
            font=("Segoe UI", 12, "bold"),
            bg="#52b788",
            fg="white",
            relief="flat",
            padx=18,
            pady=8,
            command=confirmacion.destroy
        ).pack(pady=(8, 24))

    # ---------- Header ----------
    frame_header_export = tk.Frame(ventana_exportar, bg="#2d6a4f", height=46)
    frame_header_export.pack(fill="x")
    frame_header_export.pack_propagate(False)

    tk.Label(
        frame_header_export,
        text="📊 Histórico de sensores",
        font=("Segoe UI", 15, "bold"),
        bg="#2d6a4f",
        fg="white"
    ).pack(side="left", padx=16)

    tk.Button(
        frame_header_export,
        text="← Regresar",
        font=("Segoe UI", 11, "bold"),
        bg="white",
        fg="#2d6a4f",
        activebackground="#d8f3dc",
        activeforeground="#1b4332",
        relief="flat",
        bd=0,
        padx=14,
        command=cerrar_exportar
    ).pack(side="right", padx=12, pady=7)

    frame_form = tk.Frame(ventana_exportar, bg="#f4f7f6")
    frame_form.pack(fill="x", padx=14, pady=(8, 4))
    frame_form.grid_columnconfigure(1, weight=1)
    frame_form.grid_columnconfigure(3, weight=1)

    tk.Label(
        frame_form,
        text="Correo destino:",
        font=("Segoe UI", 10, "bold"),
        bg="#f4f7f6",
        fg="#1b4332"
    ).grid(row=0, column=0, sticky="w", padx=(0, 8), pady=3)

    entry_correo = tk.Entry(frame_form, font=("Segoe UI", 13), width=42)
    entry_correo.grid(row=0, column=1, columnspan=4, sticky="ew", pady=3)
    entry_correo.bind("<FocusIn>", lambda e: marcar_campo(entry_correo))
    entry_correo.bind("<Button-1>", lambda e: marcar_campo(entry_correo))

    correo_ok, texto_estado_correo = estado_config_correo()
    lbl_estado_correo_config = tk.Label(
        frame_form,
        text=texto_estado_correo,
        font=("Segoe UI", 8, "bold"),
        bg="#f4f7f6",
        fg="#2d6a4f" if correo_ok else "#e63946",
        anchor="w"
    )
    lbl_estado_correo_config.grid(row=1, column=1, columnspan=4, sticky="ew", pady=(0, 1))

    frame_correos_recientes = tk.Frame(frame_form, bg="#f4f7f6")
    frame_correos_recientes.grid(row=2, column=1, columnspan=4, sticky="ew", pady=(0, 3))

    def seleccionar_correo_reciente(correo):
        entry_correo.delete(0, "end")
        entry_correo.insert(0, correo)
        marcar_campo(entry_correo)

    def actualizar_correos_recientes():
        for w in frame_correos_recientes.winfo_children():
            w.destroy()
        correos = cargar_correos_recientes()
        if not correos:
            tk.Label(
                frame_correos_recientes,
                text="Sin correos recientes.",
                font=("Segoe UI", 8),
                bg="#f4f7f6",
                fg="#6c757d"
            ).pack(side="left")
            return

        tk.Label(
            frame_correos_recientes,
            text="Recientes:",
            font=("Segoe UI", 8, "bold"),
            bg="#f4f7f6",
            fg="#1b4332"
        ).pack(side="left", padx=(0, 4))

        for correo in correos[:3]:
            tk.Button(
                frame_correos_recientes,
                text=correo,
                font=("Segoe UI", 8, "bold"),
                bg="#eaf4f4",
                fg="#1b4332",
                activebackground="#d8f3dc",
                activeforeground="#1b4332",
                relief="flat",
                bd=0,
                padx=6,
                command=lambda c=correo: seleccionar_correo_reciente(c)
            ).pack(side="left", padx=2)

    actualizar_correos_recientes()
    correos_iniciales = cargar_correos_recientes()
    if correos_iniciales:
        entry_correo.insert(0, correos_iniciales[0])

    tk.Label(
        frame_form,
        text="Desde:",
        font=("Segoe UI", 10, "bold"),
        bg="#f4f7f6",
        fg="#1b4332"
    ).grid(row=3, column=0, sticky="w", padx=(0, 8), pady=5)

    btn_fecha_inicio = tk.Button(
        frame_form,
        textvariable=tk.StringVar(),
        font=("Segoe UI", 1),
        bg="#f4f7f6",
        bd=0,
        state="disabled"
    )
    # Labels visuales para fechas, con botones táctiles grandes.
    caja_inicio = tk.Frame(frame_form, bg="white", highlightbackground="#b7e4c7", highlightthickness=2)
    caja_inicio.grid(row=3, column=1, sticky="ew", pady=5)
    lbl_fecha_inicio = tk.Label(
        caja_inicio,
        text="",
        font=("Segoe UI", 13, "bold"),
        bg="white",
        fg="#1b4332"
    )
    lbl_fecha_inicio.pack(side="left", fill="x", expand=True, padx=12, pady=8)
    tk.Button(
        caja_inicio,
        text="📅",
        font=("Segoe UI", 14, "bold"),
        bg="#52b788",
        fg="white",
        relief="flat",
        command=lambda: abrir_calendario("inicio")
    ).pack(side="right", fill="y")

    tk.Label(
        frame_form,
        text="Hasta:",
        font=("Segoe UI", 10, "bold"),
        bg="#f4f7f6",
        fg="#1b4332"
    ).grid(row=3, column=2, sticky="e", padx=(12, 8), pady=5)

    caja_fin = tk.Frame(frame_form, bg="white", highlightbackground="#b7e4c7", highlightthickness=2)
    caja_fin.grid(row=3, column=3, sticky="ew", pady=5)
    lbl_fecha_fin = tk.Label(
        caja_fin,
        text="",
        font=("Segoe UI", 13, "bold"),
        bg="white",
        fg="#1b4332"
    )
    lbl_fecha_fin.pack(side="left", fill="x", expand=True, padx=12, pady=8)
    tk.Button(
        caja_fin,
        text="📅",
        font=("Segoe UI", 14, "bold"),
        bg="#52b788",
        fg="white",
        relief="flat",
        command=lambda: abrir_calendario("fin")
    ).pack(side="right", fill="y")

    frame_rapido = tk.Frame(ventana_exportar, bg="#f4f7f6", height=40)
    frame_rapido.pack(fill="x", padx=14, pady=(0, 4))
    frame_rapido.pack_propagate(False)

    for texto, comando in [
        ("Hoy", set_rango_hoy),
        ("Últimos 7 días", set_rango_7_dias),
        ("Últimos 30 días", set_rango_30_dias),
    ]:
        tk.Button(
            frame_rapido,
            text=texto,
            font=("Segoe UI", 9, "bold"),
            bg="#eaf4f4",
            fg="#1b4332",
            activebackground="#d8f3dc",
            activeforeground="#1b4332",
            relief="flat",
            bd=0,
            command=comando
        ).pack(side="left", fill="both", expand=True, padx=4)

    btn_exportar = tk.Button(
        frame_rapido,
        text="Exportar datos",
        font=("Segoe UI", 10, "bold"),
        bg="#52b788",
        fg="white",
        activebackground="#40916c",
        activeforeground="white",
        relief="flat",
        bd=0,
        command=exportar_y_enviar
    )
    btn_exportar.pack(side="left", fill="both", expand=True, padx=4)

    lbl_resumen_exportar = tk.Label(
        ventana_exportar,
        text="",
        font=("Segoe UI", 9, "bold"),
        bg="#f4f7f6",
        fg="#1b4332",
        wraplength=740,
        justify="left"
    )
    lbl_resumen_exportar.pack(fill="x", padx=16, pady=(0, 2))

    lbl_estado_exportar = tk.Label(
        ventana_exportar,
        text="Selecciona fechas con el calendario y escribe el correo destino.",
        font=("Segoe UI", 9, "bold"),
        bg="#f4f7f6",
        fg="#6c757d",
        wraplength=740,
        justify="left"
    )
    lbl_estado_exportar.pack(fill="x", padx=16, pady=(0, 3))

    # ---------- Teclado táctil para correo ----------
    frame_teclado = tk.Frame(
        ventana_exportar,
        bg="#dfeee8",
        highlightbackground="#b7e4c7",
        highlightthickness=2
    )
    frame_teclado.pack(fill="both", expand=True, padx=10, pady=(0, 8))

    filas_teclado = [
        list("1234567890"),
        list("qwertyuiop") + ["@"],
        list("asdfghjkl") + [".", "_"],
        list("zxcvbnm") + ["-", "/", ""],
        ["Mayús", "Espacio", "Borrar", "Limpiar", "OK"]
    ]

    def redibujar_teclado():
        for widget in frame_teclado.winfo_children():
            widget.destroy()

        for fila in filas_teclado:
            frame_fila = tk.Frame(frame_teclado, bg="#dfeee8")
            frame_fila.pack(fill="both", expand=True, pady=1)

            for tecla in fila:
                if tecla == "":
                    tk.Label(frame_fila, text="", bg="#dfeee8").pack(side="left", fill="both", expand=True, padx=1, pady=1)
                    continue

                if tecla in ("Borrar", "Limpiar"):
                    bg, fg = "#f4a261", "white"
                elif tecla == "OK":
                    bg, fg = "#52b788", "white"
                elif tecla == "Mayús":
                    bg, fg = ("#2d6a4f", "white") if teclado_mayus["activo"] else ("#adb5bd", "#111")
                else:
                    bg, fg = "white", "#1b4332"

                texto = tecla
                if len(tecla) == 1 and tecla.isalpha() and teclado_mayus["activo"]:
                    texto = tecla.upper()

                tk.Button(
                    frame_fila,
                    text=texto,
                    font=("Segoe UI", 9, "bold"),
                    bg=bg,
                    fg=fg,
                    activebackground="#d8f3dc",
                    activeforeground="#1b4332",
                    relief="flat",
                    bd=0,
                    command=lambda t=tecla: presionar_tecla(t)
                ).pack(side="left", fill="both", expand=True, padx=1, pady=1)

    redibujar_teclado()
    actualizar_labels_fecha()
    ventana_exportar.after(150, lambda: marcar_campo(entry_correo))

# ==========================================
# DISEÑO DE LA VENTANA
# ==========================================
cargar_nombres_ui()
cargar_ajustes_usuario()
ventana = tk.Tk()
ventana.title("SAVIA - Panel de Control")
ventana.geometry("800x480")
ventana.configure(bg="#f4f7f6")
ventana.attributes("-fullscreen", True)


# ==========================================
# LIGHT SLEEP DE PANTALLA POR INACTIVIDAD - SAVIA_SCREEN_SLEEP_MARCA_5MIN
# ==========================================
# Después de 5 minutos sin tocar la pantalla, SAVIA entra en modo descanso:
# muestra una pantalla de descanso con la marca SAVIA.
# Al tocar la pantalla, la interfaz despierta inmediatamente.
TIEMPO_INACTIVIDAD_MS = 5 * 60 * 1000
# Lo dejamos en False para que se vea la pantalla de descanso con el mensaje SAVIA.
# Si se pone en True, xset puede apagar físicamente la pantalla y ocultar el mensaje.
INTENTAR_APAGADO_FISICO_PANTALLA = False

pantalla_dormida = False
timer_inactividad_id = None
frame_sleep = None


def ejecutar_xset_pantalla(accion):
    """Intenta controlar la pantalla con xset sin romper la app si no está disponible."""
    try:
        env = os.environ.copy()
        env.setdefault("DISPLAY", ":0")
        subprocess.Popen(
            ["xset", "dpms", "force", accion],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env
        )
    except Exception as e:
        print(f"No se pudo ejecutar xset {accion}: {e}")


def despertar_pantalla(event=None):
    """Despierta la interfaz cuando el usuario toca la pantalla."""
    global pantalla_dormida, frame_sleep

    if not pantalla_dormida:
        reiniciar_timer_inactividad()
        return None

    pantalla_dormida = False

    if INTENTAR_APAGADO_FISICO_PANTALLA:
        ejecutar_xset_pantalla("on")

    try:
        if frame_sleep is not None:
            frame_sleep.place_forget()
    except Exception:
        pass

    reiniciar_timer_inactividad()
    return "break"


def dormir_pantalla():
    """Activa el descanso visual después de un periodo sin interacción."""
    global pantalla_dormida, frame_sleep

    if pantalla_dormida:
        return

    pantalla_dormida = True

    if frame_sleep is None:
        frame_sleep = tk.Frame(ventana, bg="black")

        # Zona grande invisible al usuario: cualquier toque despierta.
        frame_sleep.bind("<Button-1>", despertar_pantalla)
        frame_sleep.bind("<ButtonRelease-1>", lambda e: "break")
        frame_sleep.bind("<B1-Motion>", lambda e: "break")

        # Pantalla de descanso visual: mantiene la marca presente sin mostrar controles.
        lbl_sleep_marca = tk.Label(
            frame_sleep,
            text="SAVIA",
            font=("Segoe UI", 42, "bold"),
            bg="black",
            fg="white"
        )
        lbl_sleep_marca.place(relx=0.5, rely=0.44, anchor="center")
        lbl_sleep_marca.bind("<Button-1>", despertar_pantalla)

        lbl_sleep_frase = tk.Label(
            frame_sleep,
            text="El futuro de tu campo",
            font=("Segoe UI", 18, "bold"),
            bg="black",
            fg="#b7e4c7"
        )
        lbl_sleep_frase.place(relx=0.5, rely=0.56, anchor="center")
        lbl_sleep_frase.bind("<Button-1>", despertar_pantalla)

    frame_sleep.place(relx=0, rely=0, relwidth=1, relheight=1)
    frame_sleep.lift()

    if INTENTAR_APAGADO_FISICO_PANTALLA:
        # Pequeño retraso para que la pantalla negra se dibuje antes de apagar video.
        ventana.after(250, lambda: ejecutar_xset_pantalla("off"))


def reiniciar_timer_inactividad(event=None):
    """Reinicia el contador de inactividad cuando hay interacción del usuario."""
    global timer_inactividad_id

    if pantalla_dormida:
        return None

    try:
        if timer_inactividad_id is not None:
            ventana.after_cancel(timer_inactividad_id)
    except Exception:
        pass

    timer_inactividad_id = ventana.after(TIEMPO_INACTIVIDAD_MS, dormir_pantalla)
    return None


def activar_detector_inactividad():
    """Detecta toques, movimiento o teclado en toda la app."""
    eventos = (
        "<Button-1>",
        "<ButtonRelease-1>",
        "<B1-Motion>",
        "<Motion>",
        "<Key>",
        "<MouseWheel>"
    )

    for evento in eventos:
        ventana.bind_all(evento, reiniciar_timer_inactividad, add="+")

    reiniciar_timer_inactividad()


# ==========================================
# BARRA SUPERIOR
# ==========================================
frame_header = tk.Frame(ventana, bg="#2d6a4f", pady=8)
frame_header.pack(fill="x")

# La barra se divide en 3 columnas iguales:
# izquierda = fecha/hora, centro = logo SAVIA, derecha = menú
frame_header.grid_columnconfigure(0, weight=1, uniform="header")
frame_header.grid_columnconfigure(1, weight=1, uniform="header")
frame_header.grid_columnconfigure(2, weight=1, uniform="header")

lbl_reloj = tk.Label(
    frame_header,
    text="",
    font=("Segoe UI", 10, "bold"),
    bg="#2d6a4f",
    fg="white"
)
lbl_reloj.grid(row=0, column=0, sticky="w", padx=15)

# Logo SAVIA centrado en la barra superior.
# Usa una imagen PNG transparente ubicada en /home/savia/savia_logo_header_blanco.png
RUTA_LOGO_SAVIA = "/home/savia/savia_logo_header_blanco.png"

try:
    logo_savia_img = tk.PhotoImage(file=RUTA_LOGO_SAVIA)
    lbl_logo_savia = tk.Label(
        frame_header,
        image=logo_savia_img,
        bg="#2d6a4f"
    )
    # Mantener referencia para que Tkinter no borre la imagen de memoria
    lbl_logo_savia.image = logo_savia_img
except Exception as e:
    print(f"No se pudo cargar el logo SAVIA: {e}")
    lbl_logo_savia = tk.Label(
        frame_header,
        text="SAVIA",
        font=("Segoe UI", 18, "bold"),
        bg="#2d6a4f",
        fg="white"
    )

lbl_logo_savia.grid(row=0, column=1, sticky="n")

frame_header_menu = tk.Frame(frame_header, bg="#2d6a4f")
frame_header_menu.grid(row=0, column=2, sticky="e", padx=12)



# ==========================================
# ACTUALIZACIÓN DESDE LA INTERFAZ
# ==========================================
def abrir_actualizar_savia():
    """Lanza el actualizador de SAVIA desde la interfaz.

    El script /home/savia/actualizar_savia.sh se encarga de consultar GitHub,
    descargar la última release, respaldar savia_f.py y reiniciar la app.
    Se ejecuta en segundo plano para que pueda cerrar esta interfaz sin bloquearse.
    """
    ruta_actualizador = "/home/savia/actualizar_savia.sh"
    ruta_log = "/home/savia/actualizar_savia.log"

    if not os.path.exists(ruta_actualizador):
        messagebox.showerror(
            "Actualización no disponible",
            "No se encontró el actualizador de SAVIA.\n\n"
            "Debe existir este archivo:\n"
            f"{ruta_actualizador}"
        )
        return

    confirmar = messagebox.askyesno(
        "Actualizar SAVIA",
        "SAVIA buscará la versión más reciente en GitHub.\n\n"
        "Si existe una actualización, se descargará, se creará un respaldo "
        "y la interfaz se reiniciará automáticamente.\n\n"
        "¿Quieres continuar?"
    )

    if not confirmar:
        return

    try:
        # Ejecutar en segundo plano. El script puede cerrar esta app con pkill
        # y volver a abrirla sin dejar la ventana congelada.
        comando = (
            f"nohup bash {ruta_actualizador} > {ruta_log} 2>&1 &"
        )
        subprocess.Popen(["bash", "-lc", comando])

        messagebox.showinfo(
            "Actualizando SAVIA",
            "Se inició la búsqueda de actualización.\n\n"
            "Si hay una versión nueva, la interfaz se cerrará y volverá a abrirse automáticamente.\n\n"
            "Si no pasa nada, revisa el registro en:\n"
            f"{ruta_log}"
        )

    except Exception as e:
        messagebox.showerror(
            "Error de actualización",
            f"No se pudo iniciar el actualizador:\n{e}"
        )

# ==========================================
# MENÚ TÁCTIL DESPLEGABLE - BRILLO_MENU_SLIDER_SIN_BOTONES
# ==========================================
# Panel lateral limpio, con botones grandes y scroll táctil funcional para pantalla de 7 pulgadas.
# FIX_SCROLL_MENU_TACTIL
menu_abierto = False
menu_animando = False
ALTURA_MENU = 405
ANCHO_MENU = 405
PASO_ANIMACION = 35

frame_menu_desplegable = tk.Frame(
    ventana,
    bg="#f8fbfa",
    highlightbackground="#95d5b2",
    highlightthickness=2
)


def cerrar_menu():
    global menu_abierto, menu_animando

    if not menu_abierto or menu_animando:
        return

    menu_animando = True
    btn_menu.config(text="☰", bg="#2d6a4f", activebackground="#40916c")

    def animar_cierre(altura):
        global menu_abierto, menu_animando

        if altura <= 0:
            frame_menu_desplegable.place_forget()
            menu_abierto = False
            menu_animando = False
            return

        frame_menu_desplegable.place(
            relx=1.0,
            x=-12,
            y=54,
            anchor="ne",
            width=ANCHO_MENU,
            height=altura
        )
        ventana.after(8, lambda: animar_cierre(altura - PASO_ANIMACION))

    animar_cierre(ALTURA_MENU)


def abrir_menu():
    global menu_abierto, menu_animando

    if menu_abierto or menu_animando:
        return

    menu_animando = True
    btn_menu.config(text="✕", bg="#40916c", activebackground="#2d6a4f")
    frame_menu_desplegable.lift()

    def animar_apertura(altura):
        global menu_abierto, menu_animando

        frame_menu_desplegable.place(
            relx=1.0,
            x=-12,
            y=54,
            anchor="ne",
            width=ANCHO_MENU,
            height=altura
        )

        if altura >= ALTURA_MENU:
            menu_abierto = True
            menu_animando = False
            return

        ventana.after(8, lambda: animar_apertura(min(ALTURA_MENU, altura + PASO_ANIMACION)))

    animar_apertura(0)


def alternar_menu():
    if menu_abierto:
        cerrar_menu()
    else:
        abrir_menu()


def ejecutar_desde_menu(funcion):
    cerrar_menu()
    ventana.after(180, funcion)


# Control táctil del scroll del menú.
# SAVIA_MENU_SCROLL_BAR_NATIVO_FINAL_V1
# SAVIA_THINGSBOARD_TELEMETRIA_V1
# Scroll corregido: NO usa yview_moveto con la posición del dedo.
# Usa desplazamiento incremental desde donde quedó el menú, como en una app.
menu_touch_last_y_root = 0
menu_touch_total_dy = 0
menu_touch_moved = False
menu_scroll_remainder = 0.0
MENU_TOUCH_UMBRAL_PX = 10
MENU_SCROLL_PIXELS_POR_UNIDAD = 24.0


def _menu_scroll_units(units):
    try:
        canvas_menu.yview_scroll(int(units), "units")
        _actualizar_barra_menu_desde_canvas()
    except Exception:
        pass


def _menu_mousewheel(event):
    try:
        if event.delta:
            _menu_scroll_units(-1 if event.delta > 0 else 1)
    except Exception:
        pass
    return "break"


def _menu_touch_inicio(event):
    global menu_touch_last_y_root, menu_touch_total_dy, menu_touch_moved, menu_scroll_remainder
    menu_touch_last_y_root = event.y_root
    menu_touch_total_dy = 0
    menu_touch_moved = False
    menu_scroll_remainder = 0.0
    return "break"


def _menu_touch_mover(event):
    global menu_touch_last_y_root, menu_touch_total_dy, menu_touch_moved, menu_scroll_remainder
    dy = event.y_root - menu_touch_last_y_root
    menu_touch_last_y_root = event.y_root
    menu_touch_total_dy += dy

    if abs(menu_touch_total_dy) >= MENU_TOUCH_UMBRAL_PX:
        menu_touch_moved = True

    # Finger up => contenido baja hacia opciones inferiores.
    # Finger down => contenido sube hacia opciones superiores.
    menu_scroll_remainder += (-dy / MENU_SCROLL_PIXELS_POR_UNIDAD)
    unidades = int(menu_scroll_remainder)
    if unidades != 0:
        _menu_scroll_units(unidades)
        menu_scroll_remainder -= unidades

    return "break"


def _menu_touch_fin(event=None):
    return "break"


def _vincular_scroll_menu(widget):
    # Evitar interferir con sliders o la barra de scroll.
    if isinstance(widget, tk.Scale) or getattr(widget, "_no_menu_touch_scroll", False):
        return

    if not getattr(widget, "_menu_scroll_bound", False):
        widget._menu_scroll_bound = True
        widget.bind("<MouseWheel>", _menu_mousewheel)
        widget.bind("<ButtonPress-1>", _menu_touch_inicio)
        widget.bind("<B1-Motion>", _menu_touch_mover)
        widget.bind("<ButtonRelease-1>", _menu_touch_fin)

    for hijo in widget.winfo_children():
        _vincular_scroll_menu(hijo)


def crear_seccion_menu(parent, titulo):
    seccion = tk.Frame(parent, bg="#f8fbfa")
    seccion.pack(fill="x", padx=12, pady=(10, 4))

    tk.Label(
        seccion,
        text=titulo,
        font=("Segoe UI", 10, "bold"),
        bg="#f8fbfa",
        fg="#6c757d",
        anchor="w"
    ).pack(fill="x", padx=2, pady=(0, 4))

    return seccion


def crear_boton_menu(parent, texto, subtitulo, comando, bg="white", fg="#1b4332", borde="#d8f3dc"):
    tarjeta = tk.Frame(
        parent,
        bg=bg,
        highlightbackground=borde,
        highlightthickness=1,
        padx=12,
        pady=10,
        cursor="hand2"
    )
    tarjeta.pack(fill="x", pady=5)

    lbl_titulo = tk.Label(
        tarjeta,
        text=texto,
        font=("Segoe UI", 12, "bold"),
        bg=bg,
        fg=fg,
        anchor="w",
        cursor="hand2"
    )
    lbl_titulo.pack(fill="x")

    lbl_subtitulo = None
    if subtitulo:
        lbl_subtitulo = tk.Label(
            tarjeta,
            text=subtitulo,
            font=("Segoe UI", 8, "bold"),
            bg=bg,
            fg="#6c757d" if fg != "white" else "#f8f9fa",
            anchor="w",
            wraplength=300,
            justify="left",
            cursor="hand2"
        )
        lbl_subtitulo.pack(fill="x", pady=(3, 0))

    def soltar(event=None):
        global menu_touch_moved
        if not menu_touch_moved:
            ejecutar_desde_menu(comando)
        return "break"

    widgets = [tarjeta, lbl_titulo]
    if lbl_subtitulo is not None:
        widgets.append(lbl_subtitulo)

    for w in widgets:
        w._menu_scroll_bound = True
        w.bind("<MouseWheel>", _menu_mousewheel)
        w.bind("<ButtonPress-1>", _menu_touch_inicio)
        w.bind("<B1-Motion>", _menu_touch_mover)
        w.bind("<ButtonRelease-1>", soltar)

    return tarjeta


frame_menu_titulo = tk.Frame(frame_menu_desplegable, bg="#1b4332", height=58)
frame_menu_titulo.pack(fill="x")
frame_menu_titulo.pack_propagate(False)

tk.Label(
    frame_menu_titulo,
    text="Menú SAVIA",
    font=("Segoe UI", 15, "bold"),
    bg="#1b4332",
    fg="white"
).pack(side="left", padx=16)

frame_menu_scroll = tk.Frame(frame_menu_desplegable, bg="#f8fbfa")
frame_menu_scroll.pack(fill="both", expand=True, padx=0, pady=(8, 8))

canvas_menu = tk.Canvas(
    frame_menu_scroll,
    bg="#f8fbfa",
    highlightthickness=0,
    bd=0
)
canvas_menu.pack(fill="both", expand=True, padx=(8, 42), pady=0)

frame_menu_contenido = tk.Frame(canvas_menu, bg="#f8fbfa")
ventana_menu_canvas = canvas_menu.create_window((0, 0), window=frame_menu_contenido, anchor="nw")

# Barra lateral derecha visible y arrastrable, independiente del tema de Ubuntu.
canvas_barra_menu = tk.Canvas(
    frame_menu_scroll,
    bg="#eef7f1",
    highlightthickness=1,
    highlightbackground="#b7e4c7",
    bd=0,
    cursor="hand2"
)
canvas_barra_menu._no_menu_touch_scroll = True
track_menu = canvas_barra_menu.create_rectangle(12, 8, 18, 300, fill="#d8f3dc", outline="#d8f3dc")
thumb_menu = canvas_barra_menu.create_rectangle(5, 20, 25, 95, fill="#2d6a4f", outline="#1b4332")
barra_drag_offset = 0


def _colocar_barra_menu(event=None):
    try:
        alto = max(80, frame_menu_scroll.winfo_height() - 12)
        canvas_barra_menu.place(relx=1.0, x=-8, y=6, width=32, height=alto, anchor="ne")
        canvas_barra_menu.tk.call("raise", canvas_barra_menu._w)
        _actualizar_barra_menu_desde_canvas()
    except Exception:
        pass


def _actualizar_barra_menu(first=0.0, last=1.0):
    try:
        first = float(first)
        last = float(last)
        alto = max(80, canvas_barra_menu.winfo_height())
        margen = 8
        area = max(1, alto - margen * 2)
        y1 = margen + int(first * area)
        y2 = margen + int(last * area)
        minimo = 54
        if (y2 - y1) < minimo:
            centro = (y1 + y2) // 2
            y1 = max(margen, centro - minimo // 2)
            y2 = min(alto - margen, y1 + minimo)
            y1 = max(margen, y2 - minimo)
        canvas_barra_menu.coords(track_menu, 13, margen, 19, alto - margen)
        canvas_barra_menu.coords(thumb_menu, 5, y1, 27, y2)
        if first <= 0.001 and last >= 0.999:
            canvas_barra_menu.itemconfig(thumb_menu, fill="#95d5b2", outline="#74c69d")
        else:
            canvas_barra_menu.itemconfig(thumb_menu, fill="#2d6a4f", outline="#1b4332")
    except Exception:
        pass


def _actualizar_barra_menu_desde_canvas():
    try:
        first, last = canvas_menu.yview()
        _actualizar_barra_menu(first, last)
    except Exception:
        pass


def _yscroll_menu(first, last):
    _actualizar_barra_menu(first, last)


def _barra_menu_press(event):
    global barra_drag_offset
    try:
        coords = canvas_barra_menu.coords(thumb_menu)
        if len(coords) == 4 and coords[1] <= event.y <= coords[3]:
            barra_drag_offset = event.y - coords[1]
        else:
            barra_drag_offset = 27
        _barra_menu_drag(event)
    except Exception:
        pass
    return "break"


def _barra_menu_drag(event):
    try:
        alto = max(80, canvas_barra_menu.winfo_height())
        margen = 8
        coords = canvas_barra_menu.coords(thumb_menu)
        thumb_alto = max(54, coords[3] - coords[1]) if len(coords) == 4 else 54
        usable = max(1, alto - (2 * margen) - thumb_alto)
        y1 = event.y - barra_drag_offset
        y1 = max(margen, min(alto - margen - thumb_alto, y1))
        fraccion = (y1 - margen) / usable
        canvas_menu.yview_moveto(max(0.0, min(1.0, fraccion)))
        _actualizar_barra_menu_desde_canvas()
    except Exception:
        pass
    return "break"


canvas_barra_menu.bind("<ButtonPress-1>", _barra_menu_press)
canvas_barra_menu.bind("<B1-Motion>", _barra_menu_drag)
canvas_barra_menu.bind("<MouseWheel>", _menu_mousewheel)
canvas_menu.configure(yscrollcommand=_yscroll_menu)


def _actualizar_scroll_menu(event=None):
    try:
        canvas_menu.configure(scrollregion=canvas_menu.bbox("all"))
        canvas_menu.itemconfig(ventana_menu_canvas, width=canvas_menu.winfo_width())
        _colocar_barra_menu()
        _actualizar_barra_menu_desde_canvas()
    except Exception:
        pass


frame_menu_contenido.bind("<Configure>", _actualizar_scroll_menu)
canvas_menu.bind("<Configure>", _actualizar_scroll_menu)
frame_menu_scroll.bind("<Configure>", _colocar_barra_menu)
canvas_menu.bind("<MouseWheel>", _menu_mousewheel)
canvas_menu.bind("<ButtonPress-1>", _menu_touch_inicio)
canvas_menu.bind("<B1-Motion>", _menu_touch_mover)
canvas_menu.bind("<ButtonRelease-1>", _menu_touch_fin)
seccion_reportes = crear_seccion_menu(frame_menu_contenido, "REPORTES")
crear_boton_menu(
    seccion_reportes,
    "📊  Histórico / Exportar datos",
    "Selecciona fechas y envía el CSV por correo.",
    abrir_exportar_datos,
    bg="white",
    fg="#1b4332"
)

seccion_conectividad = crear_seccion_menu(frame_menu_contenido, "CONECTIVIDAD")
crear_boton_menu(
    seccion_conectividad,
    "📶  Conectar a WiFi",
    "Busca redes disponibles y guarda la conexión.",
    abrir_config_wifi,
    bg="white",
    fg="#1b4332"
)

crear_boton_menu(
    seccion_conectividad,
    "✏️  Nombres de nodos y sensores",
    "Personaliza títulos de nodos y sensores de suelo.",
    abrir_config_nombres,
    bg="white",
    fg="#1b4332"
)

seccion_usuario = crear_seccion_menu(frame_menu_contenido, "BRILLO DE PANTALLA")

frame_brillo_menu = tk.Frame(
    seccion_usuario,
    bg="white",
    highlightbackground="#d8f3dc",
    highlightthickness=1,
    padx=12,
    pady=10
)
frame_brillo_menu.pack(fill="x", pady=5)

tk.Label(
    frame_brillo_menu,
    text="☀️  Brillo",
    font=("Segoe UI", 12, "bold"),
    bg="white",
    fg="#1b4332",
    anchor="w"
).pack(fill="x")

tk.Label(
    frame_brillo_menu,
    text="Ajusta directamente la intensidad de la pantalla.",
    font=("Segoe UI", 8, "bold"),
    bg="white",
    fg="#6c757d",
    anchor="w",
    wraplength=285,
    justify="left"
).pack(fill="x", pady=(3, 8))

fila_brillo_menu = tk.Frame(frame_brillo_menu, bg="white")
fila_brillo_menu.pack(fill="x")

lbl_valor_brillo_menu = tk.Label(
    fila_brillo_menu,
    text=f"{int(ajustes_usuario.get('brillo', 80))}%",
    font=("Segoe UI", 11, "bold"),
    bg="white",
    fg="#1b4332",
    width=5
)
lbl_valor_brillo_menu.pack(side="right", padx=(8, 0))

_brillo_menu_after = {"id": None}

def mover_brillo_menu(v):
    valor = int(float(v))
    ajustes_usuario["brillo"] = valor
    guardar_ajustes_usuario()
    lbl_valor_brillo_menu.config(text=f"{valor}%")
    try:
        lbl_valor_brillo.config(text=f"{valor}%")
    except Exception:
        pass
    if _brillo_menu_after["id"]:
        ventana.after_cancel(_brillo_menu_after["id"])
    _brillo_menu_after["id"] = ventana.after(180, lambda: aplicar_brillo(valor))

slider_brillo_menu = tk.Scale(
    fila_brillo_menu,
    from_=10,
    to=100,
    orient="horizontal",
    font=("Segoe UI", 9, "bold"),
    bg="white",
    fg="#1b4332",
    highlightthickness=0,
    troughcolor="#d8f3dc",
    command=mover_brillo_menu
)
slider_brillo_menu.set(int(ajustes_usuario.get("brillo", 80)))
slider_brillo_menu.pack(side="left", fill="x", expand=True)


seccion_actualizacion = crear_seccion_menu(frame_menu_contenido, "ACTUALIZACIÓN")
crear_boton_menu(
    seccion_actualizacion,
    "⬇️  Actualizar SAVIA",
    "Busca la última versión en GitHub e instala la actualización automáticamente.",
    abrir_actualizar_savia,
    bg="white",
    fg="#1b4332"
)

seccion_energia = crear_seccion_menu(frame_menu_contenido, "ENERGÍA DE LA RASPBERRY")
crear_boton_menu(
    seccion_energia,
    "⏸  Suspender",
    "Pone el equipo en reposo temporal.",
    suspender_rasp,
    bg="white",
    fg="#1b4332"
)
crear_boton_menu(
    seccion_energia,
    "🔄  Reiniciar sistema",
    "Reinicia la Raspberry si algo no responde.",
    reiniciar_rasp,
    bg="white",
    fg="#1b4332"
)
crear_boton_menu(
    seccion_energia,
    "⏻  Apagar Raspberry",
    "Apaga el sistema de forma segura.",
    apagar_rasp,
    bg="#e63946",
    fg="white",
    borde="#e63946"
)


# Vincular scroll táctil al contenido del menú una vez que todos los widgets existen.
_vincular_scroll_menu(frame_menu_contenido)

btn_menu = tk.Button(
    frame_header_menu,
    text="☰",
    font=("Segoe UI", 20, "bold"),
    bg="#2d6a4f",
    fg="white",
    activebackground="#40916c",
    activeforeground="white",
    bd=0,
    width=3,
    height=1,
    cursor="hand2",
    command=alternar_menu
)

btn_menu.pack()


def actualizar_reloj():
    fecha_hora = time.strftime("%d/%m/%Y  %H:%M:%S")
    lbl_reloj.config(text=fecha_hora)
    ventana.after(1000, actualizar_reloj)


actualizar_reloj()


# ==========================================
# CONTENEDOR PRINCIPAL - MONITOREO 3 NODOS
# ==========================================
frame_main = tk.Frame(ventana, bg="#f4f7f6")
frame_main.pack(fill="both", expand=True, padx=20, pady=16)

frame_titulo_monitoreo = tk.Frame(frame_main, bg="#f4f7f6")
frame_titulo_monitoreo.pack(fill="x", pady=(0, 12))

tk.Label(
    frame_titulo_monitoreo,
    text="Monitoreo de Sensores",
    font=("Segoe UI", 18, "bold"),
    bg="#f4f7f6",
    fg="#1b4332"
).pack(side="left")

# Texto de ayuda retirado para una interfaz más limpia.

frame_dashboard = tk.Frame(frame_main, bg="#f4f7f6")
frame_dashboard.pack(fill="both", expand=True)

# PANEL DE RESUMEN DE HOY RETIRADO - UI LIMPIA
# Panel inferior de resumen retirado para mantener la pantalla principal más limpia.

for col in range(3):
    frame_dashboard.grid_columnconfigure(col, weight=1, uniform="nodos")
frame_dashboard.grid_rowconfigure(0, weight=1)


def hacer_clickable(widget, comando):
    widget.bind("<Button-1>", lambda e: comando())
    try:
        widget.config(cursor="hand2")
    except Exception:
        pass
    for hijo in widget.winfo_children():
        hacer_clickable(hijo, comando)


def crear_tarjeta_resumen_nodo(parent, nodo, columna):
    tarjeta = tk.Frame(
        parent,
        bg="white",
        highlightbackground="#b7e4c7",
        highlightthickness=2,
        padx=14,
        pady=12
    )
    tarjeta.grid(row=0, column=columna, sticky="nsew", padx=8, pady=6)

    encabezado_frame = tk.Frame(tarjeta, bg="white")
    encabezado_frame.pack(fill="x", pady=(2, 8))

    tk.Label(
        encabezado_frame,
        text="🌱",
        font=("Segoe UI", 18, "bold"),
        bg="white",
        fg="#2d6a4f"
    ).pack(side="left")

    encabezado = tk.Label(
        encabezado_frame,
        text=nombre_nodo(nodo),
        font=("Segoe UI", 14, "bold"),
        bg="white",
        fg="#1b4332"
    )
    encabezado.pack(side="left", padx=(6, 0))

    barra_fondo = tk.Frame(tarjeta, bg="#e9ecef", height=8)
    barra_fondo.pack(fill="x", pady=(0, 12))
    barra_fondo.pack_propagate(False)

    lbl_prom = tk.Label(
        tarjeta,
        text="-- %",
        font=("Segoe UI", 36, "bold"),
        bg="white",
        fg="#6c757d"
    )
    lbl_prom.pack(pady=(0, 2))

    tk.Label(
        tarjeta,
        text="Promedio de 3 sensores de suelo",
        font=("Segoe UI", 9, "bold"),
        bg="white",
        fg="#6c757d"
    ).pack(pady=(0, 12))

    lbl_clima = tk.Label(
        tarjeta,
        text="🌡 -- °C   💧 Aire -- %",
        font=("Segoe UI", 10, "bold"),
        bg="#eaf4f4",
        fg="#1b4332",
        padx=8,
        pady=8
    )
    lbl_clima.pack(fill="x", pady=(0, 10))

    frame_ultima = tk.Frame(tarjeta, bg="white")
    frame_ultima.pack(pady=(0, 10))

    # Indicador visual de comunicación LoRa, colocado junto a "Última lectura".
    # Verde = recibe datos recientes. Rojo = sin lectura reciente. Gris = esperando primera lectura.
    canvas_conexion = tk.Canvas(
        frame_ultima,
        width=14,
        height=14,
        bg="white",
        highlightthickness=0,
        bd=0
    )
    canvas_conexion.pack(side="left", padx=(0, 6), pady=1)
    conexion_dot_item = canvas_conexion.create_oval(
        3, 3, 11, 11,
        fill=COLOR_LORA_ESPERANDO,
        outline=COLOR_LORA_ESPERANDO
    )

    lbl_estado = tk.Label(
        frame_ultima,
        text="Última lectura: Sin lectura",
        font=("Segoe UI", 9),
        bg="white",
        fg="#777"
    )
    lbl_estado.pack(side="left")

    btn_alerta = tk.Button(
        tarjeta,
        text="⏰ Configurar alerta de riego\nSin recordatorio activo",
        font=("Segoe UI", 10, "bold"),
        bg="#e9ecef",
        fg="#1b4332",
        activebackground="#d8f3dc",
        activeforeground="#1b4332",
        relief="flat",
        bd=0,
        highlightthickness=2,
        highlightbackground="#ced4da",
        justify="center",
        padx=10,
        pady=8,
        command=lambda n=nodo: abrir_config_alerta_riego(n)
    )
    btn_alerta.pack(fill="x", pady=(4, 0))

    labels_resumen[nodo] = {
        "tarjeta": tarjeta,
        "titulo": encabezado,
        "prom": lbl_prom,
        "clima": lbl_clima,
        "estado": lbl_estado,
        "alerta_btn": btn_alerta,
        "conexion_canvas": canvas_conexion,
        "conexion_dot_item": conexion_dot_item
    }

    # El usuario puede tocar la parte de datos para abrir el detalle.
    # El botón inferior queda reservado exclusivamente para la alerta de riego.
    for widget in (encabezado_frame, encabezado, lbl_prom, lbl_clima, frame_ultima, lbl_estado):
        hacer_clickable(widget, lambda n=nodo: abrir_detalle_nodo(n))

    actualizar_alerta_ui(nodo)
    return tarjeta


def crear_tarjeta_detalle(parent, titulo, valor_inicial="--", fila=0, columna=0, columnas=1, grande=False):
    tarjeta = tk.Frame(
        parent,
        bg="white",
        highlightbackground="#b7e4c7",
        highlightthickness=2,
        padx=10,
        pady=8
    )
    tarjeta.grid(row=fila, column=columna, columnspan=columnas, sticky="nsew", padx=6, pady=6)

    lbl_titulo = tk.Label(
        tarjeta,
        text=titulo,
        font=("Segoe UI", 11, "bold"),
        bg="white",
        fg="#1b4332"
    )
    lbl_titulo.pack(pady=(2, 4))

    lbl_valor = tk.Label(
        tarjeta,
        text=valor_inicial,
        font=("Segoe UI", 26 if grande else 22, "bold"),
        bg="white",
        fg="#2d6a4f"
    )
    lbl_valor.pack(expand=True)
    lbl_valor.titulo_label = lbl_titulo

    return lbl_valor


def abrir_detalle_nodo(nodo):
    if nodo in ventanas_detalle and ventanas_detalle[nodo].winfo_exists():
        ventanas_detalle[nodo].lift()
        ventanas_detalle[nodo].focus_force()
        return

    detalle = tk.Toplevel(ventana)
    detalle.title(f"Detalle Nodo {nodo}")
    detalle.geometry("800x480+0+0")
    detalle.configure(bg="#f4f7f6")
    detalle.resizable(False, False)
    detalle.transient(ventana)
    detalle.focus_force()

    try:
        detalle.attributes("-fullscreen", True)
    except Exception:
        pass

    ventanas_detalle[nodo] = detalle

    def cerrar_detalle():
        if nodo in labels_detalle:
            del labels_detalle[nodo]
        if nodo in ventanas_detalle:
            del ventanas_detalle[nodo]
        detalle.destroy()

    frame_detalle_header = tk.Frame(detalle, bg="#2d6a4f", height=48)
    frame_detalle_header.pack(fill="x")
    frame_detalle_header.pack_propagate(False)

    lbl_titulo_detalle = tk.Label(
        frame_detalle_header,
        text=f"🌱 {nombre_nodo(nodo)} - Detalle",
        font=("Segoe UI", 15, "bold"),
        bg="#2d6a4f",
        fg="white"
    )
    lbl_titulo_detalle.pack(side="left", padx=18)

    tk.Button(
        frame_detalle_header,
        text="← Regresar",
        font=("Segoe UI", 11, "bold"),
        bg="white",
        fg="#2d6a4f",
        activebackground="#d8f3dc",
        activeforeground="#1b4332",
        relief="flat",
        bd=0,
        padx=14,
        command=cerrar_detalle
    ).pack(side="right", padx=12, pady=7)

    frame_detalle_main = tk.Frame(detalle, bg="#f4f7f6")
    frame_detalle_main.pack(fill="both", expand=True, padx=18, pady=14)

    frame_detalle_main.grid_columnconfigure(0, weight=1, uniform="detalle")
    frame_detalle_main.grid_columnconfigure(1, weight=1, uniform="detalle")
    frame_detalle_main.grid_columnconfigure(2, weight=1, uniform="detalle")
    frame_detalle_main.grid_rowconfigure(0, weight=1)
    frame_detalle_main.grid_rowconfigure(1, weight=1)
    frame_detalle_main.grid_rowconfigure(2, weight=1)

    lbl_prom = crear_tarjeta_detalle(
        frame_detalle_main,
        f"Promedio · {nombre_nodo(nodo)}",
        "-- %",
        fila=0,
        columna=0,
        columnas=3,
        grande=True
    )

    lbl_s1 = crear_tarjeta_detalle(frame_detalle_main, nombre_sensor(nodo, "s1"), "-- %", 1, 0)
    lbl_s2 = crear_tarjeta_detalle(frame_detalle_main, nombre_sensor(nodo, "s2"), "-- %", 1, 1)
    lbl_s3 = crear_tarjeta_detalle(frame_detalle_main, nombre_sensor(nodo, "s3"), "-- %", 1, 2)
    lbl_temp = crear_tarjeta_detalle(frame_detalle_main, "Temperatura del aire", "-- °C", 2, 0)
    lbl_hum = crear_tarjeta_detalle(frame_detalle_main, "Humedad del aire", "-- %", 2, 1)

    tarjeta_estado = tk.Frame(
        frame_detalle_main,
        bg="white",
        highlightbackground="#b7e4c7",
        highlightthickness=2,
        padx=10,
        pady=8
    )
    tarjeta_estado.grid(row=2, column=2, sticky="nsew", padx=6, pady=6)

    tk.Label(
        tarjeta_estado,
        text="Estado",
        font=("Segoe UI", 11, "bold"),
        bg="white",
        fg="#1b4332"
    ).pack(pady=(2, 12))

    lbl_ultimo = tk.Label(
        tarjeta_estado,
        text="Última lectura: Sin lectura",
        font=("Segoe UI", 11, "bold"),
        bg="white",
        fg="#6c757d",
        wraplength=190
    )
    lbl_ultimo.pack(expand=True)

    labels_detalle[nodo] = {
        "titulo_ventana": lbl_titulo_detalle,
        "prom": lbl_prom,
        "prom_titulo": getattr(lbl_prom, "titulo_label", None),
        "s1": lbl_s1,
        "s1_titulo": getattr(lbl_s1, "titulo_label", None),
        "s2": lbl_s2,
        "s2_titulo": getattr(lbl_s2, "titulo_label", None),
        "s3": lbl_s3,
        "s3_titulo": getattr(lbl_s3, "titulo_label", None),
        "temp": lbl_temp,
        "hum": lbl_hum,
        "ultimo": lbl_ultimo
    }

    detalle.protocol("WM_DELETE_WINDOW", cerrar_detalle)
    actualizar_interfaz_nodo(nodo)


for nodo in (1, 2, 3):
    crear_tarjeta_resumen_nodo(frame_dashboard, nodo, nodo - 1)

# Inicializa los textos de las tarjetas.
for nodo in (1, 2, 3):
    actualizar_interfaz_nodo(nodo)


# ==========================================
# PANTALLA DE INICIO SAVIA
# ==========================================
def mostrar_pantalla_inicio():
    """Pantalla inicial tipo producto: aparece unos segundos al arrancar."""
    splash = tk.Frame(ventana, bg="#f4f7f6")
    splash.place(relx=0, rely=0, relwidth=1, relheight=1)
    splash.lift()

    cont = tk.Frame(splash, bg="#f4f7f6")
    cont.place(relx=0.5, rely=0.48, anchor="center")

    try:
        logo_inicio = tk.PhotoImage(file=RUTA_LOGO_SAVIA)
        logo_label = tk.Label(cont, image=logo_inicio, bg="#f4f7f6")
        logo_label.image = logo_inicio
        logo_label.pack(pady=(0, 18))
    except Exception:
        tk.Label(
            cont,
            text="SAVIA",
            font=("Segoe UI", 36, "bold"),
            bg="#f4f7f6",
            fg="#1b4332"
        ).pack(pady=(0, 18))

    tk.Label(
        cont,
        text="Inicializando monitoreo del cultivo",
        font=("Segoe UI", 18, "bold"),
        bg="#f4f7f6",
        fg="#1b4332"
    ).pack(pady=(0, 12))

    lbl_estado_inicio = tk.Label(
        cont,
        text="Conectando sensores...",
        font=("Segoe UI", 12, "bold"),
        bg="#f4f7f6",
        fg="#6c757d"
    )
    lbl_estado_inicio.pack(pady=(0, 12))

    barra_fondo = tk.Frame(cont, bg="#d8f3dc", width=360, height=12)
    barra_fondo.pack()
    barra_fondo.pack_propagate(False)
    barra = tk.Frame(barra_fondo, bg="#52b788", width=1, height=12)
    barra.place(x=0, y=0)

    pasos = [
        "Conectando sensores...",
        "Preparando historial...",
        "Cargando interfaz SAVIA...",
        "Listo"
    ]

    def animar(i=0):
        if i < len(pasos):
            lbl_estado_inicio.config(text=pasos[i])
            barra.place_configure(width=int(360 * (i + 1) / len(pasos)))
            ventana.after(650, lambda: animar(i + 1))
        else:
            splash.destroy()

    animar()

# ==========================================
# INICIO DEL SISTEMA
# ==========================================
def on_closing():
    cerrar_uart()
    ventana.destroy()


ventana.protocol("WM_DELETE_WINDOW", on_closing)

activar_detector_inactividad()
try:
    aplicar_brillo(ajustes_usuario.get("brillo", 80))
except Exception as e:
    print(f"No se pudo aplicar el brillo inicial: {e}")
actualizar_resumen_hoy()
actualizar_alertas_riego()
actualizar_indicadores_conexion_lora()
mostrar_pantalla_inicio()
ventana.after(500, leer_sensores)
ventana.mainloop()
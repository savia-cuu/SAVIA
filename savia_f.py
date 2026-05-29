import tkinter as tk
from tkinter import messagebox
import serial
from serial.tools import list_ports
import time
import re
import glob
import subprocess

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
    ventana_wifi = tk.Toplevel(ventana)
    ventana_wifi.title("Configurar WiFi")
    ventana_wifi.geometry("420x300")
    ventana_wifi.configure(bg="white")
    ventana_wifi.resizable(False, False)

    tk.Label(
        ventana_wifi,
        text="Configurar red WiFi",
        font=("Segoe UI", 16, "bold"),
        bg="white",
        fg="#2d6a4f"
    ).pack(pady=(15, 5))

    tk.Label(
        ventana_wifi,
        text="Nombre de la red (SSID):",
        font=("Segoe UI", 10, "bold"),
        bg="white"
    ).pack(pady=(10, 0))

    entry_ssid = tk.Entry(
        ventana_wifi,
        font=("Segoe UI", 12),
        width=30
    )
    entry_ssid.pack(pady=5)

    tk.Label(
        ventana_wifi,
        text="Contraseña:",
        font=("Segoe UI", 10, "bold"),
        bg="white"
    ).pack(pady=(10, 0))

    entry_password = tk.Entry(
        ventana_wifi,
        font=("Segoe UI", 12),
        width=30,
        show="*"
    )
    entry_password.pack(pady=5)

    lbl_wifi_estado = tk.Label(
        ventana_wifi,
        text="",
        font=("Segoe UI", 9),
        bg="white",
        fg="#555",
        wraplength=360
    )
    lbl_wifi_estado.pack(pady=8)

    def conectar_wifi():
        ssid = entry_ssid.get().strip()
        password = entry_password.get().strip()

        if not ssid:
            messagebox.showwarning("Dato faltante", "Escribe el nombre de la red WiFi.")
            return

        lbl_wifi_estado.config(text="Conectando a WiFi...")
        ventana_wifi.update_idletasks()

        try:
            if password:
                comando = [
                    "nmcli",
                    "dev",
                    "wifi",
                    "connect",
                    ssid,
                    "password",
                    password
                ]
            else:
                comando = [
                    "nmcli",
                    "dev",
                    "wifi",
                    "connect",
                    ssid
                ]

            resultado = subprocess.run(
                comando,
                capture_output=True,
                text=True,
                timeout=25
            )

            if resultado.returncode == 0:
                lbl_wifi_estado.config(
                    text="Conexión WiFi realizada correctamente.",
                    fg="#2d6a4f"
                )
                messagebox.showinfo("WiFi", "Conexión WiFi realizada correctamente.")
                ventana_wifi.destroy()
            else:
                error = resultado.stderr.strip() or resultado.stdout.strip()
                lbl_wifi_estado.config(
                    text=f"No se pudo conectar: {error}",
                    fg="#e63946"
                )

        except FileNotFoundError:
            lbl_wifi_estado.config(
                text="No se encontró nmcli. Verifica que NetworkManager esté instalado.",
                fg="#e63946"
            )

        except subprocess.TimeoutExpired:
            lbl_wifi_estado.config(
                text="La conexión tardó demasiado. Revisa el SSID o la contraseña.",
                fg="#e63946"
            )

        except Exception as e:
            lbl_wifi_estado.config(
                text=f"Error: {e}",
                fg="#e63946"
            )

    frame_wifi_botones = tk.Frame(ventana_wifi, bg="white")
    frame_wifi_botones.pack(pady=12)

    tk.Button(
        frame_wifi_botones,
        text="Conectar",
        font=("Segoe UI", 11, "bold"),
        bg="#52b788",
        fg="white",
        width=12,
        command=conectar_wifi
    ).pack(side="left", padx=5)

    tk.Button(
        frame_wifi_botones,
        text="Cancelar",
        font=("Segoe UI", 11, "bold"),
        bg="#ccc",
        fg="#333",
        width=12,
        command=ventana_wifi.destroy
    ).pack(side="left", padx=5)


# ==========================================
# LÓGICA DE LA INTERFAZ Y CONTROL
# ==========================================
PATRON = re.compile(
    r"\(\s*([\d.+-]+)\s*,\s*([\d.+-]+)\s*,\s*([\d.+-]+)\s*,\s*([\d.+-]+)\s*,\s*([\d.+-]+)\s*\)"
)


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

                m = PATRON.search(linea)

                if m:
                    v1 = float(m.group(1))
                    v2 = float(m.group(2))
                    v3 = float(m.group(3))
                    temp = float(m.group(4))
                    hum = float(m.group(5))
                    prom = (v1 + v2 + v3) / 3

                    lbl_val_ec5_1.config(text=f"{v1:.1f} %")
                    lbl_val_ec5_2.config(text=f"{v2:.1f} %")
                    lbl_val_ec5_3.config(text=f"{v3:.1f} %")
                    lbl_val_prom.config(text=f"{prom:.1f} %")
                    lbl_val_temp.config(text=f"{temp:.1f} °C")
                    lbl_val_hum.config(text=f"{hum:.1f} %")

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


def set_modo_auto():
    btn_auto.config(bg="#52b788", fg="white")
    btn_manual.config(bg="#ccc", fg="#555")
    lbl_estado.config(text="⚙️ Manejado por SAVIA (Automático)", fg="#2d6a4f")
    btn_riego_on.config(state="disabled", bg="#ccc")
    btn_riego_off.config(state="disabled", bg="#ccc")
    enviar_comando("a")


def set_modo_manual():
    btn_auto.config(bg="#ccc", fg="#555")
    btn_manual.config(bg="#52b788", fg="white")
    lbl_estado.config(text="✋ Control Manual Activado", fg="#e63946")
    btn_riego_on.config(state="normal", bg="#ccc")
    btn_riego_off.config(state="normal", bg="#e63946")
    enviar_comando("m")


def encender_riego():
    btn_riego_on.config(bg="#52b788", fg="white")
    btn_riego_off.config(bg="#ccc", fg="#555")
    enviar_comando("1o")


def apagar_riego():
    btn_riego_on.config(bg="#ccc", fg="#555")
    btn_riego_off.config(bg="#e63946", fg="white")
    enviar_comando("1c")


# ==========================================
# DISEÑO DE LA VENTANA
# ==========================================
ventana = tk.Tk()
ventana.title("SAVIA - Panel de Control")
ventana.geometry("800x480")
ventana.configure(bg="#f4f7f6")
ventana.attributes("-fullscreen", True)

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

tk.Label(
    frame_header,
    text="🌱 SAVIA",
    font=("Segoe UI", 18, "bold"),
    bg="#2d6a4f",
    fg="white"
).grid(row=0, column=1, sticky="n")

frame_header_menu = tk.Frame(frame_header, bg="#2d6a4f")
frame_header_menu.grid(row=0, column=2, sticky="e", padx=12)

# ==========================================
# MENÚ TÁCTIL DESPLEGABLE
# ==========================================
# Nota: este menú reemplaza al tk.Menu clásico porque en pantalla táctil
# es más cómodo usar botones grandes y claros.
menu_abierto = False
menu_animando = False
ALTURA_MENU = 320
ANCHO_MENU = 340
PASO_ANIMACION = 32

frame_menu_desplegable = tk.Frame(
    ventana,
    bg="white",
    highlightbackground="#b7e4c7",
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


def crear_boton_menu(parent, texto, comando, bg="white", fg="#1b4332"):
    boton = tk.Button(
        parent,
        text=texto,
        font=("Segoe UI", 12, "bold"),
        bg=bg,
        fg=fg,
        activebackground="#d8f3dc" if bg == "white" else bg,
        activeforeground=fg,
        relief="flat",
        bd=0,
        height=2,
        anchor="w",
        padx=16,
        cursor="hand2",
        command=lambda: ejecutar_desde_menu(comando)
    )
    boton.pack(fill="x", padx=12, pady=5)
    return boton


frame_menu_titulo = tk.Frame(frame_menu_desplegable, bg="#f1faee")
frame_menu_titulo.pack(fill="x")

tk.Label(
    frame_menu_titulo,
    text="Menú de opciones",
    font=("Segoe UI", 13, "bold"),
    bg="#f1faee",
    fg="#1b4332"
).pack(side="left", padx=14, pady=10)

tk.Button(
    frame_menu_titulo,
    text="Cerrar",
    font=("Segoe UI", 10, "bold"),
    bg="#f1faee",
    fg="#555",
    activebackground="#d8f3dc",
    relief="flat",
    bd=0,
    cursor="hand2",
    command=cerrar_menu
).pack(side="right", padx=12)

crear_boton_menu(
    frame_menu_desplegable,
    "📶  Conectar a WiFi",
    abrir_config_wifi,
    bg="white",
    fg="#1b4332"
)

tk.Label(
    frame_menu_desplegable,
    text="⏻  Energía de la Raspberry",
    font=("Segoe UI", 11, "bold"),
    bg="white",
    fg="#6c757d",
    anchor="w"
).pack(fill="x", padx=16, pady=(8, 2))

crear_boton_menu(
    frame_menu_desplegable,
    "⏸  Suspender pantalla/equipo",
    suspender_rasp,
    bg="#f8f9fa",
    fg="#1b4332"
)

crear_boton_menu(
    frame_menu_desplegable,
    "🔄  Reiniciar sistema",
    reiniciar_rasp,
    bg="#f8f9fa",
    fg="#1b4332"
)

crear_boton_menu(
    frame_menu_desplegable,
    "⏻  Apagar Raspberry",
    apagar_rasp,
    bg="#e63946",
    fg="white"
)

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
# CONTENEDOR PRINCIPAL
# ==========================================
frame_main = tk.Frame(ventana, bg="#f4f7f6")
frame_main.pack(fill="both", expand=True, padx=20, pady=20)

# ==========================================
# PANEL IZQUIERDO
# ==========================================
frame_izq = tk.Frame(frame_main, bg="white", padx=10, pady=10, relief="flat")
frame_izq.pack(side="left", fill="both", expand=True, padx=(0, 10))

tk.Label(
    frame_izq,
    text="Datos del Cultivo",
    font=("Segoe UI", 13, "bold"),
    bg="white"
).pack(pady=(0, 8))

frame_sensores = tk.Frame(frame_izq, bg="white")
frame_sensores.pack(fill="both", expand=True)


def crear_tarjeta_sensor(parent, titulo, fila, columna):
    tarjeta = tk.Frame(
        parent,
        bg="#eaf4f4",
        highlightbackground="#52b788",
        highlightthickness=2,
        padx=5,
        pady=5
    )

    tarjeta.grid(row=fila, column=columna, padx=5, pady=5, sticky="nsew")

    parent.grid_columnconfigure(columna, weight=1)
    parent.grid_rowconfigure(fila, weight=1)

    tk.Label(
        tarjeta,
        text=titulo,
        font=("Segoe UI", 8),
        bg="#eaf4f4"
    ).pack()

    lbl_valor = tk.Label(
        tarjeta,
        text="--",
        font=("Segoe UI", 14, "bold"),
        fg="#2d6a4f",
        bg="#eaf4f4"
    )

    lbl_valor.pack(pady=2)

    return lbl_valor


lbl_val_ec5_1 = crear_tarjeta_sensor(frame_sensores, "Hum. Suelo 1 (EC5)", 0, 0)
lbl_val_ec5_2 = crear_tarjeta_sensor(frame_sensores, "Hum. Suelo 2 (EC5)", 0, 1)
lbl_val_ec5_3 = crear_tarjeta_sensor(frame_sensores, "Hum. Suelo 3 (EC5)", 0, 2)

lbl_val_prom = crear_tarjeta_sensor(frame_sensores, "Prom. Suelo", 1, 0)
lbl_val_temp = crear_tarjeta_sensor(frame_sensores, "Temp. Aire (DHT22)", 1, 1)
lbl_val_hum = crear_tarjeta_sensor(frame_sensores, "Hum. Aire (DHT22)", 1, 2)

# ==========================================
# PANEL DERECHO
# ==========================================
frame_der = tk.Frame(frame_main, bg="white", padx=20, pady=20, relief="flat")
frame_der.pack(side="right", fill="both", expand=True, padx=(10, 0))

tk.Label(
    frame_der,
    text="Modo del Sistema",
    font=("Segoe UI", 16, "bold"),
    bg="white"
).pack()

lbl_estado = tk.Label(
    frame_der,
    text="--",
    font=("Segoe UI", 12, "bold"),
    bg="#eee",
    pady=10
)

lbl_estado.pack(fill="x", pady=10)

frame_botones_modo = tk.Frame(frame_der, bg="white")
frame_botones_modo.pack(fill="x", pady=(0, 20))

btn_manual = tk.Button(
    frame_botones_modo,
    text="✋ Manual",
    font=("Segoe UI", 12, "bold"),
    command=set_modo_manual,
    height=2
)

btn_manual.pack(side="left", fill="x", expand=True, padx=5)

btn_auto = tk.Button(
    frame_botones_modo,
    text="⚙️ Automático",
    font=("Segoe UI", 12, "bold"),
    command=set_modo_auto,
    height=2
)

btn_auto.pack(side="right", fill="x", expand=True, padx=5)

tk.Frame(frame_der, height=2, bg="#eee").pack(fill="x", pady=15)

tk.Label(
    frame_der,
    text="Bomba de Riego (Zona 1)",
    font=("Segoe UI", 14, "bold"),
    bg="white"
).pack(pady=(0, 10))

frame_botones_riego = tk.Frame(frame_der, bg="white")
frame_botones_riego.pack(fill="x")

btn_riego_on = tk.Button(
    frame_botones_riego,
    text="💧 Activar",
    font=("Segoe UI", 12, "bold"),
    command=encender_riego,
    height=2
)

btn_riego_on.pack(side="left", fill="x", expand=True, padx=5)

btn_riego_off = tk.Button(
    frame_botones_riego,
    text="🛑 Desactivar",
    font=("Segoe UI", 12, "bold"),
    command=apagar_riego,
    height=2
)

btn_riego_off.pack(side="right", fill="x", expand=True, padx=5)

# ==========================================
# INICIO DEL SISTEMA
# ==========================================
def on_closing():
    cerrar_uart()
    ventana.destroy()


ventana.protocol("WM_DELETE_WINDOW", on_closing)

set_modo_auto()
ventana.after(500, leer_sensores)
ventana.mainloop()
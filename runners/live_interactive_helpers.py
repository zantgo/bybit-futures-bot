# =============== INICIO ARCHIVO: runners/live_interactive_helpers.py (Solo Linux) ===============
"""
Contiene las funciones de apoyo y el estado global para el live_interactive_runner.
Esto incluye el listener de teclas para la intervención manual, optimizado para Linux.
"""
import threading
import time
import os
import sys

# --- Imports para listener de teclas (Solo Linux/Unix) ---
# Se eliminan los imports y la lógica para Windows.
import select
import tty
import termios

# --- Estado Global para Intervención Manual ---
_key_pressed_event = threading.Event()
_manual_intervention_char = 'm'
_stop_key_listener_thread = threading.Event()

def get_key_pressed_event() -> threading.Event:
    """Devuelve el evento que se activa cuando se presiona la tecla de intervención."""
    return _key_pressed_event

def get_stop_key_listener_event() -> threading.Event:
    """Devuelve el evento para detener el hilo del listener de teclas."""
    return _stop_key_listener_thread

# --- Hilo Listener de Teclas (Solo Linux/Unix) ---
def key_listener_thread_func():
    """
    Hilo que escucha en segundo plano la pulsación de una tecla para activar el menú manual.
    Diseñado y optimizado para sistemas tipo Unix (Linux, macOS).
    """
    global _key_pressed_event, _manual_intervention_char, _stop_key_listener_thread
    
    # Verificar que estamos en un entorno Unix compatible.
    if os.name != 'posix':
        print(f"ADVERTENCIA [Key Listener]: El listener de teclas está diseñado para Linux/Unix (os.name='posix') pero el sistema es '{os.name}'. Podría no funcionar.")

    print(f"\n[Key Listener] Hilo iniciado. Presiona '{_manual_intervention_char}' para menú manual, Ctrl+C para salir del bot.")
    
    old_settings = None
    try:
        # Verificar que la entrada estándar es una terminal interactiva (TTY).
        if not sys.stdin.isatty():
             print("ERROR [Key Listener]: La entrada estándar no es una TTY. El modo interactivo no funcionará en este entorno (ej. ejecución en segundo plano sin terminal).")
             return
             
        # Guardar la configuración actual de la terminal para restaurarla después.
        old_settings = termios.tcgetattr(sys.stdin)
        # Poner la terminal en modo "cbreak", que lee las teclas al instante sin esperar un Enter.
        tty.setcbreak(sys.stdin.fileno())
        
        # Bucle principal del listener.
        while not _stop_key_listener_thread.is_set():
            # Usar select para esperar datos en la entrada estándar con un timeout.
            # Esto evita que el bucle consuma 100% de la CPU.
            if select.select([sys.stdin], [], [], 0.1)[0]:
                char = sys.stdin.read(1).lower()
                if char == _manual_intervention_char:
                    print(f"\n[Key Listener] Tecla '{_manual_intervention_char}' detectada!")
                    _key_pressed_event.set()
                    
    except Exception as e:
        # Silenciar errores que pueden ocurrir durante el cierre abrupto del programa.
        # En un cierre normal, el bloque finally se encargará de la limpieza.
        print(f"DEBUG [Key Listener]: Excepción en el hilo del listener (puede ser normal al cerrar): {e}")
        pass
    finally:
        # --- Bloque CRÍTICO: Restaurar la configuración de la TTY ---
        # Es fundamental que esto se ejecute siempre para no dejar la terminal del usuario corrupta.
        if old_settings:
            try:
                # TCSADRAIN: Espera a que toda la salida pendiente se escriba antes de cambiar la configuración.
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
                print("[Key Listener] Configuración de terminal restaurada exitosamente.")
            except Exception as e_restore:
               print("\n" + "!"*80)
               print("!!! ERROR GRAVE [Key Listener]: Falló la restauración de la configuración de la terminal !!!".center(80))
               print(f"!!! Detalle del error: {e_restore} !!!".center(80))
               print("!!! Es posible que necesites reiniciar tu terminal. Ejecuta el comando 'reset' si es necesario. !!!".center(80))
               print("!"*80 + "\n")
            
    print("[Key Listener] Hilo terminado.")

# =============== FIN ARCHIVO: runners/live_interactive_helpers.py (Solo Linux) ===============
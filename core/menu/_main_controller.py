# core/menu/_main_controller.py

"""
Controlador Principal del Ciclo de Vida de la TUI.

Este módulo contiene la lógica de orquestación de alto nivel para la interfaz
de usuario. Es el verdadero punto de entrada de la aplicación después de `main.py`.
"""
import sys
import os
import time
import traceback
from typing import Dict, Any

try:
    from simple_term_menu import TerminalMenu
except ImportError:
    TerminalMenu = None

# --- Dependencias del Menú ---
# Se importa el paquete 'screens' completo, que actúa como fachada para todas las pantallas.
from . import screens
from ._helpers import clear_screen, print_tui_header, press_enter_to_continue, MENU_STYLE

# --- Variables Globales del Controlador ---
# Almacenaremos las dependencias inyectadas desde main.py aquí
_deps: Dict[str, Any] = {}

def launch_bot(dependencies: Dict[str, Any]):
    """
    Punto de entrada principal para la TUI. Orquesta todo el ciclo de vida.

    Args:
        dependencies (Dict[str, Any]): Diccionario con todos los módulos
                                       y componentes del bot inyectados.
    """
    global _deps
    if not TerminalMenu:
        print("ERROR: La librería 'simple-term-menu' no está instalada. Por favor, ejecuta 'pip install simple-term-menu'")
        sys.exit(1)

    _deps = dependencies
    
    # Inyectar dependencias en las pantallas que las necesiten.
    if hasattr(screens, 'init_screens'):
        screens.init_screens(dependencies)
    
    bot_initialized = False # Variable para rastrear el estado para un apagado seguro
    try:
        # 1. Pantalla de Bienvenida y Configuración
        # Esta función ahora controla el bucle de "Iniciar/Modificar/Salir".
        if not screens.show_welcome_screen():
            # El usuario eligió salir en la pantalla de bienvenida.
            print("\nSalida solicitada por el usuario. ¡Hasta luego!")
            sys.exit(0)

        # 2. Inicialización del Backend
        # Se obtienen los parámetros de configuración que el usuario pudo haber modificado.
        config_module = _deps["config"]
        base_size = getattr(config_module, 'POSITION_BASE_SIZE_USDT', 10.0)
        initial_slots = getattr(config_module, 'POSITION_MAX_LOGICAL_POSITIONS', 5)

        bot_initialized = _deps["initialize_bot_backend"](
            # Argumentos requeridos por la función de inicialización.
            operation_mode="live_interactive",
            base_size=base_size,
            initial_slots=initial_slots,
            # Inyección del resto de las dependencias.
            config_module=config_module,
            event_processor_module=_deps["event_processor"],
            position_manager_module=_deps["position_manager"],
            ta_manager_module=_deps["ta_manager"],
            open_snapshot_logger_module=_deps["open_snapshot_logger"]
        )
        
        if not bot_initialized:
            print("\nEl bot no pudo inicializarse. Revisa los logs de error.")
            press_enter_to_continue()
            sys.exit(1)
            
        print("\nBot inicializado y operando en segundo plano.")
        time.sleep(2)
        
        # 3. Bucle del Dashboard Principal
        # Esta función ahora es bloqueante y solo retorna cuando el usuario decide salir.
        screens.show_dashboard_screen()

    except (KeyboardInterrupt, SystemExit):
        print("\n\nInterrupción detectada. Saliendo de forma ordenada...")
    except Exception as e:
        clear_screen()
        print("\n" + "="*80)
        print("!!! ERROR CRÍTICO INESPERADO EN EL CONTROLADOR DEL MENÚ !!!")
        print(f"  Tipo de Error: {type(e).__name__}")
        print(f"  Mensaje: {e}")
        print("-" * 80)
        traceback.print_exc()
        print("=" * 80)
    finally:
        # 4. Secuencia de Apagado
        print("\nIniciando secuencia de apagado final...")
        final_summary = {}
        # Llamamos a la función de apagado, pasando el estado de inicialización.
        _deps["shutdown_bot_backend"](
            final_summary=final_summary,
            bot_started=bot_initialized,
            config_module=_deps["config"],
            connection_ticker_module=_deps["connection_ticker"],
            position_manager_module=_deps["position_manager"],
            open_snapshot_logger_module=_deps["open_snapshot_logger"]
        )
        print("\nPrograma finalizado. ¡Hasta luego!")
        # os._exit(0) asegura que todos los hilos terminen.
        os._exit(0)

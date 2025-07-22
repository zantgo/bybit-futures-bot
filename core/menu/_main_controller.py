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

from . import screens
from ._helpers import clear_screen, press_enter_to_continue

# --- Variables Globales del Controlador ---
_deps: Dict[str, Any] = {}

def launch_bot(dependencies: Dict[str, Any]):
    """
    Punto de entrada principal para la TUI. Orquesta todo el ciclo de vida.
    """
    global _deps
    if not TerminalMenu:
        print("ERROR: La librería 'simple-term-menu' no está instalada.")
        sys.exit(1)

    _deps = dependencies
    
    # 1. Inicializar el gestor de conexiones ANTES de hacer cualquier otra cosa.
    #    Esto cargará las claves API y creará los clientes necesarios.
    print("Inicializando gestor de conexiones y cargando credenciales API...")
    try:
        connection_manager = _deps.get("connection_manager_module")
        if connection_manager:
            connection_manager.initialize_all_clients()
        else:
            raise RuntimeError("El módulo 'connection_manager' no fue inyectado.")
        print("Gestor de conexiones inicializado.")
        time.sleep(1) # Pequeña pausa para que el usuario vea el mensaje
    except Exception as e:
        print(f"ERROR FATAL: No se pudo inicializar el gestor de conexiones: {e}")
        traceback.print_exc()
        sys.exit(1)

    # Inyectar dependencias en las pantallas de la TUI
    if hasattr(screens, 'init_screens'):
        screens.init_screens(dependencies)
    
    bot_initialized = False
    try:
        # Mostrar pantalla de bienvenida y esperar la decisión del usuario
        if not screens.show_welcome_screen():
            print("\nSalida solicitada por el usuario. ¡Hasta luego!")
            sys.exit(0)

        config_module = _deps["config_module"]
        base_size = getattr(config_module, 'POSITION_BASE_SIZE_USDT', 10.0)
        initial_slots = getattr(config_module, 'POSITION_MAX_LOGICAL_POSITIONS', 5)

        # Copiar dependencias para pasarlas al inicializador
        init_kwargs = _deps.copy()
        
        # Llamar al inicializador del backend del bot
        success, message = _deps["initialize_bot_backend"](
            operation_mode="live_interactive",
            base_size=base_size,
            initial_slots=initial_slots,
            **init_kwargs
        )
        
        if not success:
            print(f"\nEl bot no pudo inicializarse: {message}")
            press_enter_to_continue()
            sys.exit(1)

        bot_initialized = True
        print("\nBot inicializado y operando en segundo plano.")
        time.sleep(2)
        
        # Iniciar el bucle principal de la TUI (Dashboard)
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
        print("\nIniciando secuencia de apagado final...")
        final_summary = {}
        
        # Llamar a la función de apagado del backend, asegurando que pasamos
        # las dependencias que espera explícitamente.
        shutdown_bot_backend_func = _deps.get("shutdown_bot_backend")
        if shutdown_bot_backend_func:
            shutdown_bot_backend_func(
                final_summary=final_summary,
                bot_started=bot_initialized,
                config_module=_deps.get("config_module"),
                connection_ticker_module=_deps.get("connection_ticker_module"),
                position_manager_module=_deps.get("position_manager_api_module"),
                open_snapshot_logger_module=_deps.get("open_snapshot_logger_module")
            )
        
        print("\nPrograma finalizado. ¡Hasta luego!")
        # Usar os._exit(0) para una salida forzada y limpia, especialmente si hay hilos daemon.
        os._exit(0)
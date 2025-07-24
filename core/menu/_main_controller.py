"""
Controlador Principal del Ciclo de Vida de la TUI.

v2.2: Implementa la recepción explícita del `exchange_adapter` desde el
inicializador del backend. Esto resuelve la dependencia crítica para arrancar
el ticker y completa la corrección del flujo de arranque.
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
    
    # --- PASO 1: LÓGICA DE PRE-INICIO ---
    print("Inicializando gestor de conexiones y cargando credenciales API...")
    try:
        connection_manager = _deps.get("connection_manager_module")
        if connection_manager:
            connection_manager.initialize_all_clients()
        else:
            raise RuntimeError("El módulo 'connection_manager' no fue inyectado.")
        print("Gestor de conexiones inicializado.")
        time.sleep(1)
    except Exception as e:
        print(f"ERROR FATAL: No se pudo inicializar el gestor de conexiones: {e}")
        traceback.print_exc()
        sys.exit(1)

    if hasattr(screens, 'init_screens'):
        screens.init_screens(dependencies)
    
    # --- PASO 2: PANTALLA DE BIENVENIDA Y DECISIÓN DEL USUARIO ---
    if not screens.show_welcome_screen():
        print("\nSalida solicitada por el usuario. ¡Hasta luego!")
        sys.exit(0)

    # --- PASO 3: CICLO DE VIDA DEL BOT ---
    bot_started = False
    try:
        # --- 3a. Inicialización y Arranque del Backend ---
        initialize_bot_backend = _deps.get("initialize_bot_backend")
        if not initialize_bot_backend:
            raise RuntimeError("La función 'initialize_bot_backend' no fue encontrada.")

        config_module = _deps["config_module"]
        base_size = getattr(config_module, 'POSITION_BASE_SIZE_USDT', 10.0)
        initial_slots = getattr(config_module, 'POSITION_MAX_LOGICAL_POSITIONS', 5)

        # La función de inicialización ahora devuelve el adaptador creado.
        success, message, exchange_adapter = initialize_bot_backend(
            operation_mode="live_interactive",
            base_size=base_size,
            initial_slots=initial_slots,
            **_deps
        )
        
        if not success:
            raise RuntimeError(f"Fallo en la inicialización del backend: {message}")

        # Inyectamos la instancia del adaptador en las dependencias para que esté disponible para las pantallas.
        _deps['exchange_adapter'] = exchange_adapter

        bot_started = True
        print("\nComponentes Core del bot inicializados con éxito.")
        
        # --- 3b. Arranque de Servicios en Segundo Plano (Ticker) ---
        print("Iniciando servicios en segundo plano (Ticker de precios)...")
        connection_ticker_module = _deps.get("connection_ticker_module")
        event_processor_module = _deps.get("event_processor_module")
        
        # Usamos el `exchange_adapter` que nos devolvió la función de inicialización.
        if not all([connection_ticker_module, event_processor_module, exchange_adapter]):
             raise RuntimeError("Dependencias críticas para el ticker no encontradas.")

        connection_ticker_module.start_ticker_thread(
            exchange_adapter=exchange_adapter,
            raw_event_callback=event_processor_module.process_event
        )
        print("Ticker de precios operativo.")
        time.sleep(1.5)

        # --- 3c. Iniciar la Interfaz de Usuario (TUI) ---
        screens.show_dashboard_screen()

    except (KeyboardInterrupt, SystemExit):
        print("\n\n[Main Controller] Interrupción detectada. Saliendo de forma ordenada...")
    except RuntimeError as e:
        print(f"\nERROR CRÍTICO EN TIEMPO DE EJECUCIÓN: {e}")
        traceback.print_exc()
        press_enter_to_continue()
    except Exception as e:
        clear_screen()
        print("\n" + "="*80)
        print("!!! ERROR CRÍTICO INESPERADO EN EL CONTROLADOR DEL MENÚ !!!")
        print(f"  Tipo de Error: {type(e).__name__}")
        print(f"  Mensaje: {e}")
        print("-" * 80)
        traceback.print_exc()
        print("=" * 80)
        press_enter_to_continue()
    finally:
        # --- 4. Secuencia de Apagado Limpio ---
        print("\n[Main Controller] Iniciando secuencia de apagado final...")
        final_summary = {}
        
        shutdown_bot_backend_func = _deps.get("shutdown_bot_backend")
        if shutdown_bot_backend_func:
            shutdown_bot_backend_func(
                final_summary=final_summary,
                bot_started=bot_started,
                config_module=_deps.get("config_module"),
                connection_ticker_module=_deps.get("connection_ticker_module"),
                position_manager_module=_deps.get("position_manager_api_module"),
                open_snapshot_logger_module=_deps.get("open_snapshot_logger_module")
            )
        
        # --- INICIO DE LA MODIFICACIÓN ---
        # Apagar los hilos de logging de archivos de forma segura
        logging_package = _deps.get("logging_package")
        if logging_package and hasattr(logging_package, 'shutdown_loggers'):
            print("[Main Controller] Deteniendo hilos de logging de archivos...")
            logging_package.shutdown_loggers()
        # --- FIN DE LA MODIFICACIÓN ---
        
        print("\nPrograma finalizado. ¡Hasta luego!")
        os._exit(0)
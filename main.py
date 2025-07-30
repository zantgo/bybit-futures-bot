"""
Punto de Entrada Principal del Bot de Trading.

v4.0 (Arquitectura de Controladores):
- Este archivo es el lanzador de la aplicación. Su responsabilidad es:
1. Llamar al ensamblador de dependencias para obtener un diccionario con
   todas las clases y módulos del sistema.
2. Instanciar el controlador de más alto nivel (BotController).
3. Inyectar el BotController en el orquestador de la TUI (launch_bot).
4. Ceder el control total del ciclo de vida de la aplicación al paquete 'menu'.
"""
import sys
import traceback

# --- Importaciones de Componentes y Dependencias ---
try:
    # Paquete del Menú (TUI)
    from core.menu import launch_bot
    
    # Paquete de Logging
    from core import logging as logging_package

    # Paquete Runner (ahora solo para el ensamblador de dependencias)
    from runner._initializer import assemble_dependencies

except ImportError as e:
    print("="*80)
    print("!!! ERROR CRÍTICO DE IMPORTACIÓN !!!")
    print(f"No se pudo importar un módulo esencial: {e}")
    traceback.print_exc()
    sys.exit(1)


# --- Punto de Entrada Principal ---
if __name__ == "__main__":
    """
    Ensambla las dependencias, instancia el BotController y lanza la TUI.
    """
    
    # 1. Inicializar el sistema de logging asíncrono de archivos PRIMERO.
    logging_package.initialize_loggers()

    # 2. Ensamblar el diccionario de dependencias (clases y módulos).
    # Esta función ahora solo recoge las "recetas", no cocina nada.
    dependencies = assemble_dependencies()
    
    if not dependencies:
        print("Fallo al ensamblar las dependencias. No se puede iniciar el bot.")
        sys.exit(1)

    # 3. Instanciar el controlador de más alto nivel (BotController).
    # El BotController es el "cerebro" de la aplicación.
    try:
        BotController = dependencies['BotController']
        bot_controller_instance = BotController(dependencies)
    except KeyError as e:
        print(f"Error fatal: La dependencia '{e}' no fue encontrada por el ensamblador.")
        sys.exit(1)
    except Exception as e:
        print(f"\n!!! ERROR FATAL AL INSTANCIAR EL BOTCONTROLLER !!!")
        print(f"  Mensaje: {e}")
        traceback.print_exc()
        sys.exit(1)
        
    # 4. Ceder el control total al lanzador de la TUI.
    # Ahora pasamos tanto la instancia del controlador como el diccionario de dependencias.
    try:
        launch_bot(bot_controller_instance, dependencies)
    except Exception as e:
        print("\n" + "="*80)
        print("!!! ERROR FATAL NO CAPTURADO EN EL LANZADOR PRINCIPAL (main.py) !!!")
        print(f"  Tipo de Error: {type(e).__name__}")
        print(f"  Mensaje: {e}")
        print("-" * 80)
        traceback.print_exc()
        print("=" * 80)
        print("El bot se ha detenido de forma inesperada.")
        
        # Asegurar el apagado de los loggers en caso de un crash
        if logging_package:
            logging_package.shutdown_loggers()
            
        sys.exit(1)
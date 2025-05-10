!!! IMPORTANTE !!!

SIEMPRE VERIFICAR QUE LOS PARAMETROS DEL CONFIG CORRESPONDAN CON LA INFORMACION EN EL NAVEGADOR.
- VERIFICAR QUE EL SIMBOLO O PAR CORRESPONDA
- VERIFICAR QUE EL APALANCAMIENTO POR LADO CORRESPONDA
- VERIFICAR QUE HAY SUFICIENTE CAPITAL POR LADO
- VERIFICAR QUE ES HEDGE MODE (PROBABLEMENTE YA ESTE SETEADO)

SIEMPRE PROBAR EL BOT CON LA OPCION PARA PROBAR EL CICLO COMPLETO ANTES DE COMENZARLO





MANUAL DE USUARIO:

1. ANTES DE COMENZAR ESTABLECER API KEYS CON PERMISOS CORREPONDINETE (UTA Y ASSETS) Y PONER DINERO SUFICIENTE EN LAS CUENTAS (LONGS Y SHORTS) DEBE SER LA CUENTA UNIFIED TRADING ACCOUNT (UTA)

2. ESTABLECER CONFIG (FIJARSE QUE LONGS Y SHORTS EN UTA SUMEN COMO MINIMO EL CAPITAL TOTAL)

3. ASEGURARSE QUE EL APALANCAMIENTO CORRESPONDA EN EL CONFIG CON EL NAVEGADOR AL IGUAL QUE SEA ISOLATED 

4. SE DEBE ACTIVAR MANUALMENTE EL HEDGE MODE POR CADA CUENTA

5. SE DEBE CHECKEAR PERIODICAMENTE SI SE HAN ALCANZADO LOS PUNTOS DE LIQUIDACION EN TODO CASO EL PROGRAMA SIGUIRA FUNCIONANDO (ASI NO SE DETIENE LA OTRA CUENTE QUE PUEDE NO ESTAR LIQUIDADA) SIMPLEMENTE VAN A FALLAR AL INTENTAR CERRAR LAS POSICIONES LOGICAS ABIERTAS


# Pasos:
# Abre tu Terminal o Símbolo del sistema.
# Navega hasta la raíz de tu proyecto (el directorio que contiene main.py, config.py, etc.).
# cd ruta/a/tu/proyecto/DFE-Futures-Bot-B

# Crea el entorno virtual: Ejecuta el módulo venv de Python. 
# python -m venv venv

# Activa el entorno virtual: Este paso varía según tu sistema operativo:
# Windows (PowerShell):
# .\venv\Scripts\Activate.ps1

# macOS / Linux (bash, zsh):
# source venv/bin/activate

# Confirmación: Después de activar, deberías ver (venv) al principio de la línea de comandos de tu terminal, indicando que el entorno está activo.
# Instala las dependencias DENTRO del entorno activo: Ahora que el entorno está activo, usa pip para instalar los paquetes listados en tu requirements.txt.
# pip install -r requirements.txt


# Pip instalará los paquetes dentro del directorio venv, sin afectar tu instalación global de Python.
# Ejecuta tu bot: Con el entorno aún activo, puedes ejecutar tu script como siempre. Python usará los paquetes instalados en venv.
# python main.py

# Desactiva el entorno virtual: Cuando termines de trabajar en el proyecto, simplemente ejecuta:
# deactivate


# IN CONFIG.PY:
# UNIVERSAL_TESTNET_MODE = False

# UIDs
BYBIT_LONGS_UID=
BYBIT_SHORTS_UID=
BYBIT_PROFIT_UID=

# Claves Cuenta Principal (NECESARIAS PARA TRANSFERENCIAS ENTRE SUBCUENTAS)
# Asegúrate que esta clave tenga permiso de "Subaccount Transfer" en Bybit
BYBIT_MAIN_API_KEY=""
BYBIT_MAIN_API_SECRET=""

# Claves Subcuenta Futuros Long
BYBIT_LONGS_API_KEY=""
BYBIT_LONGS_API_SECRET=""

# Claves Subcuenta Futuros Short
BYBIT_SHORTS_API_KEY=""
BYBIT_SHORTS_API_SECRET=""

# Claves Subcuenta Ganancias
BYBIT_PROFIT_API_KEY=""
BYBIT_PROFIT_API_SECRET=""

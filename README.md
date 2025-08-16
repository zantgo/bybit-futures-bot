# Bybit Futures Bot - Versión 50+ (Modelo de Hitos y Tendencias)

Este es un bot de trading algorítmico avanzado para futuros de Bybit, diseñado con una arquitectura modular y una potente interfaz de usuario en la terminal (TUI) para un control total en tiempo real.

El bot opera bajo un modelo estratégico jerárquico:
-   **Sesión:** El ciclo de vida completo de una ejecución, con disyuntores de seguridad globales.
-   **Hitos (Milestones):** Reglas condicionales ("SI el precio cruza X...") que activan modos operativos.
-   **Tendencias (Trends):** Modos operativos con reglas específicas de riesgo y finalización que se ejecutan cuando un hito se activa.

---

## !! Advertencia de Seguridad y Riesgo !!

**EL TRADING DE FUTUROS CON APALANCAMIENTO ES EXTREMADAMENTE RIESGOSO Y PUEDE RESULTAR EN LA PÉRDIDA TOTAL DE SU CAPITAL.**

-   Este software se proporciona "tal cual", sin ninguna garantía.
-   El autor no se hace responsable de ninguna pérdida financiera.
-   **NUNCA** ejecute este bot en una cuenta real sin haberlo probado extensivamente en **TESTNET** (`UNIVERSAL_TESTNET_MODE = True` en `config.py`).
-   Comprenda completamente el código y los riesgos antes de depositar fondos reales.

---

## !!! IMPORTANTE: Checklist Antes de Cada Ejecución !!!

**SIEMPRE VERIFICA QUE TU CONFIGURACIÓN LOCAL COINCIDA CON LA DE LA PLATAFORMA DE BYBIT.**

-   **HEDGE MODE:** El bot está diseñado para operar exclusivamente en **Modo Hedge**. Asegúrate de que esta opción esté activada en Bybit para el par que vas a operar.
    -   *Cómo verificar:* En la interfaz de trading de Bybit, busca el icono de configuración (engranaje) y en "Preferencias de Trading" -> "Modo de Posición", selecciona "Modo Hedge".

-   **APALANCAMIENTO:** El valor de `POSITION_LEVERAGE` en tu archivo `config.py` debe ser **exactamente el mismo** que tienes configurado en la interfaz de Bybit para los lados Long y Short de ese símbolo.

-   **SÍMBOLO:** Confirma que el `TICKER_SYMBOL` en `config.py` (o el que selecciones en la TUI) es el par correcto que deseas operar.

-   **CAPITAL:** Asegúrate de que haya suficiente balance (USDT) en las subcuentas de `longs` y `shorts` para cubrir las operaciones que el bot pueda abrir.

---

## 1. Configuración Inicial (Solo una vez)

### 1.1. Prerrequisitos
-   Python 3.10 o superior.
-   Una cuenta en [Bybit](https://www.bybit.com/).

### 1.2. Pasos de Instalación
1.  **Clona el repositorio:**
    ```bash
    git clone <URL_DEL_REPOSITORIO>
    cd <NOMBRE_DEL_DIRECTORIO>
    ```
2.  **Crea y activa un entorno virtual:**
    ```bash
    python -m venv venv
    source venv/bin/activate  # En macOS/Linux
    # .\venv\Scripts\Activate.ps1 # En Windows PowerShell
    ```
3.  **Instala las dependencias:**
    ```bash
    pip install -r requirements.txt
    ```

### 1.3. Configuración de Cuentas y API en Bybit
El bot está diseñado para operar con subcuentas para un aislamiento de riesgo superior.

1.  **Crea Subcuentas en Bybit:** En tu panel de Bybit, ve a "Subcuentas" y crea tres subcuentas de tipo "Cuenta de Trading Unificado". Dales nombres descriptivos como:
    *   `longs`
    *   `shorts`
    *   `profit` (para acumular ganancias)
2.  **Genera Claves API:**
    *   **Cuenta Principal:** Crea una clave API con permisos de **"Leer/Escribir"** para **Activos -> Transferencia**. Esta clave es **esencial** para mover las ganancias a la subcuenta de `profit`.
    *   **Subcuentas (`longs`, `shorts`, `profit`):** Para cada una, crea una clave API con permisos de **"Leer/Escribir"** para **Contrato -> Trading Unificado**.
3.  **Obtén los UIDs:** En la sección de "Gestión de Subcuentas", anota el UID de cada una de tus subcuentas.

### 1.4. Configuración del Archivo `.env`
1.  En la raíz del proyecto, crea un archivo llamado `.env`.
2.  Copia, pega y rellena el siguiente contenido con tus claves y UIDs:

    ```dotenv
    # --- UIDs (Encuéntralos en la sección de Subcuentas de Bybit) ---
    BYBIT_LONGS_UID=1234567
    BYBIT_SHORTS_UID=2345678
    BYBIT_PROFIT_UID=3456789

    # --- Claves Cuenta Principal (SOLO para transferencias) ---
    BYBIT_MAIN_API_KEY="YOUR_MAIN_API_KEY"
    BYBIT_MAIN_API_SECRET="YOUR_MAIN_API_SECRET"

    # --- Claves Subcuenta Futuros Long ---
    BYBIT_LONGS_API_KEY="YOUR_LONGS_API_KEY"
    BYBIT_LONGS_API_SECRET="YOUR_LONGS_API_SECRET"

    # --- Claves Subcuenta Futuros Short ---
    BYBIT_SHORTS_API_KEY="YOUR_SHORTS_API_KEY"
    BYBIT_SHORTS_API_SECRET="YOUR_SHORTS_API_SECRET"

    # --- Claves Subcuenta Ganancias (para obtener el ticker) ---
    BYBIT_PROFIT_API_KEY="YOUR_PROFIT_API_KEY"
    BYBIT_PROFIT_API_SECRET="YOUR_PROFIT_API_SECRET"
    ```

### 1.5. Deposita Fondos
Desde tu Cuenta Principal en Bybit, transfiere los fondos (USDT) que deseas operar a tus subcuentas `longs` y `shorts`.

## 1.6. Archivos de Log

El bot genera varios archivos en la carpeta `logs/` para auditoría y análisis:
-   `signals_log.jsonl`: Un registro de cada señal de trading generada.
-   `closed_positions.jsonl`: Un registro detallado de cada posición que se ha cerrado, incluyendo PNL.
-   `open_positions_snapshot.jsonl`: Una instantánea de las posiciones que quedaron abiertas al cerrar el bot.

Estos archivos están limitados a las últimas 1000 entradas para evitar consumir espacio en disco excesivo.
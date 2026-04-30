"""
╔══════════════════════════════════════════════════════════════════════════════╗
║        SmartX — Interfaz Streamlit (Frontend)                                ║
║        Hospital Civil de Guadalajara | Piloto v1.0                          ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  INSTALACIÓN Y EJECUCIÓN:                                                    ║
║                                                                              ║
║  1. Asegúrate de que el backend está corriendo:                              ║
║     cd 04_Codigo                                                             ║
║     .venv\Scripts\activate.bat  (Windows) o source .venv/bin/activate (Mac)  ║
║     uvicorn smartx_api:app --reload --port 8000                              ║
║                                                                              ║
║  2. En otra terminal, lanza Streamlit:                                       ║
║     cd 04_Codigo/frontend                                                    ║
║     ..\\.venv\\Scripts\\streamlit run streamlit_app.py                       ║
║     (o simplemente: streamlit run streamlit_app.py)                          ║
║                                                                              ║
║  3. Accede a la interfaz:                                                    ║
║     http://localhost:8501                                                    ║
║                                                                              ║
║  SINCRONIZACIÓN:                                                             ║
║    - Backend: http://localhost:8000 (FastAPI)                                ║
║    - Frontend: http://localhost:8501 (Streamlit)                             ║
║    - CORS: habilitado para desarrollo (permite cross-origin)                 ║
║    - JSON: modelo SintomasInput de Pydantic                                   ║
║                                                                              ║
║  NORMATIVAS: NOM-004-SSA3 · NOM-024-SSA3 · LFPDPPP                           ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any

import streamlit as st
import requests
from requests.exceptions import ConnectionError, RequestException, Timeout

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURACIÓN
# ═══════════════════════════════════════════════════════════════════════════════

API_BASE_URL = os.getenv("SMARTX_API_URL", "http://127.0.0.1:8000")
HEALTH_ENDPOINT = f"{API_BASE_URL}/health"
TRIAJE_ENDPOINT = f"{API_BASE_URL}/api/v1/inferencia"

# Configurar página
st.set_page_config(
    page_title="SmartX Triaje — HCG",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ═══════════════════════════════════════════════════════════════════════════════
# UTILIDADES DE CONEXIÓN
# ═══════════════════════════════════════════════════════════════════════════════

@st.cache_resource
def verificar_backend() -> Dict[str, Any]:
    """Verifica la salud del backend y retorna info del motor."""
    try:
        resp = requests.get(HEALTH_ENDPOINT, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            return {
                "online": True,
                "version": data.get("motor_version", "desconocida"),
                "timestamp": data.get("timestamp_utc", ""),
            }
    except (ConnectionError, Timeout):
        pass
    except RequestException:
        pass
    return {"online": False, "version": None, "timestamp": None}


def construir_payload_triaje(
    edad: int,
    sexo_biologico: str,
    disnea_presente: bool,
    perdida_conciencia: bool,
    sangrado_activo: bool,
    fiebre_presente: bool,
    intensidad_dolor_eva: Optional[int],
    sintomas_texto: Optional[str],
    diabetes_mellitus: bool = False,
    hipertension: bool = False,
    cardiopatia_isquemica: bool = False,
    epoc_asma: bool = False,
    embarazo_posible: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Construye el JSON que se envía al backend.
    Modelo: SintomasInput (Pydantic) de smartx_api.py
    """
    return {
        "edad": int(edad),
        "sexo_biologico": sexo_biologico,
        "disnea_presente": bool(disnea_presente),
        "perdida_conciencia": bool(perdida_conciencia),
        "sangrado_activo": bool(sangrado_activo),
        "fiebre_presente": bool(fiebre_presente),
        "temperatura_celsius": None,  # No se captura en el formulario
        "intensidad_dolor_eva": int(intensidad_dolor_eva) if intensidad_dolor_eva else None,
        "duracion_sintoma_horas": None,
        "sintomas_texto": sintomas_texto.strip() if sintomas_texto and len(sintomas_texto.strip()) >= 10 else None,
        "peso_kg": None,
        "talla_cm": None,
        "diabetes_mellitus": bool(diabetes_mellitus),
        "hipertension": bool(hipertension),
        "cardiopatia_isquemica": bool(cardiopatia_isquemica),
        "epoc_asma": bool(epoc_asma),
        "embarazo_posible": embarazo_posible,
        "semanas_gestacion": None,
    }


def procesar_triaje_en_backend(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    POST /api/v1/inferencia
    Envía datos al motor y retorna resultado o None si falla.
    """
    try:
        resp = requests.post(TRIAJE_ENDPOINT, json=payload, timeout=30)

        if resp.status_code == 200:
            return resp.json()
        elif resp.status_code == 422:
            error_data = resp.json()
            detalle = error_data.get("detail", {})
            if isinstance(detalle, dict):
                raise ValueError(f"Validación: {detalle.get('detalle', 'Error desconocido')}")
            else:
                raise ValueError(f"Validación fallida: {detalle}")
        else:
            error_data = resp.json()
            raise ValueError(f"HTTP {resp.status_code}: {error_data.get('error', 'Error desconocido')}")

    except ConnectionError:
        raise ConnectionError(
            f"No se puede conectar al backend en {API_BASE_URL}. "
            "¿Está corriendo uvicorn en el puerto 8000?"
        )
    except Timeout:
        raise TimeoutError("El backend tardó demasiado en responder (timeout 30s)")
    except RequestException as e:
        raise RequestException(f"Error de conexión HTTP: {str(e)}")


# ═══════════════════════════════════════════════════════════════════════════════
# UI — HEADER Y ESTADO DEL BACKEND
# ═══════════════════════════════════════════════════════════════════════════════

col1, col2 = st.columns([4, 1])

with col1:
    st.title("🏥 SmartX — Triaje Médico")
    st.caption("Hospital Civil Viejo de Guadalajara | Sistema IA de Emergencias")

with col2:
    # Verificar estado del backend
    backend_status = verificar_backend()

    if backend_status["online"]:
        st.success(f"✅ API conectada")
        st.caption(f"Motor v{backend_status['version']}")
    else:
        st.error("❌ API desconectada")
        st.caption(f"Esperando en {API_BASE_URL}")

st.divider()

# ═══════════════════════════════════════════════════════════════════════════════
# UI — FORMULARIO DE TRIAJE
# ═══════════════════════════════════════════════════════════════════════════════

with st.form("formulario_triaje"):
    st.subheader("📋 Datos Demográficos")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        edad = st.number_input(
            "Edad (años) *",
            min_value=0,
            max_value=120,
            value=30,
            step=1,
        )

    with col2:
        sexo = st.selectbox(
            "Sexo biológico *",
            options=["M", "F"],
            index=0,
        )

    with col3:
        embarazo = st.checkbox("Embarazo posible") if sexo == "F" else False

    with col4:
        intensidad = st.slider(
            "Intensidad dolor (EVA 0-10)",
            min_value=0,
            max_value=10,
            value=5,
        )

    # Banderas rojas críticas
    st.subheader("🚩 Banderas Rojas Críticas (BYPASS AUTOMÁTICO)")
    st.info(
        "Si marcas cualquiera de estas, el paciente será clasificado automáticamente como CRÍTICO (ROJO)"
    )

    col1, col2 = st.columns(2)

    with col1:
        disnea_severa = st.checkbox("Disnea severa (dificultad para respirar)")
        sangrado_abundante = st.checkbox("Sangrado abundante")

    with col2:
        deficit_neuro = st.checkbox("Déficit neurológico súbito")
        dolor_toracico_sudor = st.checkbox("Dolor torácico opresivo + sudoración")

    # Síntomas adicionales
    st.subheader("🩺 Síntomas Adicionales")

    col1, col2, col3 = st.columns(3)

    with col1:
        fiebre = st.checkbox("Fiebre")
        tos = st.checkbox("Tos")
        dificultad_resp = st.checkbox("Dificultad respiratoria")

    with col2:
        dolor_toracico = st.checkbox("Dolor torácico")
        sangrado_activo = st.checkbox("Sangrado activo")

    with col3:
        confusion = st.checkbox("Confusión / alteración de consciencia")

    # Descripción libre (prompt para IA)
    st.subheader("📝 Descripción Libre de Síntomas")
    st.caption("Mínimo 10 caracteres. Será procesada por el motor IA.")

    sintomas_texto = st.text_area(
        "Describa los síntomas en texto libre",
        placeholder="Ejemplo: Dolor en el pecho desde hace 2 horas, irradia al brazo izquierdo, con falta de aire…",
        height=100,
    )

    # Botón de envío
    submitted = st.form_submit_button(
        "⚡ PROCESAR TRIAJE",
        use_container_width=True,
        type="primary",
    )

# ═══════════════════════════════════════════════════════════════════════════════
# PROCESAR TRIAJE
# ═══════════════════════════════════════════════════════════════════════════════

if submitted:
    # Validación básica del cliente
    if edad < 0 or edad > 120:
        st.error("Edad fuera de rango (0-120)")
        st.stop()

    if intensidad < 0 or intensidad > 10:
        st.error("Intensidad de dolor fuera de rango (0-10)")
        st.stop()

    # Construir payload
    payload = construir_payload_triaje(
        edad=edad,
        sexo_biologico=sexo,
        disnea_presente=disnea_severa or dificultad_resp,
        perdida_conciencia=deficit_neuro or confusion,
        sangrado_activo=sangrado_abundante or sangrado_activo,
        fiebre_presente=fiebre,
        intensidad_dolor_eva=intensidad,
        sintomas_texto=sintomas_texto,
        diabetes_mellitus=False,
        hipertension=False,
        cardiopatia_isquemica=dolor_toracico_sudor,
        epoc_asma=False,
        embarazo_posible=embarazo if sexo == "F" else None,
    )

    # Llamar al backend
    with st.spinner("🔄 Procesando triaje con Motor SmartX…"):
        try:
            resultado = procesar_triaje_en_backend(payload)

            # Mostrar resultados
            st.divider()
            st.success("✅ Triaje procesado correctamente")

            # Nivel de urgencia (rojo/amarillo/verde)
            nivel = resultado.get("nivel_ia", "desconocido").upper()
            col1, col2, col3 = st.columns(3)

            with col1:
                if nivel == "ROJO":
                    st.error(f"## 🔴 {nivel} — CRÍTICO")
                    st.write("Acción: **PASAR A CHOQUE**")
                elif nivel == "AMARILLO":
                    st.warning(f"## 🟡 {nivel} — URGENTE")
                    st.write("Acción: **MONITOREO 30 MIN**")
                else:
                    st.success(f"## 🟢 {nivel} — ESTABLE")
                    st.write("Acción: **SALA DE ESPERA**")

            # Probabilidades
            with col2:
                st.write("### Confianza (%) del modelo:")
                probs = resultado.get("probabilidades", {})
                if probs:
                    for level_name, prob_value in probs.items():
                        prob_pct = round(float(prob_value) * 100, 1)
                        st.write(f"- {level_name}: {prob_pct}%")

            # Escenarios diferenciales
            with col3:
                st.write("### Top Escenarios Clínicos:")
                escenarios = resultado.get("escenarios", [])
                if escenarios:
                    for i, escenario in enumerate(escenarios[:3], 1):
                        prob = escenario.get("probabilidad", 0)
                        nombre = escenario.get("nombre", "Desconocido")
                        cie = escenario.get("cie10", "")
                        st.write(f"{i}. {nombre} ({round(prob*100)}%) {cie}")

            # Explicación SHAP
            shap_exp = resultado.get("explicacion_shap", "")
            if shap_exp:
                with st.expander("📊 Explicación SHAP (importancia de variables)"):
                    st.write(shap_exp)

            # Análisis LLM
            analisis_llm = resultado.get("analisis_llm")
            if analisis_llm:
                with st.expander("🤖 Análisis LLM (razonamiento médico)"):
                    st.write(analisis_llm)

        except ConnectionError as e:
            st.error(f"❌ Error de conexión: {str(e)}")
        except TimeoutError as e:
            st.error(f"⏱️ Timeout: {str(e)}")
        except ValueError as e:
            st.error(f"❌ Error de validación: {str(e)}")
        except RequestException as e:
            st.error(f"❌ Error HTTP: {str(e)}")
        except Exception as e:
            st.error(f"❌ Error inesperado: {str(e)}")
            st.write("Verifica el log de la consola para más detalles.")

# ═══════════════════════════════════════════════════════════════════════════════
# SIDEBAR — INFO Y CONFIGURACIÓN
# ═══════════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.header("⚙️ Configuración")

    st.subheader("Backend")
    st.code(API_BASE_URL, language="bash")

    if st.button("🔄 Reconectar", use_container_width=True):
        st.cache_resource.clear()
        st.rerun()

    st.divider()

    st.subheader("ℹ️ Información")
    st.info(
        "**SmartX v1.0**\n\n"
        "Sistema de Triage IA para el HCG.\n\n"
        "Normativas: NOM-004-SSA3 · NOM-024-SSA3 · LFPDPPP"
    )

    st.caption("Frontend: Streamlit 1.31+")
    st.caption("Backend: FastAPI 0.109+")
    st.caption("Motor: scikit-learn RF")

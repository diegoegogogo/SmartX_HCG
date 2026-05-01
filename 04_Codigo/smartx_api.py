"""
╔══════════════════════════════════════════════════════════════════════════════╗
║        SMART X — API REST (FastAPI)                                          ║
║        Conexión Frontend ↔ Motor de Inferencia ↔ Base de Datos               ║
║        Hospital Civil Viejo de Guadalajara | Piloto v1.0                     ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  INSTALACIÓN Y EJECUCIÓN:                                                    ║
║                                                                              ║
║  1. Crear entorno virtual:                                                   ║
║     python -m venv .venv                                                     ║
║                                                                              ║
║  2. Activar entorno:                                                         ║
║     # Windows CMD:                                                           ║
║     .venv\Scripts\activate.bat                                               ║
║     # Windows PowerShell:                                                    ║
║     .venv\Scripts\Activate.ps1                                               ║
║     # macOS/Linux:                                                           ║
║     source .venv/bin/activate                                                ║
║                                                                              ║
║  3. Instalar dependencias:                                                   ║
║     pip install -r requirements.txt                                          ║
║                                                                              ║
║  4. Ejecutar servidor:                                                       ║
║     uvicorn smartx_api:app --reload --port 8000                              ║
║                                                                              ║
║  5. Documentación interactiva (Swagger):                                      ║
║     http://localhost:8000/docs                                               ║
║                                      


                                        ║
║  SINCRONIZACIÓN FRONTEND-BACKEND:                                            ║
║    - Frontend (Streamlit) en puerto 8501                                     ║
║    - Backend (FastAPI) en puerto 8000                                        ║
║    - CORS habilitado para ambos (desarrollo)                                 ║
║    - Endpoint principal: POST /api/v1/inferencia                             ║
║                                                                              ║
║  NORMATIVAS: NOM-004-SSA3 · NOM-024-SSA3 · LFPDPPP                           ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

# ─── IMPORTACIONES ESTÁNDAR ───────────────────────────────────────────────────
import uuid
import json
import time
import hashlib
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Optional

# ─── IMPORTACIONES FASTAPI ────────────────────────────────────────────────────
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator, model_validator

# ─── MOTOR DE INFERENCIA (relativo al mismo directorio) ───────────────────────
# Importar desde smartx_motor_inferencia.py (es el que está activo en este proyecto)
from smartx_motor_inferencia import (
    MotorInferenciaSmartX,
    Paciente,
    NivelSemaforo,
)


# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 1 — INICIALIZACIÓN DE LA APP
# ══════════════════════════════════════════════════════════════════════════════

app = FastAPI(
    title       = "Smart X API — Motor de Triage HCG",
    description = (
        "API REST del sistema Smart X para el Hospital Civil de Guadalajara. "
        "Recibe síntomas de pacientes y devuelve clasificación de urgencia "
        "(semáforo rojo/amarillo/verde) conforme a NOM-004 y NOM-024."
    ),
    version     = "1.0.0-piloto",
    docs_url    = "/docs",       # Swagger UI
    redoc_url   = "/redoc",      # ReDoc alternativo
)

# ── CORS — permite que el frontend (React/Streamlit) llame a la API ───────────
# En producción reemplazar "*" con el dominio real del frontend HCG
app.add_middleware(
    CORSMiddleware,
    allow_origins     = ["*"],
    allow_credentials = True,
    allow_methods     = ["GET", "POST"],
    allow_headers     = ["*"],
)

# ── Instancia única del motor (se carga una vez al arrancar el servidor) ──────
motor = MotorInferenciaSmartX()


# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 2 — MODELOS PYDANTIC (contrato del API)
# ══════════════════════════════════════════════════════════════════════════════

class SintomasInput(BaseModel):
    """
    Modelo de entrada: lo que el formulario del paciente envía al API.

    Pydantic valida automáticamente tipos y restricciones antes de
    que el request llegue al motor de inferencia.
    """

    # ── Identificación (generada por el frontend) ─────────────────────────────
    id_paciente   : str = Field(default_factory=lambda: str(uuid.uuid4()),
                                description="UUID seudonimizado del paciente (LFPDPPP)")
    unidad_atencion: str = Field(default="HCG_URGENCIAS",
                                description="Unidad del HCG: HCG_URGENCIAS o HCG_MED_INTERNA")

    # ── Variables demográficas ────────────────────────────────────────────────
    edad          : int   = Field(..., ge=0, le=120,
                                  description="Edad en años. Rango válido: 0–120")
    sexo_biologico: str   = Field(default="M",
                                  description="'M' para masculino, 'F' para femenino")

    # ── Alertas críticas (disparan ROJO inmediato si son True) ────────────────
    disnea_presente    : bool = Field(default=False, description="¿Dificultad para respirar?")
    perdida_conciencia : bool = Field(default=False, description="¿Pérdida o alteración de consciencia?")
    sangrado_activo    : bool = Field(default=False, description="¿Sangrado activo visible?")

    # ── Síntomas estructurados ────────────────────────────────────────────────
    fiebre_presente        : bool              = Field(default=False)
    temperatura_celsius    : Optional[float]   = Field(default=None, ge=35.0, le=42.5,
                                                       description="Solo si fiebre_presente=True")
    intensidad_dolor_eva   : Optional[int]     = Field(default=None, ge=0, le=10,
                                                       description="Escala EVA 0–10")
    duracion_sintoma_horas : Optional[int]     = Field(default=None, ge=0,
                                                       description="Duración del síntoma en horas")
    sintomas_texto         : Optional[str]     = Field(default=None, min_length=10,
                                                       description="Descripción libre del paciente (mín. 10 chars)")

    # ── Medidas antropométricas ────────────────────────────────────────────────
    peso_kg   : Optional[float] = Field(default=None, ge=1.0,   le=300.0)
    talla_cm  : Optional[float] = Field(default=None, ge=30.0,  le=250.0)

    # ── Antecedentes patológicos ───────────────────────────────────────────────
    diabetes_mellitus    : bool          = Field(default=False)
    hipertension         : bool          = Field(default=False)
    cardiopatia_isquemica: bool          = Field(default=False)
    epoc_asma            : bool          = Field(default=False)
    embarazo_posible     : Optional[bool]= Field(default=None)
    semanas_gestacion    : Optional[int] = Field(default=None, ge=0, le=42)

    # ── Validación de consistencia lógica (NOM-004) ───────────────────────────
    @field_validator("sexo_biologico")
    @classmethod
    def validar_sexo(cls, v: str) -> str:
        if v not in ("M", "F"):
            raise ValueError("sexo_biologico debe ser 'M' o 'F'")
        return v

    @model_validator(mode="after")
    def validar_consistencia(self) -> "SintomasInput":
        # Temperatura solo si hay fiebre
        if not self.fiebre_presente and self.temperatura_celsius is not None:
            raise ValueError(
                "temperatura_celsius debe ser None cuando fiebre_presente=False"
            )
        # Embarazo solo en mujeres
        if self.embarazo_posible is True and self.sexo_biologico != "F":
            raise ValueError(
                "embarazo_posible=True solo es válido con sexo_biologico='F'"
            )
        # Semanas solo si hay embarazo
        if self.semanas_gestacion is not None and not self.embarazo_posible:
            raise ValueError(
                "semanas_gestacion requiere embarazo_posible=True"
            )
        return self

    class Config:
        json_schema_extra = {
            "example": {
                "edad"                  : 62,
                "sexo_biologico"        : "M",
                "disnea_presente"       : True,
                "fiebre_presente"       : False,
                "temperatura_celsius"   : None,
                "intensidad_dolor_eva"  : 9,
                "duracion_sintoma_horas": 1,
                "peso_kg"               : 85.0,
                "talla_cm"              : 170.0,
                "diabetes_mellitus"     : True,
                "hipertension"          : True,
                "cardiopatia_isquemica" : True,
                "sintomas_texto"        : "Dolor fuerte en el pecho que se va al brazo izquierdo",
            }
        }


class SemaforoOutput(BaseModel):
    """
    Modelo de salida: lo que el API devuelve al frontend.
    Compatible con DiagnosticReport HL7-FHIR R4.
    """
    id_resultado              : str
    id_consulta               : str
    id_paciente               : str
    timestamp_utc             : str
    nivel_ia                  : str   # "rojo" | "amarillo" | "verde"
    fuente_nivel              : str
    conservadurismo_aplicado  : bool
    probabilidades            : dict
    escenarios_diferenciales  : list
    especialidad_sugerida     : Optional[str]
    shap_explicacion          : str
    shap_variables_top3       : list
    imc_calculado             : Optional[float]
    alerta_critica            : bool
    alertas_detalle           : list
    modelo_version            : str
    tiempo_procesamiento_ms   : Optional[int]
    hash_resultado            : str


# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 3 — MIDDLEWARE DE AUDITORÍA
# ══════════════════════════════════════════════════════════════════════════════

@app.middleware("http")
async def middleware_auditoria(request: Request, call_next):
    """
    Registra cada request al API en el log de auditoría.
    En producción este middleware escribe en la tabla AUDITORIA de PostgreSQL.
    Referencia: Documento 2 — tabla auditoria (NOM-024-SSA3)
    """
    inicio = time.time()
    response = await call_next(request)
    duracion_ms = int((time.time() - inicio) * 1000)

    # En producción: INSERT en tabla auditoria de PostgreSQL
    log_entry = {
        "timestamp_utc" : datetime.now(timezone.utc).isoformat(),
        "metodo"        : request.method,
        "ruta"          : str(request.url.path),
        "ip_origen"     : request.client.host if request.client else "unknown",
        "status_code"   : response.status_code,
        "duracion_ms"   : duracion_ms,
    }
    # print(f"[AUDIT] {json.dumps(log_entry)}")  # Descomentar para debug
    return response


# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 4 — ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/", tags=["Sistema"])
async def raiz():
    """Health check básico del servidor."""
    return {
        "sistema"  : "Smart X API",
        "version"  : "1.0.0-piloto",
        "unidad"   : "Hospital Civil Viejo de Guadalajara",
        "estado"   : "operativo",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "docs"     : "/docs",
    }


@app.get("/health", tags=["Sistema"])
async def health_check():
    """
    Endpoint de salud para monitoreo de infraestructura.
    En producción verifica también la conexión a PostgreSQL.
    """
    return {
        "status"          : "ok",
        "motor_version"   : motor.MODELO_VERSION,
        "timestamp_utc"   : datetime.now(timezone.utc).isoformat(),
    }


# ── ENDPOINT PRINCIPAL — Clasificación de triage ──────────────────────────────
@app.post(
    "/api/v1/inferencia",
    response_model = dict,
    status_code    = status.HTTP_200_OK,
    tags           = ["Triage"],
    summary        = "Clasificar urgencia del paciente",
    description    = (
        "Recibe los síntomas y antecedentes del paciente, ejecuta el pipeline "
        "completo del Motor de Inferencia Smart X, y devuelve el nivel de urgencia "
        "(semáforo), los 3 escenarios clínicos probables y la explicación SHAP. "
        "Conforme a NOM-004-SSA3 y NOM-024-SSA3."
    ),
)
async def clasificar_paciente(datos: SintomasInput) -> dict:
    """
    Pipeline completo de clasificación:
      1. Recibe JSON del frontend (validado por Pydantic)
      2. Construye objeto Paciente para el motor
      3. Ejecuta motor.procesar()
      4. Serializa resultado a SemaforoOutput
      5. Devuelve al frontend
    """
    try:
        # ── Paso 1: Construir objeto Paciente desde el input del API ──────────
        paciente = Paciente(
            id_paciente            = datos.id_paciente,
            id_consulta            = str(uuid.uuid4()),  # Nueva consulta
            unidad_atencion        = datos.unidad_atencion,
            edad                   = datos.edad,
            sexo_biologico         = datos.sexo_biologico,
            disnea_presente        = datos.disnea_presente,
            perdida_conciencia     = datos.perdida_conciencia,
            sangrado_activo        = datos.sangrado_activo,
            fiebre_presente        = datos.fiebre_presente,
            temperatura_celsius    = datos.temperatura_celsius,
            intensidad_dolor_eva   = datos.intensidad_dolor_eva,
            duracion_sintoma_horas = datos.duracion_sintoma_horas,
            peso_kg                = datos.peso_kg,
            talla_cm               = datos.talla_cm,
            diabetes_mellitus      = datos.diabetes_mellitus,
            hipertension           = datos.hipertension,
            cardiopatia_isquemica  = datos.cardiopatia_isquemica,
            epoc_asma              = datos.epoc_asma,
            embarazo_posible       = datos.embarazo_posible,
            semanas_gestacion      = datos.semanas_gestacion,
            sintomas_texto         = datos.sintomas_texto,
        )

        # ── Paso 2: Ejecutar el motor de inferencia ───────────────────────────
        resultado = motor.procesar(paciente)

        # ── Paso 3: Parsear el JSON del resultado y devolver ──────────────────
        resultado_dict = json.loads(resultado.to_json())
        resultado_ml = SimpleNamespace(
            nivel=resultado_dict.get("nivel_ia"),
            probabilidades=resultado_dict.get("probabilidades"),
            escenarios=resultado_dict.get("escenarios_diferenciales"),
            shap=resultado_dict.get("shap_explicacion"),
        )
        analisis_llm = resultado_dict.get("analisis_llm")
        return {
            "nivel_ia": resultado_ml.nivel,
            "probabilidades": resultado_ml.probabilidades,
            "escenarios": resultado_ml.escenarios,
            "explicacion_shap": resultado_ml.shap,
            "analisis_llm": analisis_llm,
        }

    except ValueError as e:
        # Error de validación clínica (NOM-004) — 422 Unprocessable Entity
        raise HTTPException(
            status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail      = {
                "error"     : "Validación clínica fallida (NOM-004-SSA3)",
                "detalle"   : str(e),
                "codigo"    : "SMARTX_VALIDATION_ERROR",
            }
        )
    except Exception as e:
        # Error inesperado — 500 Internal Server Error
        raise HTTPException(
            status_code = status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail      = {
                "error"  : "Error interno del Motor de Inferencia",
                "codigo" : "SMARTX_ENGINE_ERROR",
                "mensaje": str(e),
            }
        )


# ── ENDPOINT — Historial de semáforo de un paciente ───────────────────────────
@app.get(
    "/api/v1/paciente/{id_paciente}/historial",
    tags    = ["Historial"],
    summary = "Obtener historial de clasificaciones del paciente",
)
async def historial_paciente(id_paciente: str):
    """
    Devuelve el resumen longitudinal del paciente.
    En producción consulta la vista mv_historial_longitudinal de PostgreSQL.
    Referencia: Documento 4 — Vista longitudinal del paciente.
    """
    # Simulación — en producción: SELECT * FROM mv_historial_longitudinal
    # WHERE id_paciente = $1 ORDER BY fecha_registro DESC
    return {
        "id_paciente"        : id_paciente,
        "nota"               : "Endpoint activo. En producción conecta a mv_historial_longitudinal (PostgreSQL).",
        "total_visitas"      : 0,
        "visitas"            : [],
        "condiciones_cronicas": [],
        "alerta_alergias"    : [],
    }


# ── ENDPOINT — Catálogo de escenarios CIE-10 disponibles ─────────────────────
@app.get(
    "/api/v1/catalogo/escenarios",
    tags    = ["Catálogo"],
    summary = "Listar escenarios CIE-10 por nivel de urgencia",
)
async def catalogo_escenarios():
    """
    Devuelve el catálogo de escenarios clínicos del sistema.
    Útil para que el frontend muestre las opciones al médico.
    """
    return {
        "catalogo"  : motor.CATALOGO_ESCENARIOS,
        "version"   : motor.MODELO_VERSION,
        "timestamp" : datetime.now(timezone.utc).isoformat(),
    }


# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 5 — MANEJO GLOBAL DE ERRORES
# ══════════════════════════════════════════════════════════════════════════════

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Formato uniforme para todos los errores HTTP del API."""
    return JSONResponse(
        status_code = exc.status_code,
        content     = {
            "sistema"   : "Smart X API",
            "error"     : exc.detail,
            "timestamp" : datetime.now(timezone.utc).isoformat(),
            "ruta"      : str(request.url.path),
        }
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Captura errores no controlados — nunca expone stack trace al cliente."""
    return JSONResponse(
        status_code = 500,
        content     = {
            "sistema" : "Smart X API",
            "error"   : "Error interno. Contactar al equipo de infraestructura HCG.",
            "codigo"  : "SMARTX_UNHANDLED_ERROR",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )


# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 6 — PUNTO DE ENTRADA (desarrollo local)
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn  # type: ignore[reportMissingImports]

    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║   SMART X API — Motor de Triage HCG  |  Piloto v1.0            ║")
    print("╠════════════════════════════════════════════════════════════════╣")
    print("║   Swagger UI  : http://localhost:8000/docs                     ║")
    print("║   Health check: http://localhost:8000/health                   ║")
    print("║   Inferencia  : POST http://localhost:8000/api/v1/inferencia   ║")
    print("╚════════════════════════════════════════════════════════════════╝\n")

    uvicorn.run(
        "smartx_api:app",
        host     = "0.0.0.0",
        port     = 8000,
        reload   = True,   # Auto-recarga en cambios (solo desarrollo)
        log_level= "info",
    )

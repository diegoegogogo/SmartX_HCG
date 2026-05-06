"""
╔══════════════════════════════════════════════════════════════════════════════╗
║        SMART X — API REST (FastAPI)                                          ║
║        Conexión Frontend ↔ Motor de Inferencia ↔ Base de Datos               ║
║        Hospital Civil Viejo de Guadalajara | Piloto v1.0                     ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Ejecución:                                                                  ║
║     cd 04_Codigo                                                             ║
║     uvicorn smartx_api:app --reload --port 8000                              ║
║                                                                              ║
║  Documentación interactiva (Swagger):                                        ║
║     http://localhost:8000/docs                                               ║
║                                                                              ║
║  NORMATIVAS: NOM-004-SSA3 · NOM-024-SSA3 · LFPDPPP                           ║
╚══════════════════════════════════════════════════════════════════════════════╝

CONTRATO DEL API — Nombres de campos en SintomasInput:
  Los campos clínicos usan exactamente los mismos nombres que las columnas
  del dataset (y las features del modelo XGBoost). Esto evita cualquier mapeo
  y es la causa raíz de los errores 422 anteriores.

  Campos requeridos : edad
  Campos opcionales : todos los demás (tienen defaults seguros)
"""

import uuid
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from smartx_motor_inferencia import (
    CATALOGO_MOTIVOS,
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
    version  = "1.0.0-piloto",
    docs_url = "/docs",
    redoc_url= "/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins     = ["*"],
    allow_credentials = True,
    allow_methods     = ["GET", "POST"],
    allow_headers     = ["*"],
)

motor = MotorInferenciaSmartX()


# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 2 — MODELO PYDANTIC DE ENTRADA
# ══════════════════════════════════════════════════════════════════════════════

class SintomasInput(BaseModel):
    """
    Cuerpo del POST /api/v1/inferencia.

    Los nombres de los campos clínicos son idénticos a las columnas del dataset
    y a las features del modelo XGBoost. No hay mapeo intermedio.

    Solo 'edad' es estrictamente requerido; todos los demás tienen defaults.
    """

    # ── Metadata del paciente (trazabilidad, no son features del modelo) ───────
    id_paciente:     str           = Field(default_factory=lambda: str(uuid.uuid4()),
                                           description="UUID seudonimizado (LFPDPPP)")
    unidad_atencion: str           = Field(default="HCG_URGENCIAS",
                                           description="HCG_URGENCIAS | HCG_MED_INTERNA")
    sexo_biologico:  str           = Field(default="M",   description="'M' | 'F'")
    peso_kg:         Optional[float] = Field(default=None, ge=1.0,  le=300.0)
    talla_cm:        Optional[float] = Field(default=None, ge=30.0, le=250.0)
    sintomas_texto:  Optional[str]   = Field(default=None, description="Descripción libre")

    # ── Columnas del dataset fuera del modelo (trazabilidad) ───────────────────
    antecedentes_riesgo: str = Field(default="Ninguno",
                                     description="Ej: 'Diabetes, Hipertensión'")
    sintomas_digestivos: str = Field(default="Ninguno",
                                     description="Ej: 'Náusea, Vómito'")

    # ── Features del modelo — nombres exactos del dataset ──────────────────────
    edad: int = Field(..., ge=0, le=120, description="Edad en años (requerido)")

    embarazo: bool = Field(default=False,
                           description="¿Paciente está o puede estar embarazada?")

    motivo_consulta: str = Field(
        default="Fiebre sin foco claro",
        description=(
            "Motivo principal. Valores válidos: "
            + ", ".join(f'"{m}"' for m in CATALOGO_MOTIVOS)
        ),
    )

    tiempo_evolucion_horas: int = Field(default=0, ge=0,
                                        description="Horas desde inicio del síntoma")

    intensidad_sintoma: int = Field(default=0, ge=0, le=10,
                                    description="Escala EVA 0–10")

    fiebre_reportada:        bool = Field(default=False)
    tos:                     bool = Field(default=False)
    dificultad_respiratoria: bool = Field(default=False)
    dolor_toracico:          bool = Field(default=False)
    dolor_al_orinar:         bool = Field(default=False)
    sangrado_activo:         bool = Field(default=False)
    confusion:               bool = Field(default=False,
                                          description="Alteración de consciencia")
    disminucion_movimientos_fetales: bool = Field(default=False)

    # ── 4 Redflags — disparan ROJO inmediato sin pasar por ML ──────────────────
    redflag_disnea_severa:                          bool = Field(default=False)
    redflag_sangrado_abundante:                     bool = Field(default=False)
    redflag_deficit_neurologico_subito:             bool = Field(default=False)
    redflag_dolor_toracico_opresivo_con_sudoracion: bool = Field(default=False)

    # ── Validaciones ───────────────────────────────────────────────────────────
    @field_validator("motivo_consulta")
    @classmethod
    def validar_motivo(cls, v: str) -> str:
        if v not in CATALOGO_MOTIVOS:
            raise ValueError(
                f"'{v}' no es un motivo válido. "
                f"Opciones: {CATALOGO_MOTIVOS}"
            )
        return v

    @field_validator("sexo_biologico")
    @classmethod
    def validar_sexo(cls, v: str) -> str:
        if v not in ("M", "F"):
            raise ValueError("sexo_biologico debe ser 'M' o 'F'")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "edad"                    : 45,
                "sexo_biologico"          : "M",
                "motivo_consulta"         : "Fiebre sin foco claro",
                "tiempo_evolucion_horas"  : 12,
                "intensidad_sintoma"      : 6,
                "fiebre_reportada"        : True,
                "tos"                     : False,
                "dificultad_respiratoria" : False,
                "dolor_toracico"          : False,
                "dolor_al_orinar"         : False,
                "sangrado_activo"         : False,
                "confusion"               : False,
                "disminucion_movimientos_fetales"                : False,
                "redflag_disnea_severa"                         : False,
                "redflag_sangrado_abundante"                    : False,
                "redflag_deficit_neurologico_subito"            : False,
                "redflag_dolor_toracico_opresivo_con_sudoracion": False,
                "embarazo"                : False,
                "antecedentes_riesgo"     : "Hipertensión",
                "peso_kg"                 : 75.0,
                "talla_cm"                : 170.0,
            }
        }


# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 3 — MIDDLEWARE DE AUDITORÍA
# ══════════════════════════════════════════════════════════════════════════════

@app.middleware("http")
async def middleware_auditoria(request: Request, call_next):
    """Registra cada request. En producción escribe en tabla AUDITORIA (NOM-024)."""
    inicio   = time.time()
    response = await call_next(request)
    log_entry = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "metodo"       : request.method,
        "ruta"         : str(request.url.path),
        "ip_origen"    : request.client.host if request.client else "unknown",
        "status_code"  : response.status_code,
        "duracion_ms"  : int((time.time() - inicio) * 1000),
    }
    # print(f"[AUDIT] {json.dumps(log_entry)}")  # descomentar para debug
    return response


# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 4 — ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/", tags=["Sistema"])
async def raiz():
    """Health check básico."""
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
    """Estado del motor de inferencia."""
    return {
        "status"        : "ok",
        "motor_version" : motor.MODELO_VERSION,
        "timestamp_utc" : datetime.now(timezone.utc).isoformat(),
    }


@app.post(
    "/api/v1/inferencia",
    response_model = dict,
    status_code    = status.HTTP_200_OK,
    tags           = ["Triage"],
    summary        = "Clasificar urgencia del paciente",
    description    = (
        "Recibe síntomas y antecedentes del paciente, ejecuta el pipeline "
        "del Motor de Inferencia Smart X y devuelve el nivel de urgencia "
        "(semáforo rojo/amarillo/verde). Conforme a NOM-004-SSA3 y NOM-024-SSA3."
    ),
)
async def clasificar_paciente(datos: SintomasInput) -> dict:
    """
    Pipeline:
      1. Construye Paciente desde SintomasInput (campos 1-a-1, sin mapeo)
      2. Ejecuta motor.procesar(paciente)
      3. Devuelve nivel_ia, fuente_nivel y probabilidades
    """
    try:
        paciente = Paciente(
            # Metadata
            id_paciente     = datos.id_paciente,
            id_consulta     = str(uuid.uuid4()),
            unidad_atencion = datos.unidad_atencion,
            # 17 features del modelo
            edad                    = datos.edad,
            embarazo                = datos.embarazo,
            motivo_consulta         = datos.motivo_consulta,
            tiempo_evolucion_horas  = datos.tiempo_evolucion_horas,
            intensidad_sintoma      = datos.intensidad_sintoma,
            fiebre_reportada        = datos.fiebre_reportada,
            tos                     = datos.tos,
            dificultad_respiratoria = datos.dificultad_respiratoria,
            dolor_toracico          = datos.dolor_toracico,
            dolor_al_orinar         = datos.dolor_al_orinar,
            sangrado_activo         = datos.sangrado_activo,
            confusion               = datos.confusion,
            disminucion_movimientos_fetales              = datos.disminucion_movimientos_fetales,
            redflag_disnea_severa                        = datos.redflag_disnea_severa,
            redflag_sangrado_abundante                   = datos.redflag_sangrado_abundante,
            redflag_deficit_neurologico_subito           = datos.redflag_deficit_neurologico_subito,
            redflag_dolor_toracico_opresivo_con_sudoracion = datos.redflag_dolor_toracico_opresivo_con_sudoracion,
            # Trazabilidad
            antecedentes_riesgo = datos.antecedentes_riesgo,
            sintomas_digestivos = datos.sintomas_digestivos,
            sexo_biologico      = datos.sexo_biologico,
            peso_kg             = datos.peso_kg,
            talla_cm            = datos.talla_cm,
            sintomas_texto      = datos.sintomas_texto,
        )

        resultado = motor.procesar(paciente)

        return {
            "nivel_ia"      : resultado.nivel_ia,
            "fuente_nivel"  : resultado.fuente_nivel,
            "probabilidades": resultado.probabilidades,
        }

    except ValueError as e:
        raise HTTPException(
            status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail      = {"error": "Validación clínica fallida", "detalle": str(e)},
        )
    except Exception as e:
        raise HTTPException(
            status_code = status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail      = {"error": "Error interno del Motor de Inferencia", "mensaje": str(e)},
        )


@app.get(
    "/api/v1/paciente/{id_paciente}/historial",
    tags    = ["Historial"],
    summary = "Historial de clasificaciones del paciente",
)
async def historial_paciente(id_paciente: str):
    """En producción consulta mv_historial_longitudinal de PostgreSQL."""
    return {
        "id_paciente"        : id_paciente,
        "nota"               : "En producción conecta a mv_historial_longitudinal (PostgreSQL).",
        "total_visitas"      : 0,
        "visitas"            : [],
        "condiciones_cronicas": [],
        "alerta_alergias"    : [],
    }


@app.get(
    "/api/v1/catalogo/escenarios",
    tags    = ["Catálogo"],
    summary = "Catálogo CIE-10 por nivel de urgencia",
)
async def catalogo_escenarios():
    return {
        "catalogo" : motor.CATALOGO_ESCENARIOS,
        "version"  : motor.MODELO_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get(
    "/api/v1/catalogo/motivos",
    tags    = ["Catálogo"],
    summary = "Lista de motivos de consulta válidos",
)
async def catalogo_motivos():
    return {"motivos": CATALOGO_MOTIVOS}


# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 5 — MANEJO GLOBAL DE ERRORES
# ══════════════════════════════════════════════════════════════════════════════

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code = exc.status_code,
        content     = {
            "sistema"  : "Smart X API",
            "error"    : exc.detail,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ruta"     : str(request.url.path),
        }
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
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
    import uvicorn

    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║   SMART X API — Motor de Triage HCG  |  Piloto v1.0            ║")
    print("╠════════════════════════════════════════════════════════════════╣")
    print("║   Swagger UI  : http://localhost:8000/docs                     ║")
    print("║   Health check: http://localhost:8000/health                   ║")
    print("║   Inferencia  : POST http://localhost:8000/api/v1/inferencia   ║")
    print("╚════════════════════════════════════════════════════════════════╝\n")

    uvicorn.run(
        "smartx_api:app",
        host      = "0.0.0.0",
        port      = 8000,
        reload    = True,
        log_level = "info",
    )

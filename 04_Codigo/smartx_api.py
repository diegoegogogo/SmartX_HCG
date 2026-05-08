"""
╔══════════════════════════════════════════════════════════════════════════════╗
║        SMART X — API REST (FastAPI)                                          ║
║        Conexión Frontend ↔ Motor de Inferencia ↔ Supabase                   ║
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
"""

import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from smartx_motor_inferencia import (
    CATALOGO_MOTIVOS,
    MotorInferenciaSmartX,
    Paciente,
)

load_dotenv()

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 1 — CLIENTE SUPABASE
# ══════════════════════════════════════════════════════════════════════════════

_sb = None

def _init_supabase():
    global _sb
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SECRET_KEY", "")
    if not url or not key:
        logger.warning("SUPABASE_URL / SUPABASE_SECRET_KEY no configuradas — sin persistencia")
        return
    try:
        from supabase import create_client
        _sb = create_client(url, key)
        logger.info("Supabase conectado: %s", url)
    except Exception as exc:
        logger.warning("No se pudo conectar a Supabase: %s", exc)

_init_supabase()


# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 2 — INICIALIZACIÓN DE LA APP
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

_CORS_ORIGINS = [
    "http://localhost:8000",
    "http://localhost:8501",   # Streamlit dev
    "http://127.0.0.1:8000",
    "http://127.0.0.1:8501",
    # Agrega aquí el dominio de producción cuando se despliegue
]

app.add_middleware(
    CORSMiddleware,
    allow_origins     = _CORS_ORIGINS,
    allow_credentials = False,         # True solo si usas cookies/sesiones
    allow_methods     = ["GET", "POST"],
    allow_headers     = ["Content-Type", "Authorization", "apikey"],
)

motor = MotorInferenciaSmartX()


# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 3 — MODELO PYDANTIC DE ENTRADA
# ══════════════════════════════════════════════════════════════════════════════

class SintomasInput(BaseModel):
    """
    Cuerpo del POST /api/v1/inferencia.
    Solo 'edad' es requerido; todos los demás tienen defaults.
    """

    # ── Metadata ───────────────────────────────────────────────────────────────
    id_paciente:     str           = Field(default_factory=lambda: str(uuid.uuid4()))
    unidad_atencion: str           = Field(default="HCG_URGENCIAS")
    sexo_biologico:  str           = Field(default="M")
    peso_kg:         Optional[float] = Field(default=None, ge=1.0,  le=300.0)
    talla_cm:        Optional[float] = Field(default=None, ge=30.0, le=250.0)
    sintomas_texto:  Optional[str]   = Field(default=None, max_length=2000,
                                             description="Descripción libre — mín 10 chars si se envía")
    antecedentes_riesgo: str = Field(default="Ninguno", max_length=500)
    sintomas_digestivos: str = Field(default="Ninguno", max_length=500)

    @field_validator("sintomas_texto")
    @classmethod
    def validar_sintomas_texto(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        if len(v) == 0:
            return None
        if len(v) < 10:
            raise ValueError("sintomas_texto debe tener al menos 10 caracteres o no enviarse")
        return v

    # ── Features del modelo ────────────────────────────────────────────────────
    edad: int = Field(..., ge=0, le=120)

    embarazo: bool = Field(default=False)
    motivo_consulta: str = Field(default="Fiebre sin foco claro")
    tiempo_evolucion_horas: int = Field(default=0, ge=0)
    intensidad_sintoma: int = Field(default=0, ge=0, le=10)

    fiebre_reportada:        bool = Field(default=False)
    tos:                     bool = Field(default=False)
    dificultad_respiratoria: bool = Field(default=False)
    dolor_toracico:          bool = Field(default=False)
    dolor_al_orinar:         bool = Field(default=False)
    sangrado_activo:         bool = Field(default=False)
    confusion:               bool = Field(default=False)
    disminucion_movimientos_fetales: bool = Field(default=False)

    redflag_disnea_severa:                          bool = Field(default=False)
    redflag_sangrado_abundante:                     bool = Field(default=False)
    redflag_deficit_neurologico_subito:             bool = Field(default=False)
    redflag_dolor_toracico_opresivo_con_sudoracion: bool = Field(default=False)

    @field_validator("motivo_consulta")
    @classmethod
    def validar_motivo(cls, v: str) -> str:
        if v not in CATALOGO_MOTIVOS:
            raise ValueError(f"'{v}' no es válido. Opciones: {CATALOGO_MOTIVOS}")
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
                "edad": 45, "sexo_biologico": "M",
                "motivo_consulta": "Fiebre sin foco claro",
                "tiempo_evolucion_horas": 12, "intensidad_sintoma": 6,
                "fiebre_reportada": True,
            }
        }


# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 4 — MIDDLEWARE DE AUDITORÍA
# ══════════════════════════════════════════════════════════════════════════════

@app.middleware("http")
async def middleware_auditoria(request: Request, call_next):
    inicio   = time.time()
    response = await call_next(request)
    duracion = int((time.time() - inicio) * 1000)

    if _sb:
        try:
            _sb.table("auditoria_api").insert({
                "metodo"      : request.method,
                "ruta"        : str(request.url.path),
                "ip_origen"   : request.client.host if request.client else "unknown",
                "status_code" : response.status_code,
                "duracion_ms" : duracion,
            }).execute()
        except Exception as _audit_err:
            logger.warning("Auditoría Supabase falló (no interrumpe la respuesta): %s", _audit_err)

    return response


# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 5 — ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/", tags=["Sistema"])
async def raiz():
    return {
        "sistema"  : "Smart X API",
        "version"  : "1.0.0-piloto",
        "unidad"   : "Hospital Civil Viejo de Guadalajara",
        "estado"   : "operativo",
        "supabase" : "conectado" if _sb else "no configurado",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "docs"     : "/docs",
    }


@app.get("/health", tags=["Sistema"])
async def health_check():
    return {
        "status"        : "ok",
        "motor_version" : motor.MODELO_VERSION,
        "supabase"      : "conectado" if _sb else "no configurado",
        "timestamp_utc" : datetime.now(timezone.utc).isoformat(),
    }


@app.post(
    "/api/v1/inferencia",
    response_model = dict,
    status_code    = status.HTTP_200_OK,
    tags           = ["Triage"],
    summary        = "Clasificar urgencia del paciente",
)
async def clasificar_paciente(datos: SintomasInput) -> dict:
    try:
        paciente = Paciente(
            id_paciente     = datos.id_paciente,
            id_consulta     = str(uuid.uuid4()),
            unidad_atencion = datos.unidad_atencion,
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
            antecedentes_riesgo = datos.antecedentes_riesgo,
            sintomas_digestivos = datos.sintomas_digestivos,
            sexo_biologico      = datos.sexo_biologico,
            peso_kg             = datos.peso_kg,
            talla_cm            = datos.talla_cm,
            sintomas_texto      = datos.sintomas_texto,
        )

        resultado = motor.procesar(paciente)

        # ── Persistir en Supabase ─────────────────────────────────────────────
        if _sb:
            try:
                _sb.table("inferencias").insert({
                    "id_paciente"  : datos.id_paciente,
                    "id_consulta"  : paciente.id_consulta,
                    "unidad_atencion": datos.unidad_atencion,
                    "sexo_biologico" : datos.sexo_biologico,
                    "peso_kg"        : datos.peso_kg,
                    "talla_cm"       : datos.talla_cm,
                    "edad"                                         : datos.edad,
                    "embarazo"                                     : datos.embarazo,
                    "motivo_consulta"                              : datos.motivo_consulta,
                    "tiempo_evolucion_horas"                       : datos.tiempo_evolucion_horas,
                    "intensidad_sintoma"                           : datos.intensidad_sintoma,
                    "fiebre_reportada"                             : datos.fiebre_reportada,
                    "tos"                                          : datos.tos,
                    "dificultad_respiratoria"                      : datos.dificultad_respiratoria,
                    "dolor_toracico"                               : datos.dolor_toracico,
                    "dolor_al_orinar"                              : datos.dolor_al_orinar,
                    "sangrado_activo"                              : datos.sangrado_activo,
                    "confusion"                                    : datos.confusion,
                    "disminucion_movimientos_fetales"              : datos.disminucion_movimientos_fetales,
                    "redflag_disnea_severa"                        : datos.redflag_disnea_severa,
                    "redflag_sangrado_abundante"                   : datos.redflag_sangrado_abundante,
                    "redflag_deficit_neurologico_subito"           : datos.redflag_deficit_neurologico_subito,
                    "redflag_dolor_toracico_opresivo_con_sudoracion": datos.redflag_dolor_toracico_opresivo_con_sudoracion,
                    "antecedentes_riesgo"   : datos.antecedentes_riesgo,
                    "sintomas_digestivos"   : datos.sintomas_digestivos,
                    "sintomas_texto"        : datos.sintomas_texto,
                    "nivel_ia"              : resultado.nivel_ia,
                    "fuente_nivel"          : resultado.fuente_nivel,
                    "probabilidad_rojo"     : resultado.probabilidades.get("rojo", 0),
                    "probabilidad_amarillo" : resultado.probabilidades.get("amarillo", 0),
                    "probabilidad_verde"    : resultado.probabilidades.get("verde", 0),
                    "alerta_critica"        : resultado.alerta_critica,
                    "imc_calculado"         : resultado.imc_calculado,
                    "hash_resultado"        : resultado.hash_resultado,
                    "tiempo_procesamiento_ms": resultado.tiempo_procesamiento_ms,
                    "modelo_version"        : resultado.modelo_version,
                }).execute()
            except Exception as exc:
                logger.warning("No se pudo persistir en Supabase: %s", exc)

        return {
            "nivel_ia"      : resultado.nivel_ia,
            "fuente_nivel"  : resultado.fuente_nivel,
            "probabilidades": resultado.probabilidades,
            "escenarios"    : resultado.escenarios_diferenciales,
            "explicacion_shap": resultado.shap_explicacion,
            "alerta_critica": resultado.alerta_critica,
            "alertas_detalle": resultado.alertas_detalle,
            "imc_calculado" : resultado.imc_calculado,
            "modelo_version": resultado.modelo_version,
            "tiempo_procesamiento_ms": resultado.tiempo_procesamiento_ms,
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
    if not _sb:
        return {
            "id_paciente": id_paciente,
            "nota": "Supabase no configurado.",
            "total_visitas": 0,
            "visitas": [],
        }

    try:
        resp = (
            _sb.table("inferencias")
            .select("id_consulta, nivel_ia, fuente_nivel, motivo_consulta, intensidad_sintoma, created_at")
            .eq("id_paciente", id_paciente)
            .order("created_at", desc=True)
            .limit(50)
            .execute()
        )
        visitas = resp.data or []
        return {
            "id_paciente"  : id_paciente,
            "total_visitas": len(visitas),
            "visitas"      : visitas,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get(
    "/api/v1/inferencias/recientes",
    tags    = ["Triage"],
    summary = "Últimas N inferencias (para cargar el dashboard)",
)
async def inferencias_recientes(limite: int = 50):
    if not _sb:
        return {"inferencias": [], "nota": "Supabase no configurado."}

    try:
        resp = (
            _sb.table("inferencias")
            .select(
                "id_consulta, id_paciente, edad, sexo_biologico, motivo_consulta, "
                "nivel_ia, fuente_nivel, probabilidad_rojo, probabilidad_amarillo, "
                "probabilidad_verde, alerta_critica, intensidad_sintoma, created_at"
            )
            .order("created_at", desc=True)
            .limit(min(limite, 200))
            .execute()
        )
        return {"inferencias": resp.data or []}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


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
# SECCIÓN 6 — MANEJO GLOBAL DE ERRORES
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
# SECCIÓN 7 — PUNTO DE ENTRADA (desarrollo local)
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn

    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║   SMART X API — Motor de Triage HCG  |  Piloto v1.0           ║")
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

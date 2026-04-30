"""
Router de triaje — extrae los endpoints de clasificación de smartx_api.py
para que puedan montarse como sub-aplicación de FastAPI.

Uso en smartx_api.py (opcional):
    from backend.app.routers.triaje import router
    app.include_router(router, prefix="/api/v1")
"""
import uuid
import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, field_validator, model_validator

# Motor (importado desde la raíz de 04_Codigo)
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from smartx_motor_inferencia import MotorInferenciaSmartX, Paciente   # noqa: E402

router = APIRouter(tags=["Triage"])
motor  = MotorInferenciaSmartX()


# ── Modelo de entrada ─────────────────────────────────────────────────────────
class SintomasInput(BaseModel):
    id_paciente          : str            = Field(default_factory=lambda: str(uuid.uuid4()))
    unidad_atencion      : str            = Field(default="HCG_URGENCIAS")
    edad                 : int            = Field(..., ge=0, le=120)
    sexo_biologico       : str            = Field(default="M")
    disnea_presente      : bool           = Field(default=False)
    perdida_conciencia   : bool           = Field(default=False)
    sangrado_activo      : bool           = Field(default=False)
    fiebre_presente      : bool           = Field(default=False)
    temperatura_celsius  : Optional[float]= Field(default=None, ge=35.0, le=42.5)
    intensidad_dolor_eva : Optional[int]  = Field(default=None, ge=0, le=10)
    duracion_sintoma_horas: Optional[int] = Field(default=None, ge=0)
    sintomas_texto       : Optional[str]  = Field(default=None, min_length=10)
    peso_kg              : Optional[float]= Field(default=None, ge=1.0, le=300.0)
    talla_cm             : Optional[float]= Field(default=None, ge=30.0, le=250.0)
    diabetes_mellitus    : bool           = Field(default=False)
    hipertension         : bool           = Field(default=False)
    cardiopatia_isquemica: bool           = Field(default=False)
    epoc_asma            : bool           = Field(default=False)
    embarazo_posible     : Optional[bool] = Field(default=None)
    semanas_gestacion    : Optional[int]  = Field(default=None, ge=0, le=42)

    @field_validator("sexo_biologico")
    @classmethod
    def validar_sexo(cls, v):
        if v not in ("M", "F"):
            raise ValueError("sexo_biologico debe ser 'M' o 'F'")
        return v

    @model_validator(mode="after")
    def validar_consistencia(self):
        if not self.fiebre_presente and self.temperatura_celsius is not None:
            raise ValueError("temperatura_celsius requiere fiebre_presente=True")
        if self.embarazo_posible is True and self.sexo_biologico != "F":
            raise ValueError("embarazo_posible=True solo es válido con sexo_biologico='F'")
        if self.semanas_gestacion is not None and not self.embarazo_posible:
            raise ValueError("semanas_gestacion requiere embarazo_posible=True")
        return self


# ── Endpoint principal ────────────────────────────────────────────────────────
@router.post("/inferencia", status_code=status.HTTP_200_OK,
             summary="Clasificar urgencia del paciente")
async def clasificar_paciente(datos: SintomasInput) -> dict:
    try:
        paciente = Paciente(
            id_paciente            = datos.id_paciente,
            id_consulta            = str(uuid.uuid4()),
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
        resultado = motor.procesar(paciente)
        rd = json.loads(resultado.to_json())
        return {
            "nivel_ia":        rd.get("nivel_ia"),
            "probabilidades":  rd.get("probabilidades"),
            "escenarios":      rd.get("escenarios_diferenciales"),
            "explicacion_shap": rd.get("shap_explicacion"),
            "analisis_llm":    rd.get("analisis_llm"),
        }
    except ValueError as e:
        raise HTTPException(
            status_code=422,
            detail={"error": "Validación clínica fallida", "detalle": str(e)},
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"error": "Error interno del motor", "mensaje": str(e)},
        )


# ── Endpoints de catálogo e historial ────────────────────────────────────────
@router.get("/catalogo/escenarios", summary="Listar escenarios CIE-10")
async def catalogo_escenarios():
    return {
        "catalogo":  motor.CATALOGO_ESCENARIOS,
        "version":   motor.MODELO_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/paciente/{id_paciente}/historial", summary="Historial del paciente")
async def historial_paciente(id_paciente: str):
    return {
        "id_paciente": id_paciente,
        "nota":        "En producción conecta a mv_historial_longitudinal (PostgreSQL).",
        "total_visitas": 0,
        "visitas":     [],
    }

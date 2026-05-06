# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║        SMART X — Motor de Inferencia Clínica                                 ║
║        smartx_motor_inferencia.py                                            ║
║        Hospital Civil Viejo de Guadalajara | Piloto v1.0                     ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Expone:                                                                     ║
║    · NivelSemaforo       — Enum rojo / amarillo / verde                      ║
║    · Paciente            — Dataclass con los 17 campos exactos del dataset   ║
║    · ResultadoInferencia — Dataclass de salida                               ║
║    · MotorInferenciaSmartX — Clase principal con .procesar(paciente)         ║
║                                                                              ║
║  Pipeline de procesar():                                                     ║
║    1. Alertas críticas (4 redflag) → ROJO inmediato sin ML                   ║
║    2. Inferencia XGBoost sobre las 17 features del dataset                   ║
║    3. Conservadurismo médico (márgenes estrechos → nivel más seguro)         ║
║    4. SHAP mock + escenarios CIE-10                                          ║
║                                                                              ║
║  Modelo:  assets/models/smartx_model_v2.pkl  (XGBoost, 17 features)         ║
║  Encoder: assets/models/encoder_motivo.pkl   (LabelEncoder, 10 clases)      ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

import joblib
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 1 — CONSTANTES Y CATÁLOGOS
# ══════════════════════════════════════════════════════════════════════════════

_BASE         = Path(__file__).parent
_RUTA_MODELO  = _BASE / "assets" / "models" / "smartx_model_v2.pkl"
_RUTA_ENCODER = _BASE / "assets" / "models" / "encoder_motivo.pkl"

MODELO_VERSION = "xgboost-v2.0-hcg-piloto"

# Umbrales de conservadurismo médico
_UMBRAL_ROJO_DESDE_AMARILLO  = 0.30   # AMARILLO → ROJO si P(rojo) >= 30 %
_UMBRAL_AMARILLO_DESDE_VERDE = 0.30   # VERDE → AMARILLO si P(amarillo) >= 30 %

# Catálogo de motivos de consulta — orden exacto del LabelEncoder entrenado
CATALOGO_MOTIVOS: list[str] = [
    "Dificultad respiratoria",
    "Dolor abdominal",
    "Dolor de cabeza",
    "Dolor torácico",
    "Embarazo o síntoma relacionado con embarazo",
    "Fiebre sin foco claro",
    "Mareo o desmayo",
    "Problema gastrointestinal",
    "Problema urinario",
    "Tos o síntomas respiratorios",
]

CATALOGO_ESCENARIOS: dict[str, list] = {
    "rojo": [
        {"cie10": "I21", "descripcion": "Infarto agudo de miocardio",                        "probabilidad_relativa": "alta"},
        {"cie10": "J80", "descripcion": "Síndrome de dificultad respiratoria aguda (SDRA)",  "probabilidad_relativa": "media"},
        {"cie10": "I64", "descripcion": "Accidente vascular cerebral no especificado",       "probabilidad_relativa": "media"},
        {"cie10": "R57", "descripcion": "Choque, no especificado",                           "probabilidad_relativa": "media"},
        {"cie10": "O67", "descripcion": "Trabajo de parto con hemorragia intrapartum",       "probabilidad_relativa": "baja"},
    ],
    "amarillo": [
        {"cie10": "R07", "descripcion": "Dolor torácico no especificado",                    "probabilidad_relativa": "alta"},
        {"cie10": "R51", "descripcion": "Cefalea",                                           "probabilidad_relativa": "alta"},
        {"cie10": "N30", "descripcion": "Cistitis aguda",                                    "probabilidad_relativa": "media"},
        {"cie10": "K59", "descripcion": "Trastorno funcional intestinal",                    "probabilidad_relativa": "media"},
        {"cie10": "O21", "descripcion": "Hiperemesis gravídica",                             "probabilidad_relativa": "baja"},
    ],
    "verde": [
        {"cie10": "J06", "descripcion": "Infección aguda de vías respiratorias superiores",  "probabilidad_relativa": "alta"},
        {"cie10": "J02", "descripcion": "Faringoamigdalitis aguda",                          "probabilidad_relativa": "alta"},
        {"cie10": "H66", "descripcion": "Otitis media",                                      "probabilidad_relativa": "media"},
        {"cie10": "K30", "descripcion": "Dispepsia funcional",                               "probabilidad_relativa": "media"},
        {"cie10": "M54", "descripcion": "Lumbalgia inespecífica",                            "probabilidad_relativa": "baja"},
    ],
}

_ESPECIALIDAD_POR_NIVEL: dict[str, str] = {
    "rojo":     "Medicina de Urgencias",
    "amarillo": "Medicina General / Especialidad según motivo",
    "verde":    "Consulta General",
}

_NOMBRES_FEATURES: dict[str, str] = {
    "edad":                                            "Edad del paciente",
    "embarazo":                                        "Embarazo",
    "motivo_consulta":                                 "Motivo de consulta",
    "tiempo_evolucion_horas":                          "Duración del síntoma (horas)",
    "intensidad_sintoma":                              "Intensidad del síntoma (EVA)",
    "fiebre_reportada":                                "Fiebre reportada",
    "tos":                                             "Tos",
    "dificultad_respiratoria":                         "Dificultad respiratoria",
    "dolor_toracico":                                  "Dolor torácico",
    "dolor_al_orinar":                                 "Dolor al orinar",
    "sangrado_activo":                                 "Sangrado activo",
    "confusion":                                       "Confusión / alteración de consciencia",
    "disminucion_movimientos_fetales":                 "Disminución movimientos fetales",
    "redflag_disnea_severa":                           "Disnea severa (REDFLAG)",
    "redflag_sangrado_abundante":                      "Sangrado abundante (REDFLAG)",
    "redflag_deficit_neurologico_subito":              "Déficit neurológico súbito (REDFLAG)",
    "redflag_dolor_toracico_opresivo_con_sudoracion":  "Dolor torácico opresivo con sudoración (REDFLAG)",
}

# classes_ del modelo: [0, 1, 2] → 0=rojo, 1=amarillo, 2=verde
_MAPA_CLASE: dict[int, str] = {0: "rojo", 1: "amarillo", 2: "verde"}


# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 2 — ESTRUCTURAS DE DATOS
# ══════════════════════════════════════════════════════════════════════════════

class NivelSemaforo(str, Enum):
    ROJO     = "rojo"
    AMARILLO = "amarillo"
    VERDE    = "verde"


@dataclass
class Paciente:
    """
    Representa un paciente que ingresa al sistema de triaje SmartX.

    Campos clínicos (edad … redflag_*): son exactamente las 17 columnas
    que usa el modelo XGBoost.  Las booleanas se pasan como bool Python;
    el motor las convierte a 0/1 antes de llamar al modelo.

    Campos de metadata (id_*, sexo_biologico, peso_kg, talla_cm, etc.):
    no son features del modelo; se usan para trazabilidad, IMC y auditoría.

    antecedentes_riesgo y sintomas_digestivos existen en el dataset pero
    fueron descartados durante el entrenamiento; se conservan para auditoría.
    """

    # ── Metadata ──────────────────────────────────────────────────────────────
    id_paciente:     str
    id_consulta:     str
    unidad_atencion: str = "HCG_URGENCIAS"

    # ── 17 features del modelo ─────────────────────────────────────────────────
    edad:                    int  = 0
    embarazo:                bool = False
    motivo_consulta:         str  = "Fiebre sin foco claro"
    tiempo_evolucion_horas:  int  = 0
    intensidad_sintoma:      int  = 0
    fiebre_reportada:        bool = False
    tos:                     bool = False
    dificultad_respiratoria: bool = False
    dolor_toracico:          bool = False
    dolor_al_orinar:         bool = False
    sangrado_activo:         bool = False
    confusion:               bool = False
    disminucion_movimientos_fetales:              bool = False
    redflag_disnea_severa:                        bool = False
    redflag_sangrado_abundante:                   bool = False
    redflag_deficit_neurologico_subito:           bool = False
    redflag_dolor_toracico_opresivo_con_sudoracion: bool = False

    # ── Columnas del dataset fuera del modelo (trazabilidad) ──────────────────
    antecedentes_riesgo: str = "Ninguno"
    sintomas_digestivos: str = "Ninguno"

    # ── Metadata clínica adicional (no features) ───────────────────────────────
    sexo_biologico: str             = "M"
    peso_kg:        Optional[float] = None
    talla_cm:       Optional[float] = None
    sintomas_texto: Optional[str]   = None


@dataclass
class ResultadoInferencia:
    """Resultado completo del pipeline. Compatible con HL7-FHIR DiagnosticReport."""
    id_resultado:              str
    id_consulta:               str
    id_paciente:               str
    timestamp_utc:             str
    nivel_ia:                  str   # "rojo" | "amarillo" | "verde"
    fuente_nivel:              str   # "regla_critica" | "XGBoost" | "XGBoost+conservadurismo"
    conservadurismo_aplicado:  bool
    probabilidades:            dict  # {"rojo": float, "amarillo": float, "verde": float}
    escenarios_diferenciales:  list
    especialidad_sugerida:     Optional[str]
    shap_explicacion:          str
    shap_variables_top3:       list
    imc_calculado:             Optional[float]
    alerta_critica:            bool
    alertas_detalle:           list
    modelo_version:            str
    tiempo_procesamiento_ms:   Optional[int]
    hash_resultado:            str

    def to_json(self) -> str:
        return json.dumps(
            {
                "id_resultado":              self.id_resultado,
                "id_consulta":               self.id_consulta,
                "id_paciente":               self.id_paciente,
                "timestamp_utc":             self.timestamp_utc,
                "nivel_ia":                  self.nivel_ia,
                "fuente_nivel":              self.fuente_nivel,
                "conservadurismo_aplicado":  self.conservadurismo_aplicado,
                "probabilidades":            self.probabilidades,
                "escenarios_diferenciales":  self.escenarios_diferenciales,
                "especialidad_sugerida":     self.especialidad_sugerida,
                "shap_explicacion":          self.shap_explicacion,
                "shap_variables_top3":       self.shap_variables_top3,
                "imc_calculado":             self.imc_calculado,
                "alerta_critica":            self.alerta_critica,
                "alertas_detalle":           self.alertas_detalle,
                "modelo_version":            self.modelo_version,
                "tiempo_procesamiento_ms":   self.tiempo_procesamiento_ms,
                "hash_resultado":            self.hash_resultado,
                "analisis_llm":              None,
            },
            ensure_ascii=False,
            default=str,
        )


# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 3 — MOTOR DE INFERENCIA
# ══════════════════════════════════════════════════════════════════════════════

class MotorInferenciaSmartX:
    """
    Motor principal de clasificación clínica SmartX.
    Se instancia una vez al arrancar el servidor (singleton).
    """

    MODELO_VERSION      = MODELO_VERSION
    CATALOGO_ESCENARIOS = CATALOGO_ESCENARIOS

    def __init__(self) -> None:
        logger.info("Iniciando Motor de Inferencia SmartX...")
        try:
            self._modelo  = joblib.load(_RUTA_MODELO)
            self._encoder = joblib.load(_RUTA_ENCODER)
        except FileNotFoundError as exc:
            raise RuntimeError(
                "Modelo no encontrado en assets/models/. "
                "Ejecuta: python models/clasificacion.py"
            ) from exc

        self._importancias: dict[str, float] = {
            name: float(imp)
            for name, imp in zip(
                self._modelo.feature_names_in_,
                self._modelo.feature_importances_,
            )
        }
        logger.info(
            "Motor listo. Versión: %s | %d features | Encoder: %d clases",
            MODELO_VERSION,
            self._modelo.n_features_in_,
            len(self._encoder.classes_),
        )

    # ── Utilidades ────────────────────────────────────────────────────────────

    @staticmethod
    def _b(val: bool) -> int:
        """bool → 0/1 para el vector de features."""
        return 1 if val else 0

    def _calcular_imc(self, p: Paciente) -> Optional[float]:
        if p.peso_kg and p.talla_cm and p.talla_cm > 0:
            return round(p.peso_kg / (p.talla_cm / 100) ** 2, 1)
        return None

    def _codificar_motivo(self, motivo: str) -> int:
        """LabelEncoder → índice numérico. Fallback a 'Fiebre sin foco claro'."""
        try:
            return int(self._encoder.transform([motivo])[0])
        except ValueError:
            logger.warning(
                "motivo_consulta '%s' fuera del catálogo — fallback aplicado.", motivo
            )
            return int(self._encoder.transform(["Fiebre sin foco claro"])[0])

    # ── Paso 1: Alertas críticas ──────────────────────────────────────────────

    def _alertas_criticas(self, p: Paciente) -> list[str]:
        """Evalúa los 4 redflag. Si alguno está activo → ROJO sin pasar por ML."""
        alertas: list[str] = []
        if p.redflag_disnea_severa:
            alertas.append("Disnea severa — riesgo de falla respiratoria")
        if p.redflag_sangrado_abundante:
            alertas.append("Sangrado abundante — riesgo de choque hipovolémico")
        if p.redflag_deficit_neurologico_subito:
            alertas.append("Déficit neurológico súbito — posible EVC")
        if p.redflag_dolor_toracico_opresivo_con_sudoracion:
            alertas.append("Dolor torácico opresivo con sudoración — posible IAM")
        return alertas

    # ── Paso 2: Vector de features (17 columnas, orden exacto del modelo) ─────

    def _construir_vector(self, p: Paciente) -> pd.DataFrame:
        return pd.DataFrame([{
            "edad":                    p.edad,
            "embarazo":                self._b(p.embarazo),
            "motivo_consulta":         self._codificar_motivo(p.motivo_consulta),
            "tiempo_evolucion_horas":  p.tiempo_evolucion_horas,
            "intensidad_sintoma":      p.intensidad_sintoma,
            "fiebre_reportada":        self._b(p.fiebre_reportada),
            "tos":                     self._b(p.tos),
            "dificultad_respiratoria": self._b(p.dificultad_respiratoria),
            "dolor_toracico":          self._b(p.dolor_toracico),
            "dolor_al_orinar":         self._b(p.dolor_al_orinar),
            "sangrado_activo":         self._b(p.sangrado_activo),
            "confusion":               self._b(p.confusion),
            "disminucion_movimientos_fetales":                self._b(p.disminucion_movimientos_fetales),
            "redflag_disnea_severa":                          self._b(p.redflag_disnea_severa),
            "redflag_sangrado_abundante":                     self._b(p.redflag_sangrado_abundante),
            "redflag_deficit_neurologico_subito":             self._b(p.redflag_deficit_neurologico_subito),
            "redflag_dolor_toracico_opresivo_con_sudoracion": self._b(p.redflag_dolor_toracico_opresivo_con_sudoracion),
        }])

    # ── Paso 3: Conservadurismo médico ────────────────────────────────────────

    def _aplicar_conservadurismo(self, nivel: str, proba: dict) -> tuple[str, bool]:
        if nivel == "amarillo" and proba["rojo"] >= _UMBRAL_ROJO_DESDE_AMARILLO:
            return "rojo", True
        if nivel == "verde" and proba["amarillo"] >= _UMBRAL_AMARILLO_DESDE_VERDE:
            return "amarillo", True
        return nivel, False

    # ── Paso 4: SHAP mock ─────────────────────────────────────────────────────

    def _generar_shap_mock(self, vector: pd.DataFrame, nivel: str) -> tuple[str, list]:
        """Proxy SHAP usando feature_importances_ del modelo."""
        fila = vector.iloc[0].to_dict()
        NUMERICAS = {"edad", "tiempo_evolucion_horas", "intensidad_sintoma", "motivo_consulta"}
        pesos: dict[str, float] = {}
        for nombre, valor in fila.items():
            imp = self._importancias.get(nombre, 0.0)
            if nombre in NUMERICAS or float(valor) > 0:
                pesos[nombre] = round(imp, 4)

        top3 = sorted(pesos.items(), key=lambda x: x[1], reverse=True)[:3]
        top3_lista = [
            {"variable": _NOMBRES_FEATURES.get(n, n), "peso_shap": p}
            for n, p in top3
        ]
        if top3_lista:
            vars_str = ", ".join(d["variable"] for d in top3_lista[:2])
            explicacion = f"Clasificación {nivel.upper()} determinada principalmente por: {vars_str}."
        else:
            explicacion = f"Clasificación {nivel.upper()} basada en el perfil clínico general."
        return explicacion, top3_lista

    def _seleccionar_escenarios(self, nivel: str) -> list:
        return CATALOGO_ESCENARIOS.get(nivel, [])[:3]

    # ── Pipeline principal ────────────────────────────────────────────────────

    def procesar(self, paciente: Paciente) -> ResultadoInferencia:
        """
        Pipeline completo de triaje en 4 pasos:
          1. Alertas críticas  → ROJO inmediato si hay algún redflag activo
          2. Inferencia XGBoost → probabilidades (17 features)
          3. Conservadurismo    → escala nivel si márgenes son estrechos
          4. SHAP mock + CIE-10 → explicabilidad y escenarios diferenciales
        """
        t0        = time.time()
        timestamp = datetime.now(timezone.utc).isoformat()

        alertas = self._alertas_criticas(paciente)

        if alertas:
            nivel     = NivelSemaforo.ROJO.value
            fuente    = "regla_critica"
            conserv   = False
            proba     = {"rojo": 1.0, "amarillo": 0.0, "verde": 0.0}
            shap_exp  = (
                f"ROJO por regla clínica directa: {'; '.join(alertas)}. "
                "El motor ML no fue consultado."
            )
            shap_top3 = [
                {"variable": a.split(" — ")[0], "peso_shap": 1.0}
                for a in alertas[:3]
            ]
        else:
            vector    = self._construir_vector(paciente)
            proba_raw = self._modelo.predict_proba(vector)[0]
            proba = {
                "rojo":     round(float(proba_raw[0]), 4),
                "amarillo": round(float(proba_raw[1]), 4),
                "verde":    round(float(proba_raw[2]), 4),
            }
            nivel_raw = _MAPA_CLASE[int(np.argmax(proba_raw))]
            nivel, conserv = self._aplicar_conservadurismo(nivel_raw, proba)
            fuente = "XGBoost+conservadurismo" if conserv else "XGBoost"
            shap_exp, shap_top3 = self._generar_shap_mock(vector, nivel)

        escenarios = self._seleccionar_escenarios(nivel)
        _payload   = f"{paciente.id_paciente}|{nivel}|{timestamp}"
        hash_r     = hashlib.sha256(_payload.encode()).hexdigest()[:16]

        return ResultadoInferencia(
            id_resultado             = str(uuid.uuid4()),
            id_consulta              = paciente.id_consulta,
            id_paciente              = paciente.id_paciente,
            timestamp_utc            = timestamp,
            nivel_ia                 = nivel,
            fuente_nivel             = fuente,
            conservadurismo_aplicado = conserv,
            probabilidades           = proba,
            escenarios_diferenciales = escenarios,
            especialidad_sugerida    = _ESPECIALIDAD_POR_NIVEL[nivel],
            shap_explicacion         = shap_exp,
            shap_variables_top3      = shap_top3,
            imc_calculado            = self._calcular_imc(paciente),
            alerta_critica           = bool(alertas),
            alertas_detalle          = alertas,
            modelo_version           = MODELO_VERSION,
            tiempo_procesamiento_ms  = int((time.time() - t0) * 1000),
            hash_resultado           = hash_r,
        )

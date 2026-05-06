# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║        SMART X — Motor de Inferencia Clínica                                 ║
║        smartx_motor_inferencia.py                                            ║
║        Hospital Civil Viejo de Guadalajara | Piloto v1.0                     ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Expone:                                                                     ║
║    · NivelSemaforo    — Enum rojo / amarillo / verde                         ║
║    · Paciente         — Dataclass con campos exactos del dataset             ║
║    · ResultadoInferencia — Dataclass de salida con to_json()                 ║
║    · MotorInferenciaSmartX — Clase principal con .procesar(paciente)         ║
║                                                                              ║
║  Pipeline de procesar():                                                     ║
║    1. Alertas críticas (4 redflag del dataset) → ROJO inmediato sin ML       ║
║    2. Inferencia XGBoost sobre las 17 features exactas del dataset           ║
║    3. Conservadurismo médico (márgenes estrechos → nivel más seguro)         ║
║    4. SHAP mock + escenarios CIE-10 estructurados                            ║
║                                                                              ║
║  Sincronización dataset:                                                     ║
║    Hoja "entrenamiento" — 17 features / hoja "catalogos" — motivos           ║
║    Modelo: assets/models/smartx_model_v2.pkl (XGBoost)                       ║
║    Encoder: assets/models/encoder_motivo.pkl (LabelEncoder, 10 clases)       ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

# ─── IMPORTACIONES ────────────────────────────────────────────────────────────
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
# Si P(rojo) >= 30 % cuando el modelo dice AMARILLO → escalar a ROJO
_UMBRAL_ROJO_DESDE_AMARILLO  = 0.30
# Si P(amarillo) >= 30 % cuando el modelo dice VERDE  → escalar a AMARILLO
_UMBRAL_AMARILLO_DESDE_VERDE = 0.30

# Catálogo de motivos de consulta (hoja "catalogos" del dataset — columna motivo_consulta)
# Orden alfabético usado por el LabelEncoder entrenado.
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

# Escenarios CIE-10 por nivel de urgencia (mock estructurado para el piloto)
CATALOGO_ESCENARIOS: dict[str, list] = {
    "rojo": [
        {"cie10": "I21", "descripcion": "Infarto agudo de miocardio",                       "probabilidad_relativa": "alta"},
        {"cie10": "J80", "descripcion": "Síndrome de dificultad respiratoria aguda (SDRA)", "probabilidad_relativa": "media"},
        {"cie10": "I64", "descripcion": "Accidente vascular cerebral no especificado",      "probabilidad_relativa": "media"},
        {"cie10": "R57", "descripcion": "Choque, no especificado",                          "probabilidad_relativa": "media"},
        {"cie10": "O67", "descripcion": "Trabajo de parto con hemorragia intrapartum",      "probabilidad_relativa": "baja"},
    ],
    "amarillo": [
        {"cie10": "R07", "descripcion": "Dolor torácico no especificado",                   "probabilidad_relativa": "alta"},
        {"cie10": "R51", "descripcion": "Cefalea",                                          "probabilidad_relativa": "alta"},
        {"cie10": "N30", "descripcion": "Cistitis aguda",                                   "probabilidad_relativa": "media"},
        {"cie10": "K59", "descripcion": "Trastorno funcional intestinal",                   "probabilidad_relativa": "media"},
        {"cie10": "O21", "descripcion": "Hiperemesis gravídica",                            "probabilidad_relativa": "baja"},
    ],
    "verde": [
        {"cie10": "J06", "descripcion": "Infección aguda de vías respiratorias superiores", "probabilidad_relativa": "alta"},
        {"cie10": "J02", "descripcion": "Faringoamigdalitis aguda",                         "probabilidad_relativa": "alta"},
        {"cie10": "H66", "descripcion": "Otitis media",                                     "probabilidad_relativa": "media"},
        {"cie10": "K30", "descripcion": "Dispepsia funcional",                              "probabilidad_relativa": "media"},
        {"cie10": "M54", "descripcion": "Lumbalgia inespecífica",                           "probabilidad_relativa": "baja"},
    ],
}

_ESPECIALIDAD_POR_NIVEL: dict[str, str] = {
    "rojo":     "Medicina de Urgencias",
    "amarillo": "Medicina General / Especialidad según motivo",
    "verde":    "Consulta General",
}

# Nombres legibles de las 17 features (para la explicación SHAP mock)
_NOMBRES_FEATURES: dict[str, str] = {
    "edad":                    "Edad del paciente",
    "embarazo":                "Embarazo",
    "motivo_consulta":         "Motivo de consulta",
    "tiempo_evolucion_horas":  "Duración del síntoma (horas)",
    "intensidad_sintoma":      "Intensidad del síntoma (EVA)",
    "fiebre_reportada":        "Fiebre reportada",
    "tos":                     "Tos",
    "dificultad_respiratoria": "Dificultad respiratoria",
    "dolor_toracico":          "Dolor torácico",
    "dolor_al_orinar":         "Dolor al orinar",
    "sangrado_activo":         "Sangrado activo",
    "confusion":               "Confusión / alteración de consciencia",
    "disminucion_movimientos_fetales":                "Disminución movimientos fetales",
    "redflag_disnea_severa":                          "Disnea severa (REDFLAG)",
    "redflag_sangrado_abundante":                     "Sangrado abundante (REDFLAG)",
    "redflag_deficit_neurologico_subito":             "Déficit neurológico súbito (REDFLAG)",
    "redflag_dolor_toracico_opresivo_con_sudoracion": "Dolor torácico opresivo con sudoración (REDFLAG)",
}

# Mapeo numérico del target que usó clasificacion.py al entrenar
# (mapa_gravedad en clasificacion.py: rojo→0, amarillo→1, verde→2)
# XGBoost.classes_ = [0, 1, 2]  →  índice 0=rojo, 1=amarillo, 2=verde
_MAPA_CLASE: dict[int, str] = {0: "rojo", 1: "amarillo", 2: "verde"}


# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 2 — ESTRUCTURAS DE DATOS
# ══════════════════════════════════════════════════════════════════════════════

class NivelSemaforo(str, Enum):
    """Niveles de urgencia del sistema SmartX conforme a NOM-004-SSA3."""
    ROJO     = "rojo"
    AMARILLO = "amarillo"
    VERDE    = "verde"


@dataclass
class Paciente:
    """
    Representa un paciente que ingresa al sistema de triaje SmartX.

    Los campos clínicos (desde 'edad' hasta el último redflag) reflejan
    exactamente las columnas de la hoja "entrenamiento" del dataset
    dataset_SmartX_2200_casos_con_ruido.xlsx.

    Los campos de metadata (id_*, unidad_atencion, sexo_biologico, peso_kg,
    talla_cm, sintomas_texto) son adicionales para trazabilidad y cálculo
    de IMC; no forman parte del vector de features del modelo.

    Nota sobre antecedentes_riesgo y sintomas_digestivos:
    Estas columnas existen en el dataset pero fueron descartadas durante el
    entrenamiento (clasificacion.py, línea 102). Se conservan en Paciente
    únicamente para trazabilidad clínica y auditoría.
    """

    # ── Metadata ──────────────────────────────────────────────────────────────
    id_paciente:     str
    id_consulta:     str
    unidad_atencion: str = "HCG_URGENCIAS"

    # ── Features del modelo — hoja "entrenamiento", 17 columnas activas ───────
    edad:                    int  = 0
    embarazo:                bool = False
    motivo_consulta:         str  = "Fiebre sin foco claro"   # del CATALOGO_MOTIVOS
    tiempo_evolucion_horas:  int  = 0
    intensidad_sintoma:      int  = 0                         # escala 0–10 (EVA)
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

    # ── Columnas del dataset que no son features del modelo (trazabilidad) ─────
    antecedentes_riesgo:  str = "Ninguno"    # ej. "Diabetes, Hipertensión"
    sintomas_digestivos:  str = "Ninguno"    # ej. "Náusea, Vómito"

    # ── Metadata clínica adicional proveniente del API ─────────────────────────
    sexo_biologico: str            = "M"
    peso_kg:        Optional[float] = None
    talla_cm:       Optional[float] = None
    sintomas_texto: Optional[str]   = None


@dataclass
class ResultadoInferencia:
    """
    Resultado completo del pipeline de inferencia SmartX.
    Compatible con DiagnosticReport HL7-FHIR R4 (adaptado a NOM-024-SSA3).
    """
    id_resultado:              str
    id_consulta:               str
    id_paciente:               str
    timestamp_utc:             str
    nivel_ia:                  str            # "rojo" | "amarillo" | "verde"
    fuente_nivel:              str            # "regla_critica" | "XGBoost" | "XGBoost+conservadurismo"
    conservadurismo_aplicado:  bool
    probabilidades:            dict           # {"rojo": float, "amarillo": float, "verde": float}
    escenarios_diferenciales:  list           # lista de dicts CIE-10
    especialidad_sugerida:     Optional[str]
    shap_explicacion:          str
    shap_variables_top3:       list           # lista de dicts {"variable": str, "peso_shap": float}
    imc_calculado:             Optional[float]
    alerta_critica:            bool
    alertas_detalle:           list           # lista de strings con descripción de cada redflag activo
    modelo_version:            str
    tiempo_procesamiento_ms:   Optional[int]
    hash_resultado:            str            # SHA-256 truncado 16 chars (NOM-024 integridad)

    def to_json(self) -> str:
        """Serializa el resultado a JSON. analisis_llm reservado para integración LLM futura."""
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

    Se instancia una única vez al arrancar el servidor FastAPI (singleton).
    Carga en memoria el modelo XGBoost y el LabelEncoder de motivo_consulta.

    Uso:
        motor = MotorInferenciaSmartX()
        resultado = motor.procesar(paciente)
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
                "Ejecuta primero: python models/clasificacion.py"
            ) from exc

        # Importancias de features para el mock SHAP (feature_importances_ de XGBoost)
        # float() convierte numpy.float32 → Python float para serialización JSON correcta
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

    # ══════════════════════════════════════════════════════════════════════════
    # UTILIDADES INTERNAS
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def _b(val: bool) -> int:
        """Convierte bool → 0/1 para el vector de features."""
        return 1 if val else 0

    def _calcular_imc(self, p: Paciente) -> Optional[float]:
        if p.peso_kg and p.talla_cm and p.talla_cm > 0:
            return round(p.peso_kg / (p.talla_cm / 100) ** 2, 1)
        return None

    def _codificar_motivo(self, motivo: str) -> int:
        """
        Transforma motivo_consulta a su índice numérico mediante el
        LabelEncoder entrenado con las 10 clases del catálogo.
        Fallback a 'Fiebre sin foco claro' si llega un valor inesperado.
        """
        try:
            return int(self._encoder.transform([motivo])[0])
        except ValueError:
            logger.warning(
                "motivo_consulta '%s' fuera del catálogo — usando fallback 'Fiebre sin foco claro'.",
                motivo,
            )
            return int(self._encoder.transform(["Fiebre sin foco claro"])[0])

    # ══════════════════════════════════════════════════════════════════════════
    # PASO 1 — ALERTAS CRÍTICAS (bypass de ML)
    # ══════════════════════════════════════════════════════════════════════════

    def _alertas_criticas(self, p: Paciente) -> list[str]:
        """
        Evalúa los 4 redflag exactos del dataset (hoja "entrenamiento").
        Si alguno está activo, el resultado es ROJO inmediato sin pasar por ML.
        Retorna lista de descripciones de alertas activas (vacía = sin alertas).
        """
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

    # ══════════════════════════════════════════════════════════════════════════
    # PASO 2 — VECTOR DE FEATURES (17 columnas en orden exacto del modelo)
    # ══════════════════════════════════════════════════════════════════════════

    def _construir_vector(self, p: Paciente) -> pd.DataFrame:
        """
        Construye el DataFrame de 17 features en el orden exacto verificado
        contra model.feature_names_in_:

        ['edad', 'embarazo', 'motivo_consulta', 'tiempo_evolucion_horas',
         'intensidad_sintoma', 'fiebre_reportada', 'tos',
         'dificultad_respiratoria', 'dolor_toracico', 'dolor_al_orinar',
         'sangrado_activo', 'confusion', 'disminucion_movimientos_fetales',
         'redflag_disnea_severa', 'redflag_sangrado_abundante',
         'redflag_deficit_neurologico_subito',
         'redflag_dolor_toracico_opresivo_con_sudoracion']
        """
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

    # ══════════════════════════════════════════════════════════════════════════
    # PASO 3 — CONSERVADURISMO MÉDICO
    # ══════════════════════════════════════════════════════════════════════════

    def _aplicar_conservadurismo(
        self, nivel: str, proba: dict
    ) -> tuple[str, bool]:
        """
        Ajusta el nivel hacia el más seguro cuando los márgenes son estrechos:
        · AMARILLO → ROJO   si P(rojo)    >= _UMBRAL_ROJO_DESDE_AMARILLO  (0.30)
        · VERDE    → AMARILLO si P(amarillo) >= _UMBRAL_AMARILLO_DESDE_VERDE (0.30)
        Retorna (nivel_final, conservadurismo_aplicado).
        """
        if nivel == "amarillo" and proba["rojo"] >= _UMBRAL_ROJO_DESDE_AMARILLO:
            return "rojo", True
        if nivel == "verde" and proba["amarillo"] >= _UMBRAL_AMARILLO_DESDE_VERDE:
            return "amarillo", True
        return nivel, False

    # ══════════════════════════════════════════════════════════════════════════
    # PASO 4 — SHAP MOCK Y ESCENARIOS CIE-10
    # ══════════════════════════════════════════════════════════════════════════

    def _generar_shap_mock(
        self, vector: pd.DataFrame, nivel: str
    ) -> tuple[str, list]:
        """
        Proxy de SHAP usando feature_importances_ del modelo XGBoost.
        Incluye solo features activas (booleanas = 1) o numéricas.
        Las numéricas contribuyen siempre con su importancia global.

        En producción: reemplazar por shap.TreeExplainer(self._modelo).
        """
        fila = vector.iloc[0].to_dict()
        pesos: dict[str, float] = {}

        FEATURES_NUMERICAS = {"edad", "tiempo_evolucion_horas", "intensidad_sintoma", "motivo_consulta"}

        for nombre, valor in fila.items():
            imp = self._importancias.get(nombre, 0.0)
            if nombre in FEATURES_NUMERICAS:
                pesos[nombre] = round(imp, 4)
            elif float(valor) > 0:
                pesos[nombre] = round(imp, 4)

        top3 = sorted(pesos.items(), key=lambda x: x[1], reverse=True)[:3]
        top3_lista = [
            {"variable": _NOMBRES_FEATURES.get(n, n), "peso_shap": p}
            for n, p in top3
        ]

        if top3_lista:
            vars_str = ", ".join(d["variable"] for d in top3_lista[:2])
            explicacion = (
                f"Clasificación {nivel.upper()} determinada principalmente por: {vars_str}."
            )
        else:
            explicacion = f"Clasificación {nivel.upper()} basada en el perfil clínico general del paciente."

        return explicacion, top3_lista

    def _seleccionar_escenarios(self, nivel: str) -> list:
        """Retorna los 3 escenarios CIE-10 más probables para el nivel dado."""
        return CATALOGO_ESCENARIOS.get(nivel, [])[:3]

    # ══════════════════════════════════════════════════════════════════════════
    # PIPELINE PRINCIPAL
    # ══════════════════════════════════════════════════════════════════════════

    def procesar(self, paciente: Paciente) -> ResultadoInferencia:
        """
        Ejecuta el pipeline completo de triaje clínico SmartX en 4 pasos:
          1. Alertas críticas  → ROJO inmediato si hay algún redflag activo
          2. Inferencia XGBoost → probabilidades sobre las 17 features del dataset
          3. Conservadurismo    → escala a nivel más grave en márgenes estrechos
          4. SHAP mock + CIE-10 → explicabilidad y escenarios diferenciales

        La clave 'fuente_nivel' en el resultado indica qué mecanismo tomó
        la decisión clínica: "regla_critica", "XGBoost" o "XGBoost+conservadurismo".
        """
        t0        = time.time()
        timestamp = datetime.now(timezone.utc).isoformat()

        # ── PASO 1: Alertas críticas — ROJO inmediato ─────────────────────────
        alertas = self._alertas_criticas(paciente)

        if alertas:
            nivel     = NivelSemaforo.ROJO.value
            fuente    = "regla_critica"
            conserv   = False
            proba     = {"rojo": 1.0, "amarillo": 0.0, "verde": 0.0}
            shap_exp  = (
                f"ROJO por regla clínica directa: {'; '.join(alertas)}. "
                "El motor de ML no fue consultado."
            )
            shap_top3 = [
                {"variable": alerta.split(" — ")[0], "peso_shap": 1.0}
                for alerta in alertas[:3]
            ]

        else:
            # ── PASO 2: Inferencia XGBoost ────────────────────────────────────
            vector    = self._construir_vector(paciente)
            proba_raw = self._modelo.predict_proba(vector)[0]

            # classes_ = [0, 1, 2] → índice 0=rojo, 1=amarillo, 2=verde
            proba = {
                "rojo":     round(float(proba_raw[0]), 4),
                "amarillo": round(float(proba_raw[1]), 4),
                "verde":    round(float(proba_raw[2]), 4),
            }
            nivel_raw = _MAPA_CLASE[int(np.argmax(proba_raw))]

            # ── PASO 3: Conservadurismo médico ────────────────────────────────
            nivel, conserv = self._aplicar_conservadurismo(nivel_raw, proba)
            fuente = "XGBoost+conservadurismo" if conserv else "XGBoost"

            # ── PASO 4: SHAP mock ─────────────────────────────────────────────
            shap_exp, shap_top3 = self._generar_shap_mock(vector, nivel)

        # ── Escenarios CIE-10 y especialidad sugerida ─────────────────────────
        escenarios = self._seleccionar_escenarios(nivel)

        # ── Hash de integridad (NOM-024-SSA3) ─────────────────────────────────
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

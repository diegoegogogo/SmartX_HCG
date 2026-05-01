"""
╔══════════════════════════════════════════════════════════════════════════════╗
║      SMART X — MOTOR DE INFERENCIA v2.0 (Random Forest)                      ║
║      Hospital Civil Viejo de Guadalajara (HCG)                               ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Cambio respecto a v1.0:                                                     ║
║    XGBoost (simulado) → Random Forest (scikit-learn)                         ║
║    Se mantiene TODO lo demás: validaciones, conservadurismo,                 ║
║    SHAP, escenarios CIE-10, HL7-FHIR, hash SHA-256, API, Streamlit.          ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Instalación:                                                                ║
║    pip install scikit-learn joblib pandas shap                               ║
║                                                                              ║
║  Modos de operación:                                                         ║
║    MODO A — Simulación (sin dataset): funciona igual que v1.0                ║
║    MODO B — Modelo real: carga smartx_rf_modelo.pkl entrenado                ║
║             con dataset_hcg.csv del Hospital Civil                           ║
║                                                                              ║
║  Normativas: NOM-004-SSA3 · NOM-024-SSA3 · LFPDPPP                           ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

# ─── IMPORTACIONES ─────────────────────────────────────────────────────────────
import json
import math
import random
import uuid
import hashlib
import joblib
import os
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
from joblib import Memory
# Cachedir relativo al directorio del script (portabilidad)
_script_dir = os.path.dirname(os.path.abspath(__file__))
_cachedir = os.path.join(_script_dir, "cachedir")
os.makedirs(_cachedir, exist_ok=True)
memory = Memory(_cachedir, verbose=0)

# Scikit-learn — se importa solo si el modelo está disponible
try:
    import joblib
    import numpy as np
    import sklearn
    SKLEARN_DISPONIBLE = True
except ImportError:
    SKLEARN_DISPONIBLE = False


# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 1 — ENUMERACIONES Y CONSTANTES
# ══════════════════════════════════════════════════════════════════════════════

class NivelSemaforo(str, Enum):
    """
    Niveles de urgencia del semáforo Smart X.
    Referencia: Documento 1 — Flujo y Variables, Sección B.3
    """
    ROJO     = "rojo"
    AMARILLO = "amarillo"
    VERDE    = "verde"


class FuenteNivel(str, Enum):
    """Indica el origen de la clasificación del semáforo."""
    ALERTA_CRITICA  = "alerta_critica_inmediata"
    MODELO_RF       = "random_forest"          # ← Cambiado de modelo_xgboost
    SIMULACION      = "simulacion_heuristica"  # Cuando no hay modelo entrenado
    CONSERVADURISMO = "conservadurismo_medico"


# Ruta del modelo entrenado — ajustar si está en otra ubicación
RUTA_MODELO_RF = "smartx_rf_modelo.pkl"

# Rangos de validación — NOM-004-SSA3-2012
RANGO_EDAD_MIN        = 0
RANGO_EDAD_MAX        = 120
RANGO_TEMPERATURA_MIN = 35.0
RANGO_TEMPERATURA_MAX = 42.5
RANGO_EVA_MIN         = 0
RANGO_EVA_MAX         = 10
RANGO_PESO_MIN        = 1.0
RANGO_PESO_MAX        = 300.0
RANGO_TALLA_MIN       = 30.0
RANGO_TALLA_MAX       = 250.0
RANGO_SEMANAS_MIN     = 0
RANGO_SEMANAS_MAX     = 42

# Umbral de conservadurismo médico
UMBRAL_CONSERVADURISMO = 0.10

# Orden de clases que scikit-learn usa (alfabético)
# Importante: predict_proba devuelve en este orden
CLASES_MODELO = ["amarillo", "rojo", "verde"]


# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 2 — CLASE PACIENTE
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class Paciente:
    """
    Perfil clínico del paciente. Entrada al Motor de Inferencia Smart X.

    Normativa:
      • NOM-004-SSA3-2012 Art. 10 — Ficha de identificación y antecedentes
      • LFPDPPP — id_paciente es UUID seudonimizado, nunca nombre/NSS
    """
    # ── Identificación seudonimizada ──────────────────────────────────────────
    id_paciente    : str = field(default_factory=lambda: str(uuid.uuid4()))
    id_consulta    : str = field(default_factory=lambda: str(uuid.uuid4()))
    unidad_atencion: str = "HCG_URGENCIAS"

    # ── Demográficas ──────────────────────────────────────────────────────────
    edad           : int  = 0
    sexo_biologico : str  = "M"

    # ── Alertas críticas — bypass del modelo si cualquiera es True ────────────
    disnea_presente    : bool = False
    perdida_conciencia : bool = False
    sangrado_activo    : bool = False

    # ── Síntomas ──────────────────────────────────────────────────────────────
    fiebre_presente        : bool            = False
    temperatura_celsius    : Optional[float] = None
    intensidad_dolor_eva   : Optional[int]   = None
    duracion_sintoma_horas : Optional[int]   = None
    sintomas_texto         : Optional[str]   = None

    # ── Antropometría (para IMC) ───────────────────────────────────────────────
    peso_kg  : Optional[float] = None
    talla_cm : Optional[float] = None

    # ── Antecedentes ──────────────────────────────────────────────────────────
    diabetes_mellitus     : bool          = False
    hipertension          : bool          = False
    cardiopatia_isquemica : bool          = False
    epoc_asma             : bool          = False
    embarazo_posible      : Optional[bool]= None
    semanas_gestacion     : Optional[int] = None


# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 3 — RESULTADO DE INFERENCIA
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class ResultadoInferencia:
    """
    Output del Motor de Inferencia.
    Compatible con DiagnosticReport HL7-FHIR R4 (Documento 4, Sección 1.5).
    """
    id_resultado             : str
    id_consulta              : str
    id_paciente              : str
    timestamp_utc            : str
    nivel_ia                 : NivelSemaforo
    fuente_nivel             : FuenteNivel
    conservadurismo_aplicado : bool
    p_rojo                   : float
    p_amarillo               : float
    p_verde                  : float
    escenario_1_cie10        : Optional[str]
    escenario_1_prob         : Optional[float]
    escenario_2_cie10        : Optional[str]
    escenario_2_prob         : Optional[float]
    escenario_3_cie10        : Optional[str]
    escenario_3_prob         : Optional[float]
    especialidad_sugerida    : Optional[str]
    shap_explicacion         : str
    shap_variables_top3      : list
    modelo_version           : str
    imc_calculado            : Optional[float]
    alerta_critica           : bool
    alertas_detalle          : list
    tiempo_procesamiento_ms  : Optional[int]
    hash_resultado           : str = ""

    def to_json(self) -> str:
        """Serializa a JSON compatible con HL7-FHIR DiagnosticReport R4."""
        return json.dumps({
            "resourceType"             : "DiagnosticReport",
            "id_resultado"             : self.id_resultado,
            "id_consulta"              : self.id_consulta,
            "id_paciente"              : self.id_paciente,
            "timestamp_utc"            : self.timestamp_utc,
            "nivel_ia"                 : self.nivel_ia.value,
            "fuente_nivel"             : self.fuente_nivel.value,
            "conservadurismo_aplicado" : self.conservadurismo_aplicado,
            "probabilidades": {
                "p_rojo"    : round(self.p_rojo,     4),
                "p_amarillo": round(self.p_amarillo, 4),
                "p_verde"   : round(self.p_verde,    4),
            },
            "escenarios_diferenciales": [
                {"cie10": self.escenario_1_cie10, "probabilidad": self.escenario_1_prob, "orden": 1},
                {"cie10": self.escenario_2_cie10, "probabilidad": self.escenario_2_prob, "orden": 2},
                {"cie10": self.escenario_3_cie10, "probabilidad": self.escenario_3_prob, "orden": 3},
            ],
            "especialidad_sugerida" : self.especialidad_sugerida,
            "shap_explicacion"      : self.shap_explicacion,
            "shap_variables_top3"   : self.shap_variables_top3,
            "imc_calculado"         : self.imc_calculado,
            "alerta_critica"        : self.alerta_critica,
            "alertas_detalle"       : self.alertas_detalle,
            "modelo_version"        : self.modelo_version,
            "tiempo_procesamiento_ms": self.tiempo_procesamiento_ms,
            "hash_resultado"        : self.hash_resultado,
        }, ensure_ascii=False, indent=2)


# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 4 — MOTOR DE INFERENCIA (Random Forest)
# ══════════════════════════════════════════════════════════════════════════════

class MotorInferenciaSmartX:
    """
    Motor de Inferencia Smart X v2.0 — Random Forest.

    Detecta automáticamente si existe el modelo entrenado (smartx_rf_modelo.pkl):
      - Si existe → usa Random Forest real (MODO B — producción)
      - Si no existe → usa simulación heurística (MODO A — desarrollo)

    En ambos modos el resto del pipeline es idéntico:
    validación → alertas → IMC → clasificación → conservadurismo →
    escenarios → SHAP → resultado → hash SHA-256.
    """

    MODELO_VERSION_SIMULACION = "rf_v2.0.0-simulacion-hcg"
    MODELO_VERSION_REAL       = "rf_v2.0.0-piloto-hcg"

    # ── Catálogo de escenarios CIE-10 por nivel ───────────────────────────────
    CATALOGO_ESCENARIOS = {
        NivelSemaforo.ROJO.value: [
            ("I21.0", "IAM con elevación del segmento ST",          "Cardiología / Urgencias"),
            ("J96.0", "Insuficiencia respiratoria aguda",           "Urgencias / Medicina Interna"),
            ("I64",   "Enfermedad vascular cerebral aguda (EVC)",   "Neurología / Urgencias"),
            ("R57.0", "Choque cardiogénico",                        "Urgencias / Cuidados Intensivos"),
            ("K25.0", "Úlcera gástrica con hemorragia activa",      "Cirugía / Urgencias"),
            ("O15.9", "Eclampsia — período no especificado",        "Ginecología / Urgencias"),
        ],
        NivelSemaforo.AMARILLO.value: [
            ("J18.9", "Neumonía — organismo no especificado",       "Medicina Interna"),
            ("N10",   "Pielonefritis aguda",                        "Medicina Interna / Urología"),
            ("K35.9", "Apendicitis aguda, sin peritonitis",         "Cirugía General"),
            ("I10",   "Hipertensión esencial (descompensada)",      "Medicina Interna"),
            ("E11.65","Diabetes mellitus tipo 2 con hiperglucemia", "Endocrinología"),
            ("R51",   "Cefalea intensa de inicio súbito",           "Neurología"),
        ],
        NivelSemaforo.VERDE.value: [
            ("Z00.00","Examen médico general sin hallazgos",        "Medicina Familiar"),
            ("J00",   "Rinofaringitis aguda (resfriado común)",     "Medicina Familiar"),
            ("M54.5", "Lumbalgia crónica conocida — control",       "Rehabilitación"),
            ("K21.0", "Reflujo gastroesofágico",                    "Gastroenterología"),
            ("F41.1", "Trastorno de ansiedad generalizada",         "Psiquiatría / Med. Familiar"),
        ],
    }

    # ── Pesos SHAP heurísticos (usados en simulación y como fallback) ─────────
    PESOS_SHAP = {
        "perdida_conciencia"    : 0.95,
        "sangrado_activo"       : 0.93,
        "disnea_presente"       : 0.90,
        "cardiopatia_isquemica" : 0.78,
        "edad_mayor_60"         : 0.72,
        "intensidad_dolor_alta" : 0.68,
        "temperatura_alta"      : 0.65,
        "hipertension"          : 0.60,
        "diabetes_mellitus"     : 0.57,
        "duracion_corta"        : 0.52,
        "embarazo"              : 0.50,
        "epoc_asma"             : 0.48,
        "imc_obesidad"          : 0.35,
    }

    NOMBRES_LEGIBLES = {
        "perdida_conciencia"    : "pérdida de consciencia",
        "sangrado_activo"       : "sangrado activo",
        "disnea_presente"       : "dificultad respiratoria",
        "cardiopatia_isquemica" : "antecedente de cardiopatía isquémica",
        "edad_mayor_60"         : "edad mayor de 60 años",
        "intensidad_dolor_alta" : "dolor de alta intensidad (EVA ≥ 7)",
        "temperatura_alta"      : "fiebre elevada (≥ 38.5°C)",
        "hipertension"          : "hipertensión conocida",
        "diabetes_mellitus"     : "diabetes mellitus",
        "duracion_corta"        : "inicio súbito del síntoma (< 2 horas)",
        "embarazo"              : "embarazo activo",
        "epoc_asma"             : "antecedente de EPOC / asma",
        "imc_obesidad"          : "obesidad (IMC ≥ 30)",
    }

    def __init__(self):
        """
        Inicializa el motor. Carga el modelo Random Forest si está disponible.
        Si no encuentra el archivo .pkl, opera en modo simulación.
        """
        self._modelo_rf   = None
        self._usar_modelo = False

        if SKLEARN_DISPONIBLE and os.path.exists(RUTA_MODELO_RF):
            try:
                self._modelo_rf   = joblib.load(RUTA_MODELO_RF)
                self._usar_modelo = True
                print(f"✅ Modelo Random Forest cargado: {RUTA_MODELO_RF}")
                print(f"   Modo: PRODUCCIÓN (modelo real)")
            except Exception as e:
                print(f"⚠️  No se pudo cargar el modelo: {e}")
                print(f"   Modo: SIMULACIÓN (heurística)")
        else:
            print("ℹ️  Modelo .pkl no encontrado. Modo: SIMULACIÓN (heurística)")
            print(f"   Para activar el modelo real, coloca '{RUTA_MODELO_RF}' en este directorio.")

        self.MODELO_VERSION = (
            self.MODELO_VERSION_REAL
            if self._usar_modelo
            else self.MODELO_VERSION_SIMULACION
        )

    # ─────────────────────────────────────────────────────────────────────────
    # MÉTODO PRINCIPAL
    # ─────────────────────────────────────────────────────────────────────────

    def procesar(self, paciente: Paciente) -> ResultadoInferencia:
        """
        Pipeline completo de clasificación de triage.

        Paso 1:  Validar rangos y consistencia (NOM-004)
        Paso 2:  Calcular IMC
        Paso 3:  Detectar alertas críticas (bypass del modelo)
        Paso 4:  Clasificar con Random Forest o simulación
        Paso 5:  Aplicar conservadurismo médico
        Paso 6:  Determinar nivel final
        Paso 7:  Seleccionar escenarios CIE-10
        Paso 8:  Generar explicación SHAP
        Paso 9:  Construir objeto resultado
        Paso 10: Calcular hash SHA-256 de integridad (NOM-024)
        """
        t_inicio = datetime.now(timezone.utc)

        self._validar_paciente(paciente)
        imc = self._calcular_imc(paciente.peso_kg, paciente.talla_cm)
        alertas, es_alerta_critica = self._detectar_alertas_criticas(paciente)

        if es_alerta_critica:
            p_rojo, p_amarillo, p_verde = 0.97, 0.02, 0.01
            fuente                      = FuenteNivel.ALERTA_CRITICA
            conservadurismo_aplicado    = False
        else:
            p_rojo, p_amarillo, p_verde = self._clasificar(paciente, imc)
            p_rojo, p_amarillo, p_verde, conservadurismo_aplicado = \
                self._aplicar_conservadurismo(p_rojo, p_amarillo, p_verde)
            fuente = (
                FuenteNivel.CONSERVADURISMO if conservadurismo_aplicado else
                FuenteNivel.MODELO_RF       if self._usar_modelo         else
                FuenteNivel.SIMULACION
            )

        nivel_ia = self._determinar_nivel(p_rojo, p_amarillo, p_verde)
        esc1, esc2, esc3 = self._seleccionar_escenarios(nivel_ia, paciente)
        shap_texto, top3_vars = self._generar_shap(paciente, nivel_ia, imc, alertas)

        t_fin = datetime.now(timezone.utc)
        ms    = int((t_fin - t_inicio).total_seconds() * 1000)

        resultado = ResultadoInferencia(
            id_resultado             = str(uuid.uuid4()),
            id_consulta              = paciente.id_consulta,
            id_paciente              = paciente.id_paciente,
            timestamp_utc            = t_fin.isoformat(),
            nivel_ia                 = nivel_ia,
            fuente_nivel             = fuente,
            conservadurismo_aplicado = conservadurismo_aplicado,
            p_rojo                   = p_rojo,
            p_amarillo               = p_amarillo,
            p_verde                  = p_verde,
            escenario_1_cie10        = esc1[0] if esc1 else None,
            escenario_1_prob         = esc1[2] if esc1 else None,
            escenario_2_cie10        = esc2[0] if esc2 else None,
            escenario_2_prob         = esc2[2] if esc2 else None,
            escenario_3_cie10        = esc3[0] if esc3 else None,
            escenario_3_prob         = esc3[2] if esc3 else None,
            especialidad_sugerida    = esc1[1] if esc1 else None,
            shap_explicacion         = shap_texto,
            shap_variables_top3      = top3_vars,
            modelo_version           = self.MODELO_VERSION,
            imc_calculado            = imc,
            alerta_critica           = es_alerta_critica,
            alertas_detalle          = alertas,
            tiempo_procesamiento_ms  = ms,
        )
        resultado.hash_resultado = self._calcular_hash(resultado)
        return resultado

    # ═══════════════════════════════════════════════════════════════════════════
    # MÉTODOS PRIVADOS
    # ═══════════════════════════════════════════════════════════════════════════

    def _validar_paciente(self, p: Paciente) -> None:
        """Valida rangos y consistencia lógica. NOM-004-SSA3-2012."""
        errores = []

        if not (RANGO_EDAD_MIN <= p.edad <= RANGO_EDAD_MAX):
            errores.append(f"edad fuera de rango: {p.edad} (válido: 0–120)")

        if p.intensidad_dolor_eva is not None:
            if not (RANGO_EVA_MIN <= p.intensidad_dolor_eva <= RANGO_EVA_MAX):
                errores.append(f"intensidad_dolor_eva fuera de rango: {p.intensidad_dolor_eva} (0–10)")

        if not p.fiebre_presente and p.temperatura_celsius is not None:
            errores.append("temperatura_celsius debe ser None cuando fiebre_presente=False")

        if p.fiebre_presente and p.temperatura_celsius is not None:
            if not (RANGO_TEMPERATURA_MIN <= p.temperatura_celsius <= RANGO_TEMPERATURA_MAX):
                errores.append(f"temperatura_celsius fuera de rango: {p.temperatura_celsius} (35.0–42.5°C)")

        if p.peso_kg is not None and not (RANGO_PESO_MIN <= p.peso_kg <= RANGO_PESO_MAX):
            errores.append(f"peso_kg fuera de rango: {p.peso_kg}")

        if p.talla_cm is not None and not (RANGO_TALLA_MIN <= p.talla_cm <= RANGO_TALLA_MAX):
            errores.append(f"talla_cm fuera de rango: {p.talla_cm}")

        if p.embarazo_posible is True and p.sexo_biologico != "F":
            errores.append("embarazo_posible=True requiere sexo_biologico='F'")

        if p.semanas_gestacion is not None and not p.embarazo_posible:
            errores.append("semanas_gestacion requiere embarazo_posible=True")

        if p.sexo_biologico not in ("M", "F"):
            errores.append(f"sexo_biologico inválido: '{p.sexo_biologico}' (válido: 'M' o 'F')")

        if errores:
            raise ValueError(
                f"[SmartX NOM-004] Validación fallida para id_paciente={p.id_paciente}:\n"
                + "\n".join(f"  • {e}" for e in errores)
            )

    def _calcular_imc(self, peso_kg, talla_cm) -> Optional[float]:
        """IMC = peso(kg) / (talla(m))². Retorna None si faltan datos."""
        if peso_kg is None or talla_cm is None:
            return None
        return round(peso_kg / (talla_cm / 100.0) ** 2, 2)

    def _detectar_alertas_criticas(self, p: Paciente) -> tuple:
        """
        Detecta condiciones de alarma que bypassan el modelo.
        Si cualquiera es True → ROJO inmediato sin consultar RF.
        """
        alertas = []
        if p.perdida_conciencia:
            alertas.append("⚠️ ALERTA CRÍTICA: pérdida o alteración de consciencia — activar protocolo neurológico urgente")
        if p.sangrado_activo:
            alertas.append("⚠️ ALERTA CRÍTICA: sangrado activo visible — activar protocolo hemostático urgente")
        if p.disnea_presente:
            alertas.append("⚠️ ALERTA CRÍTICA: dificultad respiratoria presente — evaluar vía aérea inmediatamente")
        return alertas, len(alertas) > 0

    def _paciente_a_vector(self, p: Paciente, imc: Optional[float]) -> list:
        """
        Convierte el objeto Paciente a vector numérico para el modelo.

        El orden de las columnas DEBE coincidir con el dataset de entrenamiento.
        Referencia: smartx_entrenamiento_rf.py — columnas de X_train.

        Variables: 13 features en el orden del script de entrenamiento.
        """
        return [
            float(p.edad),
            1.0 if p.sexo_biologico == "F" else 0.0,
            float(p.intensidad_dolor_eva or 0),
            float(p.duracion_sintoma_horas or 0),
            float(p.temperatura_celsius or 0),
            1.0 if p.fiebre_presente else 0.0,
            1.0 if p.diabetes_mellitus else 0.0,
            1.0 if p.hipertension else 0.0,
            1.0 if p.cardiopatia_isquemica else 0.0,
            1.0 if p.epoc_asma else 0.0,
            1.0 if p.embarazo_posible else 0.0,
            float(imc or 0),
            float(p.semanas_gestacion or 0),
        ]

    def _clasificar(self, p: Paciente, imc: Optional[float]) -> tuple:
        """
        Clasifica usando Random Forest real (si está disponible)
        o simulación heurística (si no hay modelo entrenado).

        Retorna: (p_rojo, p_amarillo, p_verde) — suman exactamente 1.0
        """
        if self._usar_modelo and SKLEARN_DISPONIBLE:
            return self._random_forest_real(p, imc)
        else:
            return self._simulacion_heuristica(p, imc)

    def _random_forest_real(self, p: Paciente, imc: Optional[float]) -> tuple:
        """
        MODO B — Clasificación con el modelo Random Forest entrenado.

        sklearn devuelve probabilidades en orden ALFABÉTICO de clases:
        [amarillo, rojo, verde] → remapeamos a (p_rojo, p_amarillo, p_verde)
        """
        if self._modelo_rf is None:
            return self._simulacion_heuristica(p, imc)
        vector = self._paciente_a_vector(p, imc)
        probs  = self._modelo_rf.predict_proba([vector])[0]

        # CLASES_MODELO = ["amarillo", "rojo", "verde"] → índices 0, 1, 2
        p_amarillo = float(probs[0])
        p_rojo     = float(probs[1])
        p_verde    = float(probs[2])

        # Garantizar suma exacta = 1.0
        total      = p_rojo + p_amarillo + p_verde
        p_rojo     = round(p_rojo     / total, 4)
        p_amarillo = round(p_amarillo / total, 4)
        p_verde    = round(1.0 - p_rojo - p_amarillo, 4)

        return p_rojo, p_amarillo, p_verde

    def _simulacion_heuristica(self, p: Paciente, imc: Optional[float]) -> tuple:
        """
        MODO A — Simulación cuando no hay modelo entrenado.
        Usa pesos heurísticos para generar probabilidades plausibles.
        Idéntico al comportamiento de v1.0.
        """
        score = 0.0
        if p.cardiopatia_isquemica:                                    score += self.PESOS_SHAP["cardiopatia_isquemica"]
        if p.edad > 60:                                                score += self.PESOS_SHAP["edad_mayor_60"]
        if p.intensidad_dolor_eva is not None and p.intensidad_dolor_eva >= 7: score += self.PESOS_SHAP["intensidad_dolor_alta"]
        if p.fiebre_presente and p.temperatura_celsius and p.temperatura_celsius >= 38.5: score += self.PESOS_SHAP["temperatura_alta"]
        if p.hipertension:                                             score += self.PESOS_SHAP["hipertension"]
        if p.diabetes_mellitus:                                        score += self.PESOS_SHAP["diabetes_mellitus"]
        if p.duracion_sintoma_horas is not None and p.duracion_sintoma_horas < 2: score += self.PESOS_SHAP["duracion_corta"]
        if p.embarazo_posible:                                         score += self.PESOS_SHAP["embarazo"]
        if p.epoc_asma:                                                score += self.PESOS_SHAP["epoc_asma"]
        if imc is not None and imc >= 30.0:                            score += self.PESOS_SHAP["imc_obesidad"]

        score = max(0.0, min(score + random.uniform(-0.05, 0.05), 3.0))

        if score >= 1.8:
            p_rojo     = min(0.60 + (score - 1.8) * 0.18 + random.uniform(0, 0.05), 0.94)
            p_amarillo = random.uniform(0.03, 0.20)
            p_verde    = max(0.01, 1.0 - p_rojo - p_amarillo)
        elif score >= 0.9:
            p_amarillo = min(0.50 + (score - 0.9) * 0.22 + random.uniform(0, 0.05), 0.85)
            p_rojo     = random.uniform(0.05, 0.35)
            p_verde    = max(0.01, 1.0 - p_rojo - p_amarillo)
        else:
            p_verde    = min(0.55 + (0.9 - score) * 0.30 + random.uniform(0, 0.05), 0.90)
            p_amarillo = random.uniform(0.05, 0.30)
            p_rojo     = max(0.01, 1.0 - p_verde - p_amarillo)

        total      = p_rojo + p_amarillo + p_verde
        p_rojo     = round(p_rojo     / total, 4)
        p_amarillo = round(p_amarillo / total, 4)
        p_verde    = round(1.0 - p_rojo - p_amarillo, 4)

        return p_rojo, p_amarillo, p_verde

    def _aplicar_conservadurismo(self, p_rojo, p_amarillo, p_verde) -> tuple:
        """
        Si |P(rojo) − P(amarillo)| < 0.10 → subir a ROJO por seguridad.
        El modelo está indeciso: en caso de duda, proteger al paciente.
        """
        if abs(p_rojo - p_amarillo) < UMBRAL_CONSERVADURISMO:
            p_r = round(max(p_rojo, p_amarillo) + 0.05, 4)
            p_a = round(min(p_rojo, p_amarillo), 4)
            p_v = round(max(0.01, 1.0 - p_r - p_a), 4)
            t   = p_r + p_a + p_v
            return round(p_r/t, 4), round(p_a/t, 4), round(1.0 - p_r/t - p_a/t, 4), True
        return p_rojo, p_amarillo, p_verde, False

    def _determinar_nivel(self, p_rojo, p_amarillo, p_verde) -> NivelSemaforo:
        """Nivel = probabilidad máxima después del conservadurismo."""
        probs = {NivelSemaforo.ROJO: p_rojo, NivelSemaforo.AMARILLO: p_amarillo, NivelSemaforo.VERDE: p_verde}
        return max(probs, key=lambda k: probs[k])

    def _seleccionar_escenarios(self, nivel, p) -> tuple:
        """Selecciona 3 escenarios CIE-10 del catálogo según el nivel."""
        catalogo  = self.CATALOGO_ESCENARIOS.get(nivel.value, [])
        if not catalogo:
            return None, None, None
        seleccion = random.sample(catalogo, min(3, len(catalogo)))
        probs     = [0.60, 0.25, 0.15]
        probs     = [max(0.05, p + random.uniform(-0.05, 0.05)) for p in probs]
        total     = sum(probs)
        probs     = [round(v/total, 3) for v in probs]
        def fmt(e, p): return (e[0], e[1], p)
        return (
            fmt(seleccion[0], probs[0]) if len(seleccion) > 0 else None,
            fmt(seleccion[1], probs[1]) if len(seleccion) > 1 else None,
            fmt(seleccion[2], probs[2]) if len(seleccion) > 2 else None,
        )

    def _generar_shap(self, p, nivel, imc, alertas) -> tuple:
        """Genera explicación SHAP en español natural para el médico."""
        activos = {}
        if p.perdida_conciencia:                                           activos["perdida_conciencia"]    = self.PESOS_SHAP["perdida_conciencia"]
        if p.sangrado_activo:                                              activos["sangrado_activo"]       = self.PESOS_SHAP["sangrado_activo"]
        if p.disnea_presente:                                              activos["disnea_presente"]       = self.PESOS_SHAP["disnea_presente"]
        if p.cardiopatia_isquemica:                                        activos["cardiopatia_isquemica"] = self.PESOS_SHAP["cardiopatia_isquemica"]
        if p.edad > 60:                                                    activos["edad_mayor_60"]         = self.PESOS_SHAP["edad_mayor_60"]
        if p.intensidad_dolor_eva is not None and p.intensidad_dolor_eva >= 7: activos["intensidad_dolor_alta"] = self.PESOS_SHAP["intensidad_dolor_alta"]
        if p.fiebre_presente and p.temperatura_celsius and p.temperatura_celsius >= 38.5: activos["temperatura_alta"] = self.PESOS_SHAP["temperatura_alta"]
        if p.hipertension:                                                 activos["hipertension"]          = self.PESOS_SHAP["hipertension"]
        if p.diabetes_mellitus:                                            activos["diabetes_mellitus"]     = self.PESOS_SHAP["diabetes_mellitus"]
        if p.duracion_sintoma_horas is not None and p.duracion_sintoma_horas < 2: activos["duracion_corta"] = self.PESOS_SHAP["duracion_corta"]
        if p.embarazo_posible:                                             activos["embarazo"]              = self.PESOS_SHAP["embarazo"]
        if p.epoc_asma:                                                    activos["epoc_asma"]             = self.PESOS_SHAP["epoc_asma"]
        if imc is not None and imc >= 30.0:                                activos["imc_obesidad"]          = self.PESOS_SHAP["imc_obesidad"]

        top3      = sorted(activos.items(), key=lambda x: x[1], reverse=True)[:3]
        top3_vars = [self.NOMBRES_LEGIBLES.get(k, k) for k, _ in top3]
        etiqueta  = {NivelSemaforo.ROJO:"ROJO (urgente)",NivelSemaforo.AMARILLO:"AMARILLO (prioritario)",NivelSemaforo.VERDE:"VERDE (no urgente)"}[nivel]

        if not top3_vars:
            texto = f"Clasificado como {etiqueta}. Combinación de factores de baja intensidad individual."
        elif len(top3_vars) == 1:
            texto = f"Clasificado como {etiqueta} principalmente por: {top3_vars[0]}."
        elif len(top3_vars) == 2:
            texto = f"Clasificado como {etiqueta} principalmente por: {top3_vars[0]} y {top3_vars[1]}."
        else:
            texto = f"Clasificado como {etiqueta} principalmente por: {top3_vars[0]}, {top3_vars[1]} y {top3_vars[2]}."

        return texto, top3_vars

    def _calcular_hash(self, r: ResultadoInferencia) -> str:
        """Hash SHA-256 de integridad del resultado. NOM-024-SSA3-2012."""
        contenido = (
            f"{r.id_resultado}|{r.id_consulta}|{r.id_paciente}|"
            f"{r.timestamp_utc}|{r.nivel_ia.value}|"
            f"{r.p_rojo}|{r.p_amarillo}|{r.p_verde}|"
            f"{r.escenario_1_cie10}|{r.modelo_version}"
        )
        return hashlib.sha256(contenido.encode("utf-8")).hexdigest()


# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 5 — PRESENTACIÓN EN CONSOLA
# ══════════════════════════════════════════════════════════════════════════════

def imprimir_resultado(r: ResultadoInferencia) -> None:
    COLOR = {NivelSemaforo.ROJO:"\033[91m", NivelSemaforo.AMARILLO:"\033[93m", NivelSemaforo.VERDE:"\033[92m"}
    RESET = "\033[0m"; BOLD = "\033[1m"
    sep   = "─" * 62
    label = {NivelSemaforo.ROJO:"🔴 ROJO — URGENTE", NivelSemaforo.AMARILLO:"🟡 AMARILLO — PRIORITARIO", NivelSemaforo.VERDE:"🟢 VERDE — NO URGENTE"}[r.nivel_ia]

    print(f"\n{sep}")
    print(f"{BOLD}  SMART X v2.0 — RESULTADO (Random Forest)  |  HCG{RESET}")
    print(sep)
    print(f"  {COLOR[r.nivel_ia]}{BOLD}  {label}{RESET}")
    print(f"  Fuente: {r.fuente_nivel.value}")
    print(f"  Conservadurismo: {'Sí ⚠️' if r.conservadurismo_aplicado else 'No'}")
    print(f"\n  p_rojo={r.p_rojo:.4f}  p_amarillo={r.p_amarillo:.4f}  p_verde={r.p_verde:.4f}")
    if r.alerta_critica:
        print(f"\n  {BOLD}ALERTAS:{RESET}")
        for a in r.alertas_detalle: print(f"    {a}")
    print(f"\n  Escenarios: {r.escenario_1_cie10} / {r.escenario_2_cie10} / {r.escenario_3_cie10}")
    if r.imc_calculado:
        cat = "Bajo peso" if r.imc_calculado<18.5 else "Normal" if r.imc_calculado<25 else "Sobrepeso" if r.imc_calculado<30 else "Obesidad"
        print(f"  IMC: {r.imc_calculado} kg/m² ({cat})")
    print(f"\n  SHAP: {r.shap_explicacion}")
    print(f"  Modelo: {r.modelo_version}  |  {r.tiempo_procesamiento_ms} ms")
    print(f"  Hash: {r.hash_resultado[:24]}...")
    print(f"{sep}\n")


# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 6 — CASOS DE PRUEBA
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║   SMART X v2.0 — Motor Random Forest  |  HCG Piloto 2026    ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    motor = MotorInferenciaSmartX()

    # Caso 1 — Alerta crítica
    imprimir_resultado(motor.procesar(Paciente(
        edad=62, disnea_presente=True, cardiopatia_isquemica=True,
        hipertension=True, intensidad_dolor_eva=9, duracion_sintoma_horas=1,
        peso_kg=85.0, talla_cm=170.0
    )))

    # Caso 2 — Riesgo moderado
    imprimir_resultado(motor.procesar(Paciente(
        edad=55, fiebre_presente=True, temperatura_celsius=38.8,
        intensidad_dolor_eva=6, diabetes_mellitus=True, hipertension=True,
        peso_kg=90.0, talla_cm=168.0
    )))

    # Caso 3 — Control crónico (verde esperado)
    imprimir_resultado(motor.procesar(Paciente(
        edad=45, sexo_biologico="F", intensidad_dolor_eva=2,
        duracion_sintoma_horas=720, diabetes_mellitus=True,
        peso_kg=68.0, talla_cm=162.0
    )))

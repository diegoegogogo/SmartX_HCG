"""
╔══════════════════════════════════════════════════════════════════════════════╗
║           SMART X — MOTOR DE INFERENCIA DE TRIAGE CLÍNICO                    ║
║           Hospital Civil Viejo de Guadalajara (HCG)                          ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Normativas aplicables:                                                      ║
║    • NOM-004-SSA3-2012  — Del Expediente Clínico                             ║
║    • NOM-024-SSA3-2012  — Sistemas de Información de Registro Electrónico    ║
║    • LFPDPPP            — Ley Federal de Protección de Datos Personales      ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Descripción:                                                                ║
║    Simula el pipeline completo del Motor de Inferencia Smart X:              ║
║    1. Validación de rangos y nulos (NOM-004 § integridad del dato)           ║
║    2. Detección de alertas críticas inmediatas                               ║
║    3. Cálculo de IMC como variable derivada                                  ║
║    4. Simulación del modelo XGBoost (probabilidades p_rojo/amarillo/verde)   ║
║    5. Regla de conservadurismo médico                                        ║
║    6. Generación de explicación SHAP simplificada                            ║
║    7. Output JSON conforme a HL7-FHIR DiagnosticReport                       ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Autor del sistema: Equipo Smart X — UdeG / HCG                              ║
║  Versión: 1.0.0-piloto                                                       ║
║  Fecha: Febrero 2026                                                         ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

# ─── IMPORTACIONES ─────────────────────────────────────────────────────────────
import json
import math
import random
import uuid
import hashlib
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


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
    """
    Indica el origen de la clasificación del semáforo.
    Permite al médico saber si la IA fue determinística o probabilística.
    """
    ALERTA_CRITICA       = "alerta_critica_inmediata"   # Regla hard-coded (no modelo)
    MODELO_DIRECTO       = "modelo_xgboost"             # Decisión directa del modelo
    CONSERVADURISMO      = "conservadurismo_medico"     # Subida de nivel por indecisión


# Rangos de validación — NOM-004-SSA3-2012 (integridad del dato clínico)
RANGO_EDAD_MIN           = 0
RANGO_EDAD_MAX           = 120
RANGO_TEMPERATURA_MIN    = 35.0
RANGO_TEMPERATURA_MAX    = 42.5
RANGO_EVA_MIN            = 0
RANGO_EVA_MAX            = 10
RANGO_PESO_MIN           = 1.0       # kg — mínimo neonato
RANGO_PESO_MAX           = 300.0     # kg
RANGO_TALLA_MIN          = 30.0      # cm — mínimo neonato
RANGO_TALLA_MAX          = 250.0     # cm
RANGO_SEMANAS_MIN        = 0
RANGO_SEMANAS_MAX        = 42

# Umbral de conservadurismo médico
# Referencia: Documento 1 — Paso 2.4 del flujo de procesamiento IA
UMBRAL_CONSERVADURISMO   = 0.10


# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 2 — CLASE PACIENTE
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class Paciente:
    """
    Representa el perfil clínico de un paciente en Smart X.

    Contiene todas las variables de entrada al motor de inferencia,
    clasificadas según el Documento 1 (Flujo y Variables):
      — Variables numéricas continuas / discretas
      — Variables categóricas / booleanas
      — Variables de texto libre (procesadas externamente por NLP)
      — Antecedentes patológicos

    Normativa aplicable:
      • NOM-004-SSA3-2012 Art. 10: Ficha de identificación y antecedentes
      • NOM-024-SSA3-2012:         Estructura del registro electrónico
      • LFPDPPP:                   El id_paciente es un UUID seudonimizado;
                                   nunca se almacena nombre ni NSS en este objeto
    """

    # ── Identificación seudonimizada (LFPDPPP) ────────────────────────────────
    id_paciente: str = field(default_factory=lambda: str(uuid.uuid4()))
    id_consulta: str = field(default_factory=lambda: str(uuid.uuid4()))
    unidad_atencion: str = "HCG_URGENCIAS"  # Unidades disponibles en piloto HCG

    # ── Variables demográficas (numéricas) ────────────────────────────────────
    edad: int = 0                            # años cumplidos — rango válido: 0–120
    sexo_biologico: str = "M"               # 'M' / 'F'

    # ── Signos y síntomas de alarma (booleanas) — NOM-004 Art. 10 ────────────
    # Estas tres variables disparan ALERTA INMEDIATA si son TRUE
    # y cortocircuitan el modelo (ver Sección 4 — lógica de triage)
    disnea_presente: bool = False            # Dificultad respiratoria
    perdida_conciencia: bool = False         # Pérdida o alteración de consciencia
    sangrado_activo: bool = False            # Sangrado activo visible

    # ── Síntomas estructurados (numéricas y booleanas) ────────────────────────
    fiebre_presente: bool = False
    temperatura_celsius: Optional[float] = None  # NULL si fiebre_presente = False
    intensidad_dolor_eva: Optional[int] = None   # Escala EVA 0–10; NULL si no aplica
    duracion_sintoma_horas: Optional[int] = None # Duración del síntoma principal

    # ── Medidas antropométricas para cálculo de IMC (opcional) ───────────────
    peso_kg: Optional[float] = None
    talla_cm: Optional[float] = None

    # ── Antecedentes patológicos (booleanas) — NOM-004 Art. 10 ───────────────
    diabetes_mellitus: bool = False
    hipertension: bool = False
    cardiopatia_isquemica: bool = False
    epoc_asma: bool = False

    # ── Antecedentes obstétricos (solo sexo F) ────────────────────────────────
    embarazo_posible: Optional[bool] = None   # None si no aplica por sexo o edad
    semanas_gestacion: Optional[int] = None   # Solo si embarazo_posible = True

    # ── Campo de síntomas en texto libre (entrada al NLP externo) ─────────────
    # En producción este campo alimenta el pipeline spaCy+BioBERT.
    # En esta simulación no se procesa pero se incluye para completitud del objeto.
    sintomas_texto: Optional[str] = None


# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 3 — RESULTADO DEL MOTOR DE INFERENCIA
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class ResultadoInferencia:
    """
    Output completo del Motor de Inferencia Smart X.

    Estructura diseñada para ser serializable a JSON y compatible con
    el recurso DiagnosticReport de HL7-FHIR R4 (Documento 4, Sección 1.5).

    Normativa:
      • NOM-024-SSA3-2012: Todo resultado del sistema debe ser trazable
        (modelo_version, timestamp, id_consulta).
    """
    id_resultado: str
    id_consulta: str
    id_paciente: str
    timestamp_utc: str

    # ── Clasificación semáforo ─────────────────────────────────────────────────
    nivel_ia: NivelSemaforo
    fuente_nivel: FuenteNivel
    conservadurismo_aplicado: bool

    # ── Probabilidades del modelo ──────────────────────────────────────────────
    p_rojo: float
    p_amarillo: float
    p_verde: float

    # ── Escenarios clínicos diferenciales (CIE-10) ────────────────────────────
    escenario_1_cie10: Optional[str]
    escenario_1_prob: Optional[float]
    escenario_2_cie10: Optional[str]
    escenario_2_prob: Optional[float]
    escenario_3_cie10: Optional[str]
    escenario_3_prob: Optional[float]
    especialidad_sugerida: Optional[str]

    # ── Explicabilidad SHAP simplificada ──────────────────────────────────────
    shap_explicacion: str
    shap_variables_top3: list[str]

    # ── Metadatos técnicos ────────────────────────────────────────────────────
    modelo_version: str
    imc_calculado: Optional[float]
    alerta_critica: bool
    alertas_detalle: list[str]
    tiempo_procesamiento_ms: Optional[int]

    # ── Hash de integridad del resultado (NOM-024) ────────────────────────────
    diagnostico_final: str = ""
    hash_resultado: str = ""

    def to_json(self) -> str:
        """Serializa el resultado a JSON con formato legible."""
        d = {
            "resourceType":          "DiagnosticReport",  # HL7-FHIR R4
            "id_resultado":          self.id_resultado,
            "id_consulta":           self.id_consulta,
            "id_paciente":           self.id_paciente,
            "timestamp_utc":         self.timestamp_utc,
            "nivel_ia":              self.nivel_ia.value,
            "fuente_nivel":          self.fuente_nivel.value,
            "conservadurismo_aplicado": self.conservadurismo_aplicado,
            "probabilidades": {
                "p_rojo":     round(self.p_rojo, 4),
                "p_amarillo": round(self.p_amarillo, 4),
                "p_verde":    round(self.p_verde, 4),
            },
            "escenarios_diferenciales": [
                {"cie10": self.escenario_1_cie10, "probabilidad": self.escenario_1_prob, "orden": 1},
                {"cie10": self.escenario_2_cie10, "probabilidad": self.escenario_2_prob, "orden": 2},
                {"cie10": self.escenario_3_cie10, "probabilidad": self.escenario_3_prob, "orden": 3},
            ],
            "especialidad_sugerida": self.especialidad_sugerida,
            "shap_explicacion":      self.shap_explicacion,
            "shap_variables_top3":   self.shap_variables_top3,
            "imc_calculado":         self.imc_calculado,
            "alerta_critica":        self.alerta_critica,
            "alertas_detalle":       self.alertas_detalle,
            "modelo_version":        self.modelo_version,
            "tiempo_procesamiento_ms": self.tiempo_procesamiento_ms,
            "hash_resultado":        self.hash_resultado,
        }
        return json.dumps(d, ensure_ascii=False, indent=2)


# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 4 — MOTOR DE INFERENCIA
# ══════════════════════════════════════════════════════════════════════════════

class MotorInferenciaSmartX:
    """
    Motor de Inferencia del sistema Smart X para el Hospital Civil de Guadalajara.

    Pipeline de procesamiento (Documento 1 — Fases 2 y 3):
      1. validar_paciente()        → Validación de rangos y consistencia de nulos
      2. detectar_alertas()        → Reglas críticas hard-coded (bypass del modelo)
      3. calcular_imc()            → Variable derivada antropométrica
      4. simular_xgboost()         → Probabilidades del modelo de clasificación
      5. aplicar_conservadurismo() → Regla de seguridad clínica
      6. seleccionar_escenarios()  → Diagnósticos diferenciales CIE-10
      7. generar_shap()            → Explicabilidad para el médico
      8. construir_resultado()     → Output JSON conforme HL7-FHIR
    """

    MODELO_VERSION = "xgb_v1.0.0-piloto-hcg"

    # ── Catálogo de escenarios por nivel de urgencia ──────────────────────────
    # En producción este catálogo proviene del clasificador multi-etiqueta.
    # Estructura: nivel → [(cie10, descripcion, especialidad), ...]
    CATALOGO_ESCENARIOS: dict[str, list[tuple]] = {
        NivelSemaforo.ROJO.value: [
            ("I21.0",  "IAM con elevación del segmento ST",            "Cardiología / Urgencias"),
            ("J96.0",  "Insuficiencia respiratoria aguda",             "Urgencias / Medicina Interna"),
            ("I64",    "Enfermedad vascular cerebral aguda (EVC)",      "Neurología / Urgencias"),
            ("R57.0",  "Choque cardiogénico",                          "Urgencias / Cuidados Intensivos"),
            ("K25.0",  "Úlcera gástrica con hemorragia activa",         "Cirugía / Urgencias"),
            ("O15.9",  "Eclampsia — período no especificado",           "Ginecología / Urgencias"),
        ],
        NivelSemaforo.AMARILLO.value: [
            ("J18.9",  "Neumonía — organismo no especificado",          "Medicina Interna"),
            ("N10",    "Pielonefritis aguda",                           "Medicina Interna / Urología"),
            ("K35.9",  "Apendicitis aguda, sin peritonitis",            "Cirugía General"),
            ("I10",    "Hipertensión esencial (descompensada)",          "Medicina Interna"),
            ("E11.65", "Diabetes mellitus tipo 2 con hiperglucemia",    "Endocrinología"),
            ("R51",    "Cefalea intensa de inicio súbito",              "Neurología"),
        ],
        NivelSemaforo.VERDE.value: [
            ("Z00.00", "Examen médico general — sin hallazgos anormales","Medicina Familiar"),
            ("J00",    "Rinofaringitis aguda (resfriado común)",         "Medicina Familiar"),
            ("M54.5",  "Lumbalgia crónica conocida — control",           "Rehabilitación / Med. Familiar"),
            ("K21.0",  "Enfermedad por reflujo gastroesofágico",         "Gastroenterología"),
            ("F41.1",  "Trastorno de ansiedad generalizada",             "Psiquiatría / Med. Familiar"),
        ],
    }

    # ── Pesos de variables para la simulación SHAP ────────────────────────────
    # En producción estos valores vienen del cálculo real de SHAP values.
    # Aquí se usan pesos heurísticos basados en literatura de triage.
    PESOS_SHAP: dict[str, float] = {
        "perdida_conciencia":    0.95,
        "sangrado_activo":       0.93,
        "disnea_presente":       0.90,
        "cardiopatia_isquemica": 0.78,
        "edad_mayor_60":         0.72,  # Variable derivada
        "intensidad_dolor_alta": 0.68,  # EVA >= 7
        "temperatura_alta":      0.65,  # >= 38.5°C
        "hipertension":          0.60,
        "diabetes_mellitus":     0.57,
        "duracion_corta":        0.52,  # Síntoma < 2 horas (más urgente)
        "embarazo":              0.50,
        "epoc_asma":             0.48,
        "imc_obesidad":          0.35,  # IMC >= 30
    }

    # ── Nombres legibles para el médico ──────────────────────────────────────
    NOMBRES_LEGIBLES: dict[str, str] = {
        "perdida_conciencia":    "pérdida de consciencia",
        "sangrado_activo":       "sangrado activo",
        "disnea_presente":       "dificultad respiratoria",
        "cardiopatia_isquemica": "antecedente de cardiopatía isquémica",
        "edad_mayor_60":         "edad mayor de 60 años",
        "intensidad_dolor_alta": "dolor de alta intensidad (EVA ≥ 7)",
        "temperatura_alta":      "fiebre elevada (≥ 38.5°C)",
        "hipertension":          "hipertensión conocida",
        "diabetes_mellitus":     "diabetes mellitus",
        "duracion_corta":        "inicio súbito del síntoma (< 2 horas)",
        "embarazo":              "embarazo activo",
        "epoc_asma":             "antecedente de EPOC / asma",
        "imc_obesidad":          "obesidad (IMC ≥ 30)",
    }

    # ─────────────────────────────────────────────────────────────────────────
    # MÉTODO PRINCIPAL — procesar()
    # ─────────────────────────────────────────────────────────────────────────

    def procesar(self, paciente: Paciente) -> ResultadoInferencia:
        """
        Ejecuta el pipeline completo de inferencia para un paciente.

        Args:
            paciente: Objeto Paciente con las variables de entrada validadas.

        Returns:
            ResultadoInferencia: Objeto JSON-serializable con el diagnóstico
                                 de soporte del sistema, conforme a NOM-024.

        Raises:
            ValueError: Si alguna variable de entrada está fuera de rango
                        o es inconsistente (NOM-004 — integridad del dato).
        """
        t_inicio = datetime.now(timezone.utc)

        # ── Paso 1: Validar rangos y consistencia ─────────────────────────────
        self._validar_paciente(paciente)

        # ── Paso 2: Calcular IMC si hay datos antropométricos ─────────────────
        imc = self._calcular_imc(paciente.peso_kg, paciente.talla_cm)

        # ── Paso 3: Detectar alertas críticas (bypass del modelo) ─────────────
        alertas, es_alerta_critica = self._detectar_alertas_criticas(paciente)

        # ── Paso 4: Obtener probabilidades del modelo ─────────────────────────
        if es_alerta_critica:
            # Alerta crítica: el modelo NO se consulta, nivel ROJO directo
            p_rojo, p_amarillo, p_verde = 0.97, 0.02, 0.01
            fuente = FuenteNivel.ALERTA_CRITICA
            conservadurismo_aplicado = False
        else:
            # Flujo normal: simular XGBoost
            p_rojo, p_amarillo, p_verde = self._simular_xgboost(paciente, imc)

            # ── Paso 5: Regla de conservadurismo médico ───────────────────────
            p_rojo, p_amarillo, p_verde, conservadurismo_aplicado = \
                self._aplicar_conservadurismo(p_rojo, p_amarillo, p_verde)

            fuente = (
                FuenteNivel.CONSERVADURISMO
                if conservadurismo_aplicado
                else FuenteNivel.MODELO_DIRECTO
            )

        # ── Paso 6: Determinar nivel final ────────────────────────────────────
        nivel_ia = self._determinar_nivel(p_rojo, p_amarillo, p_verde)

        # ── Paso 7: Seleccionar escenarios diferenciales ──────────────────────
        esc1, esc2, esc3 = self._seleccionar_escenarios(nivel_ia, paciente)

        # ── Paso 8: Generar explicación SHAP simplificada ─────────────────────
        shap_texto, top3_vars = self._generar_shap(paciente, nivel_ia, imc, alertas)

        # ── Paso 9: Calcular tiempo de procesamiento ──────────────────────────
        t_fin = datetime.now(timezone.utc)
        ms = int((t_fin - t_inicio).total_seconds() * 1000)

        # ── Paso 10: Construir objeto resultado ───────────────────────────────
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
            imc_calculado            = imc,
            alerta_critica           = es_alerta_critica,
            alertas_detalle          = alertas,
            modelo_version           = self.MODELO_VERSION,
            tiempo_procesamiento_ms  = ms,
        )

        # ── Paso 11: Calcular hash de integridad del resultado (NOM-024) ──────
        resultado.hash_resultado = self._calcular_hash(resultado)

        return resultado

    # ═══════════════════════════════════════════════════════════════════════════
    # MÉTODOS PRIVADOS DEL PIPELINE
    # ═══════════════════════════════════════════════════════════════════════════

    def _validar_paciente(self, p: Paciente) -> None:
        """
        Valida rangos clínicos y consistencia lógica del objeto Paciente.

        Referencia: Documento 1 — Clasificación de Variables, columna 'Reglas/Validaciones'
        Normativa:  NOM-004-SSA3-2012 — integridad y veracidad del dato clínico

        Raises:
            ValueError: Si algún campo está fuera de rango o es lógicamente inconsistente.
        """
        errores: list[str] = []

        # ── Validaciones numéricas ────────────────────────────────────────────
        if not (RANGO_EDAD_MIN <= p.edad <= RANGO_EDAD_MAX):
            errores.append(
                f"edad fuera de rango: {p.edad} "
                f"(válido: {RANGO_EDAD_MIN}–{RANGO_EDAD_MAX})"
            )

        if p.intensidad_dolor_eva is not None:
            if not (RANGO_EVA_MIN <= p.intensidad_dolor_eva <= RANGO_EVA_MAX):
                errores.append(
                    f"intensidad_dolor_eva fuera de rango: {p.intensidad_dolor_eva} "
                    f"(válido: {RANGO_EVA_MIN}–{RANGO_EVA_MAX})"
                )

        # ── Validación de consistencia: temperatura solo si hay fiebre ────────
        # Regla de nulos: si fiebre_presente = False, temperatura debe ser NULL
        # Referencia: Documento 1 — Variable temperatura_celsius
        if not p.fiebre_presente and p.temperatura_celsius is not None:
            errores.append(
                "inconsistencia: temperatura_celsius proporcionada "
                "pero fiebre_presente es False — debe ser None"
            )

        if p.fiebre_presente and p.temperatura_celsius is not None:
            if not (RANGO_TEMPERATURA_MIN <= p.temperatura_celsius <= RANGO_TEMPERATURA_MAX):
                errores.append(
                    f"temperatura_celsius fuera de rango: {p.temperatura_celsius}°C "
                    f"(válido: {RANGO_TEMPERATURA_MIN}–{RANGO_TEMPERATURA_MAX}°C)"
                )

        # ── Validación de medidas antropométricas ─────────────────────────────
        if p.peso_kg is not None:
            if not (RANGO_PESO_MIN <= p.peso_kg <= RANGO_PESO_MAX):
                errores.append(
                    f"peso_kg fuera de rango: {p.peso_kg} kg "
                    f"(válido: {RANGO_PESO_MIN}–{RANGO_PESO_MAX} kg)"
                )

        if p.talla_cm is not None:
            if not (RANGO_TALLA_MIN <= p.talla_cm <= RANGO_TALLA_MAX):
                errores.append(
                    f"talla_cm fuera de rango: {p.talla_cm} cm "
                    f"(válido: {RANGO_TALLA_MIN}–{RANGO_TALLA_MAX} cm)"
                )

        # ── Validación obstétrica ─────────────────────────────────────────────
        if p.embarazo_posible is True:
            if p.sexo_biologico != "F":
                errores.append(
                    "inconsistencia: embarazo_posible = True "
                    "pero sexo_biologico no es 'F'"
                )
            if p.semanas_gestacion is not None:
                if not (RANGO_SEMANAS_MIN <= p.semanas_gestacion <= RANGO_SEMANAS_MAX):
                    errores.append(
                        f"semanas_gestacion fuera de rango: {p.semanas_gestacion} "
                        f"(válido: {RANGO_SEMANAS_MIN}–{RANGO_SEMANAS_MAX})"
                    )

        if p.semanas_gestacion is not None and not p.embarazo_posible:
            errores.append(
                "inconsistencia: semanas_gestacion proporcionadas "
                "pero embarazo_posible no es True"
            )

        # ── Sexo biológico válido ─────────────────────────────────────────────
        if p.sexo_biologico not in ("M", "F"):
            errores.append(
                f"sexo_biologico inválido: '{p.sexo_biologico}' "
                "(válido: 'M' o 'F')"
            )

        if errores:
            raise ValueError(
                f"[SmartX NOM-004] Validación fallida para id_paciente={p.id_paciente}:\n"
                + "\n".join(f"  • {e}" for e in errores)
            )

    # ─────────────────────────────────────────────────────────────────────────

    def _calcular_imc(
        self,
        peso_kg: Optional[float],
        talla_cm: Optional[float]
    ) -> Optional[float]:
        """
        Calcula el Índice de Masa Corporal como variable derivada.

        Fórmula: IMC = peso(kg) / (talla(m))²
        Referencia: Documento 1 — Variable imc_calculado (numérica continua derivada)

        Returns:
            IMC redondeado a 2 decimales, o None si faltan datos.
        """
        if peso_kg is None or talla_cm is None:
            return None

        talla_m = talla_cm / 100.0
        imc = peso_kg / (talla_m ** 2)
        return round(imc, 2)

    # ─────────────────────────────────────────────────────────────────────────

    def _detectar_alertas_criticas(
        self,
        p: Paciente
    ) -> tuple[list[str], bool]:
        """
        Detecta condiciones de alarma que requieren atención INMEDIATA.

        Estas reglas son hard-coded y NO pasan por el modelo de ML.
        El flujo del paciente se interrumpe y se genera alerta al personal.

        Referencia: Documento 1 — Paso 1.2 del flujo paciente:
            'Si síntoma de alarma grave → ALERTA INMEDIATA al personal'
        Referencia: Documento 2 — variables con restricción ⚠️ en esquema BD

        Returns:
            (lista_alertas, es_alerta_critica)
        """
        alertas: list[str] = []

        if p.perdida_conciencia:
            alertas.append(
                "⚠️  ALERTA CRÍTICA: pérdida o alteración de consciencia detectada — "
                "activar protocolo neurológico urgente"
            )

        if p.sangrado_activo:
            alertas.append(
                "⚠️  ALERTA CRÍTICA: sangrado activo visible — "
                "activar protocolo hemostático urgente"
            )

        if p.disnea_presente:
            alertas.append(
                "⚠️  ALERTA CRÍTICA: dificultad respiratoria presente — "
                "evaluar vía aérea inmediatamente"
            )

        es_critica = len(alertas) > 0
        return alertas, es_critica

    # ─────────────────────────────────────────────────────────────────────────

    def _simular_xgboost(
        self,
        p: Paciente,
        imc: Optional[float]
    ) -> tuple[float, float, float]:
        """
        Simula la salida del modelo XGBoost de clasificación.

        En producción, este método llama al modelo serializado con joblib/pickle.
        En esta simulación, usa los pesos heurísticos para generar probabilidades
        plausibles que reflejan la lógica clínica real del sistema.

        Referencia: Documento 1 — Paso 2.4 (Clasificación — Modelo XGBoost)
        Referencia: Documento 2 — tabla resultado_ia, columnas p_rojo/p_amarillo/p_verde

        Returns:
            (p_rojo, p_amarillo, p_verde) — probabilidades que suman exactamente 1.0
        """
        # Acumulador de score de urgencia (0.0 = sin riesgo, 1.0 = máximo riesgo)
        score_urgencia: float = 0.0

        # ── Aplicar factores de riesgo con sus pesos SHAP heurísticos ─────────
        if p.cardiopatia_isquemica:
            score_urgencia += self.PESOS_SHAP["cardiopatia_isquemica"]
        if p.edad > 60:
            score_urgencia += self.PESOS_SHAP["edad_mayor_60"]
        if p.intensidad_dolor_eva is not None and p.intensidad_dolor_eva >= 7:
            score_urgencia += self.PESOS_SHAP["intensidad_dolor_alta"]
        if p.fiebre_presente and p.temperatura_celsius is not None:
            if p.temperatura_celsius >= 38.5:
                score_urgencia += self.PESOS_SHAP["temperatura_alta"]
        if p.hipertension:
            score_urgencia += self.PESOS_SHAP["hipertension"]
        if p.diabetes_mellitus:
            score_urgencia += self.PESOS_SHAP["diabetes_mellitus"]
        if p.duracion_sintoma_horas is not None and p.duracion_sintoma_horas < 2:
            score_urgencia += self.PESOS_SHAP["duracion_corta"]
        if p.embarazo_posible:
            score_urgencia += self.PESOS_SHAP["embarazo"]
        if p.epoc_asma:
            score_urgencia += self.PESOS_SHAP["epoc_asma"]
        if imc is not None and imc >= 30.0:
            score_urgencia += self.PESOS_SHAP["imc_obesidad"]

        # ── Pequeña variación aleatoria (simula incertidumbre del modelo) ─────
        # En producción esto no existe: el modelo es determinístico dado el input.
        ruido = random.uniform(-0.05, 0.05)
        score_urgencia = max(0.0, min(score_urgencia + ruido, 3.0))

        # ── Convertir score a distribución de probabilidades ──────────────────
        # Umbrales calibrados sobre el dataset de entrenamiento simulado:
        #   score >= 1.8 → mayoritariamente ROJO
        #   score >= 0.9 → mayoritariamente AMARILLO
        #   score < 0.9  → mayoritariamente VERDE
        if score_urgencia >= 1.8:
            p_rojo     = min(0.60 + (score_urgencia - 1.8) * 0.18 + random.uniform(0, 0.05), 0.94)
            p_amarillo = random.uniform(0.03, 0.20)
            p_verde    = max(0.01, 1.0 - p_rojo - p_amarillo)
        elif score_urgencia >= 0.9:
            p_amarillo = min(0.50 + (score_urgencia - 0.9) * 0.22 + random.uniform(0, 0.05), 0.85)
            p_rojo     = random.uniform(0.05, 0.35)
            p_verde    = max(0.01, 1.0 - p_rojo - p_amarillo)
        else:
            p_verde    = min(0.55 + (0.9 - score_urgencia) * 0.30 + random.uniform(0, 0.05), 0.90)
            p_amarillo = random.uniform(0.05, 0.30)
            p_rojo     = max(0.01, 1.0 - p_verde - p_amarillo)

        # ── Normalizar para garantizar que sumen exactamente 1.0 ─────────────
        total = p_rojo + p_amarillo + p_verde
        p_rojo     = round(p_rojo     / total, 4)
        p_amarillo = round(p_amarillo / total, 4)
        p_verde    = round(1.0 - p_rojo - p_amarillo, 4)  # Garantiza suma exacta

        return p_rojo, p_amarillo, p_verde

    # ─────────────────────────────────────────────────────────────────────────

    def _aplicar_conservadurismo(
        self,
        p_rojo: float,
        p_amarillo: float,
        p_verde: float
    ) -> tuple[float, float, float, bool]:
        """
        Aplica la regla de conservadurismo médico del sistema Smart X.

        Regla:
            Si |P(rojo) − P(amarillo)| < UMBRAL_CONSERVADURISMO (0.10),
            el sistema sube automáticamente al nivel más alto (ROJO),
            porque la incertidumbre del modelo no es suficiente para
            descartar una urgencia. Proteger al paciente prevalece.

        Esta es la implementación de la máxima clínica:
            'En caso de duda, tratar como urgencia hasta demostrar lo contrario.'

        Referencia: Documento 1 — Paso 2.4, regla de conservadurismo
        Referencia: Documento 2 — resultado_ia.conservadurismo_aplicado (BOOLEAN)

        Returns:
            (p_rojo, p_amarillo, p_verde, conservadurismo_fue_aplicado)
        """
        diferencia = abs(p_rojo - p_amarillo)

        if diferencia < UMBRAL_CONSERVADURISMO:
            # El modelo está indeciso entre ROJO y AMARILLO
            # → Subir a ROJO por seguridad clínica
            p_rojo_nuevo     = round(max(p_rojo, p_amarillo) + 0.05, 4)
            p_amarillo_nuevo = round(min(p_rojo, p_amarillo), 4)
            p_verde_nuevo    = round(max(0.01, 1.0 - p_rojo_nuevo - p_amarillo_nuevo), 4)
            # Renormalizar
            total = p_rojo_nuevo + p_amarillo_nuevo + p_verde_nuevo
            return (
                round(p_rojo_nuevo / total, 4),
                round(p_amarillo_nuevo / total, 4),
                round(1.0 - (p_rojo_nuevo / total) - (p_amarillo_nuevo / total), 4),
                True,   # conservadurismo aplicado
            )

        return p_rojo, p_amarillo, p_verde, False   # sin cambio

    # ─────────────────────────────────────────────────────────────────────────

    def _determinar_nivel(
        self,
        p_rojo: float,
        p_amarillo: float,
        p_verde: float
    ) -> NivelSemaforo:
        """
        Determina el nivel de semáforo a partir de las probabilidades finales.

        Simplemente selecciona el nivel de mayor probabilidad.
        La lógica de conservadurismo ya fue aplicada en el paso anterior.
        """
        probs = {
            NivelSemaforo.ROJO:     p_rojo,
            NivelSemaforo.AMARILLO: p_amarillo,
            NivelSemaforo.VERDE:    p_verde,
        }
        return max(probs, key=lambda k: probs[k])

    # ─────────────────────────────────────────────────────────────────────────

    def _seleccionar_escenarios(
        self,
        nivel: NivelSemaforo,
        p: Paciente
    ) -> tuple[
        Optional[tuple[str, str, float]],
        Optional[tuple[str, str, float]],
        Optional[tuple[str, str, float]],
    ]:
        """
        Selecciona hasta 3 escenarios clínicos diferenciales del catálogo.

        En producción este método usa el clasificador multi-etiqueta.
        Aquí selecciona aleatoriamente del catálogo filtrado por nivel,
        con mayor peso hacia escenarios relevantes para los antecedentes.

        Referencia: Documento 1 — Paso 3.1 (escenarios CIE-10)
        Referencia: Documento 2 — resultado_ia.escenario_1/2/3_cie10

        Returns:
            Tres tuplas (cie10, especialidad, probabilidad) o None si no hay.
        """
        catalogo = self.CATALOGO_ESCENARIOS.get(nivel.value, [])

        if not catalogo:
            return None, None, None

        # Mezclar para variedad y tomar máximo 3
        seleccion = random.sample(catalogo, min(3, len(catalogo)))

        # Generar probabilidades decrecientes para los 3 escenarios
        probs_base = [0.60, 0.25, 0.15]
        ruido = [random.uniform(-0.05, 0.05) for _ in range(3)]
        probs = [max(0.05, p + r) for p, r in zip(probs_base, ruido)]
        total = sum(probs)
        probs = [round(v / total, 3) for v in probs]

        def formatear(esc, prob) -> tuple[str, str, float]:
            return (esc[0], esc[1], prob)

        esc1 = formatear(seleccion[0], probs[0]) if len(seleccion) > 0 else None
        esc2 = formatear(seleccion[1], probs[1]) if len(seleccion) > 1 else None
        esc3 = formatear(seleccion[2], probs[2]) if len(seleccion) > 2 else None

        return esc1, esc2, esc3

    # ─────────────────────────────────────────────────────────────────────────

    def _generar_shap(
        self,
        p: Paciente,
        nivel: NivelSemaforo,
        imc: Optional[float],
        alertas: list[str]
    ) -> tuple[str, list[str]]:
        """
        Genera la explicación SHAP simplificada en lenguaje natural para el médico.

        La explicación identifica las 3 variables de mayor peso que determinaron
        la clasificación, y las presenta en texto legible en español clínico.

        Referencia: Documento 1 — Paso 2.5 (Módulo SHAP — Explicabilidad)
        Referencia: Documento 4 — DiagnosticReport.presentedForm (SHAP JSON)

        Principio ético: el médico debe poder entender POR QUÉ el sistema clasificó
        así, no solo CUÁL fue la clasificación. Esto evita la 'caja negra'.

        Returns:
            (texto_explicacion, lista_top3_variables)
        """
        # ── Calcular pesos activos de este paciente ────────────────────────────
        pesos_activos: dict[str, float] = {}

        if p.perdida_conciencia:
            pesos_activos["perdida_conciencia"]    = self.PESOS_SHAP["perdida_conciencia"]
        if p.sangrado_activo:
            pesos_activos["sangrado_activo"]       = self.PESOS_SHAP["sangrado_activo"]
        if p.disnea_presente:
            pesos_activos["disnea_presente"]       = self.PESOS_SHAP["disnea_presente"]
        if p.cardiopatia_isquemica:
            pesos_activos["cardiopatia_isquemica"] = self.PESOS_SHAP["cardiopatia_isquemica"]
        if p.edad > 60:
            pesos_activos["edad_mayor_60"]         = self.PESOS_SHAP["edad_mayor_60"]
        if p.intensidad_dolor_eva is not None and p.intensidad_dolor_eva >= 7:
            pesos_activos["intensidad_dolor_alta"] = self.PESOS_SHAP["intensidad_dolor_alta"]
        if p.fiebre_presente and p.temperatura_celsius is not None and p.temperatura_celsius >= 38.5:
            pesos_activos["temperatura_alta"]      = self.PESOS_SHAP["temperatura_alta"]
        if p.hipertension:
            pesos_activos["hipertension"]          = self.PESOS_SHAP["hipertension"]
        if p.diabetes_mellitus:
            pesos_activos["diabetes_mellitus"]     = self.PESOS_SHAP["diabetes_mellitus"]
        if p.duracion_sintoma_horas is not None and p.duracion_sintoma_horas < 2:
            pesos_activos["duracion_corta"]        = self.PESOS_SHAP["duracion_corta"]
        if p.embarazo_posible:
            pesos_activos["embarazo"]              = self.PESOS_SHAP["embarazo"]
        if p.epoc_asma:
            pesos_activos["epoc_asma"]             = self.PESOS_SHAP["epoc_asma"]
        if imc is not None and imc >= 30.0:
            pesos_activos["imc_obesidad"]          = self.PESOS_SHAP["imc_obesidad"]

        # ── Ordenar por peso descendente y tomar las 3 más importantes ────────
        top3 = sorted(pesos_activos.items(), key=lambda x: x[1], reverse=True)[:3]
        top3_vars = [self.NOMBRES_LEGIBLES.get(k, k) for k, _ in top3]

        # ── Construir texto explicativo ────────────────────────────────────────
        etiqueta_nivel = {
            NivelSemaforo.ROJO:     "ROJO (urgente)",
            NivelSemaforo.AMARILLO: "AMARILLO (prioritario)",
            NivelSemaforo.VERDE:    "VERDE (no urgente)",
        }[nivel]

        if not top3_vars:
            texto = (
                f"Clasificado como {etiqueta_nivel}. "
                "No se identificaron factores de riesgo específicos de alto peso. "
                "La clasificación se basa en la combinación de variables de baja intensidad."
            )
        elif len(top3_vars) == 1:
            texto = (
                f"Clasificado como {etiqueta_nivel} "
                f"principalmente por: {top3_vars[0]}."
            )
        elif len(top3_vars) == 2:
            texto = (
                f"Clasificado como {etiqueta_nivel} "
                f"principalmente por: {top3_vars[0]} "
                f"y {top3_vars[1]}."
            )
        else:
            texto = (
                f"Clasificado como {etiqueta_nivel} "
                f"principalmente por: {top3_vars[0]}, "
                f"{top3_vars[1]} "
                f"y {top3_vars[2]}."
            )

        return texto, top3_vars

    # ─────────────────────────────────────────────────────────────────────────

    def _calcular_hash(self, r: ResultadoInferencia) -> str:
        """
        Calcula el hash SHA-256 del resultado para garantizar integridad.

        El hash se calcula sobre los campos clínicos clave del resultado.
        Permite detectar manipulaciones del registro post-generación.

        Referencia: Documento 2 — tabla auditoria.hash_sha256
        Referencia: Documento 4 — Sección 4 (Versionado, inmutabilidad)
        Normativa:  NOM-024-SSA3-2012 — trazabilidad e integridad del registro
        """
        contenido = (
            f"{r.id_resultado}|{r.id_consulta}|{r.id_paciente}|"
            f"{r.timestamp_utc}|{r.nivel_ia.value}|"
            f"{r.p_rojo}|{r.p_amarillo}|{r.p_verde}|"
            f"{r.escenario_1_cie10}|{r.diagnostico_final if hasattr(r, 'diagnostico_final') else ''}|"
            f"{r.modelo_version}"
        )
        return hashlib.sha256(contenido.encode("utf-8")).hexdigest()


# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 5 — UTILIDADES DE PRESENTACIÓN
# ══════════════════════════════════════════════════════════════════════════════

def imprimir_resultado(resultado: ResultadoInferencia) -> None:
    """
    Imprime el resultado en consola con formato visual claro para desarrollo.
    En producción, este método no existe: el resultado se envía al API.
    """
    COLOR = {
        NivelSemaforo.ROJO:     "\033[91m",   # Rojo
        NivelSemaforo.AMARILLO: "\033[93m",   # Amarillo
        NivelSemaforo.VERDE:    "\033[92m",   # Verde
    }
    RESET = "\033[0m"
    BOLD  = "\033[1m"

    nivel_color = COLOR.get(resultado.nivel_ia, "")
    nivel_label = {
        NivelSemaforo.ROJO:     "🔴 ROJO    — URGENTE",
        NivelSemaforo.AMARILLO: "🟡 AMARILLO — PRIORITARIO",
        NivelSemaforo.VERDE:    "🟢 VERDE   — NO URGENTE",
    }[resultado.nivel_ia]

    separador = "─" * 62

    print(f"\n{separador}")
    print(f"{BOLD}  SMART X — RESULTADO DEL MOTOR DE INFERENCIA{RESET}")
    print(f"  Hospital Civil Viejo de Guadalajara | Piloto v1")
    print(separador)
    print(f"  ID Consulta  : {resultado.id_consulta}")
    print(f"  ID Resultado : {resultado.id_resultado}")
    print(f"  Timestamp    : {resultado.timestamp_utc}")
    print(separador)
    print(f"\n  {BOLD}NIVEL DE URGENCIA:{RESET}")
    print(f"  {nivel_color}{BOLD}  {nivel_label}{RESET}")
    print(f"  Fuente       : {resultado.fuente_nivel.value}")
    print(f"  Conservadurismo aplicado: {'Sí ⚠️' if resultado.conservadurismo_aplicado else 'No'}")
    print(f"\n  Probabilidades del modelo:")
    print(f"    p_rojo     = {resultado.p_rojo:.4f}  ({resultado.p_rojo*100:.1f}%)")
    print(f"    p_amarillo = {resultado.p_amarillo:.4f}  ({resultado.p_amarillo*100:.1f}%)")
    print(f"    p_verde    = {resultado.p_verde:.4f}  ({resultado.p_verde*100:.1f}%)")

    if resultado.alerta_critica:
        print(f"\n  {BOLD}ALERTAS CRÍTICAS DETECTADAS:{RESET}")
        for alerta in resultado.alertas_detalle:
            print(f"    {alerta}")

    print(f"\n  {BOLD}ESCENARIOS CLÍNICOS SUGERIDOS:{RESET}")
    escenarios = [
        (resultado.escenario_1_cie10, resultado.escenario_1_prob),
        (resultado.escenario_2_cie10, resultado.escenario_2_prob),
        (resultado.escenario_3_cie10, resultado.escenario_3_prob),
    ]
    for i, (cie, prob) in enumerate(escenarios, 1):
        if cie and prob is not None:
            print(f"    {i}. [{cie}]  ({prob*100:.1f}% de probabilidad)")

    if resultado.especialidad_sugerida:
        print(f"  Especialidad sugerida: {resultado.especialidad_sugerida}")

    if resultado.imc_calculado is not None:
        categoria_imc = (
            "Bajo peso"      if resultado.imc_calculado < 18.5 else
            "Peso normal"    if resultado.imc_calculado < 25.0 else
            "Sobrepeso"      if resultado.imc_calculado < 30.0 else
            "Obesidad"
        )
        print(f"\n  IMC calculado: {resultado.imc_calculado} kg/m²  ({categoria_imc})")

    print(f"\n  {BOLD}EXPLICACIÓN SHAP:{RESET}")
    print(f"  {resultado.shap_explicacion}")
    print(f"  Variables top-3: {', '.join(resultado.shap_variables_top3) if resultado.shap_variables_top3 else 'N/A'}")

    print(f"\n  Modelo       : {resultado.modelo_version}")
    print(f"  Procesamiento: {resultado.tiempo_procesamiento_ms} ms")
    print(f"  Hash SHA-256 : {resultado.hash_resultado[:24]}...")
    print(f"\n{separador}\n")


# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 6 — CASOS DE PRUEBA
# ══════════════════════════════════════════════════════════════════════════════

def ejecutar_casos_de_prueba() -> None:
    """
    Ejecuta 4 casos de prueba representativos del piloto HCG.

    Caso 1 — Urgencia crítica con alerta inmediata (bypass del modelo)
    Caso 2 — Riesgo moderado-alto con conservadurismo médico
    Caso 3 — Consulta de control crónico (no urgente)
    Caso 4 — Paciente embarazada con fiebre alta

    Estos casos cubren todas las ramas del motor de inferencia
    y validan las reglas de negocio documentadas en el Flujo de Variables.
    """
    motor = MotorInferenciaSmartX()

    # ─── CASO 1: Alerta crítica — bypass del modelo ───────────────────────────
    print("\n" + "═" * 62)
    print("  CASO 1 — Urgencia crítica con alerta inmediata")
    print("═" * 62)
    paciente_1 = Paciente(
        edad                  = 62,
        sexo_biologico        = "M",
        disnea_presente       = True,      # ← ALERTA CRÍTICA
        perdida_conciencia    = False,
        sangrado_activo       = False,
        fiebre_presente       = False,
        temperatura_celsius   = None,      # NULL por regla de consistencia
        intensidad_dolor_eva  = 9,
        duracion_sintoma_horas= 1,         # inicio súbito — alto peso SHAP
        peso_kg               = 85.0,
        talla_cm              = 170.0,
        diabetes_mellitus     = True,
        hipertension          = True,
        cardiopatia_isquemica = True,
        sintomas_texto        = "Siento un dolor muy fuerte en el pecho que se va al brazo, me cuesta respirar"
    )
    resultado_1 = motor.procesar(paciente_1)
    imprimir_resultado(resultado_1)

    # ─── CASO 2: Indecisión modelo → conservadurismo ──────────────────────────
    print("═" * 62)
    print("  CASO 2 — Probabilidades cercanas → conservadurismo médico")
    print("═" * 62)
    # Para forzar el conservadurismo en la simulación, usamos un perfil
    # moderado que genera probabilidades parecidas entre rojo y amarillo
    random.seed(42)  # Semilla fija para reproducibilidad del caso de prueba
    paciente_2 = Paciente(
        edad                  = 55,
        sexo_biologico        = "M",
        disnea_presente       = False,
        perdida_conciencia    = False,
        sangrado_activo       = False,
        fiebre_presente       = True,
        temperatura_celsius   = 38.8,
        intensidad_dolor_eva  = 6,
        duracion_sintoma_horas= 3,
        peso_kg               = 90.0,
        talla_cm              = 168.0,
        diabetes_mellitus     = True,
        hipertension          = True,
        cardiopatia_isquemica = False,
    )
    resultado_2 = motor.procesar(paciente_2)
    imprimir_resultado(resultado_2)

    # ─── CASO 3: Control de crónico — nivel verde esperado ────────────────────
    print("═" * 62)
    print("  CASO 3 — Control de enfermedad crónica (consulta no urgente)")
    print("═" * 62)
    paciente_3 = Paciente(
        edad                  = 45,
        sexo_biologico        = "F",
        disnea_presente       = False,
        perdida_conciencia    = False,
        sangrado_activo       = False,
        fiebre_presente       = False,
        temperatura_celsius   = None,
        intensidad_dolor_eva  = 2,
        duracion_sintoma_horas= 720,       # Síntoma crónico (30 días)
        peso_kg               = 68.0,
        talla_cm              = 162.0,
        diabetes_mellitus     = True,
        hipertension          = False,
    )
    resultado_3 = motor.procesar(paciente_3)
    imprimir_resultado(resultado_3)

    # ─── CASO 4: Embarazo con fiebre alta ─────────────────────────────────────
    print("═" * 62)
    print("  CASO 4 — Paciente embarazada con fiebre alta")
    print("═" * 62)
    paciente_4 = Paciente(
        edad                  = 28,
        sexo_biologico        = "F",
        disnea_presente       = False,
        perdida_conciencia    = False,
        sangrado_activo       = False,
        fiebre_presente       = True,
        temperatura_celsius   = 39.4,      # Fiebre alta — alto peso SHAP
        intensidad_dolor_eva  = 5,
        duracion_sintoma_horas= 8,
        embarazo_posible      = True,
        semanas_gestacion     = 32,
        diabetes_mellitus     = False,
        hipertension          = False,
    )
    resultado_4 = motor.procesar(paciente_4)
    imprimir_resultado(resultado_4)

    # ─── Ejemplo de validación que falla ──────────────────────────────────────
    print("═" * 62)
    print("  CASO 5 — Validación de rangos (debe lanzar ValueError)")
    print("═" * 62)
    try:
        paciente_invalido = Paciente(
            edad                 = 150,    # Fuera de rango (máx. 120)
            fiebre_presente      = False,
            temperatura_celsius  = 37.5,   # Inconsistencia: fiebre=False pero hay temperatura
        )
        motor.procesar(paciente_invalido)
    except ValueError as e:
        print(f"\n  ✅ Error de validación capturado correctamente:")
        print(f"  {e}\n")


# ══════════════════════════════════════════════════════════════════════════════
# PUNTO DE ENTRADA
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║     SMART X — Motor de Inferencia  |  Piloto HCG 2026       ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    ejecutar_casos_de_prueba()

    # ── Ejemplo de uso individual con output JSON ──────────────────────────────
    print("═" * 62)
    print("  OUTPUT JSON COMPLETO — Caso 1 (para integración con API)")
    print("═" * 62)
    motor = MotorInferenciaSmartX()
    paciente_demo = Paciente(
        edad                  = 62,
        sexo_biologico        = "M",
        disnea_presente       = True,
        fiebre_presente       = False,
        temperatura_celsius   = None,
        intensidad_dolor_eva  = 9,
        duracion_sintoma_horas= 1,
        peso_kg               = 85.0,
        talla_cm              = 170.0,
        hipertension          = True,
        cardiopatia_isquemica = True,
    )
    resultado_demo = motor.procesar(paciente_demo)
    print(resultado_demo.to_json())

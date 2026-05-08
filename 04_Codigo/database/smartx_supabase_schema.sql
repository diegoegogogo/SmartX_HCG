-- ══════════════════════════════════════════════════════════════════════════════
-- SmartX HCG — Schema de Supabase
-- Hospital Civil de Guadalajara | Piloto v1.0
--
-- INSTRUCCIONES: Pegar y ejecutar en Supabase → SQL Editor → Run
-- ══════════════════════════════════════════════════════════════════════════════

-- ─────────────────────────────────────────────────────────────────────────────
-- TABLA: inferencias
-- Almacena cada clasificación emitida por el Motor de Inferencia SmartX.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS inferencias (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    id_paciente          TEXT NOT NULL,
    id_consulta          TEXT NOT NULL UNIQUE,

    -- Metadata del paciente
    unidad_atencion      TEXT    DEFAULT 'HCG_URGENCIAS',
    sexo_biologico       TEXT    DEFAULT 'M',
    peso_kg              FLOAT,
    talla_cm             FLOAT,

    -- Features clínicas (17 features del modelo XGBoost)
    edad                                              INTEGER NOT NULL,
    embarazo                                          BOOLEAN DEFAULT FALSE,
    motivo_consulta                                   TEXT,
    tiempo_evolucion_horas                            INTEGER DEFAULT 0,
    intensidad_sintoma                                INTEGER DEFAULT 0,
    fiebre_reportada                                  BOOLEAN DEFAULT FALSE,
    tos                                               BOOLEAN DEFAULT FALSE,
    dificultad_respiratoria                           BOOLEAN DEFAULT FALSE,
    dolor_toracico                                    BOOLEAN DEFAULT FALSE,
    dolor_al_orinar                                   BOOLEAN DEFAULT FALSE,
    sangrado_activo                                   BOOLEAN DEFAULT FALSE,
    confusion                                         BOOLEAN DEFAULT FALSE,
    disminucion_movimientos_fetales                   BOOLEAN DEFAULT FALSE,
    redflag_disnea_severa                             BOOLEAN DEFAULT FALSE,
    redflag_sangrado_abundante                        BOOLEAN DEFAULT FALSE,
    redflag_deficit_neurologico_subito                BOOLEAN DEFAULT FALSE,
    redflag_dolor_toracico_opresivo_con_sudoracion    BOOLEAN DEFAULT FALSE,

    -- Trazabilidad
    antecedentes_riesgo  TEXT DEFAULT 'Ninguno',
    sintomas_digestivos  TEXT DEFAULT 'Ninguno',
    sintomas_texto       TEXT,

    -- Resultado IA
    nivel_ia             TEXT NOT NULL CHECK (nivel_ia IN ('rojo', 'amarillo', 'verde')),
    fuente_nivel         TEXT,
    probabilidad_rojo    FLOAT,
    probabilidad_amarillo FLOAT,
    probabilidad_verde   FLOAT,
    alerta_critica       BOOLEAN DEFAULT FALSE,
    imc_calculado        FLOAT,
    hash_resultado       TEXT,
    tiempo_procesamiento_ms INTEGER,
    modelo_version       TEXT DEFAULT 'xgboost-v2.0-hcg-piloto',

    -- Timestamp de registro
    created_at           TIMESTAMPTZ DEFAULT NOW()
);

-- ─────────────────────────────────────────────────────────────────────────────
-- TABLA: auditoria_api
-- Registro de todas las peticiones HTTP (NOM-024-SSA3).
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS auditoria_api (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp_utc TIMESTAMPTZ DEFAULT NOW(),
    metodo        TEXT,
    ruta          TEXT,
    ip_origen     TEXT,
    status_code   INTEGER,
    duracion_ms   INTEGER
);

-- ─────────────────────────────────────────────────────────────────────────────
-- ÍNDICES para consultas frecuentes del dashboard
-- ─────────────────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_inferencias_created_at   ON inferencias (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_inferencias_nivel_ia     ON inferencias (nivel_ia);
CREATE INDEX IF NOT EXISTS idx_inferencias_id_paciente  ON inferencias (id_paciente);
CREATE INDEX IF NOT EXISTS idx_auditoria_timestamp      ON auditoria_api (timestamp_utc DESC);

-- ─────────────────────────────────────────────────────────────────────────────
-- ROW LEVEL SECURITY
-- Permite acceso completo con las claves del proyecto (publishable + secret).
-- En producción restringir por rol de usuario.
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE inferencias   ENABLE ROW LEVEL SECURITY;
ALTER TABLE auditoria_api ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "allow_all_inferencias"   ON inferencias;
DROP POLICY IF EXISTS "allow_all_auditoria"     ON auditoria_api;

CREATE POLICY "allow_all_inferencias"
    ON inferencias FOR ALL
    USING (true) WITH CHECK (true);

CREATE POLICY "allow_all_auditoria"
    ON auditoria_api FOR ALL
    USING (true) WITH CHECK (true);

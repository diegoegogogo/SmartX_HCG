import React, { useState, useEffect, useCallback } from 'react';
import { AlertTriangle, Heart, Activity, Clock, User, Plus, X, Check,
         AlertCircle, Stethoscope, Zap } from 'lucide-react';

const API = 'http://localhost:8000';

// ── Mapeador: estado del form → SintomasInput (Pydantic) ──────────────────────
function buildPayload(form) {
  const disnea   = form.redflag_disnea_severa || form.dificultad_respiratoria;
  const perdida  = form.redflag_deficit_neurologico_subito || form.confusion;
  const sangrado = form.redflag_sangrado_abundante || form.sangrado_activo;
  const texto    = (form.sintomas_texto || '').trim();

  return {
    edad:                  parseInt(form.edad),
    sexo_biologico:        form.sexo_biologico || 'M',
    disnea_presente:       disnea,
    perdida_conciencia:    perdida,
    sangrado_activo:       sangrado,
    fiebre_presente:       form.fiebre_reportada,
    temperatura_celsius:   null,
    intensidad_dolor_eva:  parseInt(form.intensidad_sintoma) || null,
    duracion_sintoma_horas: null,
    sintomas_texto:        texto.length >= 10 ? texto : null,
    diabetes_mellitus:     false,
    hipertension:          false,
    cardiopatia_isquemica: form.redflag_dolor_toracico_opresivo_con_sudoracion,
    epoc_asma:             false,
    embarazo_posible:      form.sexo_biologico === 'F' && form.embarazo ? true : null,
    semanas_gestacion:     null,
  };
}

// ── Fallback local ─────────────────────────────────────────────────────────────
function simulateTriage(payload) {
  let nivel = 'verde';
  if (payload.disnea_presente || payload.sangrado_activo ||
      payload.perdida_conciencia || payload.cardiopatia_isquemica) {
    nivel = 'rojo';
  } else if ((payload.intensidad_dolor_eva || 0) >= 7) {
    nivel = 'amarillo';
  }
  return {
    nivel_ia: nivel,
    probabilidades: {},
    escenarios: [{ nombre: 'Clasificación local (sin API)', probabilidad: 0.7 }],
    explicacion_shap: 'Motor no disponible',
    analisis_llm: null,
    _modo: 'simulacion',
  };
}

// ── Mapeador: respuesta API → objeto paciente del dashboard ───────────────────
function apiToPatient(apiResp, formData, id) {
  const nivel = apiResp.nivel_ia || 'verde';
  const labelMap = {
    rojo:     { justificacion: 'Alerta Crítica Detectada', accion: 'PASAR A CHOQUE',   banderas_rojas: ['Nivel crítico — motor IA'] },
    amarillo: { justificacion: 'Síntomas Moderados',       accion: 'MONITOREO 30MIN',  banderas_rojas: [] },
    verde:    { justificacion: 'Sintomatología Leve',       accion: 'SALA DE ESPERA',   banderas_rojas: [] },
  };
  const label = labelMap[nivel] || labelMap.verde;
  const top   = (apiResp.escenarios || [])[0] || {};
  return {
    id,
    edad:              parseInt(formData.edad),
    hora_ingreso:      new Date().toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' }),
    nivel,
    justificacion:     label.justificacion,
    accion:            label.accion,
    tiempo_espera:     0,
    banderas_rojas:    label.banderas_rojas,
    patron_referencia: top.nombre ? `${top.nombre} (${Math.round((top.probabilidad || 0) * 100)}%)` : 'Patrón identificado',
    escenarios:        apiResp.escenarios || [],
    shap:              apiResp.explicacion_shap || '',
    analisis_llm:      apiResp.analisis_llm || null,
    modo:              apiResp._modo || 'api',
  };
}

// ═══════════════════════════════════════════════════════════════════════════════
//  COMPONENTE PRINCIPAL
// ═══════════════════════════════════════════════════════════════════════════════
const SmartXDashboard = () => {
  const [patients,       setPatients]       = useState([]);
  const [showForm,       setShowForm]       = useState(false);
  const [notifications,  setNotifications]  = useState([]);
  const [currentPatient, setCurrentPatient] = useState(null);
  const [apiOnline,      setApiOnline]      = useState(null);
  const [processing,     setProcessing]     = useState(false);
  const [counter,        setCounter]        = useState(1);

  const [form, setForm] = useState({
    edad: '', sexo_biologico: 'M', embarazo: false,
    intensidad_sintoma: '5',
    fiebre_reportada: false, tos: false, dificultad_respiratoria: false,
    dolor_toracico: false, sangrado_activo: false, confusion: false,
    redflag_disnea_severa: false, redflag_sangrado_abundante: false,
    redflag_deficit_neurologico_subito: false,
    redflag_dolor_toracico_opresivo_con_sudoracion: false,
    sintomas_texto: '',
  });

  const resetForm = () => setForm({
    edad: '', sexo_biologico: 'M', embarazo: false, intensidad_sintoma: '5',
    fiebre_reportada: false, tos: false, dificultad_respiratoria: false,
    dolor_toracico: false, sangrado_activo: false, confusion: false,
    redflag_disnea_severa: false, redflag_sangrado_abundante: false,
    redflag_deficit_neurologico_subito: false,
    redflag_dolor_toracico_opresivo_con_sudoracion: false,
    sintomas_texto: '',
  });

  // health-check periódico
  const checkApi = useCallback(async () => {
    try {
      const r = await fetch(`${API}/health`, { signal: AbortSignal.timeout(3000) });
      setApiOnline(r.ok);
    } catch { setApiOnline(false); }
  }, []);

  useEffect(() => {
    checkApi();
    const iv = setInterval(checkApi, 30000);
    return () => clearInterval(iv);
  }, [checkApi]);

  // Tiempos de espera
  useEffect(() => {
    const iv = setInterval(() => setPatients(ps => ps.map(p => ({ ...p, tiempo_espera: p.tiempo_espera + 1 }))), 60000);
    return () => clearInterval(iv);
  }, []);

  const addNotification = (type, title, message) => {
    const id = Date.now();
    setNotifications(prev => [...prev, { id, type, title, message }]);
    setTimeout(() => setNotifications(prev => prev.filter(n => n.id !== id)), 8000);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setProcessing(true);

    const payload = buildPayload(form);
    let apiResp;
    try {
      const res = await fetch(`${API}/api/v1/inferencia`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: AbortSignal.timeout(15000),
      });
      apiResp = res.ok ? await res.json() : simulateTriage(payload);
    } catch {
      addNotification('warning', 'API sin conexión', 'Usando clasificación local.');
      apiResp = simulateTriage(payload);
    }

    const patientId = `PX-${String(counter).padStart(3, '0')}`;
    const newPatient = apiToPatient(apiResp, form, patientId);

    setPatients(prev => [newPatient, ...prev]);
    setCounter(c => c + 1);
    setProcessing(false);
    setShowForm(false);
    resetForm();

    if (newPatient.nivel === 'rojo') {
      addNotification('critical', 'CASO CRÍTICO DETECTADO', `${patientId}: ${newPatient.justificacion}`);
    } else if (newPatient.nivel === 'amarillo') {
      addNotification('warning', 'CASO URGENTE', `${patientId}: monitoreo 30 min`);
    } else {
      addNotification('success', 'PACIENTE PROCESADO', `${patientId}: sala de espera`);
    }
  };

  // ── Estilos por nivel ────────────────────────────────────────────────────────
  const cardStyle = nivel => ({
    rojo:     'bg-red-500 border-red-700 shadow-red-500/50 animate-pulse',
    amarillo: 'bg-yellow-500 border-yellow-700 shadow-yellow-500/30',
    verde:    'bg-green-500 border-green-700 shadow-green-500/20',
  }[nivel] || 'bg-gray-500 border-gray-700');

  const levelIcon = nivel => ({
    rojo:     <Zap className="w-8 h-8 text-white" />,
    amarillo: <Clock className="w-8 h-8 text-white" />,
    verde:    <Check className="w-8 h-8 text-white" />,
  }[nivel] || <User className="w-8 h-8 text-white" />);

  // ── RENDER ───────────────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-slate-900 text-white font-mono">

      {/* Header */}
      <header className="bg-slate-800 border-b-4 border-blue-500 p-4">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center space-x-4">
            <div className="bg-blue-500 p-3 rounded-lg">
              <Stethoscope className="w-8 h-8 text-white" />
            </div>
            <div>
              <h1 className="text-3xl font-bold text-blue-400">SMARTX TRIAJE</h1>
              <p className="text-slate-400 text-sm">Hospital Civil de Guadalajara | Emergencias AI</p>
            </div>
          </div>
          <div className="flex items-center space-x-4">
            {/* indicador API */}
            <span className={`flex items-center space-x-2 text-sm px-3 py-2 rounded-lg border ${
              apiOnline === null ? 'border-yellow-500 text-yellow-300'
              : apiOnline ? 'border-green-500 text-green-300'
              : 'border-red-500 text-red-300'}`}>
              <span className={`w-2 h-2 rounded-full ${
                apiOnline === null ? 'bg-yellow-400'
                : apiOnline ? 'bg-green-400' : 'bg-red-400'}`} />
              <span>{apiOnline === null ? 'Conectando…' : apiOnline ? 'API conectada' : 'API sin conexión'}</span>
            </span>
            <button onClick={() => setShowForm(true)}
              className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-3 rounded-lg font-bold flex items-center space-x-2 transition-all transform hover:scale-105">
              <Plus className="w-5 h-5" /><span>NUEVO TRIAJE</span>
            </button>
          </div>
        </div>
      </header>

      {/* Stats */}
      <div className="bg-slate-800 p-4 border-b border-slate-700">
        <div className="max-w-7xl mx-auto grid grid-cols-4 gap-4">
          {[
            { label: 'CRÍTICOS',   color: 'red',    count: patients.filter(p => p.nivel === 'rojo').length,     Icon: Zap },
            { label: 'URGENTES',   color: 'yellow', count: patients.filter(p => p.nivel === 'amarillo').length, Icon: Clock },
            { label: 'ESTABLES',   color: 'green',  count: patients.filter(p => p.nivel === 'verde').length,    Icon: Check },
            { label: 'TOTAL HOY',  color: 'slate',  count: patients.length,                                     Icon: Activity },
          ].map(({ label, color, count, Icon }) => (
            <div key={label} className={`bg-${color}-500/20 border border-${color}-500 rounded-lg p-4 text-center`}>
              <div className="flex items-center justify-center space-x-2 mb-2">
                <Icon className={`w-6 h-6 text-${color}-400`} />
                <h3 className={`text-${color}-400 font-bold`}>{label}</h3>
              </div>
              <p className={`text-3xl font-bold text-${color}-400`}>{count}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Dashboard */}
      <main className="max-w-7xl mx-auto p-6">
        <h2 className="text-2xl font-bold mb-6 text-slate-200">Dashboard de Pacientes</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {[...patients]
            .sort((a, b) => ({ rojo: 3, amarillo: 2, verde: 1 }[b.nivel] - { rojo: 3, amarillo: 2, verde: 1 }[a.nivel]))
            .map(patient => (
            <div key={patient.id}
              className={`${cardStyle(patient.nivel)} p-6 rounded-xl border-2 shadow-xl cursor-pointer transform transition-all hover:scale-105`}
              onClick={() => setCurrentPatient(patient)}>
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="text-2xl font-bold text-white">{patient.id}</h3>
                  <p className="text-white/80 text-sm">{patient.hora_ingreso} | {patient.edad} años</p>
                </div>
                <div className="flex flex-col items-center">
                  {levelIcon(patient.nivel)}
                  <span className="text-xs font-bold text-white mt-1">{patient.nivel.toUpperCase()}</span>
                </div>
              </div>
              <div className="mb-4">
                <h4 className="text-white font-bold text-lg text-center bg-black/20 rounded-lg p-3">
                  {patient.justificacion}
                </h4>
              </div>
              <div className="mb-4">
                <div className="bg-white/20 rounded-lg p-3 border-2 border-white/30">
                  <p className="text-white font-bold text-center">{patient.accion}</p>
                </div>
              </div>
              {patient.banderas_rojas.length > 0 && (
                <div className="mb-4 bg-red-800/50 border border-red-400 rounded-lg p-2">
                  <div className="flex items-center space-x-2">
                    <AlertTriangle className="w-4 h-4 text-red-200" />
                    <span className="text-red-200 font-bold text-sm">BANDERAS ROJAS</span>
                  </div>
                </div>
              )}
              <div className="flex items-center justify-between text-white/80 text-sm">
                <span>Espera: {patient.tiempo_espera} min</span>
                {patient.modo === 'simulacion' && (
                  <span className="text-xs bg-orange-600 px-1 rounded">sin conexión</span>
                )}
              </div>
            </div>
          ))}
        </div>
        {patients.length === 0 && (
          <div className="text-center py-12">
            <User className="w-16 h-16 text-slate-600 mx-auto mb-4" />
            <h3 className="text-xl text-slate-400 mb-2">No hay pacientes registrados hoy</h3>
            <button onClick={() => setShowForm(true)}
              className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-3 rounded-lg font-bold mt-4">
              <Plus className="w-5 h-5 inline mr-2" />INICIAR TRIAJE
            </button>
          </div>
        )}
      </main>

      {/* Modal — Nuevo Triaje */}
      {showForm && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center p-4 z-50">
          <div className="bg-slate-800 rounded-xl p-6 w-full max-w-4xl max-h-screen overflow-y-auto border border-slate-600">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-2xl font-bold text-blue-400">NUEVO TRIAJE DE PACIENTE</h2>
              <button onClick={() => { setShowForm(false); resetForm(); }}
                className="text-slate-400 hover:text-white"><X className="w-8 h-8" /></button>
            </div>
            <form onSubmit={handleSubmit} className="space-y-6">

              {/* Demográficos */}
              <div className="bg-slate-700 p-4 rounded-lg">
                <h3 className="text-xl font-bold text-slate-200 mb-4">DATOS DEMOGRÁFICOS</h3>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div>
                    <label className="block text-slate-300 font-bold mb-2">EDAD *</label>
                    <input type="number" required min="0" max="120"
                      value={form.edad}
                      onChange={e => setForm({ ...form, edad: e.target.value })}
                      className="w-full bg-slate-600 border border-slate-500 rounded-lg px-4 py-3 text-white text-lg font-bold focus:ring-2 focus:ring-blue-500"
                      placeholder="0-120" />
                  </div>
                  <div>
                    <label className="block text-slate-300 font-bold mb-2">SEXO *</label>
                    <select value={form.sexo_biologico}
                      onChange={e => setForm({ ...form, sexo_biologico: e.target.value })}
                      className="w-full bg-slate-600 border border-slate-500 rounded-lg px-4 py-3 text-white text-lg font-bold focus:ring-2 focus:ring-blue-500">
                      <option value="M">Masculino</option>
                      <option value="F">Femenino</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-slate-300 font-bold mb-2">EMBARAZO</label>
                    <select value={form.embarazo ? 'Sí' : 'No'}
                      onChange={e => setForm({ ...form, embarazo: e.target.value === 'Sí' })}
                      className="w-full bg-slate-600 border border-slate-500 rounded-lg px-4 py-3 text-white text-lg font-bold focus:ring-2 focus:ring-blue-500">
                      <option value="No">No</option>
                      <option value="Sí">Sí</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-slate-300 font-bold mb-2">INTENSIDAD (0-10)</label>
                    <input type="range" min="0" max="10" value={form.intensidad_sintoma}
                      onChange={e => setForm({ ...form, intensidad_sintoma: e.target.value })}
                      className="w-full h-3 bg-slate-600 rounded-lg appearance-none cursor-pointer" />
                    <div className="text-center mt-2">
                      <span className="text-2xl font-bold text-yellow-400">{form.intensidad_sintoma}</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Banderas rojas */}
              <div className="bg-red-900/30 border border-red-500 p-4 rounded-lg">
                <h3 className="text-xl font-bold text-red-400 mb-4 flex items-center space-x-2">
                  <AlertTriangle className="w-6 h-6" /><span>BANDERAS ROJAS CRÍTICAS</span>
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {[
                    { key: 'redflag_disnea_severa',                          label: 'DISNEA SEVERA' },
                    { key: 'redflag_sangrado_abundante',                     label: 'SANGRADO ABUNDANTE' },
                    { key: 'redflag_deficit_neurologico_subito',              label: 'DÉFICIT NEUROLÓGICO' },
                    { key: 'redflag_dolor_toracico_opresivo_con_sudoracion', label: 'DOLOR TORÁCICO + SUDOR' },
                  ].map(({ key, label }) => (
                    <label key={key} className="flex items-center space-x-3 cursor-pointer bg-red-800/20 p-3 rounded border border-red-600">
                      <input type="checkbox" checked={form[key]}
                        onChange={e => setForm({ ...form, [key]: e.target.checked })}
                        className="w-5 h-5 text-red-500" />
                      <span className="text-red-300 font-bold">{label}</span>
                    </label>
                  ))}
                </div>
              </div>

              {/* Síntomas */}
              <div className="bg-slate-700 p-4 rounded-lg">
                <h3 className="text-xl font-bold text-slate-200 mb-4">SÍNTOMAS ESPECÍFICOS</h3>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  {[
                    { key: 'fiebre_reportada',      label: 'FIEBRE' },
                    { key: 'tos',                   label: 'TOS' },
                    { key: 'dificultad_respiratoria', label: 'DISNEA' },
                    { key: 'dolor_toracico',         label: 'DOLOR TORÁCICO' },
                    { key: 'sangrado_activo',        label: 'SANGRADO' },
                    { key: 'confusion',              label: 'CONFUSIÓN' },
                  ].map(({ key, label }) => (
                    <label key={key} className="flex items-center space-x-2 cursor-pointer">
                      <input type="checkbox" checked={form[key]}
                        onChange={e => setForm({ ...form, [key]: e.target.checked })}
                        className="w-4 h-4 text-blue-500" />
                      <span className="text-slate-300 font-bold text-sm">{label}</span>
                    </label>
                  ))}
                </div>
              </div>

              {/* Texto libre */}
              <div className="bg-blue-900/30 border border-blue-500 p-4 rounded-lg">
                <h3 className="text-xl font-bold text-blue-400 mb-4 flex items-center space-x-2">
                  <Stethoscope className="w-6 h-6" /><span>DESCRIPCIÓN LIBRE DE SÍNTOMAS</span>
                </h3>
                <textarea value={form.sintomas_texto}
                  onChange={e => setForm({ ...form, sintomas_texto: e.target.value })}
                  className="w-full bg-slate-600 border border-slate-500 rounded-lg px-4 py-3 text-white h-28 focus:ring-2 focus:ring-blue-500"
                  placeholder="Mínimo 10 caracteres. Ej: 'Dolor en el pecho con irradiación al brazo izquierdo desde hace 2 horas…'" />
              </div>

              <div className="flex space-x-4 pt-4">
                <button type="button" onClick={() => { setShowForm(false); resetForm(); }}
                  className="flex-1 bg-slate-600 hover:bg-slate-700 text-white px-6 py-4 rounded-lg font-bold text-lg">
                  CANCELAR
                </button>
                <button type="submit" disabled={processing}
                  className="flex-1 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white px-6 py-4 rounded-lg font-bold text-lg transition-all transform hover:scale-105">
                  {processing ? 'PROCESANDO…' : 'PROCESAR TRIAJE'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal — Detalle paciente */}
      {currentPatient && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center p-4 z-50">
          <div className="bg-slate-800 rounded-xl p-6 w-full max-w-3xl max-h-screen overflow-y-auto border border-slate-600">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-2xl font-bold text-blue-400">PACIENTE: {currentPatient.id}</h2>
              <button onClick={() => setCurrentPatient(null)} className="text-slate-400 hover:text-white">
                <X className="w-8 h-8" />
              </button>
            </div>
            <div className="space-y-6">
              {/* Nivel */}
              <div className={`${cardStyle(currentPatient.nivel)} p-6 rounded-xl`}>
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-3xl font-bold text-white mb-2">{currentPatient.nivel.toUpperCase()}</h3>
                    <p className="text-white text-xl font-bold mb-2">{currentPatient.justificacion}</p>
                    <p className="text-white/80 bg-black/20 rounded-lg p-2 inline-block">{currentPatient.accion}</p>
                  </div>
                  {levelIcon(currentPatient.nivel)}
                </div>
              </div>

              {/* Escenarios */}
              <div className="bg-blue-900/30 border border-blue-500 p-4 rounded-lg">
                <h4 className="text-lg font-bold text-blue-400 mb-3">ESCENARIOS DIFERENCIALES</h4>
                <div className="space-y-2">
                  {(currentPatient.escenarios || []).map((e, i) => (
                    <div key={i} className="bg-slate-600 p-3 rounded-lg flex items-center justify-between">
                      <span className="text-white font-bold">{i + 1}. {e.nombre || e}</span>
                      <span className="text-blue-300 text-sm">
                        {e.probabilidad !== undefined ? `${Math.round(e.probabilidad * 100)}%` : ''}
                        {e.cie10 ? ` · ${e.cie10}` : ''}
                      </span>
                    </div>
                  ))}
                  {!(currentPatient.escenarios || []).length && (
                    <p className="text-slate-400">No disponible</p>
                  )}
                </div>
              </div>

              {/* SHAP */}
              <div className="bg-slate-700 p-4 rounded-lg">
                <h4 className="text-lg font-bold text-slate-200 mb-2">EXPLICACIÓN SHAP</h4>
                <p className="text-white text-sm bg-slate-600 p-3 rounded-lg">
                  {currentPatient.shap || 'No disponible'}
                </p>
              </div>

              {/* LLM */}
              {currentPatient.analisis_llm && (
                <div className="bg-indigo-900/30 border border-indigo-500 p-4 rounded-lg">
                  <h4 className="text-lg font-bold text-indigo-400 mb-2">ANÁLISIS LLM</h4>
                  <p className="text-white text-sm whitespace-pre-wrap">{currentPatient.analisis_llm}</p>
                </div>
              )}

              {/* Banderas */}
              {currentPatient.banderas_rojas.length > 0 && (
                <div className="bg-red-900/30 border border-red-500 p-4 rounded-lg">
                  <h4 className="text-lg font-bold text-red-400 mb-2 flex items-center space-x-2">
                    <AlertTriangle className="w-5 h-5" /><span>BANDERAS ROJAS ACTIVAS</span>
                  </h4>
                  <ul className="space-y-1">
                    {currentPatient.banderas_rojas.map((b, i) => (
                      <li key={i} className="text-red-300 font-bold">• {b}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Info general */}
              <div className="bg-slate-700 p-4 rounded-lg">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-center">
                  {[
                    { label: 'EDAD',     value: `${currentPatient.edad} años` },
                    { label: 'INGRESO',  value: currentPatient.hora_ingreso },
                    { label: 'ESPERA',   value: `${currentPatient.tiempo_espera} min` },
                    { label: 'FUENTE',   value: currentPatient.modo === 'simulacion' ? 'LOCAL' : 'MOTOR IA' },
                  ].map(({ label, value }) => (
                    <div key={label}>
                      <p className="text-slate-400 text-sm mb-1">{label}</p>
                      <p className="text-white font-bold text-lg">{value}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Notificaciones */}
      <div className="fixed top-4 right-4 space-y-4 z-50">
        {notifications.map(n => (
          <div key={n.id}
            className={`border-2 rounded-lg p-4 shadow-xl max-w-sm ${
              n.type === 'critical' ? 'bg-red-600 border-red-400 animate-pulse'
              : n.type === 'warning' ? 'bg-yellow-600 border-yellow-400'
              : 'bg-green-600 border-green-400'}`}>
            <div className="flex items-center space-x-3">
              <AlertCircle className="w-8 h-8 text-white flex-shrink-0" />
              <div>
                <h4 className="text-white font-bold">{n.title}</h4>
                <p className="text-white/90 text-sm">{n.message}</p>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default SmartXDashboard;

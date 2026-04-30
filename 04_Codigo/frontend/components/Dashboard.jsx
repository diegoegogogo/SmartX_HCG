import React, { useState, useEffect, useCallback } from 'react';
import { Stethoscope, Plus, Activity, Zap, Clock, Check, X, AlertCircle, AlertTriangle } from 'lucide-react';
import PatientCard from './PatientCard';
import TriageForm  from './TriageForm';

const API = 'http://localhost:8000';

const LEVEL_STYLES = {
  rojo:     'bg-red-500 border-red-700 animate-pulse',
  amarillo: 'bg-yellow-500 border-yellow-700',
  verde:    'bg-green-500 border-green-700',
};

const LEVEL_ICON = {
  rojo:     <Zap className="w-6 h-6 text-white" />,
  amarillo: <Clock className="w-6 h-6 text-white" />,
  verde:    <Check className="w-6 h-6 text-white" />,
};

/** Convierte respuesta de la API al formato de paciente para el dashboard. */
function apiToPatient(apiResp, counter) {
  const nivel = apiResp.nivel_ia || 'verde';
  const MAP = {
    rojo:     { justificacion: 'Alerta Crítica Detectada', accion: 'PASAR A CHOQUE',  banderas_rojas: ['Nivel crítico — motor IA'] },
    amarillo: { justificacion: 'Síntomas Moderados',       accion: 'MONITOREO 30MIN', banderas_rojas: [] },
    verde:    { justificacion: 'Sintomatología Leve',       accion: 'SALA DE ESPERA',  banderas_rojas: [] },
  };
  const label = MAP[nivel] || MAP.verde;
  const top   = (apiResp.escenarios || [])[0] || {};

  return {
    id:               `PX-${String(counter).padStart(3, '0')}`,
    edad:             parseInt(apiResp._form?.edad || 0),
    hora_ingreso:     new Date().toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' }),
    nivel,
    justificacion:    label.justificacion,
    accion:           label.accion,
    tiempo_espera:    0,
    banderas_rojas:   label.banderas_rojas,
    patron_referencia: top.nombre
      ? `${top.nombre} (${Math.round((top.probabilidad || 0) * 100)}%)`
      : 'Patrón identificado',
    escenarios:   apiResp.escenarios || [],
    shap:         apiResp.explicacion_shap || '',
    analisis_llm: apiResp.analisis_llm || null,
    modo:         apiResp._modo || 'api',
  };
}

/**
 * Dashboard principal de SmartX.
 * Orquesta PatientCard y TriageForm; se puede montar como página independiente
 * o dentro de una app React más grande.
 */
const Dashboard = () => {
  const [patients,       setPatients]       = useState([]);
  const [showForm,       setShowForm]       = useState(false);
  const [selected,       setSelected]       = useState(null);
  const [notifications,  setNotifications]  = useState([]);
  const [apiOnline,      setApiOnline]      = useState(null);
  const [counter,        setCounter]        = useState(1);

  // ── health-check periódico ─────────────────────────────────────────────────
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

  // ── incrementar tiempos de espera cada minuto ──────────────────────────────
  useEffect(() => {
    const iv = setInterval(
      () => setPatients(ps => ps.map(p => ({ ...p, tiempo_espera: p.tiempo_espera + 1 }))),
      60000,
    );
    return () => clearInterval(iv);
  }, []);

  // ── notificaciones auto-dismiss ────────────────────────────────────────────
  const addNotification = (type, title, message) => {
    const id = Date.now();
    setNotifications(prev => [...prev, { id, type, title, message }]);
    setTimeout(() => setNotifications(prev => prev.filter(n => n.id !== id)), 8000);
  };

  // ── resultado del motor → nuevo paciente ──────────────────────────────────
  const handleTriageResult = (apiResp) => {
    const patient = apiToPatient(apiResp, counter);
    setPatients(prev => [patient, ...prev]);
    setCounter(c => c + 1);
    setShowForm(false);

    if (patient.nivel === 'rojo')
      addNotification('critical', 'CASO CRÍTICO', `${patient.id}: ${patient.justificacion}`);
    else if (patient.nivel === 'amarillo')
      addNotification('warning', 'CASO URGENTE', `${patient.id}: monitoreo 30 min`);
    else
      addNotification('success', 'PACIENTE PROCESADO', `${patient.id}: sala de espera`);
  };

  // ── stats ──────────────────────────────────────────────────────────────────
  const counts = {
    rojo:     patients.filter(p => p.nivel === 'rojo').length,
    amarillo: patients.filter(p => p.nivel === 'amarillo').length,
    verde:    patients.filter(p => p.nivel === 'verde').length,
    total:    patients.length,
  };

  const sortedPatients = [...patients].sort((a, b) => {
    const ord = { rojo: 3, amarillo: 2, verde: 1 };
    return (ord[b.nivel] - ord[a.nivel]) || (b.tiempo_espera - a.tiempo_espera);
  });

  // ── RENDER ─────────────────────────────────────────────────────────────────
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
              <h1 className="text-3xl font-bold text-blue-400 tracking-tight">SMARTX TRIAJE</h1>
              <p className="text-slate-400 text-sm">Hospital Civil de Guadalajara | Emergencias AI</p>
            </div>
          </div>

          <div className="flex items-center space-x-4">
            {/* indicador API */}
            <span className={`flex items-center space-x-2 text-sm px-3 py-2 rounded-lg border ${
              apiOnline === null  ? 'border-yellow-500 text-yellow-300'
              : apiOnline         ? 'border-green-500 text-green-300'
              :                     'border-red-500 text-red-300'}`}>
              <span className={`w-2 h-2 rounded-full ${
                apiOnline === null ? 'bg-yellow-400'
                : apiOnline        ? 'bg-green-400'
                :                    'bg-red-400'}`} />
              <span>{apiOnline === null ? 'Conectando…' : apiOnline ? 'API conectada' : 'API sin conexión'}</span>
            </span>

            <button onClick={() => setShowForm(true)}
              className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-3 rounded-lg font-bold flex items-center space-x-2 transition-all transform hover:scale-105 shadow-lg">
              <Plus className="w-5 h-5" /><span>NUEVO TRIAJE</span>
            </button>
          </div>
        </div>
      </header>

      {/* Stats bar */}
      <div className="bg-slate-800 p-4 border-b border-slate-700">
        <div className="max-w-7xl mx-auto grid grid-cols-4 gap-4">
          {[
            { key: 'rojo',     label: 'CRÍTICOS',  Icon: Zap,      color: 'red' },
            { key: 'amarillo', label: 'URGENTES',  Icon: Clock,    color: 'yellow' },
            { key: 'verde',    label: 'ESTABLES',  Icon: Check,    color: 'green' },
            { key: 'total',    label: 'TOTAL HOY', Icon: Activity, color: 'slate' },
          ].map(({ key, label, Icon, color }) => (
            <div key={key}
              className={`bg-${color}-500/20 border border-${color}-500 rounded-lg p-4 text-center`}>
              <div className="flex items-center justify-center space-x-2 mb-2">
                <Icon className={`w-6 h-6 text-${color}-400`} />
                <h3 className={`text-${color}-400 font-bold`}>{label}</h3>
              </div>
              <p className={`text-3xl font-bold text-${color}-400`}>{counts[key]}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Grid de pacientes */}
      <main className="max-w-7xl mx-auto p-6">
        <h2 className="text-2xl font-bold mb-6 text-slate-200">
          Dashboard de Pacientes — Tiempo Real
        </h2>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {sortedPatients.map(p => (
            <PatientCard key={p.id} patient={p} onClick={() => setSelected(p)} />
          ))}
        </div>

        {patients.length === 0 && (
          <div className="text-center py-12">
            <Stethoscope className="w-16 h-16 text-slate-600 mx-auto mb-4" />
            <h3 className="text-xl text-slate-400 mb-4">No hay pacientes registrados hoy</h3>
            <button onClick={() => setShowForm(true)}
              className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-3 rounded-lg font-bold">
              <Plus className="w-5 h-5 inline mr-2" />INICIAR TRIAJE
            </button>
          </div>
        )}
      </main>

      {/* Modal triaje */}
      {showForm && (
        <TriageForm
          onResult={handleTriageResult}
          onClose={() => setShowForm(false)}
        />
      )}

      {/* Modal detalle paciente */}
      {selected && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center p-4 z-50">
          <div className="bg-slate-800 rounded-xl p-6 w-full max-w-3xl max-h-screen overflow-y-auto border border-slate-600">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-2xl font-bold text-blue-400">PACIENTE: {selected.id}</h2>
              <button onClick={() => setSelected(null)} className="text-slate-400 hover:text-white">
                <X className="w-8 h-8" />
              </button>
            </div>

            <div className={`${LEVEL_STYLES[selected.nivel]} p-6 rounded-xl mb-6`}>
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-3xl font-bold text-white mb-2">{selected.nivel?.toUpperCase()}</h3>
                  <p className="text-white text-xl font-bold mb-2">{selected.justificacion}</p>
                  <p className="text-white/80 bg-black/20 rounded-lg p-2 inline-block">{selected.accion}</p>
                </div>
                {LEVEL_ICON[selected.nivel]}
              </div>
            </div>

            {/* Escenarios */}
            <div className="bg-blue-900/30 border border-blue-500 p-4 rounded-lg mb-4">
              <h4 className="text-lg font-bold text-blue-400 mb-3">ESCENARIOS DIFERENCIALES</h4>
              <div className="space-y-2">
                {(selected.escenarios || []).map((e, i) => (
                  <div key={i} className="bg-slate-600 p-3 rounded-lg flex items-center justify-between">
                    <span className="text-white font-bold">{i + 1}. {e.nombre || e}</span>
                    <span className="text-blue-300 text-sm">
                      {e.probabilidad !== undefined ? `${Math.round(e.probabilidad * 100)}%` : ''}
                      {e.cie10 ? ` · ${e.cie10}` : ''}
                    </span>
                  </div>
                ))}
                {!(selected.escenarios || []).length && <p className="text-slate-400">No disponible</p>}
              </div>
            </div>

            {/* SHAP */}
            <div className="bg-slate-700 p-4 rounded-lg mb-4">
              <h4 className="text-lg font-bold text-slate-200 mb-2">EXPLICACIÓN SHAP</h4>
              <p className="text-white text-sm bg-slate-600 p-3 rounded-lg">
                {selected.shap || 'No disponible'}
              </p>
            </div>

            {/* LLM */}
            {selected.analisis_llm && (
              <div className="bg-indigo-900/30 border border-indigo-500 p-4 rounded-lg mb-4">
                <h4 className="text-lg font-bold text-indigo-400 mb-2">ANÁLISIS LLM</h4>
                <p className="text-white text-sm whitespace-pre-wrap">{selected.analisis_llm}</p>
              </div>
            )}

            {/* Banderas */}
            {selected.banderas_rojas?.length > 0 && (
              <div className="bg-red-900/30 border border-red-500 p-4 rounded-lg mb-4">
                <h4 className="text-lg font-bold text-red-400 mb-2 flex items-center space-x-2">
                  <AlertTriangle className="w-5 h-5" /><span>BANDERAS ROJAS</span>
                </h4>
                <ul className="space-y-1">
                  {selected.banderas_rojas.map((b, i) => (
                    <li key={i} className="text-red-300 font-bold">• {b}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* Info general */}
            <div className="bg-slate-700 p-4 rounded-lg">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-center">
                {[
                  { label: 'EDAD',    value: `${selected.edad} años` },
                  { label: 'INGRESO', value: selected.hora_ingreso },
                  { label: 'ESPERA',  value: `${selected.tiempo_espera} min` },
                  { label: 'FUENTE',  value: selected.modo === 'simulacion' ? 'LOCAL' : 'MOTOR IA' },
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
      )}

      {/* Notificaciones */}
      <div className="fixed top-4 right-4 space-y-4 z-50">
        {notifications.map(n => (
          <div key={n.id}
            className={`border-2 rounded-lg p-4 shadow-xl max-w-sm ${
              n.type === 'critical' ? 'bg-red-600 border-red-400 animate-pulse'
              : n.type === 'warning' ? 'bg-yellow-600 border-yellow-400'
              :                        'bg-green-600 border-green-400'}`}>
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

export default Dashboard;

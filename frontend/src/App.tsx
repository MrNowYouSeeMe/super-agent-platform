import {
  Activity, AlertTriangle, BarChart3, CheckCircle2, Clock3, Database,
  FlaskConical, Play, RefreshCw, ShieldCheck, TriangleAlert, WalletCards, XCircle,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import {
  acknowledge, assign, escalate, getAlert, getAnalysis, getDashboard, getEvaluation,
  listAlerts, resolve, startAnalysis, startReview, subscribe,
  type Alert, type AnalysisEvent, type AnalysisResult, type Dashboard, type EvaluationReport,
} from "./api";

type Language = "en" | "bn" | "banglish";
type Scenario = "liquidity_anomaly" | "normal_day" | "data_conflict";

const money = (value: number) => new Intl.NumberFormat("en-BD", {
  style: "currency", currency: "BDT", maximumFractionDigits: 0,
}).format(value);
const readable = (value: string) => value.replaceAll("_", " ").replace(/\b\w/g, c => c.toUpperCase());

function EventIcon({ event }: { event: AnalysisEvent }) {
  if (event.status === "warning") return <TriangleAlert className="h-5 w-5 text-amber-300" />;
  if (event.status === "failed") return <XCircle className="h-5 w-5 text-rose-300" />;
  return <CheckCircle2 className="h-5 w-5 text-emerald-300" />;
}

export default function App() {
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [evaluation, setEvaluation] = useState<EvaluationReport | null>(null);
  const [events, setEvents] = useState<AnalysisEvent[]>([]);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [selected, setSelected] = useState<Alert | null>(null);
  const [language, setLanguage] = useState<Language>("banglish");
  const [scenario, setScenario] = useState<Scenario>("liquidity_anomaly");
  const [running, setRunning] = useState(false);
  const [busyAction, setBusyAction] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const unsubscribeRef = useRef<(() => void) | null>(null);

  async function refresh() {
    const [dash, allAlerts, report] = await Promise.all([getDashboard(), listAlerts(), getEvaluation()]);
    setDashboard(dash);
    setAlerts(allAlerts);
    setEvaluation(report);
    if (selected) {
      const updated = allAlerts.find(item => item.alert_id === selected.alert_id);
      if (updated) setSelected(updated);
    }
  }

  useEffect(() => {
    refresh().catch(err => setError(err instanceof Error ? err.message : "Load failed."));
    return () => unsubscribeRef.current?.();
  }, []);

  async function poll(id: string) {
    for (let attempt = 0; attempt < 60; attempt += 1) {
      const snapshot = await getAnalysis(id);
      setEvents(snapshot.events);
      if (snapshot.status === "completed" && snapshot.result) {
        setResult(snapshot.result);
        if (snapshot.result.alert_id) setSelected(await getAlert(snapshot.result.alert_id));
        await refresh();
        setRunning(false);
        return;
      }
      if (snapshot.status === "failed") throw new Error(snapshot.error ?? "Analysis failed safely.");
      await new Promise(resolvePromise => window.setTimeout(resolvePromise, 400));
    }
    throw new Error("Analysis timed out.");
  }

  async function run() {
    setError(null); setEvents([]); setResult(null); setRunning(true);
    try {
      const accepted = await startAnalysis(language, scenario);
      unsubscribeRef.current?.();
      unsubscribeRef.current = subscribe(
        accepted.analysis_id,
        event => {
          setEvents(current => current.some(x => x.sequence === event.sequence) ? current : [...current, event]);
          if (event.stage === "analysis_completed") {
            unsubscribeRef.current?.();
            void poll(accepted.analysis_id).catch(err => { setError(err.message); setRunning(false); });
          }
        },
        () => void poll(accepted.analysis_id).catch(err => { setError(err.message); setRunning(false); }),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Analysis failed.");
      setRunning(false);
    }
  }

  async function act(fn: (alert: Alert) => Promise<Alert>) {
    if (!selected) return;
    setBusyAction(true); setError(null);
    try {
      const updated = await fn(selected);
      setSelected(updated);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Workflow action failed.");
    } finally { setBusyAction(false); }
  }

  const actions = selected ? {
    OPEN: [{ label: "Assign", fn: assign }],
    ASSIGNED: [{ label: "Acknowledge", fn: acknowledge }],
    ACKNOWLEDGED: [{ label: "Start review", fn: startReview }, { label: "Escalate", fn: escalate }],
    UNDER_REVIEW: [{ label: "Escalate", fn: escalate }, { label: "Resolve", fn: resolve }],
    ESCALATED: [{ label: "Resolve", fn: resolve }],
    RESOLVED: [],
  }[selected.status] : [];

  return <main className="min-h-screen bg-slate-950 text-slate-100">
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
      <header className="mb-8 flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <div className="mb-2 flex items-center gap-2 text-sm font-medium text-cyan-300"><ShieldCheck className="h-4 w-4" /> Persistent human-reviewed operations</div>
          <h1 className="text-3xl font-bold sm:text-4xl">SuperAgent Sentinel</h1>
          <p className="mt-2 text-slate-400">Redis worker pipeline + PostgreSQL case coordination.</p>
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          <select value={scenario} disabled={running} onChange={e => setScenario(e.target.value as Scenario)} className="control">
            <option value="liquidity_anomaly">Liquidity + anomaly</option>
            <option value="normal_day">Normal operation</option>
            <option value="data_conflict">Data conflict</option>
          </select>
          <select value={language} disabled={running} onChange={e => setLanguage(e.target.value as Language)} className="control">
            <option value="en">English</option><option value="bn">বাংলা</option><option value="banglish">Banglish</option>
          </select>
          <button disabled={running} onClick={run} className="primary"><Play className="h-5 w-5" />{running ? "Running" : "Run intelligence"}</button>
        </div>
      </header>

      {error && <div className="mb-5 flex gap-3 rounded-2xl border border-rose-400/30 bg-rose-400/10 p-4 text-rose-100"><AlertTriangle className="h-5 w-5" />{error}</div>}

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {dashboard && [dashboard.shared_cash, ...dashboard.provider_balances].map((item, index) => <article key={item.resource_id} className="card">
          <div className="flex items-center justify-between">{index === 0 ? <WalletCards className="text-cyan-300" /> : <Database className="text-violet-300" />}<span className="pill">{item.status}</span></div>
          <p className="mt-5 text-sm text-slate-400">{item.label}</p><p className="mt-1 text-2xl font-bold">{money(item.balance)}</p><p className="mt-3 text-xs text-slate-500">Safe threshold {money(item.safe_threshold)}</p>
        </article>)}
      </section>

      {evaluation && <section className="mt-6 panel border-violet-400/20">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div><div className="flex items-center gap-2 text-sm font-medium text-violet-300"><FlaskConical className="h-4 w-4" />Measured synthetic-data validation</div><h2 className="mt-2 text-xl font-semibold">Phase 3 evaluation evidence</h2><p className="mt-1 text-sm text-slate-400">Time-ordered train/validation/test split · seed {evaluation.seed}</p></div>
          <div className="pill"><BarChart3 className="mr-2 inline h-4 w-4" />{evaluation.champion_forecast_model}</div>
        </div>
        <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <div className="metric"><small>Forecast MAE</small><strong>{money(evaluation.forecast_candidates.find(item => item.model === evaluation.champion_forecast_model)?.mae_bdt ?? 0)}</strong></div>
          <div className="metric"><small>Forecast MAPE</small><strong>{evaluation.forecast_candidates.find(item => item.model === evaluation.champion_forecast_model)?.mape_percent ?? 0}%</strong></div>
          <div className="metric"><small>Anomaly F1</small><strong>{Math.round(evaluation.anomaly_detection.f1 * 100)}%</strong></div>
          <div className="metric"><small>Shortage recall</small><strong>{Math.round(evaluation.shortage_detection.recall * 100)}%</strong></div>
          <div className="metric"><small>Mean lead time</small><strong>{Math.round(evaluation.shortage_detection.mean_lead_time_minutes)} min</strong></div>
        </div>
        <p className="mt-4 text-xs text-slate-500">Synthetic benchmark only. Unusual activity requires human review and is not a fraud conclusion.</p>
      </section>}

      <section className="mt-6 grid gap-6 xl:grid-cols-2">
        <article className="panel">
          <div className="flex items-center justify-between"><div><h2 className="text-xl font-semibold">Live worker timeline</h2><p className="text-sm text-slate-400">Events persist in Redis across API processes.</p></div><Clock3 className="text-cyan-300" /></div>
          <div className="mt-6 space-y-5">{events.length === 0 && <p className="empty">Run an analysis to inspect the pipeline.</p>}{events.map(event => <div key={event.sequence} className="flex gap-3"><EventIcon event={event} /><div><p className="font-medium">{event.label}</p>{event.detail && <p className="mt-1 text-sm text-slate-400">{event.detail}</p>}</div></div>)}</div>
        </article>

        <article className="panel">
          <div className="flex items-center justify-between"><div><h2 className="text-xl font-semibold">Persistent alerts</h2><p className="text-sm text-slate-400">{dashboard?.active_alerts ?? 0} active · {dashboard?.cases_under_review ?? 0} under review</p></div><button className="icon" onClick={() => void refresh()}><RefreshCw className="h-5 w-5" /></button></div>
          <div className="mt-5 space-y-3">{alerts.length === 0 && <p className="empty">No persistent alerts yet.</p>}{alerts.map(alert => <button key={alert.alert_id} onClick={() => setSelected(alert)} className={`alert-row ${selected?.alert_id === alert.alert_id ? "selected" : ""}`}><div><p className="font-semibold">{alert.affected_provider} · {readable(alert.classification)}</p><p className="text-xs text-slate-500">Owner: {alert.owner}</p></div><span className="pill">{alert.status}</span></button>)}</div>
        </article>
      </section>

      {result && <section className="mt-6 panel border-cyan-400/20"><div className="flex flex-wrap gap-2"><span className="pill">{readable(result.classification)}</span><span className="pill">{Math.round(result.confidence * 100)}% confidence</span></div><h2 className="mt-4 text-2xl font-bold">Decision intelligence</h2><p className="mt-3 leading-7 text-slate-200">{result.summary}</p><div className="mt-5 grid gap-3 sm:grid-cols-3"><div className="metric"><small>Shortage ETA</small><strong>{result.shortage_eta_minutes ?? "—"} min</strong></div><div className="metric"><small>Provider</small><strong>{result.affected_provider}</strong></div><div className="metric"><small>Owner</small><strong>{result.recommended_owner}</strong></div></div></section>}

      {selected && <section className="mt-6 grid gap-6 lg:grid-cols-[0.8fr_1.2fr]">
        <article className="panel"><div className="flex items-center justify-between"><h2 className="text-xl font-semibold">Case control</h2><span className="pill">{selected.status}</span></div><p className="mt-4 text-slate-300">{selected.summary}</p><div className="mt-5 grid gap-3 sm:grid-cols-2"><div className="metric"><small>Current owner</small><strong>{selected.owner}</strong></div><div className="metric"><small>Version</small><strong>{selected.version}</strong></div></div><div className="mt-5 flex flex-wrap gap-3">{actions.map(action => <button key={action.label} disabled={busyAction} onClick={() => void act(action.fn)} className="primary">{busyAction ? <Activity className="h-4 w-4 animate-pulse" /> : null}{action.label}</button>)}</div></article>
        <article className="panel"><h2 className="text-xl font-semibold">Audit timeline</h2><div className="mt-5 space-y-4">{selected.case_events.map(event => <div key={event.event_id} className="border-l border-slate-700 pl-4"><p className="font-medium">{readable(event.action)} · {event.to_status}</p><p className="text-sm text-slate-400">{event.actor} ({event.actor_role})</p>{event.note && <p className="mt-1 text-sm text-slate-500">{event.note}</p>}</div>)}</div></article>
      </section>}
    </div>
  </main>;
}

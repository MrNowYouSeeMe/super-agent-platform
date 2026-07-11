import { Activity, AlertTriangle, CheckCircle2, Database, Play, ShieldCheck, TriangleAlert, WalletCards, XCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { z } from "zod";

const DashboardSchema = z.object({
  agent_id: z.string(),
  agent_name: z.string(),
  shared_cash: z.object({ resource_id:z.string(), label:z.string(), balance:z.number(), safe_threshold:z.number(), status:z.string(), currency:z.string() }),
  provider_balances: z.array(z.object({ resource_id:z.string(), label:z.string(), balance:z.number(), safe_threshold:z.number(), status:z.string(), currency:z.string() })),
  active_alerts: z.number(),
  cases_under_review: z.number(),
  data_feeds: z.array(z.object({ provider_id:z.string(), label:z.string(), status:z.string(), age_minutes:z.number() }))
});

const EventSchema = z.object({
  sequence:z.number(), stage:z.string(), label:z.string(), status:z.enum(["completed","warning","failed"]), detail:z.string().nullable(), metric:z.union([z.string(),z.number()]).nullable(), created_at:z.string()
});

const ResultSchema = z.object({
  analysis_id:z.string(), agent_id:z.string(), classification:z.string(), affected_resource:z.string(), affected_provider:z.string(), shortage_eta_minutes:z.number().nullable(), confidence:z.number(), confidence_adjustments:z.array(z.object({reason:z.string(),impact:z.number()})), records_checked:z.number(), supporting_claims:z.number(), conflicting_records:z.number(), evidence:z.array(z.string()), possible_normal_context:z.array(z.string()), recommendation:z.string(), recommended_owner:z.string(), summary:z.string(), safe_boundary:z.string()
});

const SnapshotSchema = z.object({
  analysis_id:z.string(), status:z.enum(["queued","running","completed","failed"]), events:z.array(EventSchema), result:ResultSchema.nullable(), error:z.string().nullable()
});

type Dashboard = z.infer<typeof DashboardSchema>;
type Event = z.infer<typeof EventSchema>;
type Result = z.infer<typeof ResultSchema>;
type Language = "en" | "bn" | "banglish";
type Scenario = "liquidity_anomaly" | "normal_day" | "data_conflict";

async function jsonRequest<T>(url:string, schema:z.ZodType<T>, options:RequestInit = {}):Promise<T>{
  const response = await fetch(url,{...options,headers:{"Content-Type":"application/json",...options.headers}});
  const payload = await response.json();
  if(!response.ok) throw new Error(payload.detail ?? `HTTP ${response.status}`);
  const parsed = schema.safeParse(payload);
  if(!parsed.success) throw new Error("Runtime response validation failed");
  return parsed.data;
}

function money(value:number){
  return new Intl.NumberFormat("en-BD",{style:"currency",currency:"BDT",maximumFractionDigits:0}).format(value);
}

function nice(value:string){ return value.replaceAll("_"," "); }

export default function App(){
  const [dashboard,setDashboard] = useState<Dashboard|null>(null);
  const [events,setEvents] = useState<Event[]>([]);
  const [result,setResult] = useState<Result|null>(null);
  const [language,setLanguage] = useState<Language>("banglish");
  const [scenario,setScenario] = useState<Scenario>("liquidity_anomaly");
  const [running,setRunning] = useState(false);
  const [error,setError] = useState<string|null>(null);
  const sourceRef = useRef<EventSource|null>(null);

  useEffect(()=>{
    jsonRequest("/api/v1/dashboard",DashboardSchema).then(setDashboard).catch(e=>setError(e.message));
    return ()=>sourceRef.current?.close();
  },[]);

  async function poll(id:string){
    for(let i=0;i<50;i++){
      const snapshot = await jsonRequest(`/api/v1/analyses/${id}`,SnapshotSchema);
      setEvents(snapshot.events);
      if(snapshot.status === "completed" && snapshot.result){ setResult(snapshot.result); setRunning(false); return; }
      if(snapshot.status === "failed"){ setError(snapshot.error ?? "Analysis failed"); setRunning(false); return; }
      await new Promise(r=>setTimeout(r,400));
    }
    setError("Analysis timeout");
    setRunning(false);
  }

  async function run(){
    setError(null); setEvents([]); setResult(null); setRunning(true); sourceRef.current?.close();
    try{
      const accepted = await jsonRequest(
        "/api/v1/analyses",
        z.object({analysis_id:z.string(),status:z.string()}),
        {method:"POST",body:JSON.stringify({agent_id:"AGT-SYL-017",scenario,language})}
      );
      const source = new EventSource(`/api/v1/analyses/${accepted.analysis_id}/events`);
      sourceRef.current = source;
      source.onmessage = message => {
        const parsed = EventSchema.safeParse(JSON.parse(message.data));
        if(parsed.success){
          setEvents(current => current.some(e=>e.sequence===parsed.data.sequence) ? current : [...current,parsed.data]);
          if(parsed.data.stage === "analysis_completed"){ source.close(); void poll(accepted.analysis_id); }
        }
      };
      source.onerror = ()=>{ source.close(); void poll(accepted.analysis_id); };
    }catch(e){ setError(e instanceof Error ? e.message : "Failed"); setRunning(false); }
  }

  return <main className="shell">
    <div className="wrap">
      <header className="header">
        <div>
          <div className="eyebrow"><ShieldCheck size={17}/> Responsible multi-provider decision support</div>
          <h1>SuperAgent Sentinel</h1>
          <p>Liquidity forecasting, explainable anomaly evidence, data-quality uncertainty and safe human coordination.</p>
        </div>
        <div className="controls">
          <select value={scenario} disabled={running} onChange={e=>setScenario(e.target.value as Scenario)}>
            <option value="liquidity_anomaly">Liquidity + anomaly</option>
            <option value="normal_day">Normal operation</option>
            <option value="data_conflict">Data conflict</option>
          </select>
          <select value={language} disabled={running} onChange={e=>setLanguage(e.target.value as Language)}>
            <option value="en">English</option><option value="bn">à¦¬à¦¾à¦‚à¦²à¦¾</option><option value="banglish">Banglish</option>
          </select>
          <button disabled={running} onClick={run}>{running?<Activity className="pulse"/>:<Play/>}{running?"Running":"Run intelligence"}</button>
        </div>
      </header>

      {error && <div className="error"><AlertTriangle/> {error}</div>}

      <section className="cards">
        {dashboard && <>
          <article className="card accent"><WalletCards/><span className="tag pressure">{dashboard.shared_cash.status}</span><small>{dashboard.shared_cash.label}</small><strong>{money(dashboard.shared_cash.balance)}</strong><em>Safe threshold {money(dashboard.shared_cash.safe_threshold)}</em></article>
          {dashboard.provider_balances.map(item=><article className="card" key={item.resource_id}><Database/><span className={`tag ${item.status}`}>{item.status}</span><small>{item.label}</small><strong>{money(item.balance)}</strong><em>Separate provider balance</em></article>)}
        </>}
      </section>

      <section className="grid">
        <article className="panel">
          <h2>Live intelligence workflow</h2><p>Actual backend stages, not a generic spinner.</p>
          <div className="timeline">
            {events.length===0 && <div className="empty">Run intelligence to inspect the pipeline.</div>}
            {events.map(event=><div className="event" key={event.sequence}>{event.status==="warning"?<TriangleAlert className="warn"/>:event.status==="failed"?<XCircle className="fail"/>:<CheckCircle2 className="ok"/>}<div><b>{event.label}</b>{event.detail&&<span>{event.detail}</span>}</div></div>)}
          </div>
        </article>

        <div className="side">
          <article className="panel"><h2>Provider feed health</h2>{dashboard?.data_feeds.map(feed=><div className="feed" key={feed.provider_id}><div><b>{feed.label}</b><span>{feed.age_minutes} min ago</span></div><span className={`tag ${feed.status}`}>{feed.status}</span></div>)}</article>
          <article className="panel"><h2>Operational status</h2><div className="stats"><div><strong>{dashboard?.active_alerts ?? "â€”"}</strong><span>Active alerts</span></div><div><strong>{dashboard?.cases_under_review ?? "â€”"}</strong><span>Under review</span></div></div></article>
        </div>
      </section>

      {result && <section className="result">
        <div className="resultTop"><span className="pill">{nice(result.classification)}</span><span className="pill cyan">{Math.round(result.confidence*100)}% confidence</span></div>
        <h2>Decision-support recommendation</h2><p className="summary">{result.summary}</p>
        <div className="metrics"><div><span>Shortage ETA</span><strong>{result.shortage_eta_minutes ?? "â€”"} min</strong></div><div><span>Provider</span><strong>{result.affected_provider}</strong></div><div><span>Owner</span><strong>{result.recommended_owner}</strong></div><div><span>Safe action</span><strong>{nice(result.recommendation)}</strong></div></div>
        <div className="resultGrid"><div><h3>Evidence</h3>{result.evidence.map(item=><p key={item}><CheckCircle2 size={16}/>{item}</p>)}</div><div><h3>Possible normal context</h3>{result.possible_normal_context.map(item=><p key={item}>â€¢ {item}</p>)}</div></div>
        <div className="safe"><b>Safe boundary:</b> {result.safe_boundary}</div>
      </section>}
    </div>
  </main>;
}
import { z } from "zod";

const UserSchema = z.object({
  username: z.string(),
  display_name: z.string(),
  role: z.enum([
    "OUTLET_OPERATOR",
    "AREA_MANAGER",
    "CENTRAL_OPERATIONS",
    "RISK_REVIEWER",
    "ADMIN",
  ]),
  outlet_ids: z.array(z.string()),
});

const TokenSchema = z.object({
  access_token: z.string(),
  token_type: z.literal("bearer"),
  expires_at: z.string(),
  user: UserSchema,
});

export type AuthSession = z.infer<typeof TokenSchema>;

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

const TOKEN_STORAGE_KEY = "superagent_sentinel_token";

let authToken = window.localStorage.getItem(TOKEN_STORAGE_KEY);

export function setAuthToken(token: string) {
  authToken = token;
  window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
}

export function clearAuthToken() {
  authToken = null;
  window.localStorage.removeItem(TOKEN_STORAGE_KEY);
}

export function getAuthToken() {
  return authToken;
}

const EventSchema = z.object({
  sequence: z.number(),
  stage: z.string(),
  label: z.string(),
  status: z.enum(["completed", "warning", "failed"]),
  detail: z.string().nullable(),
  metric: z.union([z.string(), z.number()]).nullable(),
  created_at: z.string(),
});

const ResultSchema = z.object({
  analysis_id: z.string(),
  alert_id: z.string().nullable(),
  agent_id: z.string(),
  classification: z.string(),
  affected_resource: z.string(),
  affected_provider: z.string(),
  shortage_eta_minutes: z.number().nullable(),
  confidence: z.number(),
  confidence_adjustments: z.array(z.object({ reason: z.string(), impact: z.number() })),
  records_checked: z.number(),
  supporting_claims: z.number(),
  conflicting_records: z.number(),
  evidence: z.array(z.string()),
  possible_normal_context: z.array(z.string()),
  recommendation: z.string(),
  recommended_owner: z.string(),
  summary: z.string(),
  safe_boundary: z.string(),
});

const SnapshotSchema = z.object({
  analysis_id: z.string(),
  status: z.enum(["queued", "running", "completed", "failed"]),
  events: z.array(EventSchema),
  result: ResultSchema.nullable(),
  error: z.string().nullable(),
});

const DashboardSchema = z.object({
  agent_id: z.string(),
  agent_name: z.string(),
  shared_cash: z.object({
    resource_id: z.string(), label: z.string(), balance: z.number(),
    safe_threshold: z.number(), status: z.string(), currency: z.literal("BDT"),
  }),
  provider_balances: z.array(z.object({
    resource_id: z.string(), label: z.string(), balance: z.number(),
    safe_threshold: z.number(), status: z.string(), currency: z.literal("BDT"),
  })),
  active_alerts: z.number(),
  cases_under_review: z.number(),
  data_feeds: z.array(z.object({
    provider_id: z.string(), label: z.string(), status: z.string(), age_minutes: z.number(),
  })),
});


const ForecastMetricSchema = z.object({
  model: z.string(),
  mae_bdt: z.number(),
  rmse_bdt: z.number(),
  mape_percent: z.number(),
  evaluated_rows: z.number(),
});

const ClassificationMetricSchema = z.object({
  precision: z.number(), recall: z.number(), f1: z.number(), false_positive_rate: z.number(),
  true_positive: z.number(), false_positive: z.number(), true_negative: z.number(), false_negative: z.number(),
});

const EvaluationReportSchema = z.object({
  report_version: z.string(),
  generated_at: z.string(),
  dataset_version: z.string(),
  seed: z.number(),
  split_strategy: z.string(),
  champion_forecast_model: z.string(),
  forecast_candidates: z.array(ForecastMetricSchema),
  shortage_detection: ClassificationMetricSchema.extend({
    mean_lead_time_minutes: z.number(),
    median_lead_time_minutes: z.number(),
  }),
  anomaly_detection: ClassificationMetricSchema,
  data_quality_detection: ClassificationMetricSchema,
  explanation_coverage: z.number(),
  safe_language_coverage: z.number(),
  evaluation_runtime_ms: z.number(),
  measured_metrics_count: z.number(),
  notes: z.array(z.string()),
  limitations: z.array(z.string()),
});

const CaseEventSchema = z.object({
  event_id: z.number(),
  action: z.string(),
  actor: z.string(),
  actor_role: z.string(),
  from_status: z.string().nullable(),
  to_status: z.string(),
  note: z.string().nullable(),
  created_at: z.string(),
});

const AlertSchema = z.object({
  alert_id: z.string(),
  analysis_id: z.string(),
  agent_id: z.string(),
  classification: z.string(),
  severity: z.enum(["low", "medium", "high"]),
  affected_resource: z.string(),
  affected_provider: z.string(),
  shortage_eta_minutes: z.number().nullable(),
  confidence: z.number(),
  recommendation: z.string(),
  owner: z.string(),
  status: z.enum(["OPEN", "ASSIGNED", "ACKNOWLEDGED", "UNDER_REVIEW", "ESCALATED", "RESOLVED"]),
  summary: z.string(),
  evidence: z.array(z.string()),
  possible_normal_context: z.array(z.string()),
  version: z.number(),
  created_at: z.string(),
  updated_at: z.string(),
  case_events: z.array(CaseEventSchema),
});

export type AnalysisEvent = z.infer<typeof EventSchema>;
export type AnalysisResult = z.infer<typeof ResultSchema>;
export type Dashboard = z.infer<typeof DashboardSchema>;
export type Alert = z.infer<typeof AlertSchema>;
export type EvaluationReport = z.infer<typeof EvaluationReportSchema>;

async function request<T>(path: string, schema: z.ZodType<T>, options: RequestInit = {}): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 12000);
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      ...options,
      signal: controller.signal,
      headers: { Accept: "application/json", "Content-Type": "application/json", ...options.headers },
    });
    const payload: unknown = await response.json();
    if (!response.ok) {
      const detail = typeof payload === "object" && payload && "detail" in payload
        ? String(payload.detail) : `HTTP ${response.status}`;
      throw new Error(detail);
    }
    const parsed = schema.safeParse(payload);
    if (!parsed.success) throw new Error("Runtime response validation failed.");
    return parsed.data;
  } finally {
    window.clearTimeout(timer);
  }
}

export const getDashboard = () => request("/api/v1/dashboard", DashboardSchema);
export const getEvaluation = () => request("/api/v1/evaluation/report", EvaluationReportSchema);
export const listAlerts = () => request("/api/v1/alerts", z.array(AlertSchema));
export const getAlert = (id: string) => request(`/api/v1/alerts/${id}`, AlertSchema);
export const getAnalysis = (id: string) => request(`/api/v1/analyses/${id}`, SnapshotSchema);

export async function startAnalysis(language: "en" | "bn" | "banglish", scenario: string) {
  return request(
    "/api/v1/analyses",
    z.object({ analysis_id: z.string(), status: z.string() }),
    { method: "POST", body: JSON.stringify({ agent_id: "AGT-SYL-017", language, scenario }) },
  );
}

export function subscribe(id: string, onEvent: (event: AnalysisEvent) => void, onError: () => void) {
  const source = new EventSource(`${API_BASE}/api/v1/analyses/${id}/events`);
  source.onmessage = (message) => {
    const parsed = EventSchema.safeParse(JSON.parse(message.data));
    if (parsed.success) onEvent(parsed.data);
  };
  source.onerror = () => { source.close(); onError(); };
  return () => source.close();
}

async function transition(id: string, action: string, alert: Alert, extra: Record<string, unknown> = {}) {
  return request(`/api/v1/alerts/${id}/${action}`, AlertSchema, {
    method: "POST",
    body: JSON.stringify({
      actor: "Demo Operations User",
      actor_role: "operations_manager",
      note: `Demo ${action.replaceAll("-", " ")} action`,
      expected_version: alert.version,
      ...extra,
    }),
  });
}

export const assign = (alert: Alert) => transition(alert.alert_id, "assign", alert, { owner: "bKash Field Officer" });
export const acknowledge = (alert: Alert) => transition(alert.alert_id, "acknowledge", alert);
export const startReview = (alert: Alert) => transition(alert.alert_id, "start-review", alert);
export const escalate = (alert: Alert) => transition(alert.alert_id, "escalate", alert);
export const resolve = (alert: Alert) => transition(alert.alert_id, "resolve", alert);


export async function login(username: string, password: string) {
  const session = await request(
    "/api/v1/auth/login",
    TokenSchema,
    {
      method: "POST",
      body: JSON.stringify({ username, password }),
    },
  );

  setAuthToken(session.access_token);
  return session;
}

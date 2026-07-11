import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../src/App";

const apiMocks = vi.hoisted(() => ({
  acknowledge: vi.fn(),
  assign: vi.fn(),
  escalate: vi.fn(),
  getAlert: vi.fn(),
  getAnalysis: vi.fn(),
  getDashboard: vi.fn(),
  getEvaluation: vi.fn(),
  listAlerts: vi.fn(),
  resolve: vi.fn(),
  startAnalysis: vi.fn(),
  startReview: vi.fn(),
  subscribe: vi.fn(),
}));

vi.mock("../src/api", () => apiMocks);

const dashboard = {
  agent_id: "AGT-SYL-017",
  agent_name: "Zindabazar Multi-Provider Outlet",
  shared_cash: {
    resource_id: "shared_cash",
    label: "Shared Physical Cash",
    balance: 155000,
    safe_threshold: 20000,
    status: "pressure",
    currency: "BDT",
  },
  provider_balances: [],
  active_alerts: 0,
  cases_under_review: 0,
  data_feeds: [],
};

const classificationMetrics = {
  precision: 0.9,
  recall: 0.81,
  f1: 0.85,
  false_positive_rate: 0.02,
  true_positive: 10,
  false_positive: 1,
  true_negative: 20,
  false_negative: 2,
};

const evaluation = {
  report_version: "phase3-evaluation-v1",
  generated_at: "2026-07-11T00:00:00Z",
  dataset_version: "phase3-synthetic-v1",
  seed: 20260711,
  split_strategy: "time_ordered",
  champion_forecast_model: "ewma_net_change",
  forecast_candidates: [
    {
      model: "ewma_net_change",
      mae_bdt: 8445.92,
      rmse_bdt: 10000,
      mape_percent: 11.13,
      evaluated_rows: 100,
    },
  ],
  shortage_detection: {
    ...classificationMetrics,
    mean_lead_time_minutes: 180,
    median_lead_time_minutes: 160,
  },
  anomaly_detection: classificationMetrics,
  data_quality_detection: classificationMetrics,
  explanation_coverage: 1,
  safe_language_coverage: 1,
  evaluation_runtime_ms: 10,
  measured_metrics_count: 16,
  notes: [],
  limitations: [],
};

const event = {
  sequence: 1,
  stage: "analysis_completed",
  label: "Analysis completed",
  status: "completed",
  detail: "Worker completed safely.",
  metric: null,
  created_at: "2026-07-11T00:00:00Z",
};

const result = {
  analysis_id: "analysis-1",
  alert_id: null,
  agent_id: "AGT-SYL-017",
  classification: "requires_review",
  affected_resource: "shared_cash",
  affected_provider: "bKash",
  shortage_eta_minutes: 180,
  confidence: 0.88,
  confidence_adjustments: [],
  records_checked: 10,
  supporting_claims: 8,
  conflicting_records: 0,
  evidence: ["Synthetic evidence"],
  possible_normal_context: ["Festival demand"],
  recommendation: "request_approved_cash_support",
  recommended_owner: "Operations manager",
  summary: "Shared cash pressure requires human review.",
  safe_boundary: "No automatic financial action.",
};

const completedSnapshot = {
  analysis_id: "analysis-1",
  status: "completed",
  events: [event],
  result,
  error: null,
};

async function loadApp(): Promise<void> {
  render(<App />);
  await screen.findByText("Phase 3 evaluation evidence");
}

beforeEach(() => {
  vi.clearAllMocks();

  apiMocks.getDashboard.mockResolvedValue(dashboard);
  apiMocks.getEvaluation.mockResolvedValue(evaluation);
  apiMocks.listAlerts.mockResolvedValue([]);
  apiMocks.startAnalysis.mockResolvedValue({
    analysis_id: "analysis-1",
    status: "queued",
  });
  apiMocks.subscribe.mockReturnValue(vi.fn());
  apiMocks.getAnalysis.mockResolvedValue(completedSnapshot);
});

afterEach(() => {
  cleanup();
});

describe("App analysis resilience", () => {
  it("loads evidence and completes an SSE-triggered analysis", async () => {
    await loadApp();

    fireEvent.click(
      screen.getByRole("button", { name: /Run intelligence/i }),
    );

    await waitFor(() => {
      expect(apiMocks.subscribe).toHaveBeenCalledTimes(1);
    });

    const onEvent = apiMocks.subscribe.mock.calls[0][1] as (
      value: typeof event,
    ) => void;

    await act(async () => {
      onEvent(event);
    });

    await waitFor(() => {
      expect(apiMocks.getAnalysis).toHaveBeenCalledWith("analysis-1");
    });

    expect(await screen.findByText(result.summary)).toBeInTheDocument();
    expect(screen.getByText("Analysis completed")).toBeInTheDocument();
  });

  it("surfaces a safe error when analysis creation fails", async () => {
    apiMocks.startAnalysis.mockRejectedValueOnce(new Error("Start failed."));

    await loadApp();

    fireEvent.click(
      screen.getByRole("button", { name: /Run intelligence/i }),
    );

    expect(await screen.findByText("Start failed.")).toBeInTheDocument();
  });

  it("falls back to polling and reports a polling failure", async () => {
    apiMocks.getAnalysis.mockRejectedValueOnce(new Error("Polling failed."));

    await loadApp();

    fireEvent.click(
      screen.getByRole("button", { name: /Run intelligence/i }),
    );

    await waitFor(() => {
      expect(apiMocks.subscribe).toHaveBeenCalledTimes(1);
    });

    const onError = apiMocks.subscribe.mock.calls[0][2] as () => void;

    await act(async () => {
      onError();
    });

    expect(await screen.findByText("Polling failed.")).toBeInTheDocument();
  });
});

import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { TraceEventItem } from "@/components/live-trace/trace-event-item";
import type { TraceEvent, EventType } from "@/types/event";

// Mock date-fns to avoid time-dependent output
vi.mock("date-fns", () => ({
  formatDistanceToNow: () => "just now",
}));

function makeEvent(overrides: Partial<TraceEvent> = {}): TraceEvent {
  return {
    id: "evt-1",
    session_id: "sess-1",
    event_type: "INFO",
    step: "profiling",
    payload: {},
    created_at: new Date().toISOString(),
    ...overrides,
  };
}

describe("TraceEventItem", () => {
  // ---- Basic rendering ----

  it("renders event type badge", () => {
    render(<TraceEventItem event={makeEvent()} />);
    expect(screen.getByText("INFO")).toBeInTheDocument();
  });

  it("renders relative timestamp", () => {
    render(<TraceEventItem event={makeEvent()} />);
    expect(screen.getByText("just now")).toBeInTheDocument();
  });

  // ---- DECISION event ----

  it("renders DECISION with action summary", () => {
    const event = makeEvent({
      event_type: "DECISION",
      payload: { step: "modeling", action: "Train models", reasoning: "Data ready" },
    });
    render(<TraceEventItem event={event} />);
    expect(screen.getByText("DECISION")).toBeInTheDocument();
    expect(screen.getByText("Train models")).toBeInTheDocument();
  });

  it("renders DECISION step badge and reasoning when expanded", () => {
    const event = makeEvent({
      event_type: "DECISION",
      payload: { step: "eda", action: "Run EDA", reasoning: "Profiling complete" },
    });
    render(<TraceEventItem event={event} />);

    // Click to expand
    fireEvent.click(screen.getByText("DECISION"));

    expect(screen.getByText("eda")).toBeInTheDocument();
    expect(screen.getByText("Action:")).toBeInTheDocument();
    // "Run EDA" appears in both summary and expanded content
    expect(screen.getAllByText("Run EDA").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("Reasoning:")).toBeInTheDocument();
    expect(screen.getByText("Profiling complete")).toBeInTheDocument();
  });

  // ---- AI_REASONING event ----

  it("renders AI_REASONING with truncated summary", () => {
    const longText = "A".repeat(100);
    const event = makeEvent({
      event_type: "AI_REASONING",
      payload: { reasoning: longText },
    });
    render(<TraceEventItem event={event} />);
    expect(screen.getByText("AI_REASONING")).toBeInTheDocument();
    // Summary is truncated to 80 chars + "..."
    const expected = "A".repeat(80) + "...";
    expect(screen.getByText(expected)).toBeInTheDocument();
  });

  it("renders AI_REASONING blockquote when expanded", () => {
    const event = makeEvent({
      event_type: "AI_REASONING",
      payload: { reasoning: "The data shows strong signal" },
    });
    render(<TraceEventItem event={event} />);

    fireEvent.click(screen.getByText("AI_REASONING"));

    // Text appears in summary and blockquote; find the blockquote element
    const matches = screen.getAllByText("The data shows strong signal");
    const inBlockquote = matches.find((el) => el.closest("blockquote"));
    expect(inBlockquote).toBeTruthy();
  });

  // ---- MODEL_SELECTION event ----

  it("renders MODEL_SELECTION with chosen model", () => {
    const event = makeEvent({
      event_type: "MODEL_SELECTION",
      payload: {
        chosen_model: "random_forest",
        models: ["logistic_regression", "random_forest", "gradient_boosting"],
      },
    });
    render(<TraceEventItem event={event} />);
    expect(screen.getByText("MODEL_SELECTION")).toBeInTheDocument();
    expect(screen.getByText("random_forest")).toBeInTheDocument();
  });

  it("renders MODEL_SELECTION model list when expanded", async () => {
    // expand by clicking
    const event = makeEvent({
      event_type: "MODEL_SELECTION",
      payload: {
        chosen_model: "random_forest",
        models: ["logistic_regression", "random_forest", "gradient_boosting"],
        reasoning: "Best F1 score",
      },
    });
    render(<TraceEventItem event={event} />);

    fireEvent.click(screen.getByText("MODEL_SELECTION"));

    expect(screen.getByText("Selected:")).toBeInTheDocument();
    expect(screen.getByText("logistic_regression")).toBeInTheDocument();
    expect(screen.getByText("gradient_boosting")).toBeInTheDocument();
    expect(screen.getByText("Best F1 score")).toBeInTheDocument();
  });

  // ---- FINAL_SUMMARY event ----

  it("renders FINAL_SUMMARY with title summary", () => {
    const event = makeEvent({
      event_type: "FINAL_SUMMARY",
      payload: {
        title: "Analysis Complete",
        summary: "Pipeline finished successfully",
        key_findings: ["High churn risk", "Revenue growth potential"],
      },
    });
    render(<TraceEventItem event={event} />);
    expect(screen.getByText("FINAL_SUMMARY")).toBeInTheDocument();
    expect(screen.getByText("Analysis Complete")).toBeInTheDocument();
  });

  it("renders FINAL_SUMMARY card with findings when expanded", () => {
    const event = makeEvent({
      event_type: "FINAL_SUMMARY",
      payload: {
        title: "Pipeline Results",
        summary: "All steps completed",
        key_findings: ["Finding A", "Finding B"],
      },
    });
    render(<TraceEventItem event={event} />);

    fireEvent.click(screen.getByText("FINAL_SUMMARY"));

    // Title appears in both summary and expanded card
    expect(screen.getAllByText("Pipeline Results").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("All steps completed")).toBeInTheDocument();
    expect(screen.getByText("Finding A")).toBeInTheDocument();
    expect(screen.getByText("Finding B")).toBeInTheDocument();
  });

  it("renders FINAL_SUMMARY default title when none provided", () => {
    const event = makeEvent({
      event_type: "FINAL_SUMMARY",
      payload: { summary: "Done" },
    });
    render(<TraceEventItem event={event} />);
    expect(screen.getByText("Pipeline Summary")).toBeInTheDocument();
  });

  // ---- Other new event types (icon + badge rendering) ----

  const newEventTypes: EventType[] = [
    "TOOL_DISCOVERY",
    "CODE_REUSE",
    "DOC_UPDATED",
    "ARTIFACT_CREATED",
    "STAGE_RERUN",
    "CODE_EDITED",
    "ARTIFACT",
    "WARNING",
    "USER_INPUT",
    "STEP_STALE",
  ];

  it.each(newEventTypes)("renders %s event with correct badge", (eventType) => {
    const event = makeEvent({ event_type: eventType, payload: { info: "test" } });
    render(<TraceEventItem event={event} />);
    expect(screen.getByText(eventType)).toBeInTheDocument();
  });

  // ---- TOOL_CALL / TOOL_RESULT rendering ----

  it("renders TOOL_CALL with server.tool summary", () => {
    const event = makeEvent({
      event_type: "TOOL_CALL",
      payload: { server: "eda_plots", tool: "distribution_plot" },
    });
    render(<TraceEventItem event={event} />);
    expect(screen.getByText("eda_plots.distribution_plot")).toBeInTheDocument();
  });

  it("renders TOOL_RESULT success status when expanded", async () => {
    // expand by clicking
    const event = makeEvent({
      event_type: "TOOL_RESULT",
      payload: { success: true, server: "modeling", tool: "train" },
    });
    render(<TraceEventItem event={event} />);

    fireEvent.click(screen.getByText("TOOL_RESULT"));

    expect(screen.getByText("Success")).toBeInTheDocument();
  });

  it("renders TOOL_RESULT failure with error", async () => {
    // expand by clicking
    const event = makeEvent({
      event_type: "TOOL_RESULT",
      payload: { success: false, error: "File not found" },
    });
    render(<TraceEventItem event={event} />);

    expect(screen.getByText(/Failed/)).toBeInTheDocument();
  });

  // ---- PLAN event ----

  it("renders PLAN with message", async () => {
    // expand by clicking
    const event = makeEvent({
      event_type: "PLAN",
      payload: { message: "Starting data profiling" },
    });
    render(<TraceEventItem event={event} />);

    expect(screen.getByText("Starting data profiling")).toBeInTheDocument();
  });

  // ---- Empty payload ----

  it("does not show chevron when payload is empty", () => {
    const event = makeEvent({ payload: {} });
    const { container } = render(<TraceEventItem event={event} />);
    // ChevronDown should not be rendered when there's no payload
    const chevrons = container.querySelectorAll("[class*='rotate-180']");
    // Should not find any rotated chevrons (also no chevron at all)
    expect(chevrons.length).toBe(0);
  });
});

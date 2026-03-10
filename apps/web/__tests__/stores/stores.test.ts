import { describe, it, expect, beforeEach } from "vitest";
import { act } from "@testing-library/react";
import { useTraceStore } from "@/stores/trace-store";
import { useModalStore } from "@/stores/modal-store";
import type { TraceEvent } from "@/types/event";
import type { CodeProposal, CodeContext } from "@/types/api";

describe("traceStore", () => {
  beforeEach(() => {
    act(() => {
      useTraceStore.getState().clearEvents();
      useTraceStore.getState().setConnected(false);
    });
  });

  it("starts with empty events", () => {
    expect(useTraceStore.getState().events).toEqual([]);
  });

  it("starts disconnected", () => {
    expect(useTraceStore.getState().isConnected).toBe(false);
  });

  it("addEvent appends an event", () => {
    const event = {
      id: "1",
      session_id: "s1",
      event_type: "INFO" as const,
      step: "eda",
      payload: {},
      created_at: "2024-01-01",
    } satisfies TraceEvent;

    act(() => useTraceStore.getState().addEvent(event));

    expect(useTraceStore.getState().events).toHaveLength(1);
    expect(useTraceStore.getState().events[0].id).toBe("1");
  });

  it("caps events at MAX_EVENTS (500)", () => {
    act(() => {
      for (let i = 0; i < 510; i++) {
        useTraceStore.getState().addEvent({
          id: String(i),
          session_id: "s1",
          event_type: "INFO",
          step: "eda",
          payload: {},
          created_at: "2024-01-01",
        } as TraceEvent);
      }
    });

    expect(useTraceStore.getState().events).toHaveLength(500);
    // Oldest events should be discarded
    expect(useTraceStore.getState().events[0].id).toBe("10");
  });

  it("clearEvents resets to empty", () => {
    act(() => {
      useTraceStore.getState().addEvent({
        id: "1",
        session_id: "s1",
        event_type: "INFO",
        step: "eda",
        payload: {},
        created_at: "2024-01-01",
      } as TraceEvent);
      useTraceStore.getState().clearEvents();
    });

    expect(useTraceStore.getState().events).toEqual([]);
  });

  it("setConnected updates the flag", () => {
    act(() => useTraceStore.getState().setConnected(true));
    expect(useTraceStore.getState().isConnected).toBe(true);

    act(() => useTraceStore.getState().setConnected(false));
    expect(useTraceStore.getState().isConnected).toBe(false);
  });
});

describe("modalStore", () => {
  beforeEach(() => {
    act(() => useModalStore.getState().closeModal());
  });

  it("starts closed with null proposal", () => {
    expect(useModalStore.getState().isOpen).toBe(false);
    expect(useModalStore.getState().proposal).toBeNull();
  });

  it("openModal sets isOpen and proposal", () => {
    const proposal: CodeProposal = {
      id: "p1",
      session_id: "s1",
      step: "eda",
      language: "python",
      code: "print('hi')",
      description: "test",
      status: "pending",
    };

    act(() => useModalStore.getState().openModal(proposal));

    expect(useModalStore.getState().isOpen).toBe(true);
    expect(useModalStore.getState().proposal).toEqual(proposal);
  });

  it("closeModal resets state", () => {
    const proposal: CodeProposal = {
      id: "p1",
      session_id: "s1",
      step: "eda",
      language: "python",
      code: "print('hi')",
      description: "test",
      status: "pending",
    };

    act(() => {
      useModalStore.getState().openModal(proposal);
      useModalStore.getState().closeModal();
    });

    expect(useModalStore.getState().isOpen).toBe(false);
    expect(useModalStore.getState().proposal).toBeNull();
  });

  it("starts with null context", () => {
    expect(useModalStore.getState().context).toBeNull();
  });

  it("openModal with context stores both proposal and context", () => {
    const proposal: CodeProposal = {
      id: "p2",
      session_id: "s1",
      step: "modeling",
      language: "python",
      code: "model.fit(X, y)",
      description: "Train model",
      status: "pending",
    };
    const context: CodeContext = {
      ai_explanation: "Training random forest for churn prediction",
      tool_tried: "modeling_explain.train",
      tool_insufficiency: "",
      alternative_strategies: ["gradient_boosting", "svm"],
      denial_count: 0,
      max_denials: 3,
      denial_feedback: [],
    };

    act(() => useModalStore.getState().openModal(proposal, context));

    expect(useModalStore.getState().isOpen).toBe(true);
    expect(useModalStore.getState().proposal).toEqual(proposal);
    expect(useModalStore.getState().context).toEqual(context);
  });

  it("openModal without context defaults context to null", () => {
    const proposal: CodeProposal = {
      id: "p3",
      session_id: "s1",
      step: "eda",
      language: "python",
      code: "plot()",
      description: "Generate plots",
      status: "pending",
    };

    act(() => useModalStore.getState().openModal(proposal));

    expect(useModalStore.getState().context).toBeNull();
  });

  it("closeModal resets context to null", () => {
    const proposal: CodeProposal = {
      id: "p4",
      session_id: "s1",
      step: "preprocessing",
      language: "python",
      code: "clean(df)",
      description: "Clean data",
      status: "pending",
    };
    const context: CodeContext = {
      ai_explanation: "Cleaning missing values",
      tool_tried: "preprocessing.handle_missing",
      tool_insufficiency: "",
      alternative_strategies: ["drop", "impute_median"],
      denial_count: 1,
      max_denials: 3,
      denial_feedback: ["Too aggressive"],
    };

    act(() => {
      useModalStore.getState().openModal(proposal, context);
      useModalStore.getState().closeModal();
    });

    expect(useModalStore.getState().context).toBeNull();
  });
});

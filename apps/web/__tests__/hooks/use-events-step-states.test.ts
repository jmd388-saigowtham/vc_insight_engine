import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook } from "@testing-library/react";

// Mock dependencies
const mockAddEvent = vi.fn();
const mockSetConnected = vi.fn();
const mockSetEvents = vi.fn();
const mockInvalidateQueries = vi.fn();
let mockEventHandler: ((event: any) => void) | null = null;
let mockOpenHandler: (() => void) | null = null;

vi.mock("@/stores/trace-store", () => ({
  useTraceStore: (selector: any) =>
    selector({
      addEvent: mockAddEvent,
      setConnected: mockSetConnected,
      setEvents: mockSetEvents,
      events: [],
    }),
}));

vi.mock("@/stores/modal-store", () => ({
  useModalStore: {
    getState: () => ({ openModal: vi.fn() }),
  },
}));

vi.mock("@/stores/proposal-store", () => ({
  useProposalStore: {
    getState: () => ({ openProposal: vi.fn() }),
  },
}));

vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({
    invalidateQueries: mockInvalidateQueries,
  }),
}));

vi.mock("@/lib/api-client", () => ({
  api: {
    get: vi.fn().mockResolvedValue([]),
  },
}));

vi.mock("@/lib/sse-client", () => ({
  createEventSource: vi.fn((opts: any) => {
    mockEventHandler = opts.onEvent;
    mockOpenHandler = opts.onOpen;
    return { close: vi.fn() };
  }),
}));

import { useEventStream } from "@/hooks/use-events";

describe("useEventStream — step-states invalidation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockEventHandler = null;
    mockOpenHandler = null;
  });

  it("invalidates step-states on STEP_STALE event", async () => {
    renderHook(() => useEventStream("sess-123"));

    // Wait for init to complete
    await vi.waitFor(() => {
      expect(mockEventHandler).not.toBeNull();
    });

    mockEventHandler!({
      id: "evt-1",
      event_type: "STEP_STALE",
      step: "profiling",
      payload: {},
    });

    expect(mockInvalidateQueries).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["step-states", "sess-123"] })
    );
    expect(mockInvalidateQueries).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["session", "sess-123"] })
    );
  });

  it("invalidates step-states on STAGE_RUNNING event", async () => {
    renderHook(() => useEventStream("sess-123"));

    await vi.waitFor(() => {
      expect(mockEventHandler).not.toBeNull();
    });

    mockEventHandler!({
      id: "evt-2",
      event_type: "STAGE_RUNNING",
      step: "eda",
      payload: {},
    });

    expect(mockInvalidateQueries).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["step-states", "sess-123"] })
    );
  });

  it("invalidates step-states on STAGE_DONE event", async () => {
    renderHook(() => useEventStream("sess-123"));

    await vi.waitFor(() => {
      expect(mockEventHandler).not.toBeNull();
    });

    mockEventHandler!({
      id: "evt-3",
      event_type: "STAGE_DONE",
      step: "pipeline",
      payload: {},
    });

    expect(mockInvalidateQueries).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["step-states", "sess-123"] })
    );
  });

  it("invalidates step-states on STEP_START event", async () => {
    renderHook(() => useEventStream("sess-123"));

    await vi.waitFor(() => {
      expect(mockEventHandler).not.toBeNull();
    });

    mockEventHandler!({
      id: "evt-4",
      event_type: "STEP_START",
      step: "target",
      payload: {},
    });

    expect(mockInvalidateQueries).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["step-states", "sess-123"] })
    );
  });

  it("invalidates step-states on STEP_END event", async () => {
    renderHook(() => useEventStream("sess-123"));

    await vi.waitFor(() => {
      expect(mockEventHandler).not.toBeNull();
    });

    mockEventHandler!({
      id: "evt-5",
      event_type: "STEP_END",
      step: "target",
      payload: {},
    });

    expect(mockInvalidateQueries).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["step-states", "sess-123"] })
    );
  });

  it("does NOT invalidate step-states on unrelated events", async () => {
    renderHook(() => useEventStream("sess-123"));

    await vi.waitFor(() => {
      expect(mockEventHandler).not.toBeNull();
    });

    mockEventHandler!({
      id: "evt-6",
      event_type: "INFO",
      step: "profiling",
      payload: { message: "hello" },
    });

    // Should NOT have been called with step-states key
    const stepStatesCalls = mockInvalidateQueries.mock.calls.filter(
      (call: any[]) =>
        JSON.stringify(call[0]?.queryKey) === JSON.stringify(["step-states", "sess-123"])
    );
    expect(stepStatesCalls).toHaveLength(0);
  });
});

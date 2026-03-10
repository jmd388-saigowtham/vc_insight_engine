import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook } from "@testing-library/react";

// --- Mocks ---

let mockEventHandler: ((event: any) => void) | null = null;
let mockOpenHandler: (() => void) | null = null;
let mockErrorHandler: (() => void) | null = null;
const mockClose = vi.fn();
const mockCreateEventSource = vi.fn((opts: any) => {
  mockEventHandler = opts.onEvent;
  mockOpenHandler = opts.onOpen;
  mockErrorHandler = opts.onError;
  return { close: mockClose };
});

vi.mock("@/lib/sse-client", () => ({
  createEventSource: (opts: any) => mockCreateEventSource(opts),
}));

const mockAddEvent = vi.fn();
const mockSetConnected = vi.fn();
const mockSetEvents = vi.fn();
const mockOpenModal = vi.fn();
const mockInvalidateQueries = vi.fn();

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
  useModalStore: Object.assign(vi.fn(), {
    getState: () => ({ openModal: mockOpenModal }),
  }),
}));

vi.mock("@/stores/proposal-store", () => ({
  useProposalStore: {
    getState: () => ({ openProposal: vi.fn() }),
  },
}));

vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ invalidateQueries: mockInvalidateQueries }),
}));

vi.mock("@/lib/api-client", () => ({
  api: {
    get: vi.fn().mockResolvedValue([]),
  },
}));

import { useEventStream } from "@/hooks/use-events";

describe("useEventStream", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockCreateEventSource.mockClear();
    mockEventHandler = null;
    mockOpenHandler = null;
    mockErrorHandler = null;
  });

  it("does not connect when sessionId is null", () => {
    renderHook(() => useEventStream(null));
    expect(mockCreateEventSource).not.toHaveBeenCalled();
  });

  it("connects when sessionId is provided", async () => {
    renderHook(() => useEventStream("sess-123"));
    // Wait for async init
    await vi.waitFor(() => {
      expect(mockCreateEventSource).toHaveBeenCalledWith(
        expect.objectContaining({
          url: "/sessions/sess-123/events/stream",
        })
      );
    });
  });

  it("loads historical events on mount via setEvents", async () => {
    renderHook(() => useEventStream("sess-123"));
    await vi.waitFor(() => {
      expect(mockSetEvents).toHaveBeenCalled();
    });
  });

  it("sets connected to true on open", async () => {
    renderHook(() => useEventStream("sess-123"));
    await vi.waitFor(() => {
      expect(mockOpenHandler).not.toBeNull();
    });
    mockOpenHandler?.();
    expect(mockSetConnected).toHaveBeenCalledWith(true);
  });

  it("sets connected to false on error", async () => {
    renderHook(() => useEventStream("sess-123"));
    await vi.waitFor(() => {
      expect(mockErrorHandler).not.toBeNull();
    });
    mockErrorHandler?.();
    expect(mockSetConnected).toHaveBeenCalledWith(false);
  });

  it("adds event to trace store (with dedup by id)", async () => {
    renderHook(() => useEventStream("sess-123"));
    await vi.waitFor(() => {
      expect(mockEventHandler).not.toBeNull();
    });
    const event = { id: "evt-1", event_type: "INFO", step: "eda", payload: {} };
    mockEventHandler?.(event);
    expect(mockAddEvent).toHaveBeenCalledWith(event);
  });

  it("deduplicates events with same id", async () => {
    renderHook(() => useEventStream("sess-123"));
    await vi.waitFor(() => {
      expect(mockEventHandler).not.toBeNull();
    });
    const event = { id: "evt-dup", event_type: "INFO", step: "eda", payload: {} };
    mockEventHandler?.(event);
    mockEventHandler?.(event); // Same id — should be skipped
    expect(mockAddEvent).toHaveBeenCalledTimes(1);
  });

  it("opens modal on CODE_PROPOSED event with payload", async () => {
    renderHook(() => useEventStream("sess-123"));
    await vi.waitFor(() => {
      expect(mockEventHandler).not.toBeNull();
    });
    const event = {
      id: "evt-code",
      event_type: "CODE_PROPOSED",
      step: "modeling",
      payload: {
        proposal_id: "prop-1",
        code: "print('hello')",
        language: "python",
        description: "Train models",
        node_name: "modeling",
      },
    };
    mockEventHandler?.(event);
    expect(mockOpenModal).toHaveBeenCalledWith(
      expect.objectContaining({
        id: "prop-1",
        session_id: "sess-123",
        code: "print('hello')",
        language: "python",
        status: "pending",
        step: "modeling",
        description: "Train models",
        node_name: "modeling",
      }),
      null
    );
  });

  it("does not open modal for CODE_PROPOSED without code", async () => {
    renderHook(() => useEventStream("sess-123"));
    await vi.waitFor(() => {
      expect(mockEventHandler).not.toBeNull();
    });
    const event = {
      id: "evt-nocode",
      event_type: "CODE_PROPOSED",
      step: "eda",
      payload: { proposal_id: "prop-1" },
    };
    mockEventHandler?.(event);
    expect(mockOpenModal).not.toHaveBeenCalled();
  });

  it("invalidates session and step-states on STEP_STALE event", async () => {
    renderHook(() => useEventStream("sess-123"));
    await vi.waitFor(() => {
      expect(mockEventHandler).not.toBeNull();
    });
    const event = { id: "evt-stale", event_type: "STEP_STALE", step: "eda", payload: {} };
    mockEventHandler?.(event);
    expect(mockInvalidateQueries).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["session", "sess-123"] })
    );
    expect(mockInvalidateQueries).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["step-states", "sess-123"] })
    );
  });

  it("invalidates session and step-states on STEP_END event", async () => {
    renderHook(() => useEventStream("sess-123"));
    await vi.waitFor(() => {
      expect(mockEventHandler).not.toBeNull();
    });
    const event = { id: "evt-end", event_type: "STEP_END", step: "modeling", payload: {} };
    mockEventHandler?.(event);
    expect(mockInvalidateQueries).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["session", "sess-123"] })
    );
    expect(mockInvalidateQueries).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["step-states", "sess-123"] })
    );
  });

  it("does not invalidate on regular INFO event", async () => {
    renderHook(() => useEventStream("sess-123"));
    await vi.waitFor(() => {
      expect(mockEventHandler).not.toBeNull();
    });
    const event = { id: "evt-info", event_type: "INFO", step: "eda", payload: {} };
    mockEventHandler?.(event);
    expect(mockInvalidateQueries).not.toHaveBeenCalled();
  });

  it("closes connection on unmount", async () => {
    const { unmount } = renderHook(() => useEventStream("sess-123"));
    // Wait for connection to be established
    await vi.waitFor(() => {
      expect(mockCreateEventSource).toHaveBeenCalled();
    });
    unmount();
    expect(mockClose).toHaveBeenCalled();
    expect(mockSetConnected).toHaveBeenCalledWith(false);
  });
});

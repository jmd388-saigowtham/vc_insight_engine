import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

// --- Mocks ---

const mockPost = vi.fn();
const mockToastSuccess = vi.fn();
const mockToastError = vi.fn();

vi.mock("@/lib/api-client", () => ({
  api: {
    post: (...args: unknown[]) => mockPost(...args),
  },
}));

vi.mock("sonner", () => ({
  toast: {
    success: (...args: unknown[]) => mockToastSuccess(...args),
    error: (...args: unknown[]) => mockToastError(...args),
  },
}));

import { useRerun } from "@/hooks/use-rerun";

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return React.createElement(
      QueryClientProvider,
      { client: queryClient },
      children
    );
  };
}

describe("useRerun", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("calls api.post with the correct URL on mutate", async () => {
    mockPost.mockResolvedValueOnce({ ok: true });

    const { result } = renderHook(() => useRerun("sess-456"), {
      wrapper: createWrapper(),
    });

    act(() => {
      result.current.mutate("eda");
    });

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith("/sessions/sess-456/rerun/eda");
    });
  });

  it("shows success toast and invalidates session queries on success", async () => {
    mockPost.mockResolvedValueOnce({ ok: true });

    const { result } = renderHook(() => useRerun("sess-456"), {
      wrapper: createWrapper(),
    });

    act(() => {
      result.current.mutate("profiling");
    });

    await waitFor(() => {
      expect(mockToastSuccess).toHaveBeenCalledWith(
        "Re-running pipeline from profiling"
      );
    });
  });

  it("shows 'already running' toast when error contains 409", async () => {
    mockPost.mockRejectedValueOnce(new Error("API Error 409: Conflict"));

    const { result } = renderHook(() => useRerun("sess-456"), {
      wrapper: createWrapper(),
    });

    act(() => {
      result.current.mutate("eda");
    });

    await waitFor(() => {
      expect(mockToastError).toHaveBeenCalledWith(
        "A pipeline step is already running. Please wait."
      );
    });
  });

  it("shows 'already running' toast when error contains 'already running'", async () => {
    mockPost.mockRejectedValueOnce(new Error("Pipeline is already running"));

    const { result } = renderHook(() => useRerun("sess-456"), {
      wrapper: createWrapper(),
    });

    act(() => {
      result.current.mutate("eda");
    });

    await waitFor(() => {
      expect(mockToastError).toHaveBeenCalledWith(
        "A pipeline step is already running. Please wait."
      );
    });
  });

  it("shows generic error message for other errors", async () => {
    mockPost.mockRejectedValueOnce(new Error("Network timeout"));

    const { result } = renderHook(() => useRerun("sess-456"), {
      wrapper: createWrapper(),
    });

    act(() => {
      result.current.mutate("eda");
    });

    await waitFor(() => {
      expect(mockToastError).toHaveBeenCalledWith("Network timeout");
    });
  });

  it("shows 'Rerun failed' for non-Error throws", async () => {
    mockPost.mockRejectedValueOnce("some string error");

    const { result } = renderHook(() => useRerun("sess-456"), {
      wrapper: createWrapper(),
    });

    act(() => {
      result.current.mutate("eda");
    });

    await waitFor(() => {
      expect(mockToastError).toHaveBeenCalledWith("Rerun failed");
    });
  });
});

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";

// --- Mocks ---

const mockPush = vi.fn();
const mockMutate = vi.fn();

vi.mock("next/navigation", () => ({
  useParams: () => ({ sessionId: "sess-123" }),
  useRouter: () => ({ push: mockPush }),
}));

vi.mock("@/stores/session-store", () => ({
  useSessionStore: vi.fn(),
}));

vi.mock("@/hooks/use-session", () => ({
  useUpdateSession: () => ({
    mutate: mockMutate,
    isPending: false,
  }),
}));

// Import after mocks are set up
import { useWizardNavigation } from "@/hooks/use-wizard-navigation";
import { useSessionStore } from "@/stores/session-store";

const mockUseSessionStore = vi.mocked(useSessionStore);

describe("useWizardNavigation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("isAtFrontier is true when at the high water mark", () => {
    // Session is at "profiling" (index 2), user is viewing "profiling" (index 2)
    mockUseSessionStore.mockImplementation((selector: any) =>
      selector({ session: { current_step: "profiling" } })
    );

    const { result } = renderHook(() => useWizardNavigation("profiling"));

    expect(result.current.isAtFrontier).toBe(true);
  });

  it("isAtFrontier is true when beyond the high water mark", () => {
    // Session is at "upload" (index 1), user is viewing "profiling" (index 2)
    mockUseSessionStore.mockImplementation((selector: any) =>
      selector({ session: { current_step: "upload" } })
    );

    const { result } = renderHook(() => useWizardNavigation("profiling"));

    expect(result.current.isAtFrontier).toBe(true);
  });

  it("isAtFrontier is false when reviewing a past step", () => {
    // Session is at "eda" (index 6), user is viewing "upload" (index 1)
    mockUseSessionStore.mockImplementation((selector: any) =>
      selector({ session: { current_step: "eda" } })
    );

    const { result } = renderHook(() => useWizardNavigation("upload"));

    expect(result.current.isAtFrontier).toBe(false);
  });

  it("navigateToNext calls updateSession.mutate when at frontier", () => {
    // At the frontier: session is at "profiling", viewing "profiling"
    mockUseSessionStore.mockImplementation((selector: any) =>
      selector({ session: { current_step: "profiling" } })
    );

    const { result } = renderHook(() => useWizardNavigation("profiling"));

    act(() => {
      result.current.navigateToNext("workspace");
    });

    expect(mockMutate).toHaveBeenCalledWith(
      { current_step: "workspace" },
      { onSuccess: expect.any(Function) }
    );
    // router.push should not be called directly (it's called inside onSuccess callback)
    expect(mockPush).not.toHaveBeenCalled();
  });

  it("navigateToNext calls updateSession.mutate with extraData when at frontier", () => {
    mockUseSessionStore.mockImplementation((selector: any) =>
      selector({ session: { current_step: "onboarding" } })
    );

    const { result } = renderHook(() => useWizardNavigation("onboarding"));

    act(() => {
      result.current.navigateToNext("upload", { company_name: "Acme" });
    });

    expect(mockMutate).toHaveBeenCalledWith(
      { company_name: "Acme", current_step: "upload" },
      { onSuccess: expect.any(Function) }
    );
  });

  it("navigateToNext calls router.push directly when reviewing past step without extraData", () => {
    // Reviewing past step: session is at "eda", viewing "upload"
    mockUseSessionStore.mockImplementation((selector: any) =>
      selector({ session: { current_step: "eda" } })
    );

    const { result } = renderHook(() => useWizardNavigation("upload"));

    act(() => {
      result.current.navigateToNext("profiling");
    });

    // Should navigate directly without mutation
    expect(mockPush).toHaveBeenCalledWith("/sessions/sess-123/profiling");
    expect(mockMutate).not.toHaveBeenCalled();
  });

  it("navigateToNext calls mutate with extraData when reviewing past step with extraData", () => {
    mockUseSessionStore.mockImplementation((selector: any) =>
      selector({ session: { current_step: "eda" } })
    );

    const { result } = renderHook(() => useWizardNavigation("upload"));

    act(() => {
      result.current.navigateToNext("profiling", { company_name: "Updated" });
    });

    // When reviewing past step with extraData, it still calls mutate (without current_step)
    expect(mockMutate).toHaveBeenCalledWith(
      { company_name: "Updated" },
      { onSuccess: expect.any(Function) }
    );
  });

  it("defaults to 'onboarding' when session has no current_step", () => {
    mockUseSessionStore.mockImplementation((selector: any) =>
      selector({ session: null })
    );

    const { result } = renderHook(() => useWizardNavigation("onboarding"));

    // onboarding index (0) >= onboarding index (0) => at frontier
    expect(result.current.isAtFrontier).toBe(true);
  });
});

import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import React from "react";

// --- Mocks ---

const mockPush = vi.fn();

vi.mock("next/navigation", () => ({
  useParams: () => ({ sessionId: "sess-abc" }),
  useRouter: () => ({ push: mockPush }),
}));

vi.mock("next-themes", () => ({
  useTheme: () => ({ theme: "light", setTheme: vi.fn() }),
}));

import { WizardNav } from "@/components/wizard/wizard-nav";

const STEP_KEYS = [
  "onboarding",
  "upload",
  "profiling",
  "workspace",
  "target",
  "feature-selection",
  "eda",
  "hypotheses",
  "hypothesis-results",
  "models",
  "shap",
  "report",
];

describe("WizardNav", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders 12 step buttons", () => {
    render(
      <WizardNav currentStep="onboarding" highWaterStep="onboarding" />
    );

    // Each step renders a <button> inside the nav
    const buttons = screen.getAllByRole("button");
    // 12 step buttons + 1 theme toggle button = 13
    // But the theme toggle is also a button, so filter by the step buttons
    // The steps are inside the nav, let's just count all buttons
    // 12 steps + 1 theme toggle = 13
    expect(buttons.length).toBe(13);
  });

  it("completed steps are clickable (not disabled)", () => {
    // highWaterStep = "workspace" (index 3), so steps 0-3 should be accessible
    render(
      <WizardNav currentStep="workspace" highWaterStep="workspace" />
    );

    const buttons = screen.getAllByRole("button");
    // Steps at indices 0 (onboarding), 1 (upload), 2 (profiling) should be enabled (completed)
    // Step at index 3 (workspace) should be enabled (current)
    expect(buttons[0]).not.toBeDisabled(); // onboarding - completed
    expect(buttons[1]).not.toBeDisabled(); // upload - completed
    expect(buttons[2]).not.toBeDisabled(); // profiling - completed
    expect(buttons[3]).not.toBeDisabled(); // workspace - current
  });

  it("locked steps beyond high water mark are disabled", () => {
    // highWaterStep = "upload" (index 1), so steps beyond index 1 should be locked
    render(
      <WizardNav currentStep="upload" highWaterStep="upload" />
    );

    const buttons = screen.getAllByRole("button");
    // Index 0: onboarding (completed) - enabled
    // Index 1: upload (current) - enabled
    // Index 2: profiling (locked) - disabled
    // Index 3+: locked - disabled
    expect(buttons[0]).not.toBeDisabled();
    expect(buttons[1]).not.toBeDisabled();
    expect(buttons[2]).toBeDisabled(); // profiling - locked
    expect(buttons[3]).toBeDisabled(); // workspace - locked
    expect(buttons[4]).toBeDisabled(); // target - locked
  });

  it("clicking a completed step navigates to that step", () => {
    render(
      <WizardNav currentStep="workspace" highWaterStep="workspace" />
    );

    const buttons = screen.getAllByRole("button");
    // Click "onboarding" (index 0, should be completed and clickable)
    fireEvent.click(buttons[0]);

    expect(mockPush).toHaveBeenCalledWith("/sessions/sess-abc/onboarding");
  });

  it("clicking a locked step does not navigate", () => {
    render(
      <WizardNav currentStep="upload" highWaterStep="upload" />
    );

    const buttons = screen.getAllByRole("button");
    // Click "profiling" (index 2, should be locked)
    fireEvent.click(buttons[2]);

    expect(mockPush).not.toHaveBeenCalled();
  });

  it("current step has primary styling", () => {
    render(
      <WizardNav currentStep="profiling" highWaterStep="profiling" />
    );

    const buttons = screen.getAllByRole("button");
    // Index 2 is "profiling" which is the current step
    expect(buttons[2].className).toContain("text-primary");
  });

  it("completed steps have accent styling", () => {
    render(
      <WizardNav currentStep="workspace" highWaterStep="workspace" />
    );

    const buttons = screen.getAllByRole("button");
    // Index 0 is "onboarding" which is completed
    expect(buttons[0].className).toContain("text-accent");
  });

  it("locked steps have cursor-not-allowed styling", () => {
    render(
      <WizardNav currentStep="onboarding" highWaterStep="onboarding" />
    );

    const buttons = screen.getAllByRole("button");
    // Index 1 (upload) should be locked since high water is onboarding
    expect(buttons[1].className).toContain("cursor-not-allowed");
  });

  it("all steps are accessible when high water step is report", () => {
    render(
      <WizardNav currentStep="report" highWaterStep="report" />
    );

    const buttons = screen.getAllByRole("button");
    // All 12 step buttons (indices 0-11) should be enabled, index 12 is theme toggle
    for (let i = 0; i < 12; i++) {
      expect(buttons[i]).not.toBeDisabled();
    }
  });
});

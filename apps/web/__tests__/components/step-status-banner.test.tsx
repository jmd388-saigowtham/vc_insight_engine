import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { StepStatusBanner } from "@/components/step-status-banner";

describe("StepStatusBanner", () => {
  it("renders nothing for NOT_STARTED", () => {
    const { container } = render(<StepStatusBanner state="NOT_STARTED" />);
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing for undefined state", () => {
    const { container } = render(<StepStatusBanner state={undefined} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders running banner", () => {
    render(<StepStatusBanner state="RUNNING" />);
    expect(screen.getByText(/AI is working/i)).toBeDefined();
  });

  it("renders stale banner", () => {
    render(<StepStatusBanner state="STALE" />);
    expect(screen.getByText(/stale/i)).toBeDefined();
  });

  it("renders failed banner", () => {
    render(<StepStatusBanner state="FAILED" />);
    expect(screen.getByText(/error/i)).toBeDefined();
  });

  it("hides DONE banner by default", () => {
    const { container } = render(<StepStatusBanner state="DONE" />);
    expect(container.firstChild).toBeNull();
  });

  it("shows DONE banner when showCompleted=true", () => {
    render(<StepStatusBanner state="DONE" showCompleted />);
    expect(screen.getByText(/completed/i)).toBeDefined();
  });

  it("shows AWAITING_APPROVAL when hasPendingProposal", () => {
    render(<StepStatusBanner state="RUNNING" hasPendingProposal />);
    expect(screen.getByText(/approval/i)).toBeDefined();
  });

  it("includes step label when provided", () => {
    render(<StepStatusBanner state="RUNNING" stepLabel="EDA" />);
    expect(screen.getByText(/EDA:/i)).toBeDefined();
  });
});

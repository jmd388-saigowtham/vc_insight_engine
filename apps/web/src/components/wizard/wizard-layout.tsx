"use client";

import { WizardNav } from "./wizard-nav";

interface WizardLayoutProps {
  currentStep: string;
  highWaterStep: string;
  stepStates?: Record<string, string> | null;
  children: React.ReactNode;
  sidebar?: React.ReactNode;
}

export function WizardLayout({
  currentStep,
  highWaterStep,
  stepStates,
  children,
  sidebar,
}: WizardLayoutProps) {
  return (
    <div className="flex min-h-screen flex-col">
      <WizardNav currentStep={currentStep} highWaterStep={highWaterStep} stepStates={stepStates} />
      <div className="flex flex-1">
        <main className="flex-1 overflow-y-auto p-6">{children}</main>
        {sidebar}
      </div>
    </div>
  );
}

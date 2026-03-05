"use client";

import { WizardNav } from "./wizard-nav";

interface WizardLayoutProps {
  currentStep: string;
  children: React.ReactNode;
  sidebar?: React.ReactNode;
}

export function WizardLayout({
  currentStep,
  children,
  sidebar,
}: WizardLayoutProps) {
  return (
    <div className="flex min-h-screen flex-col">
      <WizardNav currentStep={currentStep} />
      <div className="flex flex-1">
        <main className="flex-1 overflow-y-auto p-6">{children}</main>
        {sidebar}
      </div>
    </div>
  );
}

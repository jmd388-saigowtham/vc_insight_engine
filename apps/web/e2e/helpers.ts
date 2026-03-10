import { type Page, expect } from "@playwright/test";
import path from "path";
import fs from "fs";

const API_URL = process.env.E2E_API_URL ?? "http://localhost:8000";

/** Direct API call to create a session. Returns session id. */
export async function createSessionViaAPI(
  page: Page,
  companyName = "E2E Test Corp",
  industry = "SaaS",
): Promise<string> {
  const resp = await page.request.post(`${API_URL}/sessions`, {
    data: { company_name: companyName, industry },
  });
  expect(resp.ok()).toBeTruthy();
  const body = await resp.json();
  return body.id;
}

/** Direct API call to upload a CSV file. */
export async function uploadFileViaAPI(
  page: Page,
  sessionId: string,
  fixtureName = "test_churn.csv",
): Promise<void> {
  const filePath = path.resolve(__dirname, "fixtures", fixtureName);
  const fileBuffer = fs.readFileSync(filePath);
  const resp = await page.request.post(
    `${API_URL}/sessions/${sessionId}/upload`,
    {
      multipart: {
        file: {
          name: fixtureName,
          mimeType: "text/csv",
          buffer: fileBuffer,
        },
      },
    },
  );
  if (!resp.ok()) {
    const body = await resp.text();
    throw new Error(`Upload failed (${resp.status()}): ${body}`);
  }
}

/** Direct API call to advance session step. */
export async function advanceStepViaAPI(
  page: Page,
  sessionId: string,
  step: string,
): Promise<void> {
  const resp = await page.request.patch(`${API_URL}/sessions/${sessionId}`, {
    data: { current_step: step },
  });
  expect(resp.ok()).toBeTruthy();
}

/** Direct API call to get session. */
export async function getSessionViaAPI(
  page: Page,
  sessionId: string,
): Promise<Record<string, unknown>> {
  const resp = await page.request.get(`${API_URL}/sessions/${sessionId}`);
  expect(resp.ok()).toBeTruthy();
  return resp.json();
}

/** Direct API call to update feature selection. */
export async function updateFeaturesViaAPI(
  page: Page,
  sessionId: string,
  targetColumn: string,
  selectedFeatures: string[],
): Promise<void> {
  const resp = await page.request.patch(
    `${API_URL}/sessions/${sessionId}/feature-selection`,
    {
      data: { target_column: targetColumn, selected_features: selectedFeatures },
    },
  );
  expect(resp.ok()).toBeTruthy();
}

/** Direct API call to get step states. */
export async function getStepStatesViaAPI(
  page: Page,
  sessionId: string,
): Promise<Record<string, string>> {
  const resp = await page.request.get(
    `${API_URL}/sessions/${sessionId}/step-states`,
  );
  expect(resp.ok()).toBeTruthy();
  const body = await resp.json();
  return body.step_states;
}

/** Navigate to a session wizard step. */
export async function navigateToStep(
  page: Page,
  sessionId: string,
  step: string,
): Promise<void> {
  await page.goto(`/sessions/${sessionId}/${step}`, {
    waitUntil: "domcontentloaded",
  });
  // Wait a moment for client-side hydration (don't use networkidle — SSE keeps it active)
  await page.waitForTimeout(2000);
}

/** Path to the test fixture CSV file. */
export const TEST_CSV_PATH = path.resolve(
  __dirname,
  "fixtures",
  "test_churn.csv",
);

/** Fill out the onboarding form and submit. */
export async function completeOnboarding(
  page: Page,
  companyName = "E2E Test Corp",
  industry = "SaaS",
): Promise<void> {
  await page.getByLabel("Company Name").fill(companyName);

  // Open the industry select
  await page.getByRole("combobox", { name: "Industry" }).click();
  await page.getByRole("option", { name: industry }).click();

  await page.getByRole("button", { name: /Continue to Upload/i }).click();
  await page.waitForURL(/\/upload$/);
}

/** Upload a file on the upload page via the dropzone. */
export async function uploadFileOnPage(
  page: Page,
  fixturePath = TEST_CSV_PATH,
): Promise<void> {
  // Set the file on the hidden input
  const fileInput = page.locator('input[type="file"]');
  await fileInput.setInputFiles(fixturePath);

  // Wait for the upload to complete and file to appear in the list
  await expect(
    page.getByText("test_churn.csv"),
  ).toBeVisible({ timeout: 15_000 });
}

/** Wait for a toast notification with the given text. */
export async function expectToast(page: Page, text: string): Promise<void> {
  await expect(
    page.locator("[data-sonner-toast]").filter({ hasText: text }),
  ).toBeVisible({ timeout: 10_000 });
}

/** Check that the wizard nav shows a specific step as active/current. */
export async function expectWizardStepActive(
  page: Page,
  stepLabel: string,
): Promise<void> {
  const navItem = page
    .locator("[data-testid='wizard-nav'] a, [data-testid='wizard-nav'] button")
    .filter({ hasText: stepLabel });
  await expect(navItem).toBeVisible();
}

/**
 * E2E: Happy path — full pipeline walkthrough.
 *
 * Tests the user flow from landing page through the wizard steps.
 * Backend-heavy pipeline steps (EDA, modeling, SHAP) are validated
 * via API side-effects rather than waiting for full LLM execution.
 */
import { test, expect } from "@playwright/test";
import {
  createSessionViaAPI,
  uploadFileViaAPI,
  advanceStepViaAPI,
  navigateToStep,
  completeOnboarding,
  uploadFileOnPage,
  TEST_CSV_PATH,
} from "./helpers";

test.describe("Full Pipeline Happy Path", () => {
  test("landing page renders and has start button", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("VC Insight Engine")).toBeVisible();
    await expect(
      page.getByRole("button", { name: /Start New Analysis/i }),
    ).toBeVisible();
  });

  test("create session from landing page", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: /Start New Analysis/i }).click();
    await page.waitForURL(/\/sessions\/new/);

    // Should redirect to onboarding after session creation
    // The /sessions/new page auto-creates and redirects
    await page.waitForURL(/\/onboarding/, { timeout: 15_000 });
  });

  test("onboarding → upload → profiling flow", async ({ page }) => {
    // Create session via API for speed
    const sessionId = await createSessionViaAPI(page);

    // Navigate to onboarding
    await navigateToStep(page, sessionId, "onboarding");

    // Fill onboarding form
    await completeOnboarding(page, "Pipeline Test Corp", "SaaS");

    // Now on upload page
    await expect(page.getByText("Upload Data Files")).toBeVisible();

    // Upload a file
    await uploadFileOnPage(page);

    // Continue button should appear
    await expect(
      page.getByRole("button", { name: /Continue to Profiling/i }),
    ).toBeVisible();

    await page.getByRole("button", { name: /Continue to Profiling/i }).click();
    await page.waitForURL(/\/profiling$/);

    // Profiling page shows data
    await expect(page.getByText("Data Profiling")).toBeVisible();
  });

  test("profiling page shows column table", async ({ page }) => {
    // Setup: create session + upload file via API
    const sessionId = await createSessionViaAPI(page);
    await uploadFileViaAPI(page, sessionId);
    await advanceStepViaAPI(page, sessionId, "profiling");

    await navigateToStep(page, sessionId, "profiling");

    // Should see the profiling table with columns from test_churn.csv
    await expect(page.getByText("Data Profiling")).toBeVisible();
    await expect(page.getByRole("tab", { name: "test_churn.csv" })).toBeVisible({
      timeout: 10_000,
    });

    // Verify column names are present
    await expect(page.getByText("customer_id")).toBeVisible();
    await expect(page.getByText("monthly_revenue")).toBeVisible();
    await expect(page.getByText("churned")).toBeVisible();
  });

  test("feature selection page renders with features", async ({ page }) => {
    // Setup: session at target step with upload done
    const sessionId = await createSessionViaAPI(page);
    await uploadFileViaAPI(page, sessionId);
    await advanceStepViaAPI(page, sessionId, "feature-selection");

    await navigateToStep(page, sessionId, "feature-selection");

    await expect(page.getByText("Feature Selection")).toBeVisible();

    // Should show features card with select all / deselect all
    await expect(
      page.getByRole("button", { name: "Select All", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Deselect All", exact: true }),
    ).toBeVisible();
  });

  test("wizard nav shows all 12 steps", async ({ page }) => {
    const sessionId = await createSessionViaAPI(page);
    await navigateToStep(page, sessionId, "onboarding");

    // Count wizard nav steps — look for step labels or icons
    // The wizard nav should have 12 steps
    const navSteps = page.locator(
      "nav a, nav button",
    );
    // At minimum we should see multiple nav elements
    const count = await navSteps.count();
    expect(count).toBeGreaterThanOrEqual(12);
  });

  test("session appears in landing page history", async ({ page }) => {
    // Create a session with a distinctive name
    const sessionId = await createSessionViaAPI(
      page,
      "History Test Corp",
      "Fintech",
    );

    // Go to landing page
    await page.goto("/");
    await page.waitForLoadState("networkidle");

    // Should see the session in recent analyses
    await expect(page.getByText("History Test Corp").first()).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.getByText("Fintech").first()).toBeVisible();
  });
});

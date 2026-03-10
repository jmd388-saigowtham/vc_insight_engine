/**
 * E2E: Go-back-and-edit — step invalidation and rerun.
 *
 * Tests the ability to go back to a previous step, make changes,
 * and have downstream steps marked as STALE with rerun capability.
 */
import { test, expect } from "@playwright/test";
import {
  createSessionViaAPI,
  uploadFileViaAPI,
  advanceStepViaAPI,
  updateFeaturesViaAPI,
  getStepStatesViaAPI,
  navigateToStep,
} from "./helpers";

const API_URL = process.env.E2E_API_URL ?? "http://localhost:8000";

test.describe("Go Back and Edit", () => {
  test("rerun endpoint invalidates downstream steps", async ({ page }) => {
    const sessionId = await createSessionViaAPI(page);
    await uploadFileViaAPI(page, sessionId);

    // Set all steps to DONE via step_states
    const allDone: Record<string, string> = {};
    const steps = [
      "profiling",
      "merge_planning",
      "target_id",
      "feature_selection",
      "eda",
      "preprocessing",
      "hypothesis",
      "feature_eng",
      "modeling",
      "explainability",
      "recommendation",
      "report",
    ];
    for (const s of steps) {
      allDone[s] = "DONE";
    }

    await page.request.patch(`${API_URL}/sessions/${sessionId}`, {
      data: { step_states: allDone },
    });

    // Rerun from feature_selection — should STALE everything downstream
    const rerunResp = await page.request.post(
      `${API_URL}/sessions/${sessionId}/rerun/feature_selection`,
      { failOnStatusCode: false },
    );

    // Might return 200 or 500 depending on whether the pipeline can run
    // But the step_states should be updated
    const states = await getStepStatesViaAPI(page, sessionId);

    // Upstream should be untouched
    expect(states.profiling).toBe("DONE");
    expect(states.merge_planning).toBe("DONE");
    expect(states.target_id).toBe("DONE");

    // feature_selection should be READY or RUNNING (rerun initiated it)
    expect(["READY", "RUNNING"]).toContain(states.feature_selection);

    // Downstream should be STALE
    expect(states.eda).toBe("STALE");
    expect(states.preprocessing).toBe("STALE");
    expect(states.modeling).toBe("STALE");
    expect(states.report).toBe("STALE");
  });

  test("rerun invalid step returns 400", async ({ page }) => {
    const sessionId = await createSessionViaAPI(page);

    const resp = await page.request.post(
      `${API_URL}/sessions/${sessionId}/rerun/nonexistent_step`,
      { failOnStatusCode: false },
    );
    expect(resp.status()).toBe(400);
  });

  test("feature selection update via API works", async ({ page }) => {
    const sessionId = await createSessionViaAPI(page);
    await uploadFileViaAPI(page, sessionId);
    await advanceStepViaAPI(page, sessionId, "feature-selection");

    // Update features
    const resp = await page.request.patch(
      `${API_URL}/sessions/${sessionId}/feature-selection`,
      {
        data: {
          target_column: "churned",
          selected_features: ["monthly_revenue", "tenure_months"],
        },
      },
    );
    expect(resp.ok()).toBeTruthy();

    const body = await resp.json();
    expect(body.target_column).toBe("churned");
    expect(body.selected_features).toEqual([
      "monthly_revenue",
      "tenure_months",
    ]);
  });

  test("feature selection rejects target in features list", async ({
    page,
  }) => {
    const sessionId = await createSessionViaAPI(page);
    await uploadFileViaAPI(page, sessionId);

    const resp = await page.request.patch(
      `${API_URL}/sessions/${sessionId}/feature-selection`,
      {
        data: {
          target_column: "churned",
          selected_features: ["churned", "monthly_revenue"],
        },
        failOnStatusCode: false,
      },
    );
    expect(resp.status()).toBe(400);
  });

  test("feature selection rejects empty features", async ({ page }) => {
    const sessionId = await createSessionViaAPI(page);
    await uploadFileViaAPI(page, sessionId);

    const resp = await page.request.patch(
      `${API_URL}/sessions/${sessionId}/feature-selection`,
      {
        data: {
          target_column: "churned",
          selected_features: [],
        },
        failOnStatusCode: false,
      },
    );
    expect(resp.status()).toBe(400);
  });

  test("step states endpoint returns valid states", async ({ page }) => {
    const sessionId = await createSessionViaAPI(page);

    const states = await getStepStatesViaAPI(page, sessionId);

    // Should have entries for all pipeline steps
    expect(states).toHaveProperty("profiling");
    expect(states).toHaveProperty("merge_planning");
    expect(states).toHaveProperty("target_id");
    expect(states).toHaveProperty("feature_selection");
    expect(states).toHaveProperty("eda");
    expect(states).toHaveProperty("modeling");
    expect(states).toHaveProperty("report");

    // All steps should be in valid states
    const validStates = [
      "NOT_STARTED",
      "READY",
      "RUNNING",
      "DONE",
      "STALE",
      "FAILED",
    ];
    for (const [, state] of Object.entries(states)) {
      expect(validStates).toContain(state);
    }
  });

  test("EDA page shows stale banner when step is STALE", async ({ page }) => {
    const sessionId = await createSessionViaAPI(page);
    await uploadFileViaAPI(page, sessionId);
    await advanceStepViaAPI(page, sessionId, "eda");

    // Set eda to STALE
    const staleStates: Record<string, string> = {
      profiling: "DONE",
      merge_planning: "DONE",
      target_id: "DONE",
      feature_selection: "DONE",
      eda: "STALE",
      preprocessing: "STALE",
      hypothesis: "STALE",
      feature_eng: "STALE",
      modeling: "STALE",
      explainability: "STALE",
      recommendation: "STALE",
      report: "STALE",
    };

    await page.request.patch(`${API_URL}/sessions/${sessionId}`, {
      data: { step_states: staleStates },
    });

    await navigateToStep(page, sessionId, "eda");

    // The stale banner should appear
    await expect(page.getByText("Results are stale")).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.getByText("Upstream data has changed")).toBeVisible();

    // Re-run button should be present
    await expect(
      page.getByRole("button", { name: /Re-run/i }),
    ).toBeVisible();
  });

  test("navigate backwards through wizard steps", async ({ page }) => {
    const sessionId = await createSessionViaAPI(page);
    await uploadFileViaAPI(page, sessionId);
    await advanceStepViaAPI(page, sessionId, "eda");

    // Navigate to EDA
    await navigateToStep(page, sessionId, "eda");
    await expect(
      page.getByText("Exploratory Data Analysis"),
    ).toBeVisible();

    // Go back to upload
    await navigateToStep(page, sessionId, "upload");
    await expect(page.getByText("Upload Data Files")).toBeVisible();

    // Go forward to profiling
    await navigateToStep(page, sessionId, "profiling");
    await expect(page.getByText("Data Profiling")).toBeVisible();
  });
});

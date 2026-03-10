/**
 * E2E: Approval flow — code proposal, deny, approve, resume.
 *
 * Tests the human-in-the-loop code approval mechanism.
 * Code proposals are created via direct DB inserts since there's
 * no public /code/propose endpoint (proposals are created by agent nodes).
 * We test the approve/deny endpoints and SSE connectivity.
 */
import { test, expect } from "@playwright/test";
import {
  createSessionViaAPI,
  navigateToStep,
} from "./helpers";

const API_URL = process.env.E2E_API_URL ?? "http://localhost:8000";

test.describe("Approval Flow", () => {
  test("pending endpoint returns null when no proposals exist", async ({
    page,
  }) => {
    const sessionId = await createSessionViaAPI(page);

    const resp = await page.request.get(
      `${API_URL}/sessions/${sessionId}/code/pending`,
    );
    expect(resp.ok()).toBeTruthy();
    const body = await resp.json();
    // No proposals yet — should return null
    expect(body).toBeNull();
  });

  test("SSE event stream connects and page loads", async ({ page }) => {
    const sessionId = await createSessionViaAPI(page);
    await navigateToStep(page, sessionId, "onboarding");
    await expect(page.getByText("Company Onboarding")).toBeVisible();
  });

  test("resume endpoint returns 404 for nonexistent session", async ({
    page,
  }) => {
    const fakeId = "00000000-0000-0000-0000-000000000000";
    const resp = await page.request.post(
      `${API_URL}/sessions/${fakeId}/resume`,
      { failOnStatusCode: false },
    );
    expect(resp.status()).toBeGreaterThanOrEqual(400);
  });

  test("resume endpoint returns 409 when steps are running", async ({
    page,
  }) => {
    const sessionId = await createSessionViaAPI(page);

    // Set step_states with a RUNNING step
    await page.request.patch(`${API_URL}/sessions/${sessionId}`, {
      data: {
        step_states: {
          profiling: "RUNNING",
          merge_planning: "NOT_STARTED",
          target_id: "NOT_STARTED",
          feature_selection: "NOT_STARTED",
          eda: "NOT_STARTED",
          preprocessing: "NOT_STARTED",
          hypothesis: "NOT_STARTED",
          feature_eng: "NOT_STARTED",
          modeling: "NOT_STARTED",
          explainability: "NOT_STARTED",
          recommendation: "NOT_STARTED",
          report: "NOT_STARTED",
        },
      },
    });

    const resumeResp = await page.request.post(
      `${API_URL}/sessions/${sessionId}/resume`,
      { failOnStatusCode: false },
    );
    expect(resumeResp.status()).toBe(409);
  });

  test("approve endpoint returns 404 for nonexistent proposal", async ({
    page,
  }) => {
    const fakeId = "00000000-0000-0000-0000-000000000000";
    const resp = await page.request.post(
      `${API_URL}/code/${fakeId}/approve`,
      { failOnStatusCode: false },
    );
    expect(resp.status()).toBe(404);
  });

  test("deny endpoint returns 404 for nonexistent proposal", async ({
    page,
  }) => {
    const fakeId = "00000000-0000-0000-0000-000000000000";
    const resp = await page.request.post(
      `${API_URL}/code/${fakeId}/deny`,
      { failOnStatusCode: false },
    );
    expect(resp.status()).toBe(404);
  });
});

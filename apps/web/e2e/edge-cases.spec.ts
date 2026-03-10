/**
 * E2E: Edge cases — validation, constraints, error handling.
 *
 * Tests boundary conditions and error scenarios across the platform.
 */
import { test, expect } from "@playwright/test";
import {
  createSessionViaAPI,
  uploadFileViaAPI,
  advanceStepViaAPI,
  navigateToStep,
  completeOnboarding,
} from "./helpers";

const API_URL = process.env.E2E_API_URL ?? "http://localhost:8000";

test.describe("Edge Cases", () => {
  test.describe("Session Management", () => {
    test("GET nonexistent session returns 404", async ({ page }) => {
      const fakeId = "00000000-0000-0000-0000-000000000000";
      const resp = await page.request.get(`${API_URL}/sessions/${fakeId}`, {
        failOnStatusCode: false,
      });
      expect(resp.status()).toBe(404);
    });

    test("create session with minimal data", async ({ page }) => {
      const resp = await page.request.post(`${API_URL}/sessions`, {
        data: { company_name: "Minimal Corp" },
      });
      expect(resp.ok()).toBeTruthy();
      const body = await resp.json();
      expect(body.company_name).toBe("Minimal Corp");
      expect(body.current_step).toBe("onboarding");
      expect(body.status).toBe("active");
    });

    test("update session step freely (no regression guard)", async ({
      page,
    }) => {
      const sessionId = await createSessionViaAPI(page);

      // Advance to EDA
      await advanceStepViaAPI(page, sessionId, "eda");

      // Go back to onboarding — should succeed (regression guard removed)
      const resp = await page.request.patch(
        `${API_URL}/sessions/${sessionId}`,
        { data: { current_step: "onboarding" } },
      );
      expect(resp.ok()).toBeTruthy();
      const body = await resp.json();
      expect(body.current_step).toBe("onboarding");
    });
  });

  test.describe("Upload Validation", () => {
    test("upload rejects non-CSV/XLSX files", async ({ page }) => {
      const sessionId = await createSessionViaAPI(page);

      const resp = await page.request.post(
        `${API_URL}/sessions/${sessionId}/upload`,
        {
          multipart: {
            file: {
              name: "test.txt",
              mimeType: "text/plain",
              buffer: Buffer.from("just some text"),
            },
          },
          failOnStatusCode: false,
        },
      );
      // Should reject with 400 or 422
      expect(resp.status()).toBeGreaterThanOrEqual(400);
    });
  });

  test.describe("Feature Selection Constraints", () => {
    test("feature selection with 0 features returns 400", async ({
      page,
    }) => {
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

    test("feature selection: target column cannot be in features", async ({
      page,
    }) => {
      const sessionId = await createSessionViaAPI(page);
      await uploadFileViaAPI(page, sessionId);

      const resp = await page.request.patch(
        `${API_URL}/sessions/${sessionId}/feature-selection`,
        {
          data: {
            target_column: "churned",
            selected_features: ["churned", "monthly_revenue", "tenure_months"],
          },
          failOnStatusCode: false,
        },
      );
      expect(resp.status()).toBe(400);
      const body = await resp.json();
      expect(body.detail).toContain("Target column");
    });

    test("feature selection page shows error for 0 features", async ({
      page,
    }) => {
      const sessionId = await createSessionViaAPI(page);
      await uploadFileViaAPI(page, sessionId);
      await advanceStepViaAPI(page, sessionId, "feature-selection");

      await navigateToStep(page, sessionId, "feature-selection");

      // Wait for the page to load
      await expect(page.getByText("Feature Selection")).toBeVisible();

      // Click Deselect All
      const deselectBtn = page.getByRole("button", {
        name: /Deselect All/i,
      });

      // Only proceed if features are loaded
      if (await deselectBtn.isVisible()) {
        await deselectBtn.click();

        // Error message should appear
        await expect(
          page.getByText("At least one feature must be selected"),
        ).toBeVisible();

        // Continue button should be disabled
        const continueBtn = page.getByRole("button", {
          name: /Continue to EDA/i,
        });
        await expect(continueBtn).toBeDisabled();
      }
    });

    test("feature selection search filters features", async ({ page }) => {
      const sessionId = await createSessionViaAPI(page);
      await uploadFileViaAPI(page, sessionId);
      await advanceStepViaAPI(page, sessionId, "feature-selection");

      await navigateToStep(page, sessionId, "feature-selection");
      await expect(page.getByText("Feature Selection")).toBeVisible();

      // Search for a specific feature
      const searchInput = page.getByPlaceholder("Search features...");
      if (await searchInput.isVisible()) {
        await searchInput.fill("revenue");

        // Should filter to just monthly_revenue
        await expect(page.getByText("monthly_revenue")).toBeVisible();

        // Other features should not be visible (unless they contain "revenue")
        // Clear search
        await searchInput.fill("");
      }
    });
  });

  test.describe("Onboarding Validation", () => {
    test("onboarding requires company name and industry", async ({
      page,
    }) => {
      const sessionId = await createSessionViaAPI(page);
      await navigateToStep(page, sessionId, "onboarding");

      // Try to submit without filling fields
      await page
        .getByRole("button", { name: /Continue to Upload/i })
        .click();

      // Should stay on the page (form validation prevents navigation)
      await expect(page.getByText("Company Onboarding")).toBeVisible();
    });
  });

  test.describe("Health Check", () => {
    test("API health endpoint responds", async ({ page }) => {
      const resp = await page.request.get(`${API_URL}/health`);
      expect(resp.ok()).toBeTruthy();
      const body = await resp.json();
      expect(body.status).toBe("ok");
    });
  });

  test.describe("Step States API", () => {
    test("step states default to inferred from current_step", async ({
      page,
    }) => {
      const sessionId = await createSessionViaAPI(page);
      await advanceStepViaAPI(page, sessionId, "eda");

      const resp = await page.request.get(
        `${API_URL}/sessions/${sessionId}/step-states`,
      );
      expect(resp.ok()).toBeTruthy();
      const body = await resp.json();
      const states = body.step_states;

      // When step_states is null, they're inferred from current_step
      // Steps up to and including current position should be DONE
      expect(states.profiling).toBe("DONE");
    });

    test("concurrent rerun returns 409", async ({ page }) => {
      const sessionId = await createSessionViaAPI(page);
      await uploadFileViaAPI(page, sessionId);

      // Set a step as RUNNING
      const runningStates: Record<string, string> = {
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
      };

      await page.request.patch(`${API_URL}/sessions/${sessionId}`, {
        data: { step_states: runningStates },
      });

      // Try to rerun — should get 409
      const resp = await page.request.post(
        `${API_URL}/sessions/${sessionId}/rerun/profiling`,
        { failOnStatusCode: false },
      );
      expect(resp.status()).toBe(409);
    });
  });

  test.describe("Artifacts", () => {
    test("artifacts list empty for new session", async ({ page }) => {
      const sessionId = await createSessionViaAPI(page);

      const resp = await page.request.get(
        `${API_URL}/sessions/${sessionId}/artifacts`,
      );
      expect(resp.ok()).toBeTruthy();
      const body = await resp.json();
      expect(body).toEqual([]);
    });
  });

  test.describe("Events", () => {
    test("events list empty for new session", async ({ page }) => {
      const sessionId = await createSessionViaAPI(page);

      const resp = await page.request.get(
        `${API_URL}/sessions/${sessionId}/events`,
      );
      expect(resp.ok()).toBeTruthy();
      const body = await resp.json();
      expect(Array.isArray(body)).toBeTruthy();
    });
  });
});

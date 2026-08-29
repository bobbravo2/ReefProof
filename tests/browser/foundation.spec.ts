import { expect, test } from "@playwright/test";

const ORIGIN = "http://127.0.0.1:4179";
const BOOTSTRAP_SECRET = "browser-fixture-secret";

test("tracked Workbench overview bundle mounts through its page and request seams", async ({ page }) => {
  const consoleErrors: string[] = [];
  const failedRequests: string[] = [];
  const navigations: string[] = [];
  const successfulRequests = new Set<string>();

  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("requestfailed", (request) => {
    failedRequests.push(`${request.method()} ${request.url()}: ${request.failure()?.errorText ?? "unknown"}`);
  });
  page.on("framenavigated", (frame) => {
    if (frame === page.mainFrame()) navigations.push(frame.url());
  });
  await page.addInitScript(() => {
    const originalRequest = globalThis.fetch.bind(globalThis);
    (globalThis as typeof globalThis & { __fixtureRequestPaths: string[] }).__fixtureRequestPaths = [];
    globalThis.fetch = (input, init) => {
      const requestUrl = new URL(input instanceof Request ? input.url : String(input), location.href);
      (globalThis as typeof globalThis & { __fixtureRequestPaths: string[] }).__fixtureRequestPaths.push(
        requestUrl.pathname,
      );
      return originalRequest(input, init);
    };
  });
  page.on("response", (response) => {
    if (response.ok()) successfulRequests.add(new URL(response.url()).pathname);
  });
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    expect(url.origin).toBe(ORIGIN);
    if (url.pathname === "/v1/workbench/electrical-posture") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          project_id: "primary-reef-system",
          import_state: "empty",
          headline: "Fixture-backed overview request seam is active.",
          recommended_action: {
            id: "review_unproven_electrical_mappings",
            label: "Review unproven electrical mappings",
            description: "Inspect missing authored evidence.",
            href: "/workbench/system-map",
          },
          observed_entity_count: 0,
          unknown_entity_count: 4,
          redacted_field_count: 0,
          entity_counts: {},
          redaction_categories: {},
          unproven_domains: ["controller topology", "electrical mappings"],
          captured_at: null,
        }),
      });
      return;
    }
    if (url.pathname === "/v1/projects/primary-reef-system/brief") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          project_id: "primary-reef-system",
          recommended_next_action: { status: "UNKNOWN", action: null, reason_codes: ["NO_ACCEPTED_FACTS"] },
          current_posture: {
            posture: "UNKNOWN",
            evaluated_posture: "UNKNOWN",
            trust_status: "TRUSTED",
            reason_codes: ["NO_ACCEPTED_FACTS"],
            contributing_trust_event_ids: [],
          },
          highest_consequence_risks: [],
          important_unknowns: [],
          recent_accepted_decisions: [],
          continue_interview: { based_on_unknown_ids: [] },
        }),
      });
      return;
    }
    if (url.pathname === "/v1/projects/primary-reef-system/reconciliation") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          project_id: "primary-reef-system",
          observed_snapshot_hash: "sha256:fixture-observed",
          observed_captured_at: "2026-08-28T12:00:00Z",
          items: [
            {
              reconciliation_id: "authored:rp:primary-reef-system:device:dev-1",
              state: "AUTHORED_ONLY",
              canonical_subject_id: "rp:primary-reef-system:device:dev-1",
              authored_display_id: "DEV-1",
              observed_entity_id: null,
              observed_vendor_id: null,
              observed_display_name: null,
              detail: "No explicit HYDROS identity binding has been accepted.",
            },
          ],
          matched_count: 0,
          authored_only_count: 1,
          observed_only_count: 0,
          conflict_count: 0,
        }),
      });
      return;
    }
    await route.continue();
  });

  const response = await page.goto("/workbench");
  expect(response?.ok()).toBeTruthy();
  expect(page.url()).toBe(`${ORIGIN}/workbench`);
  await expect(page.locator("body")).toHaveAttribute("data-workbench-page", "overview");
  await expect(page.locator("script[src^='/assets/workbench.js']")).toHaveCount(1);

  await page.locator("input[name='bootstrap_secret']").fill(BOOTSTRAP_SECRET);
  await page.locator("#startup-session-form button[type='submit']").click();

  await expect(page.locator("#page-content")).toBeVisible();
  await expect(page.locator("#electrical-posture")).toBeVisible();
  await expect(page.locator("[data-electrical='headline']")).toHaveText(
    "Fixture-backed overview request seam is active.",
  );
  await expect(page.locator("[data-electrical='import-state']")).toHaveText("EMPTY");
  await expect(page.locator("#system-mode-badge")).toHaveText("FIXTURE · NOT LIVE");
  await expect(page.locator("#reconciliation-status")).toContainText("1 authored only");
  await expect(page.locator("#reconciliation-items")).toContainText(
    "AUTHORED_ONLY · DEV-1",
  );

  expect(successfulRequests).toContain("/assets/workbench.js");
  expect(successfulRequests).toContain("/v1/system/status");
  expect(successfulRequests).toContain("/v1/workbench/operator-sessions");
  expect(successfulRequests).toContain("/v1/workbench/electrical-posture");
  expect(successfulRequests).toContain("/v1/projects/primary-reef-system/reconciliation");
  expect(successfulRequests).not.toContain("/v1/workbench/policy-template");
  const injectedRequestPaths = await page.evaluate(
    () => (globalThis as typeof globalThis & { __fixtureRequestPaths: string[] }).__fixtureRequestPaths,
  );
  expect(injectedRequestPaths).toContain("/v1/workbench/electrical-posture");
  expect(injectedRequestPaths).toContain("/v1/projects/primary-reef-system/reconciliation");
  expect(injectedRequestPaths).not.toContain("/v1/workbench/policy-template");
  expect(navigations).toEqual([`${ORIGIN}/workbench`]);
  expect(failedRequests).toEqual([]);
  // Chromium reports the intentional unauthenticated session probe as a
  // resource error before the bootstrap form is shown. No other console error
  // is accepted.
  expect(consoleErrors).toEqual([
    "Failed to load resource: the server responded with a status of 401 (Unauthorized)",
  ]);
});

import { expect, test } from "@playwright/test";

const ORIGIN = "http://127.0.0.1:4179";
const PROJECT_ROOT = "/v1/projects/primary-reef-system";

test("shipped Source controller reviews a grouped authored import through its request seam", async ({
  page,
}) => {
  const consoleErrors: string[] = [];
  const failedRequests: string[] = [];
  const successfulRequests = new Set<string>();
  const navigations: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("requestfailed", (request) => {
    failedRequests.push(`${request.method()} ${request.url()}`);
  });
  page.on("response", (response) => {
    if (response.ok()) successfulRequests.add(new URL(response.url()).pathname);
  });
  page.on("framenavigated", (frame) => {
    if (frame === page.mainFrame()) navigations.push(frame.url());
  });
  await page.route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    expect(url.origin).toBe(ORIGIN);
    const reply = async (body: unknown, status = 200): Promise<void> => {
      await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    };
    if (url.pathname === `${PROJECT_ROOT}/authored-sources`) {
      await reply([
        {
          source_configuration_id: "source-config-fixture",
          project_id: "primary-reef-system",
          source_alias: "primary-design",
          spreadsheet_id: "sheet-fixture",
          configured_at: "2026-08-16T12:00:00Z",
          freshness_seconds: 900,
        },
      ]);
      return;
    }
    if (url.pathname === `${PROJECT_ROOT}/authored-sources/google-sheets/status`) {
      await reply({
        health: "CHANGED",
        last_successful_fetch_at: "2026-08-16T12:00:00Z",
        latest_snapshot_hash: `sha256:${"a".repeat(64)}`,
        detail: "The latest source differs from accepted authored state and requires review.",
      });
      return;
    }
    if (url.pathname === `${PROJECT_ROOT}/imports`) {
      await reply([
        {
          import_batch_id: "import-fixture",
          fetched_at: "2026-08-16T12:00:00Z",
          source_snapshot_hash: `sha256:${"a".repeat(64)}`,
          normalized_content_hash: `sha256:${"b".repeat(64)}`,
          valid: true,
          record_counts: { DEVICE_INTERFACES: 1 },
          diagnostic_count: 0,
          review_status: "PENDING_REVIEW",
        },
      ]);
      return;
    }
    if (url.pathname === `${PROJECT_ROOT}/authored-sources/google-sheets/sync`) {
      expect(request.method()).toBe("POST");
      await reply(
        {
          import_batch_id: "import-fixture",
          fetched_at: "2026-08-16T12:00:00Z",
          source_snapshot_hash: `sha256:${"a".repeat(64)}`,
          normalized_content_hash: `sha256:${"b".repeat(64)}`,
          valid: true,
          record_counts: { DEVICE_INTERFACES: 1 },
          diagnostic_count: 0,
          review_status: "PENDING_REVIEW",
        },
        201,
      );
      return;
    }
    if (url.pathname === `${PROJECT_ROOT}/imports/import-fixture` && request.method() === "GET") {
      await reply({
        import_batch_id: "import-fixture",
        source_snapshot_hash: `sha256:${"a".repeat(64)}`,
        valid: true,
        state_counts: { NEW: 1, CHANGED: 0, UNCHANGED: 0, CONFLICT: 0, INVALID: 0, REMOVED_FROM_SOURCE: 0 },
        objects: [
          {
            canonical_subject_id: "rp:primary-reef-system:interface:if-1",
            external_namespace: "INTERFACE_ID",
            external_id: "IF-1",
            tab: "DEVICE_INTERFACES",
            source_range: "DEVICE_INTERFACES!2:2",
            state: "NEW",
            changes: [{ attribute: "identity.external_id", proposed_value: "IF-1", accepted_value: null, state: "NEW" }],
          },
        ],
      });
      return;
    }
    if (url.pathname === `${PROJECT_ROOT}/imports/import-fixture/review`) {
      expect(request.method()).toBe("POST");
      expect(request.postDataJSON()).toEqual({
        decision: "ACCEPTED",
        rationale: "Reviewed fixture batch",
        totp_code: "123456",
      });
      await reply({
        import_batch_id: "import-fixture",
        decision: "ACCEPTED",
        reviewed_candidate_count: 5,
        project_sequence: 5,
      }, 201);
      return;
    }
    await route.continue();
  });

  const response = await page.goto("/workbench/source");
  expect(response?.ok()).toBeTruthy();
  await expect(page.locator("body")).toHaveAttribute("data-workbench-page", "source");
  await page.locator("input[name='bootstrap_secret']").fill("browser-fixture-secret");
  await page.locator("#startup-session-form button[type='submit']").click();
  await expect(page.locator("#source-health")).toHaveText("CHANGED");
  await expect(page.locator("#source-workbook")).toContainText("primary-design");
  await page.getByRole("button", { name: "Fetch read-only source now" }).click();
  await expect(page.locator("#source-status")).toContainText("PENDING_REVIEW · import-fixture");
  await page.getByRole("button", { name: /PENDING_REVIEW · import-fixture/ }).click();
  await expect(page.locator("#source-review-summary")).toContainText("NEW: 1");
  await page.locator("#source-review-form input[name='rationale']").fill("Reviewed fixture batch");
  await page.locator("#source-review-form input[name='totp_code']").fill("123456");
  await page.locator("#source-review-form button[type='submit']").click();
  await expect(page.locator("#source-review-status")).toContainText("ACCEPTED: 5 candidates");

  expect(successfulRequests).toContain("/assets/workbench.js");
  expect(successfulRequests).toContain(
    `${PROJECT_ROOT}/authored-sources/google-sheets/sync`,
  );
  expect(successfulRequests).toContain(`${PROJECT_ROOT}/imports/import-fixture/review`);
  expect(navigations).toEqual([`${ORIGIN}/workbench/source`]);
  expect(failedRequests).toEqual([]);
  expect(consoleErrors).toEqual([
    "Failed to load resource: the server responded with a status of 401 (Unauthorized)",
  ]);
});

import { expect, test } from "@playwright/test";
import { readFile } from "node:fs/promises";

const ORIGIN = "http://127.0.0.1:4179";
const PROJECT_ROOT = "/v1/projects/primary-reef-system";

test("operator loads, reviews, accepts, and exports the first CSV batch", async ({ page }) => {
  test.setTimeout(60_000);
  const consoleErrors: string[] = [];
  const failedRequests: { url: string; error: string }[] = [];
  const successfulRequests = new Set<string>();
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("requestfailed", (request) =>
    failedRequests.push({
      url: request.url(),
      error: request.failure()?.errorText ?? "unknown",
    }),
  );
  page.on("response", (response) => {
    if (response.ok()) successfulRequests.add(new URL(response.url()).pathname);
  });
  await page.route("**/*", async (route) => {
    expect(new URL(route.request().url()).origin).toBe(ORIGIN);
    await route.continue();
  });

  await page.goto("/workbench/source");
  await page.locator("input[name='bootstrap_secret']").fill("browser-fixture-secret");
  await page.locator("#startup-session-form button[type='submit']").click();
  await expect(page.locator("#source-health")).toHaveText("NOT_CONFIGURED");
  await page.getByRole("button", { name: "Fetch read-only source now" }).click();
  await expect(page.locator("#source-status")).toContainText("PENDING_REVIEW");

  await page.reload();
  await expect(page.getByRole("button", { name: /PENDING_REVIEW ·/ })).toBeVisible();
  await page.getByRole("button", { name: /PENDING_REVIEW ·/ }).click();
  await expect(page.locator("#source-review-summary")).toContainText("NEW:");
  await expect(page.locator("#source-review-objects")).toContainText("DEVICE_INTERFACES");
  await expect(page.locator("#source-review-objects")).toContainText("DEVICE_INTERFACES!2:2");
  await page.locator("#source-review-form input[name='rationale']").fill(
    "Reviewed the fixture source ranges and physical identities",
  );
  await page.locator("#source-review-form input[name='totp_code']").fill("123456");
  await page.locator("#source-review-form button[type='submit']").click();
  await expect(page.locator("#source-review-status")).toContainText("ACCEPTED:");

  await page.goto("/workbench");
  await expect(page).toHaveTitle("Overview · Primary Reef System · ReefProof");
  const reconciliationForm = page.locator("#reconciliation-binding-form");
  await reconciliationForm.locator("input[name='canonical_device_id']").fill(
    "rp:primary-reef-system:device:dev-1",
  );
  await reconciliationForm.locator("input[name='observed_entity_id']").fill(
    "RP.CONTROLLER.2ce799bf32d5fbe0",
  );
  await reconciliationForm.locator("input[name='evidence_reference']").fill(
    "fixture-onsite-identity-comparison",
  );
  await reconciliationForm.locator("input[name='rationale']").fill(
    "Explicitly matched accepted authored identity to sanitized observed evidence",
  );
  await reconciliationForm.locator("input[name='totp_code']").fill("123456");
  await reconciliationForm.getByRole("button", { name: "Record explicit identity binding" }).click();
  await expect(page.locator("#reconciliation-binding-status")).toContainText(
    "Explicit observed identity binding recorded",
  );
  await expect(page.locator("#reconciliation-status")).toContainText("1 matched");

  await page.goto("/workbench/commissioning");
  await expect(page.locator("#commissioning-devices")).toContainText(
    "UNKNOWN · Physical connection verification",
  );
  const verificationForm = page.locator("#commissioning-verification-form");
  await verificationForm.locator("input[name='device_id']").fill(
    "rp:primary-reef-system:device:dev-1",
  );
  await verificationForm.locator("select[name='kind']").selectOption("CONNECTION");
  await verificationForm.locator("input[name='connection_id']").fill(
    "rp:primary-reef-system:cable:cbl-0001",
  );
  await verificationForm.locator("input[name='evidence_reference']").fill(
    "fixture-physical-connection-photo",
  );
  await verificationForm.locator("input[name='rationale']").fill(
    "Matched the installed FROM and TO endpoints",
  );
  await verificationForm.locator("input[name='totp_code']").fill("123456");
  await verificationForm.getByRole("button", { name: "Record verification" }).click();
  await expect(page.locator("#commissioning-action-status")).toContainText(
    "Recorded CONNECTION PASS",
  );
  await expect(page.locator("#commissioning-devices")).toContainText(
    "PASS · Physical connection verification",
  );
  const recordVerification = async (
    kind: "POWER" | "COMMUNICATIONS" | "FAULT_TEST",
    outcome: "PASS" | "NOT_APPLICABLE",
    controlSurface = "",
  ): Promise<void> => {
    await verificationForm.locator("select[name='kind']").selectOption(kind);
    await verificationForm.locator("select[name='outcome']").selectOption(outcome);
    await verificationForm.locator("input[name='connection_id']").fill("");
    await verificationForm.locator("input[name='control_surface_id']").fill(controlSurface);
    await verificationForm.locator("input[name='evidence_reference']").fill(
      `fixture-${kind.toLowerCase()}-evidence`,
    );
    await verificationForm.locator("input[name='rationale']").fill(
      `Reviewed bounded ${kind.toLowerCase()} evidence`,
    );
    await verificationForm.locator("input[name='totp_code']").fill("123456");
    const response = page.waitForResponse(
      (item) =>
        new URL(item.url()).pathname === `${PROJECT_ROOT}/commissioning/verifications` &&
        item.request().method() === "POST",
    );
    const refreshedProjection = page.waitForResponse(
      (item) =>
        new URL(item.url()).pathname === `${PROJECT_ROOT}/commissioning` &&
        item.request().method() === "GET",
    );
    await verificationForm.getByRole("button", { name: "Record verification" }).click();
    expect((await response).ok()).toBeTruthy();
    expect((await refreshedProjection).ok()).toBeTruthy();
    await expect(page.locator("#commissioning-action-status")).toContainText(
      `Recorded ${kind} ${outcome}`,
    );
  };
  await recordVerification("POWER", "PASS");
  await recordVerification("COMMUNICATIONS", "NOT_APPLICABLE");
  await recordVerification(
    "FAULT_TEST",
    "PASS",
    "rp:primary-reef-system:output:out-1",
  );

  const dispositionForm = page.locator("#failure-mode-form");
  await dispositionForm.locator("input[name='device_id']").fill(
    "rp:primary-reef-system:device:dev-1",
  );
  for (const failureMode of ["power_loss", "control_link_loss", "leak_or_flow_loss"]) {
    await dispositionForm.locator("select[name='failure_mode_id']").selectOption(failureMode);
    await dispositionForm.locator("input[name='evidence_reference']").fill(
      `fixture-${failureMode}-evidence`,
    );
    await dispositionForm.locator("input[name='rationale']").fill(
      `Reviewed ${failureMode.replaceAll("_", " ")}`,
    );
    await dispositionForm.locator("input[name='totp_code']").fill("123456");
    const response = page.waitForResponse(
      (item) =>
        new URL(item.url()).pathname ===
          `${PROJECT_ROOT}/commissioning/failure-mode-dispositions` &&
        item.request().method() === "POST",
    );
    const refreshedProjection = page.waitForResponse(
      (item) =>
        new URL(item.url()).pathname === `${PROJECT_ROOT}/commissioning` &&
        item.request().method() === "GET",
    );
    await dispositionForm.getByRole("button", { name: "Record disposition" }).click();
    expect((await response).ok()).toBeTruthy();
    expect((await refreshedProjection).ok()).toBeTruthy();
  }

  await page.goto("/workbench/labels");
  await expect(page.locator("#labels-status")).toContainText("Primary Reef System · 4 labels");
  await expect(page.locator("#label-records")).toContainText("CABLE · CBL-0001 · 2 copies");
  const downloadPromise = page.waitForEvent("download");
  await page.locator("#labels-export").click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe(
    "reefproof-primary-reef-system-v0.1.2-labels.csv",
  );
  const downloadPath = await download.path();
  expect(downloadPath).not.toBeNull();
  const csv = await readFile(downloadPath!, "utf8");
  expect(csv).toContain("DEVICE,DEV-1");
  expect(csv).toContain("PORT,PORT-1");
  expect(csv).toContain("CABLE,CBL-0001");
  expect(csv).toContain("POWER SUPPLY,PSU-1");
  const labelForm = page.locator("#label-verification-form");
  const verifyLabel = async (labelId: string, endpoint: "ITEM" | "FROM" | "TO") => {
    await labelForm.locator("input[name='device_id']").fill(
      "rp:primary-reef-system:device:dev-1",
    );
    await labelForm.locator("input[name='label_id']").fill(labelId);
    await labelForm.locator("select[name='label_endpoint']").selectOption(endpoint);
    await labelForm.locator("input[name='evidence_reference']").fill(
      `fixture-${labelId}-${endpoint}`,
    );
    await labelForm.locator("input[name='rationale']").fill(
      `Physically matched ${labelId} at ${endpoint}`,
    );
    await labelForm.locator("input[name='totp_code']").fill("123456");
    const response = page.waitForResponse(
      (item) =>
        new URL(item.url()).pathname ===
          `${PROJECT_ROOT}/commissioning/label-verifications` &&
        item.request().method() === "POST",
    );
    await labelForm.getByRole("button", { name: "Record label verification" }).click();
    expect((await response).ok()).toBeTruthy();
  };
  await verifyLabel("device:DEV-1", "ITEM");
  await verifyLabel("port:PORT-1", "ITEM");
  await verifyLabel("cable:CBL-0001", "FROM");
  await verifyLabel("cable:CBL-0001", "TO");

  await page.goto("/workbench/commissioning");
  await expect(page.locator("#commissioning-devices")).toContainText("COMMISSIONED · DEV-1");
  await expect(page.locator("#commissioning-devices li")).toHaveCount(9);
  await expect(page.locator("#commissioning-devices li").filter({ hasText: "UNKNOWN" })).toHaveCount(0);

  expect(successfulRequests).toContain(
    `${PROJECT_ROOT}/authored-sources/google-sheets/sync`,
  );
  expect([...successfulRequests].some((path) => path.endsWith("/review"))).toBeTruthy();
  expect(successfulRequests).toContain(`${PROJECT_ROOT}/commissioning/verifications`);
  expect(successfulRequests).toContain(`${PROJECT_ROOT}/labels`);
  expect(successfulRequests).toContain(`${PROJECT_ROOT}/reconciliation/bindings`);
  const unexpectedFailures = failedRequests.filter((failure) => {
    const url = new URL(failure.url);
    return !(
      url.origin === ORIGIN &&
      url.pathname === "/v1/workbench/totp" &&
      failure.error === "net::ERR_ABORTED"
    );
  });
  expect(unexpectedFailures).toEqual([]);
  expect(consoleErrors).toEqual([
    "Failed to load resource: the server responded with a status of 401 (Unauthorized)",
  ]);
});

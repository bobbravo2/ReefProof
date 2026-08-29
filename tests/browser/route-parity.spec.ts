import { expect, test } from "@playwright/test";

const ORIGIN = "http://127.0.0.1:4179";

test("existing Workbench routes retain authenticated real-browser parity", async ({ page }) => {
  const consoleErrors: string[] = [];
  const failedRequests: string[] = [];
  const successfulRequests = new Set<string>();
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("requestfailed", (request) => {
    failedRequests.push(`${request.method()} ${request.url()}: ${request.failure()?.errorText ?? "unknown"}`);
  });
  page.on("response", (response) => {
    if (response.ok()) successfulRequests.add(new URL(response.url()).pathname);
  });
  await page.route("**/*", async (route) => {
    expect(new URL(route.request().url()).origin).toBe(ORIGIN);
    await route.continue();
  });

  await page.goto("/workbench/assurance");
  await page.locator("input[name='bootstrap_secret']").fill("browser-fixture-secret");
  await page.locator("#startup-session-form button[type='submit']").click();
  await expect(page.locator("#policy-inputs")).toBeVisible();

  await page.goto("/workbench/evidence");
  await expect(page.locator("#rule-catalog")).toBeVisible();
  await expect(page.locator("#evidence-status")).not.toHaveClass(/notice--error/);

  await page.goto("/workbench/system-map");
  await expect(page.locator("#system-map-status")).toContainText(
    "explicit observed bindings loaded",
  );
  await expect(page.locator("#reconciliation-status")).toContainText("observed only");

  await page.goto("/workbench/sessions");
  await expect(page.locator("#project-sessions")).toBeVisible();
  await expect(page.locator("#project-status")).toContainText(
    "Durable sessions and candidates loaded.",
  );

  await page.goto("/workbench/database");
  await expect(page.locator("#database-explorer")).toBeVisible();
  await expect(page.locator("#database-status")).toContainText(
    "loaded through the query-only boundary.",
  );

  for (const path of [
    "/v1/workbench/policy-template",
    "/v1/workbench/invariant-catalog",
    "/v1/projects/primary-reef-system/reconciliation",
    "/v1/projects/primary-reef-system/sessions",
    "/v1/database/schema",
  ]) {
    expect(successfulRequests).toContain(path);
  }
  expect(
    failedRequests.filter(
      (failure) =>
        failure !== `GET ${ORIGIN}/v1/workbench/totp: net::ERR_ABORTED`,
    ),
  ).toEqual([]);
  expect(consoleErrors).toEqual([
    "Failed to load resource: the server responded with a status of 401 (Unauthorized)",
  ]);
});

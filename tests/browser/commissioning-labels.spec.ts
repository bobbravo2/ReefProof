import { expect, test } from "@playwright/test";

const ORIGIN = "http://127.0.0.1:4179";
const PROJECT_ROOT = "/v1/projects/primary-reef-system";
const DEVICE = "rp:primary-reef-system:device:dev-1";

test("shipped Commissioning and Labels controllers preserve UNKNOWN and verify CSV output", async ({
  page,
}) => {
  const consoleErrors: string[] = [];
  const failedRequests: { url: string; error: string }[] = [];
  const successfulRequests = new Set<string>();
  const navigations: string[] = [];
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
  page.on("framenavigated", (frame) => {
    if (frame === page.mainFrame()) navigations.push(frame.url());
  });
  const projection = {
    project_id: "primary-reef-system",
    devices: [
      {
        device_id: "DEV-1",
        canonical_device_id: DEVICE,
        display_name: "DEV-1",
        state: "IN_PROGRESS",
        requirements: [
          {
            requirement_id: "power",
            label: "Power verification",
            state: "UNKNOWN",
            detail: "Power evidence is missing.",
            evidence_ids: [],
          },
        ],
        next_action: "Power evidence is missing.",
      },
    ],
    commissioned_count: 0,
    blocked_count: 0,
    unknown_requirement_count: 1,
  };
  const manifest = {
    manifest_id: "label-manifest-fixture",
    manifest_schema_version: "labels-v1",
    label_policy_version: "labels-v1",
    project_id: "primary-reef-system",
    project_name: "Primary Reef System",
    source_project_sequence: 42,
    records: [
      {
        label_id: "cable:CBL-0001",
        label_kind: "CABLE",
        canonical_subject_id: "rp:primary-reef-system:cable:cbl-0001",
        display_id: "CBL-0001",
        from_zone: "Cabinet",
        from_device: "Controller",
        from_port: "Output 1",
        to_zone: "Sump",
        to_device: "DEV-1",
        to_port: "Power",
        primary_text: "FROM: Cabinet · Controller · Output 1",
        secondary_text: "TO: Sump · DEV-1 · Power | CABLE: CBL-0001",
        copies: 2,
      },
    ],
  };
  await page.route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    expect(url.origin).toBe(ORIGIN);
    const json = async (body: unknown, status = 200): Promise<void> => {
      await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    };
    if (url.pathname === `${PROJECT_ROOT}/commissioning` && request.method() === "GET") {
      await json(projection);
      return;
    }
    if (url.pathname === `${PROJECT_ROOT}/commissioning/verifications`) {
      expect(request.postDataJSON()).toMatchObject({
        device_id: DEVICE,
        kind: "POWER",
        outcome: "PASS",
      });
      await json(
        {
          ...request.postDataJSON(),
          verification_id: "verification-power",
          project_id: "primary-reef-system",
          verified_by_actor_id: "acceptance-authority",
          verified_at: "2026-08-16T12:00:00Z",
        },
        201,
      );
      return;
    }
    if (url.pathname === `${PROJECT_ROOT}/labels`) {
      await json(manifest);
      return;
    }
    if (url.pathname === `${PROJECT_ROOT}/commissioning/label-verifications`) {
      expect(request.postDataJSON()).toMatchObject({
        device_id: DEVICE,
        kind: "LABEL",
        label_id: "cable:CBL-0001",
        label_endpoint: "FROM",
      });
      await json(
        {
          ...request.postDataJSON(),
          verification_id: "verification-label-from",
          project_id: "primary-reef-system",
          verified_by_actor_id: "acceptance-authority",
          verified_at: "2026-08-16T12:01:00Z",
        },
        201,
      );
      return;
    }
    await route.continue();
  });

  await page.goto("/workbench/commissioning");
  await page.locator("input[name='bootstrap_secret']").fill("browser-fixture-secret");
  await page.locator("#startup-session-form button[type='submit']").click();
  await expect(page.locator("#commissioning-status")).toContainText("1 unknown requirements");
  await expect(page.locator("#commissioning-devices")).toContainText("UNKNOWN · Power verification");
  const verification = page.locator("#commissioning-verification-form");
  await verification.locator("input[name='device_id']").fill(DEVICE);
  await verification.locator("select[name='kind']").selectOption("POWER");
  await verification.locator("input[name='evidence_reference']").fill("meter-photo-1");
  await verification.locator("input[name='rationale']").fill("Verified bounded power behavior");
  await verification.locator("input[name='totp_code']").fill("123456");
  const refreshedProjection = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === `${PROJECT_ROOT}/commissioning` && response.ok(),
  );
  await verification.getByRole("button", { name: "Record verification" }).click();
  await expect(page.locator("#commissioning-action-status")).toContainText("Recorded POWER PASS");
  await refreshedProjection;

  await page.goto("/workbench/labels");
  await expect(page.locator("#labels-status")).toContainText("Primary Reef System · 1 labels");
  await expect(page.locator("#label-records")).toContainText("FROM: Cabinet · Controller · Output 1");
  const labelForm = page.locator("#label-verification-form");
  await labelForm.locator("input[name='device_id']").fill(DEVICE);
  await labelForm.locator("input[name='label_id']").fill("cable:CBL-0001");
  await labelForm.locator("select[name='label_endpoint']").selectOption("FROM");
  await labelForm.locator("input[name='evidence_reference']").fill("applied-photo-from");
  await labelForm.locator("input[name='rationale']").fill("Matched the cable and FROM endpoint");
  await labelForm.locator("input[name='totp_code']").fill("654321");
  await labelForm.getByRole("button", { name: "Record label verification" }).click();
  await expect(page.locator("#label-verification-status")).toContainText("Recorded PASS");
  const downloadPromise = page.waitForEvent("download");
  await page.locator("#labels-export").click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe(
    "reefproof-primary-reef-system-v0.1.2-labels.csv",
  );
  expect(await download.path()).not.toBeNull();

  expect(successfulRequests).toContain(`${PROJECT_ROOT}/commissioning/verifications`);
  expect(successfulRequests).toContain(`${PROJECT_ROOT}/commissioning/label-verifications`);
  expect(navigations).toEqual([
    `${ORIGIN}/workbench/commissioning`,
    `${ORIGIN}/workbench/labels`,
  ]);
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

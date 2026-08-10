const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const workflow = readFileSync(
  path.resolve(__dirname, "../../.github/workflows/delivery.yml"),
  "utf8",
);
const releaseWorkflow = readFileSync(
  path.resolve(__dirname, "../../.github/workflows/release.yml"),
  "utf8",
);

test("delivery builds the desktop app from the checked-out commit after quality", () => {
  const desktop = workflow.indexOf("  desktop:");
  const container = workflow.indexOf("  container:");
  const job = workflow.slice(desktop, container);

  assert.ok(desktop > 0);
  assert.match(job, /needs: quality/);
  assert.match(job, /runs-on: macos-latest/);
  assert.match(job, /node-version: "22\.12\.0"/);
  assert.match(job, /- run: npm ci/);
  assert.match(job, /- run: make test\/desktop/);
  assert.match(job, /- run: make build\/desktop-app/);
});

test("delivery uploads one unsigned macOS application archive without publishing", () => {
  const desktop = workflow.indexOf("  desktop:");
  const container = workflow.indexOf("  container:");
  const job = workflow.slice(desktop, container);

  assert.match(job, /ditto -c -k --sequesterRsrc --keepParent/);
  assert.match(job, /actions\/upload-artifact@[0-9a-f]{40}/);
  assert.match(job, /reefproof-desktop-\$\{\{ runner\.os \}\}-\$\{\{ runner\.arch \}\}/);
  for (const forbidden of ["release", "publish", "codesign", "notarytool"])
    assert.doesNotMatch(job.toLowerCase(), new RegExp(forbidden));
});

test("delivery validates OCI labels with executable Docker templates", () => {
  const container = workflow.indexOf("  container:");
  const job = workflow.slice(container);

  assert.ok(container > 0);
  assert.match(
    job,
    /--format '\{\{index \.Config\.Labels "org\.opencontainers\.image\.source"\}\}'/,
  );
  assert.match(
    job,
    /--format '\{\{index \.Config\.Labels "org\.opencontainers\.image\.revision"\}\}'/,
  );
  assert.doesNotMatch(job, /\\"org\.opencontainers\.image\./);
});

test("tag publication creates a GitHub release with immutable deployment evidence", () => {
  assert.match(releaseWorkflow, /contents: write/);
  assert.match(releaseWorkflow, /gh release create "\$GITHUB_REF_NAME"/);
  assert.match(releaseWorkflow, /reefproof-release\.md#release-receipt\.md/);
  assert.match(releaseWorkflow, /reefproof\.spdx\.json#reefproof\.spdx\.json/);
  assert.match(
    releaseWorkflow,
    /reefproof\.vulnerabilities\.json#reefproof\.vulnerabilities\.json/,
  );
  assert.match(releaseWorkflow, /--verify-tag/);
  assert.match(releaseWorkflow, /--notes-file reefproof-release\.md/);
  assert.match(releaseWorkflow, /Deploy the immutable OCI digest above/);
});

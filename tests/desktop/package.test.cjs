const assert = require("node:assert/strict");
const { mkdir, mkdtemp, readFile, stat, utimes, writeFile } = require("node:fs/promises");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const repo = path.resolve(__dirname, "../..");

test("desktop package version comes from the ReefProof project", async () => {
  const { createDesktopStage, readProjectVersion } = await import("../../scripts/package-desktop.mjs");
  const stage = await mkdtemp(path.join(os.tmpdir(), "reefproof-desktop-stage-"));
  const version = await readProjectVersion(repo);
  const pyproject = await readFile(path.join(repo, "pyproject.toml"), "utf8");
  const declaredVersion = /^version = "(\d+\.\d+\.\d+)"$/m.exec(pyproject)[1];
  await createDesktopStage(repo, stage, version);
  const packageJson = JSON.parse(await readFile(path.join(stage, "package.json"), "utf8"));

  assert.equal(version, declaredVersion);
  assert.equal(packageJson.version, version);
  assert.equal(packageJson.productName, "ReefProof");
  assert.equal(packageJson.main, "main.mjs");
  assert.deepEqual(Object.keys(packageJson).sort(), ["main", "name", "private", "productName", "version"]);
});

test("desktop binary identity requires the project version and current revision", async () => {
  const { verifyBinaryIdentity } = await import("../../scripts/package-desktop.mjs");
  const output = "ReefProof 0.1.0\nGit commit: abc123\n";

  assert.doesNotThrow(() => verifyBinaryIdentity(output, "0.1.0", "abc123"));
  assert.throws(() => verifyBinaryIdentity(output, "0.1.1", "abc123"), /project version/);
  assert.throws(() => verifyBinaryIdentity(output, "0.1.0", "def456"), /Git revision/);
});

test("desktop package timestamps use one deterministic build instant", async () => {
  const { normalizeTreeTimestamps } = await import("../../scripts/package-desktop.mjs");
  const root = await mkdtemp(path.join(os.tmpdir(), "reefproof-desktop-times-"));
  const nested = path.join(root, "Contents", "Resources");
  const file = path.join(nested, "app.asar");
  await mkdir(nested, { recursive: true });
  await writeFile(file, "fixture");
  const archiveEpoch = new Date("1980-01-01T00:00:00Z");
  await utimes(file, archiveEpoch, archiveEpoch);
  const buildDate = new Date("2026-07-31T22:19:38-04:00");

  await normalizeTreeTimestamps(root, buildDate);

  for (const entry of [file, nested, path.dirname(nested), root]) {
    assert.ok(Math.abs((await stat(entry)).mtimeMs - buildDate.getTime()) < 1_000);
  }
});

test("desktop package rejects private runtime state", async () => {
  const { assertNoPrivateRuntimeState } = await import("../../scripts/package-desktop.mjs");
  const root = await mkdtemp(path.join(os.tmpdir(), "reefproof-desktop-private-"));
  await mkdir(path.join(root, ".local", "data"), { recursive: true });
  await writeFile(path.join(root, ".local", "data", "operator-totp.json"), "fixture-secret");
  await assert.rejects(() => assertNoPrivateRuntimeState(root), /private runtime state/);

  const clean = await mkdtemp(path.join(os.tmpdir(), "reefproof-desktop-clean-"));
  await writeFile(path.join(clean, "icon.png"), "fixture");
  await assertNoPrivateRuntimeState(clean);
});

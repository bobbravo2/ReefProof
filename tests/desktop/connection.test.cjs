const assert = require("node:assert/strict");
const test = require("node:test");

test("desktop defaults to local managed mode", async () => {
  const { resolveDesktopConnection } = await import("../../.build/desktop/connection.mjs");
  assert.deepEqual(resolveDesktopConnection({}), {
    mode: "local-managed",
    origin: "http://127.0.0.1:8787",
    insecureLanHttp: false,
  });
});
test("remote mode accepts an explicit private LXC origin", async () => {
  const { resolveDesktopConnection } = await import("../../.build/desktop/connection.mjs");
  assert.deepEqual(resolveDesktopConnection({
    REEFPROOF_DESKTOP_MODE: "remote-hosted",
    REEFPROOF_REMOTE_ORIGIN: "http://192.168.10.42:8787",
  }), {
    mode: "remote-hosted",
    origin: "http://192.168.10.42:8787",
    insecureLanHttp: true,
  });
});

test("remote origin validation fails closed", async () => {
  const { resolveDesktopConnection } = await import("../../.build/desktop/connection.mjs");
  const rejected = [
    "http://127.0.0.1:8787",
    "http://8.8.8.8:8787",
    "http://169.254.169.254/latest/meta-data",
    "http://user:password@192.168.1.20:8787",
    "http://192.168.1.20:8787/#fragment",
    "http://192.168.1.20:8787/workbench",
    "https://example.com",
  ];
  for (const origin of rejected) {
    assert.throws(() => resolveDesktopConnection({
      REEFPROOF_DESKTOP_MODE: "remote-hosted",
      REEFPROOF_REMOTE_ORIGIN: origin,
    }), /remote ReefProof origin/);
  }
});

test("remote mode never owns a local runtime", async () => {
  const { ownsLocalRuntime } = await import("../../.build/desktop/connection.mjs");
  assert.equal(ownsLocalRuntime("local-managed"), true);
  assert.equal(ownsLocalRuntime("remote-hosted"), false);
});

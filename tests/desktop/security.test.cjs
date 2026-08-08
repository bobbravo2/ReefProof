const assert = require("node:assert/strict");
const test = require("node:test");

test("desktop renderer uses conservative Electron isolation", async () => {
  const { SECURE_WEB_PREFERENCES } = await import("../../.build/desktop/security.mjs");
  assert.deepEqual(SECURE_WEB_PREFERENCES, {
    nodeIntegration: false,
    contextIsolation: true,
    sandbox: true,
  });
  assert.equal("preload" in SECURE_WEB_PREFERENCES, false);
});

test("navigation stays local and every child window is denied", async () => {
  const { applySecurityPolicy } = await import("../../.build/desktop/security.mjs");
  const listeners = new Map();
  let windowHandler;
  const opened = [];
  const contents = {
    on(name, listener) { listeners.set(name, listener); },
    setWindowOpenHandler(handler) { windowHandler = handler; },
  };
  applySecurityPolicy(contents, "http://127.0.0.1:8787", async (url) => { opened.push(url); });

  let prevented = false;
  listeners.get("will-navigate")({ preventDefault() { prevented = true; } }, "https://unexpected.example/");
  assert.equal(prevented, true);

  prevented = false;
  listeners.get("will-navigate")({ preventDefault() { prevented = true; } }, "http://127.0.0.1:8787/workbench/evidence");
  assert.equal(prevented, false);

  assert.deepEqual(windowHandler({ url: "https://docs.example/" }), { action: "deny" });
  await Promise.resolve();
  assert.deepEqual(opened, ["https://docs.example/"]);
  assert.deepEqual(windowHandler({ url: "http://127.0.0.1:8787/workbench" }), { action: "deny" });
  assert.deepEqual(opened, ["https://docs.example/"]);
});

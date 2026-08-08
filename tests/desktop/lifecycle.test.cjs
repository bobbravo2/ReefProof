const assert = require("node:assert/strict");
const { spawn } = require("node:child_process");
const { EventEmitter } = require("node:events");
const test = require("node:test");

test("desktop shutdown terminates its development child", async () => {
  const { terminateChild } = await import("../../.build/desktop/lifecycle.mjs");
  const child = spawn(process.execPath, ["-e", "setInterval(() => {}, 1000)"], { stdio: "ignore" });
  assert.equal(child.exitCode, null);
  await terminateChild(child, 2_000);
  assert.notEqual(child.signalCode, null);
});

test("desktop refuses to attach to an already occupied listener", async () => {
  const { assertLoopbackPortAvailable } = await import("../../.build/desktop/lifecycle.mjs");
  class OccupiedProbe extends EventEmitter {
    unref() {}
    listen() { queueMicrotask(() => this.emit("error", Object.assign(new Error("occupied"), { code: "EADDRINUSE" }))); }
  }
  await assert.rejects(
    assertLoopbackPortAvailable("127.0.0.1", 8790, () => new OccupiedProbe()),
    { code: "EADDRINUSE" },
  );
});

test("desktop quits when its development launcher exits", async () => {
  const { quitWhenParentExits } = await import("../../.build/desktop/lifecycle.mjs");
  let quit = false;
  quitWhenParentExits(123, () => { quit = true; }, 1, () => false);
  await new Promise((resolve) => setTimeout(resolve, 10));
  assert.equal(quit, true);
});

"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const root = path.resolve(__dirname, "../..");
const config = JSON.parse(
  fs.readFileSync(path.join(root, "playwright-mcp.config.json"), "utf8"),
);
const guard = require(path.join(root, "scripts/playwright-mcp-loopback-guard.cjs"));

test("MCP harness is exact, isolated, and writes only ignored local evidence", () => {
  const packageJson = JSON.parse(fs.readFileSync(path.join(root, "package.json"), "utf8"));
  const gitignore = fs.readFileSync(path.join(root, ".gitignore"), "utf8").split(/\r?\n/);

  assert.equal(packageJson.devDependencies["@playwright/mcp"], "0.0.78");
  assert.equal(packageJson.scripts["ux:mcp"], "playwright-mcp --config playwright-mcp.config.json");
  assert.equal(config.browser.isolated, true);
  assert.equal(config.browser.launchOptions.headless, true);
  assert.deepEqual(config.capabilities, ["core"]);
  assert.equal(config.codegen, "none");
  assert.deepEqual(config.network.allowedOrigins, [guard.ALLOWED_ORIGIN]);
  assert.equal(config.outputDir, ".local/ux-review");
  assert.ok(gitignore.includes(".local/"));
  assert.equal(config.saveSession, false);
});

test("repository skill is discoverable from UX and usability critique requests", () => {
  const skillPath = ".codex/skills/reefproof-ux-review/SKILL.md";
  const agentMetadataPath = ".codex/skills/reefproof-ux-review/agents/openai.yaml";
  const codexConfigPath = ".codex/config.toml";
  const skill = fs.readFileSync(path.join(root, skillPath), "utf8");
  const agentMetadata = fs.readFileSync(path.join(root, agentMetadataPath), "utf8");
  const codexConfig = fs.readFileSync(path.join(root, codexConfigPath), "utf8");

  requireTokens(skill, skillPath, [
    "name: reefproof-ux-review",
    '"UX review"',
    '"UX critique"',
    '"help with a usability critique"',
    "reefproof_playwright",
    "http://127.0.0.1:8787",
    "`/v1/system/health/live`",
    "Do not enter an operator token",
    "NOT TESTED",
  ]);
  requireTokens(agentMetadata, agentMetadataPath, [
    'display_name: "ReefProof UX Review"',
    'default_prompt: "Use $reefproof-ux-review',
  ]);
  requireTokens(codexConfig, codexConfigPath, [
    "[mcp_servers.reefproof_playwright]",
    'args = ["run", "--silent", "ux:mcp"]',
  ]);
});

test("loopback guard rejects alternate hosts, ports, protocols, and redirect targets", () => {
  const allowed = [
    "http://127.0.0.1:8787/workbench",
    "http://127.0.0.1:8787/static/workbench.css",
  ];
  const blocked = [
    "http://localhost:8787/workbench",
    "http://127.0.0.1:8000/workbench",
    "https://127.0.0.1:8787/workbench",
    "http://192.168.1.10:8787/workbench",
    "https://example.com/redirected",
    "file:///tmp/private",
    "data:text/html,unsafe",
    "not a URL",
  ];

  for (const url of allowed) assert.equal(guard.isAllowedRequest(url), true, url);
  for (const url of blocked) assert.equal(guard.isAllowedRequest(url), false, url);
});

test("loopback guard continues only exact-origin requests", async () => {
  let handler;
  const page = {
    route: async (pattern, callback) => {
      assert.equal(pattern, "**/*");
      handler = callback;
    },
  };
  await guard.default({ page });

  const calls = [];
  const fakeRoute = (url) => ({
    request: () => ({ url: () => url }),
    continue: async () => calls.push(["continue", url]),
    abort: async (reason) => calls.push(["abort", url, reason]),
  });

  await handler(fakeRoute("http://127.0.0.1:8787/workbench"));
  await handler(fakeRoute("https://example.com/redirected"));

  assert.deepEqual(calls, [
    ["continue", "http://127.0.0.1:8787/workbench"],
    ["abort", "https://example.com/redirected", "blockedbyclient"],
  ]);
});

function requireTokens(content, file, tokens) {
  const missing = tokens.filter((token) => !content.includes(token));

  assert.equal(
    missing.length,
    0,
    `${file} is missing required contract tokens:\n${missing
      .map((token) => `- ${JSON.stringify(token)}`)
      .join("\n")}`,
  );
}

test("reviewer remains advisory and defines desktop/mobile evidence", () => {
  const reviewerPath = ".codex/agents/reefproof-reviewer.toml";
  const runbookPath = "docs/ux-review-harness.md";

  const reviewer = fs.readFileSync(path.join(root, reviewerPath), "utf8");
  const runbook = fs.readFileSync(path.join(root, runbookPath), "utf8");

  requireTokens(reviewer, reviewerPath, [
    'sandbox_mode = "read-only"',
    "Never edit files",
    "MATERIAL_ISSUE",
    "NO_ACTION",
  ]);

  requireTokens(runbook, runbookPath, [
    "1440 x 1000",
    "390 x 844",
    "reefproof-workbench-desktop.png",
    "reefproof-workbench-mobile.png",
    "NOT TESTED",
  ]);
});

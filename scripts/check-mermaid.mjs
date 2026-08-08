#!/usr/bin/env node

import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import process from "node:process";

import { JSDOM } from "jsdom";

const dom = new JSDOM("<!doctype html><html><body></body></html>");
globalThis.window = dom.window;
globalThis.document = dom.window.document;
const { default: mermaid } = await import("mermaid");

function stagedMarkdownPaths() {
  const output = execFileSync(
    "git",
    [
      "diff",
      "--cached",
      "--name-only",
      "--diff-filter=ACMR",
      "-z",
      "--",
      "*.md",
      "*.markdown",
    ],
    { encoding: "utf8" },
  );
  return output.split("\0").filter(Boolean);
}

function mermaidBlocks(markdown, path) {
  const lines = markdown.split(/\r?\n/);
  const blocks = [];

  for (let index = 0; index < lines.length; index += 1) {
    const opening = lines[index].match(/^\s*(`{3,}|~{3,})\s*mermaid\s*$/i);
    if (!opening) {
      continue;
    }

    const marker = opening[1][0];
    const minimumLength = opening[1].length;
    const startLine = index + 1;
    const body = [];
    let closed = false;

    for (index += 1; index < lines.length; index += 1) {
      const closing = lines[index].match(/^\s*(`{3,}|~{3,})\s*$/);
      if (
        closing &&
        closing[1][0] === marker &&
        closing[1].length >= minimumLength
      ) {
        closed = true;
        break;
      }
      body.push(lines[index]);
    }

    if (!closed) {
      throw new Error(`${path}:${startLine}: unterminated Mermaid code fence`);
    }
    blocks.push({ source: body.join("\n"), startLine });
  }

  return blocks;
}

async function main() {
  const staged = process.argv[2] === "--staged";
  const paths = staged ? stagedMarkdownPaths() : process.argv.slice(2);
  let blockCount = 0;
  let failed = false;

  if (!staged && paths.length === 0) {
    console.error("Usage: node scripts/check-mermaid.mjs [--staged | FILE ...]");
    process.exitCode = 2;
    return;
  }

  for (const path of paths) {
    try {
      const markdown = staged
        ? execFileSync("git", ["show", `:${path}`], { encoding: "utf8" })
        : readFileSync(path, "utf8");
      const blocks = mermaidBlocks(markdown, path);
      blockCount += blocks.length;

      for (const block of blocks) {
        try {
          await mermaid.parse(block.source);
        } catch (error) {
          const detail = error instanceof Error ? error.message : String(error);
          console.error(`${path}:${block.startLine}: invalid Mermaid diagram\n${detail}`);
          failed = true;
        }
      }
    } catch (error) {
      console.error(error instanceof Error ? error.message : String(error));
      failed = true;
    }
  }

  if (failed) {
    process.exitCode = 1;
    return;
  }

  console.log(`PASS: validated ${blockCount} Mermaid diagram(s) in ${paths.length} Markdown file(s)`);
}

await main();

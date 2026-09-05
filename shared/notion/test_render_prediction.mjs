import assert from "node:assert/strict";
import test from "node:test";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import { markdownToBlocks, shouldRenderTableAsCards } from "./publish_prediction.mjs";

test("CLI still runs through an installed skill symlink", context => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "notion-skill-link-"));
  context.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const link = path.join(directory, "publish.mjs");
  fs.symlinkSync(fileURLToPath(new URL("./publish_prediction.mjs", import.meta.url)), link);
  const result = spawnSync(process.execPath, [link, "--help"], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout + result.stderr, /--summary/);
});

test("canonical final summary stays a native table in auto mode", () => {
  const parsed = {
    width: 5, hasColumnHeader: true,
    rows: [["比賽", "核心預測", "模型信心度", "建議", "核心風險"],
      ["A vs B", "A 60%；比分眾數2-1（35%）", "70%", "等待".repeat(40), "名單未定"]],
  };
  assert.equal(shouldRenderTableAsCards(parsed, "auto"), false);
  assert.equal(shouldRenderTableAsCards(parsed, "cards"), true);
});

test("long domain tables can still become readable cards", () => {
  const parsed = { width: 7, hasColumnHeader: true, rows: [Array(7).fill("指標"), Array(7).fill("內容")] };
  assert.equal(shouldRenderTableAsCards(parsed, "auto"), true);
});

test("rendering preserves report data without invoking the network", () => {
  const blocks = markdownToBlocks("## 簡表總結\n\n| 比賽 | 核心預測 | 模型信心度 | 建議 | 核心風險 |\n| --- | --- | --- | --- | --- |\n| A vs B | A 60% | 70% | 0u | 名單 |", { tableLayout: "auto" });
  const table = blocks.find(block => block.type === "table");
  assert.ok(table);
  assert.equal(table.table.table_width, 5);
  assert.match(JSON.stringify(table), /A 60%/);
});

#!/usr/bin/env node

import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { validateSnapshot } from "./validate_forecast_snapshot.mjs";

function taipeiDate(isoTimestamp) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Taipei",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date(isoTimestamp));
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}`;
}

export function recordForecast(payload, ledgerRoot) {
  const validation = validateSnapshot(payload);
  const dateDirectory = path.join(ledgerRoot, taipeiDate(payload.created_at));
  const outputPath = path.join(dateDirectory, `${validation.forecast_id}.json`);
  const canonical = `${JSON.stringify(payload, null, 2)}\n`;
  fs.mkdirSync(dateDirectory, { recursive: true });
  try {
    fs.writeFileSync(outputPath, canonical, { encoding: "utf8", flag: "wx" });
  } catch (error) {
    if (error.code !== "EEXIST") throw error;
    const existing = fs.readFileSync(outputPath, "utf8");
    let same = false;
    try {
      same = JSON.stringify(JSON.parse(existing)) === JSON.stringify(payload);
    } catch {
      same = false;
    }
    if (!same) throw new Error(`immutable forecast_id collision at ${outputPath}`);
    return { status: "already_recorded", output_path: outputPath, validation };
  }
  return {
    status: "recorded",
    output_path: outputPath,
    sha256: crypto.createHash("sha256").update(canonical).digest("hex"),
    validation,
  };
}

function runCli() {
  if (process.argv.length < 3 || process.argv.length > 4) {
    console.error("Usage: node record_forecast.mjs <forecast-snapshot.json> [ledger-root]");
    process.exit(2);
  }
  try {
    const inputPath = process.argv[2];
    const payload = JSON.parse(fs.readFileSync(inputPath, "utf8"));
    const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
    const defaultRoot = path.resolve(scriptDirectory, "../../.automation-state/valorant/history/forecasts");
    const result = recordForecast(payload, path.resolve(process.argv[3] || defaultRoot));
    console.log(JSON.stringify(result, null, 2));
  } catch (error) {
    console.error(`Record error: ${error.message}`);
    process.exit(1);
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) runCli();

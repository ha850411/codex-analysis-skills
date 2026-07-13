#!/usr/bin/env node

import fs from "node:fs";

function usage() {
  console.error("Usage: node shared/validate_probabilities.mjs <checks.json>");
}

function closeEnough(actual, expected, tolerance) {
  return Math.abs(actual - expected) <= tolerance;
}

function requireNumbers(values, label) {
  if (!Array.isArray(values) || values.length === 0 || values.some((value) => !Number.isFinite(value))) {
    throw new Error(`${label}: values must be a non-empty array of finite numbers`);
  }
}

function evaluate(check, globalTolerance) {
  const name = check.name || check.type || "unnamed check";
  const defaultTolerance = check.type === "fair_odds" ? 0.005 : check.type === "ev" ? 0.001 : globalTolerance;
  const tolerance = Number.isFinite(check.tolerance) ? check.tolerance : defaultTolerance;
  if (tolerance < 0) throw new Error(`${name}: tolerance must be non-negative`);

  if (check.type === "sum" || check.type === "complement") {
    requireNumbers(check.values, name);
    const actual = check.values.reduce((total, value) => total + value, 0);
    const expected = Number.isFinite(check.expected) ? check.expected : 100;
    return { name, pass: closeEnough(actual, expected, tolerance), actual, expected, tolerance };
  }

  if (check.type === "equal") {
    if (!Number.isFinite(check.left)) throw new Error(`${name}: left must be a finite number`);
    requireNumbers(check.right, name);
    const actual = check.right.reduce((total, value) => total + value, 0);
    return { name, pass: closeEnough(check.left, actual, tolerance), actual: check.left, expected: actual, tolerance };
  }

  if (check.type === "fair_odds") {
    if (!Number.isFinite(check.probability) || check.probability <= 0 || check.probability > 100) {
      throw new Error(`${name}: probability must be within (0, 100]`);
    }
    if (!Number.isFinite(check.fairOdds)) throw new Error(`${name}: fairOdds must be a finite number`);
    const expected = 100 / check.probability;
    return { name, pass: closeEnough(check.fairOdds, expected, tolerance), actual: check.fairOdds, expected, tolerance };
  }

  if (check.type === "ev") {
    if (!Number.isFinite(check.probability) || check.probability < 0 || check.probability > 100) {
      throw new Error(`${name}: probability must be within [0, 100]`);
    }
    if (!Number.isFinite(check.marketOdds) || !Number.isFinite(check.ev)) {
      throw new Error(`${name}: marketOdds and ev must be finite numbers`);
    }
    const expected = check.marketOdds * (check.probability / 100) - 1;
    return { name, pass: closeEnough(check.ev, expected, tolerance), actual: check.ev, expected, tolerance };
  }

  throw new Error(`${name}: unsupported check type ${JSON.stringify(check.type)}`);
}

if (process.argv.length !== 3) {
  usage();
  process.exit(2);
}

try {
  const payload = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
  const tolerance = Number.isFinite(payload.tolerance) ? payload.tolerance : 0.2;
  if (tolerance < 0) throw new Error("tolerance must be non-negative");
  if (!Array.isArray(payload.checks) || payload.checks.length === 0) {
    throw new Error("checks must be a non-empty array");
  }

  const results = payload.checks.map((check) => evaluate(check, tolerance));
  const failures = results.filter((result) => !result.pass);
  console.log(JSON.stringify({ pass: failures.length === 0, tolerance, results }, null, 2));
  process.exit(failures.length === 0 ? 0 : 1);
} catch (error) {
  console.error(`Validation error: ${error.message}`);
  process.exit(2);
}

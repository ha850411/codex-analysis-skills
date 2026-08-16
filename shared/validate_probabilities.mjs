#!/usr/bin/env node

import fs from "node:fs";
import { pathToFileURL } from "node:url";

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
  const defaultTolerance = check.type === "fair_odds" ? 0.005 : ["ev", "settlement_ev"].includes(check.type) ? 0.001 : globalTolerance;
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

  if (check.type === "settlement_ev") {
    if (!Number.isFinite(check.marketOdds) || check.marketOdds <= 1 || !Number.isFinite(check.ev)) {
      throw new Error(`${name}: marketOdds must be greater than 1 and ev must be finite`);
    }
    const fields = ["fullWin", "halfWin", "push", "halfLoss"];
    const values = Object.fromEntries(fields.map((field) => [field, Number.isFinite(check[field]) ? check[field] : 0]));
    if (Object.values(values).some((value) => value < 0 || value > 100)) {
      throw new Error(`${name}: settlement probabilities must be within [0, 100]`);
    }
    const settlementTotal = Object.values(values).reduce((total, value) => total + value, 0);
    if (settlementTotal > 100) {
      throw new Error(`${name}: settlement probabilities cannot exceed 100 in total`);
    }
    const expected = check.marketOdds * (values.fullWin / 100)
      + ((check.marketOdds + 1) / 2) * (values.halfWin / 100)
      + values.push / 100
      + 0.5 * (values.halfLoss / 100)
      - 1;
    return { name, pass: closeEnough(check.ev, expected, tolerance), actual: check.ev, expected, tolerance };
  }

  if (check.type === "weighted_confidence") {
    if (!Number.isInteger(check.value) || check.value < 0 || check.value > 100) {
      throw new Error(`${name}: value must be an integer within [0, 100]`);
    }
    const weights = {
      dataCompleteness: 0.25,
      freshness: 0.20,
      lineupCertainty: 0.25,
      regimeRelevance: 0.20,
      modelStability: 0.10,
    };
    if (!check.components || typeof check.components !== "object") {
      throw new Error(`${name}: components must be an object`);
    }
    let rawWeighted = 0;
    for (const [field, weight] of Object.entries(weights)) {
      const value = check.components[field];
      if (!Number.isFinite(value) || value < 0 || value > 100) {
        throw new Error(`${name}: components.${field} must be within [0, 100]`);
      }
      rawWeighted += value * weight;
    }
    rawWeighted = Math.round(rawWeighted);
    if (Object.hasOwn(check, "rawWeighted") && check.rawWeighted !== rawWeighted) {
      throw new Error(`${name}: rawWeighted must equal the rounded weighted components`);
    }
    if (
      Object.hasOwn(check, "applyNonCompensatoryCap")
      && typeof check.applyNonCompensatoryCap !== "boolean"
    ) {
      throw new Error(`${name}: applyNonCompensatoryCap must be boolean`);
    }
    const applyCap = check.applyNonCompensatoryCap === true;
    const triggers = Array.isArray(check.fragilityTriggers)
      ? check.fragilityTriggers
      : [];
    if (
      triggers.some((value) => typeof value !== "string" || value.trim() === "")
      || (applyCap && triggers.length === 0)
      || (!applyCap && triggers.length > 0)
    ) {
      throw new Error(`${name}: fragilityTriggers must be non-empty exactly when the cap applies`);
    }
    if (applyCap && check.rawWeighted !== rawWeighted) {
      throw new Error(`${name}: capped confidence checks must preserve rawWeighted`);
    }
    const caps = applyCap
      ? {
        dataCompleteness: check.components.dataCompleteness,
        regimeRelevance: check.components.regimeRelevance,
        modelStabilityPlusTen: check.components.modelStability + 10,
      }
      : null;
    const expected = caps
      ? Math.min(rawWeighted, ...Object.values(caps))
      : rawWeighted;
    return {
      name,
      pass: check.value === expected,
      actual: check.value,
      expected,
      rawWeighted,
      caps,
      tolerance: 0,
    };
  }

  throw new Error(`${name}: unsupported check type ${JSON.stringify(check.type)}`);
}

export function validateProbabilities(payload) {
  const tolerance = Number.isFinite(payload.tolerance) ? payload.tolerance : 0.2;
  if (tolerance < 0) throw new Error("tolerance must be non-negative");
  if (!Array.isArray(payload.checks) || payload.checks.length === 0) {
    throw new Error("checks must be a non-empty array");
  }

  const results = payload.checks.map((check) => evaluate(check, tolerance));
  const failures = results.filter((result) => !result.pass);
  if (failures.length > 0) {
    const error = new Error(
      `probability checks failed: ${failures.map((item) => item.name).join(", ")}`,
    );
    error.exitCode = 1;
    throw error;
  }
  return { pass: true, tolerance, results };
}

function main() {
  if (process.argv.length !== 3) {
    usage();
    process.exit(2);
  }
  try {
    const payload = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
    console.log(JSON.stringify(validateProbabilities(payload), null, 2));
  } catch (error) {
    console.error(`Validation error: ${error.message}`);
    process.exit(error.exitCode ?? 2);
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main();

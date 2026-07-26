#!/usr/bin/env node
import { execFileSync } from 'node:child_process';
import { mkdtemp, readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import assert from 'node:assert/strict';

const root = new URL('.', import.meta.url).pathname;
const target = await mkdtemp(join(tmpdir(), 'odds-api-'));
const output = join(target, 'snapshot.json');
execFileSync('node', [join(root, 'collect_odds_api_lol.mjs'), '--response', join(root, 'testdata/odds-api-lng-nip.json'), '--bookmaker', 'Stake', '--home-outcome', 'lng_ml', '--away-outcome', 'nip_ml', '--output', output], { stdio: 'inherit' });
const result = JSON.parse(await readFile(output, 'utf8'));
assert.equal(result.source.provider, 'Odds-API.io');
assert.equal(result.event.provider_event_id, 4242135875);
assert.deepEqual(result.market_data.map((item) => item.decimal_odds), [1.95, 1.75]);
assert.deepEqual(result.market_data.map((item) => item.outcome_key), ['lng_ml', 'nip_ml']);
assert.deepEqual(result.coverage.available_market_types, ['ML', '1st Map Moneyline']);
process.stdout.write('Odds-API collector fixture test passed\n');

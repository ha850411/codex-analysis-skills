#!/usr/bin/env node
import { execFileSync } from 'node:child_process';
import { mkdtemp, readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import assert from 'node:assert/strict';

const root = new URL('.', import.meta.url).pathname;
const target = await mkdtemp(join(tmpdir(), 'odds-api-'));
const output = join(target, 'snapshot.json');
const noNetworkEnv = { ...process.env, NODE_OPTIONS: `--require=${join(root, 'testdata/mock-no-network.cjs')}` };
execFileSync('node', [join(root, 'collect_odds_api.mjs'), '--sport', 'esports', '--event', 'LNG Esports - Ninjas in Pyjamas', '--events-response', join(root, 'testdata/events-lng-nip.json'), '--response', join(root, 'testdata/odds-api-lng-nip.json'), '--bookmaker', 'Stake', '--home-outcome', 'lng_ml', '--away-outcome', 'nip_ml', '--output', output], { stdio: 'inherit', env: noNetworkEnv });
const result = JSON.parse(await readFile(output, 'utf8'));
assert.equal(result.source.provider, 'Odds-API.io');
assert.equal(result.source.sport, 'esports');
assert.equal(result.event.provider_event_id, 4242135875);
assert.deepEqual(result.market_data.map((item) => item.decimal_odds), [1.95, 1.75]);
assert.deepEqual(result.market_data.map((item) => item.outcome_key), ['lng_ml', 'nip_ml']);
assert.deepEqual(result.coverage.available_market_types, ['ML', '1st Map Moneyline']);
const threeWayOutput = join(target, 'three-way-snapshot.json');
execFileSync('node', [join(root, 'collect_odds_api.mjs'), '--sport', 'football', '--response', join(root, 'testdata/odds-api-home-away-draw.json'), '--bookmaker', 'Stake', '--home-outcome', 'home_ml', '--draw-outcome', 'draw_ml', '--away-outcome', 'away_ml', '--output', threeWayOutput], { stdio: 'inherit', env: noNetworkEnv });
const threeWay = JSON.parse(await readFile(threeWayOutput, 'utf8'));
assert.deepEqual(threeWay.market_data.map((item) => item.outcome_key), ['home_ml', 'draw_ml', 'away_ml']);
assert.deepEqual(threeWay.market_data.map((item) => item.decimal_odds), [2.15, 3.2, 3.4]);
process.stdout.write('Odds-API collector fixture test passed\n');

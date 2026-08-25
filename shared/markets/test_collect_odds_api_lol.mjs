#!/usr/bin/env node
import { execFileSync, spawnSync } from 'node:child_process';
import { mkdtemp, readFile, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import assert from 'node:assert/strict';
import { apiJson } from './collect_odds_api_lol.mjs';

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
assert.deepEqual(result.coverage.available_market_types, ['ML', 'Spread', 'Totals', '1st Map Moneyline']);

const multiMarketOutput = join(target, 'multi-market-snapshot.json');
execFileSync('node', [
  join(root, 'collect_odds_api.mjs'),
  '--sport', 'esports',
  '--response', join(root, 'testdata/odds-api-lng-nip.json'),
  '--bookmaker', 'Stake',
  '--home-outcome', 'lng_ml',
  '--away-outcome', 'nip_ml',
  '--market', 'ML',
  '--market', 'Spread',
  '--market', 'Totals',
  '--output', multiMarketOutput,
], { stdio: 'inherit', env: noNetworkEnv });
const multiMarket = JSON.parse(await readFile(multiMarketOutput, 'utf8'));
assert.equal(multiMarket.schema_version, '1.2');
assert.equal(multiMarket.coverage.status, 'full');
assert.deepEqual(multiMarket.coverage.requested_market_types, ['ML', 'Spread', 'Totals']);
assert.deepEqual(multiMarket.coverage.captured_market_types, ['ML', 'Spread', 'Totals']);
assert.deepEqual(multiMarket.market_data.map((item) => item.outcome_key), [
  'lng_ml',
  'nip_ml',
  'lng_spread_minus_1_5',
  'nip_spread_plus_1_5',
  'lng_spread_plus_1_5',
  'nip_spread_minus_1_5',
  'total_maps_over_2_5',
  'total_maps_under_2_5',
]);
assert.deepEqual(
  multiMarket.market_data.filter((item) => item.market_family === 'series_spread').map((item) => item.line),
  [-1.5, 1.5, 1.5, -1.5],
);
assert.deepEqual(
  multiMarket.market_data.filter((item) => item.market_family === 'series_total_maps').map((item) => item.line),
  [2.5, 2.5],
);

const partialMarketOutput = join(target, 'partial-market-snapshot.json');
execFileSync('node', [
  join(root, 'collect_odds_api.mjs'),
  '--sport', 'esports',
  '--response', join(root, 'testdata/odds-api-drx-ns.json'),
  '--bookmaker', 'Stake',
  '--home-outcome', 'drx_ml',
  '--away-outcome', 'ns_ml',
  '--market', 'ML',
  '--market', 'Spread',
  '--market', 'Totals',
  '--output', partialMarketOutput,
], { stdio: 'inherit', env: noNetworkEnv });
const partialMarket = JSON.parse(await readFile(partialMarketOutput, 'utf8'));
assert.equal(partialMarket.coverage.status, 'partial');
assert.deepEqual(partialMarket.coverage.requested_but_unavailable, ['Spread', 'Totals']);
assert.deepEqual(partialMarket.market_data.map((item) => item.outcome_key), ['drx_ml', 'ns_ml']);
const threeWayOutput = join(target, 'three-way-snapshot.json');
execFileSync('node', [join(root, 'collect_odds_api.mjs'), '--sport', 'football', '--response', join(root, 'testdata/odds-api-home-away-draw.json'), '--bookmaker', 'Stake', '--home-outcome', 'home_ml', '--draw-outcome', 'draw_ml', '--away-outcome', 'away_ml', '--output', threeWayOutput], { stdio: 'inherit', env: noNetworkEnv });
const threeWay = JSON.parse(await readFile(threeWayOutput, 'utf8'));
assert.deepEqual(threeWay.market_data.map((item) => item.outcome_key), ['home_ml', 'draw_ml', 'away_ml']);
assert.deepEqual(threeWay.market_data.map((item) => item.decimal_odds), [2.15, 3.2, 3.4]);

const aliasOutput = join(target, 'alias-snapshot.json');
const staleAliasError = `${aliasOutput}.error.json`;
await writeFile(staleAliasError, '{"status":"failed"}\n', 'utf8');
execFileSync('node', [join(root, 'collect_odds_api.mjs'), '--sport', 'esports', '--event', 'DRX - Nongshim RedForce', '--events-response', join(root, 'testdata/events-drx-ns.json'), '--response', join(root, 'testdata/odds-api-drx-ns.json'), '--bookmaker', 'Stake', '--home-outcome', 'drx_ml', '--away-outcome', 'ns_ml', '--output', aliasOutput], { stdio: 'inherit', env: noNetworkEnv });
const aliasResult = JSON.parse(await readFile(aliasOutput, 'utf8'));
assert.equal(aliasResult.collection.event_resolution, 'conservative_team_alias');
assert.equal(aliasResult.event.provider_event_id, 7185943806);
assert.deepEqual(aliasResult.market_data.map((item) => item.decimal_odds), [2.5, 1.55]);
await assert.rejects(readFile(staleAliasError, 'utf8'), { code: 'ENOENT' });

let retryCalls = 0;
const retryResult = await apiJson('/events', { sport: 'esports' }, 'redacted-test-key', {
  maxAttempts: 3,
  retryDelaysMs: [0, 0],
  sleep: async () => {},
  fetchImpl: async () => {
    retryCalls += 1;
    if (retryCalls < 3) throw new Error('temporary connection reset');
    return {
      ok: true,
      status: 200,
      headers: { get: () => '77' },
      json: async () => [{ id: 1 }]
    };
  }
});
assert.equal(retryCalls, 3);
assert.equal(retryResult.attempts, 3);
assert.equal(retryResult.remaining, '77');

const failureOutput = join(target, 'missing-snapshot.json');
const failureArtifact = join(target, 'missing-snapshot.error.json');
const eventsArtifact = join(target, 'pending-events.json');
const failure = spawnSync('node', [join(root, 'collect_odds_api.mjs'), '--sport', 'esports', '--event', 'Missing Team - Other Team', '--events-response', join(root, 'testdata/events-drx-ns.json'), '--response', join(root, 'testdata/odds-api-drx-ns.json'), '--events-output', eventsArtifact, '--home-outcome', 'missing_ml', '--away-outcome', 'other_ml', '--output', failureOutput, '--error-output', failureArtifact], { encoding: 'utf8', env: noNetworkEnv });
assert.equal(failure.status, 2);
const failed = JSON.parse(await readFile(failureArtifact, 'utf8'));
assert.equal(failed.status, 'failed');
assert.equal(failed.error.kind, 'event_not_found');
assert.equal(failed.requested_event, 'Missing Team - Other Team');
const pendingEvents = JSON.parse(await readFile(eventsArtifact, 'utf8'));
assert.deepEqual(pendingEvents.events.map((item) => item.provider_event_id), [7185943806]);
process.stdout.write('Odds-API collector fixture test passed\n');

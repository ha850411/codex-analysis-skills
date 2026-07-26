#!/usr/bin/env node
/** Merge per-event Odds-API.io snapshots into one pipeline-ready market snapshot. */
import { createHash } from 'node:crypto';
import { readFile, writeFile } from 'node:fs/promises';

function fail(message) { process.stderr.write(`Odds-API merger: ${message}\n`); process.exitCode = 2; throw new Error(message); }

async function main() {
  const args = process.argv.slice(2);
  const outputIndex = args.indexOf('--output');
  if (outputIndex < 1 || outputIndex === args.length - 1) fail('usage: node merge_odds_api_snapshots.mjs <snapshot...> --output <merged.json>');
  const paths = args.slice(0, outputIndex);
  if (args.slice(outputIndex + 2).length) fail('only snapshot paths followed by --output are accepted');
  const snapshots = await Promise.all(paths.map(async (file) => JSON.parse(await readFile(file, 'utf8'))));
  const first = snapshots[0];
  if (!first?.source?.book || first.source.provider !== 'Odds-API.io') fail('all inputs must be Odds-API.io snapshots');
  const betIds = new Set();
  const marketData = [];
  for (const snapshot of snapshots) {
    if (snapshot?.source?.provider !== 'Odds-API.io' || snapshot.source.book !== first.source.book || !Array.isArray(snapshot.market_data)) fail('snapshots must use one provider and bookmaker');
    for (const market of snapshot.market_data) {
      if (!market?.bet_id || betIds.has(market.bet_id)) fail(`duplicate or missing bet_id: ${market?.bet_id ?? 'unknown'}`);
      betIds.add(market.bet_id);
      marketData.push(market);
    }
  }
  const retrievedAt = new Date().toISOString();
  const result = {
    schema_version: '1.0',
    source: {
      book: first.source.book,
      provider: 'Odds-API.io',
      source_url: 'https://api.odds-api.io/v3/odds',
      provider_url: 'https://api.odds-api.io/v3/odds',
      retrieved_at: retrievedAt,
      merged_snapshot_sha256: createHash('sha256').update(JSON.stringify(snapshots)).digest('hex')
    },
    coverage: {
      status: 'partial',
      events: snapshots.map((snapshot) => ({ event_id: snapshot.event.provider_event_id, display_name: snapshot.event.display_name, captured_market_types: snapshot.coverage.captured_market_types, available_market_types: snapshot.coverage.available_market_types }))
    },
    market_data: marketData
  };
  await writeFile(args[outputIndex + 1], `${JSON.stringify(result, null, 2)}\n`, 'utf8');
  process.stdout.write(`wrote ${args[outputIndex + 1]}: ${marketData.length} ${first.source.book} prices across ${snapshots.length} events\n`);
}

main().catch((error) => { if (!process.exitCode) { process.stderr.write(`Odds-API merger: ${error.message}\n`); process.exitCode = 1; } });

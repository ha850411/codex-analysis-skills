#!/usr/bin/env node
/** Collect bookmaker-specific LoL prices from Odds-API.io without exposing its API key. */
import { createHash } from 'node:crypto';
import { readFile, writeFile } from 'node:fs/promises';

const API_BASE = 'https://api.odds-api.io/v3';

function fail(message) {
  process.stderr.write(`Odds-API collector: ${message}\n`);
  process.exitCode = 2;
  throw new Error(message);
}

function parseArgs(argv) {
  const args = { bookmaker: 'Stake', markets: [] };
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (token === '--help' || token === '-h') args.help = true;
    else if (token === '--event') args.event = argv[++index];
    else if (token === '--event-id') args.eventId = argv[++index];
    else if (token === '--bookmaker') args.bookmaker = argv[++index];
    else if (token === '--market') args.markets.push(argv[++index]);
    else if (token === '--home-outcome') args.homeOutcome = argv[++index];
    else if (token === '--away-outcome') args.awayOutcome = argv[++index];
    else if (token === '--env-file') args.envFile = argv[++index];
    else if (token === '--response') args.response = argv[++index];
    else if (token === '--output') args.output = argv[++index];
    else fail(`unknown argument: ${token}`);
  }
  return args;
}

function usage() {
  return `Usage:
  node collect_odds_api_lol.mjs --event "LNG Esports - Ninjas in Pyjamas" \\
    --home-outcome lng_ml --away-outcome nip_ml --output odds-snapshot.json

  node collect_odds_api_lol.mjs --event-id 4242135875 --bookmaker Stake \\
    --market ML --home-outcome lng_ml --away-outcome nip_ml --output odds-snapshot.json

The API key is read only from ODDS_API_KEY in .env (or the process environment).
The default bookmaker is Stake. --response is a saved raw /v3/odds response for tests.`;
}

function normalise(value) {
  return String(value).normalize('NFKC').toLowerCase().replace(/[‐‑‒–—]/g, '-').replace(/\s+/g, ' ').trim();
}

function slug(value) {
  return normalise(value).replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '') || 'selection';
}

async function loadEnv(path) {
  let content;
  try { content = await readFile(path, 'utf8'); } catch (error) {
    if (error.code === 'ENOENT') return;
    throw error;
  }
  for (const raw of content.split(/\r?\n/)) {
    const match = raw.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$/);
    if (match && process.env[match[1]] == null) process.env[match[1]] = match[2].replace(/^['"]|['"]$/g, '');
  }
}

async function apiJson(path, params, apiKey) {
  const url = new URL(`${API_BASE}${path}`);
  for (const [name, value] of Object.entries({ ...params, apiKey })) {
    if (value != null && value !== '') url.searchParams.set(name, String(value));
  }
  let response;
  try { response = await fetch(url); } catch (error) { fail(`request failed: ${error.message}`); }
  let data;
  try { data = await response.json(); } catch { fail(`API returned non-JSON HTTP ${response.status}`); }
  if (!response.ok) fail(`API HTTP ${response.status}: ${data?.error || 'request failed'}`);
  return { data, remaining: response.headers.get('x-ratelimit-remaining') };
}

function oddsNumber(value, label) {
  const odds = Number(value);
  if (!Number.isFinite(odds) || odds <= 1) fail(`${label} is not a valid decimal odds value`);
  return odds;
}

function eventName(event) {
  return `${event.home} - ${event.away}`;
}

async function resolveEvent(args, apiKey) {
  if (args.eventId) return Number(args.eventId);
  if (!args.event) fail('provide --event or --event-id');
  const { data } = await apiJson('/events', { sport: 'esports', bookmaker: args.bookmaker, status: 'pending', limit: 500 }, apiKey);
  const matches = data.filter((item) => normalise(eventName(item)) === normalise(args.event));
  if (matches.length !== 1) fail(matches.length ? `event is ambiguous: ${args.event}; pass --event-id` : `event was not found for ${args.bookmaker}: ${args.event}`);
  return matches[0].id;
}

function selectMarkets(event, bookmaker, names) {
  const markets = event.bookmakers?.[bookmaker];
  if (!Array.isArray(markets)) fail(`${bookmaker} has no odds for event ${event.id}`);
  const requested = names.length ? names : ['ML'];
  const selected = requested.map((name) => markets.find((market) => normalise(market.name) === normalise(name))).filter(Boolean);
  const missing = requested.filter((name) => !selected.some((market) => normalise(market.name) === normalise(name)));
  if (missing.length) fail(`${bookmaker} does not offer requested market(s): ${missing.join(', ')}`);
  return { selected, all: markets };
}

function marketDataForMl(event, bookmaker, market, args, retrievedAt, sourceUrl) {
  if (!args.homeOutcome || !args.awayOutcome) fail('ML import requires --home-outcome and --away-outcome from final_prediction.json');
  const row = market.odds?.[0];
  if (!row || row.home == null || row.away == null) fail(`${bookmaker} ML response is missing home/away prices`);
  const prefix = `odds-api:${event.id}:${slug(bookmaker)}:${slug(market.name)}`;
  return [
    { bet_id: `${prefix}:home`, outcome_key: args.homeOutcome, decimal_odds: oddsNumber(row.home, 'home odds'), book: bookmaker, label: `${bookmaker} ${market.name} — ${event.home}`, retrieved_at: retrievedAt, market_updated_at: market.updatedAt ?? null, source_url: sourceUrl, provider: 'Odds-API.io', event_id: event.id, market_type: market.name },
    { bet_id: `${prefix}:away`, outcome_key: args.awayOutcome, decimal_odds: oddsNumber(row.away, 'away odds'), book: bookmaker, label: `${bookmaker} ${market.name} — ${event.away}`, retrieved_at: retrievedAt, market_updated_at: market.updatedAt ?? null, source_url: sourceUrl, provider: 'Odds-API.io', event_id: event.id, market_type: market.name }
  ];
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help) { process.stdout.write(`${usage()}\n`); return; }
  if (!args.output) fail('--output is required');
  let event;
  let remaining = null;
  if (args.response) {
    event = JSON.parse(await readFile(args.response, 'utf8'));
  } else {
    await loadEnv(args.envFile || '.env');
    const apiKey = process.env.ODDS_API_KEY;
    if (!apiKey) fail('ODDS_API_KEY is missing; add it to ignored .env or export it in the process environment');
    const id = await resolveEvent(args, apiKey);
    const response = await apiJson('/odds', { eventId: id, bookmakers: args.bookmaker }, apiKey);
    event = response.data;
    remaining = response.remaining;
  }
  if (!event || typeof event !== 'object' || !event.id || !event.home || !event.away) fail('response is not a valid Odds-API.io event');
  const { selected, all } = selectMarkets(event, args.bookmaker, args.markets);
  if (selected.some((market) => normalise(market.name) !== 'ml')) fail('only ML can currently be mapped to pipeline outcome keys; other API markets are retained as available_markets');
  const retrievedAt = new Date().toISOString();
  const sourceUrl = event.urls?.[args.bookmaker] || `${API_BASE}/odds`;
  const marketData = selected.flatMap((market) => marketDataForMl(event, args.bookmaker, market, args, retrievedAt, sourceUrl));
  const raw = JSON.stringify(event);
  const result = {
    schema_version: '1.0',
    source: { book: args.bookmaker, provider: 'Odds-API.io', source_url: sourceUrl, provider_url: `${API_BASE}/odds`, retrieved_at: retrievedAt, response_sha256: createHash('sha256').update(raw).digest('hex'), rate_limit_remaining: remaining },
    event: { provider_event_id: event.id, display_name: eventName(event), participants: [event.home, event.away], start_time: event.date, competition: event.league?.name ?? null, status: event.status },
    coverage: { status: 'partial', captured_market_types: selected.map((market) => market.name), available_market_types: all.map((market) => market.name), unavailable_or_not_mapped: all.filter((market) => !selected.includes(market)).map((market) => market.name) },
    market_data: marketData
  };
  await writeFile(args.output, `${JSON.stringify(result, null, 2)}\n`, 'utf8');
  process.stdout.write(`wrote ${args.output}: ${marketData.length} ${args.bookmaker} prices for event ${event.id}${remaining ? `; rate-limit remaining ${remaining}` : ''}\n`);
}

main().catch((error) => { if (!process.exitCode) { process.stderr.write(`Odds-API collector: ${error.message}\n`); process.exitCode = 1; } });

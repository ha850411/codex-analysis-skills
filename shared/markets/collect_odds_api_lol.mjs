#!/usr/bin/env node
/** Collect bookmaker-specific Odds-API.io prices without exposing its API key.
 * Defaults to esports for backward compatibility with the LoL workflow. */
import { createHash } from 'node:crypto';
import { readFile, unlink, writeFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';

const API_BASE = 'https://api.odds-api.io/v3';
const TRANSIENT_HTTP_STATUSES = new Set([408, 425, 429, 500, 502, 503, 504]);
const DEFAULT_RETRY_DELAYS_MS = [250, 750];

class CollectorError extends Error {
  constructor(message, {
    kind = 'collector_error',
    httpStatus = null,
    retriable = false,
    attempts = null
  } = {}) {
    super(message);
    this.name = 'CollectorError';
    this.kind = kind;
    this.httpStatus = httpStatus;
    this.retriable = retriable;
    this.attempts = attempts;
  }
}

function fail(message, options = {}) {
  throw new CollectorError(message, options);
}

function parseArgs(argv) {
  const args = { bookmaker: 'Stake', markets: [], sport: 'esports', retryAttempts: 3 };
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (token === '--help' || token === '-h') args.help = true;
    else if (token === '--event') args.event = argv[++index];
    else if (token === '--event-id') args.eventId = argv[++index];
    else if (token === '--bookmaker') args.bookmaker = argv[++index];
    else if (token === '--sport') args.sport = argv[++index];
    else if (token === '--market') args.markets.push(argv[++index]);
    else if (token === '--home-outcome') args.homeOutcome = argv[++index];
    else if (token === '--away-outcome') args.awayOutcome = argv[++index];
    else if (token === '--draw-outcome') args.drawOutcome = argv[++index];
    else if (token === '--env-file') args.envFile = argv[++index];
    else if (token === '--events-response') args.eventsResponse = argv[++index];
    else if (token === '--events-output') args.eventsOutput = argv[++index];
    else if (token === '--response') args.response = argv[++index];
    else if (token === '--output') args.output = argv[++index];
    else if (token === '--error-output') args.errorOutput = argv[++index];
    else if (token === '--retry-attempts') args.retryAttempts = Number(argv[++index]);
    else fail(`unknown argument: ${token}`, { kind: 'usage' });
  }
  if (!Number.isInteger(args.retryAttempts) || args.retryAttempts < 1 || args.retryAttempts > 5) {
    fail('--retry-attempts must be an integer from 1 to 5', { kind: 'usage' });
  }
  return args;
}

function usage() {
  return `Usage:
  node collect_odds_api.mjs --sport esports --event "DRX - Nongshim RedForce" \\
    --home-outcome drx_ml --away-outcome ns_ml --output odds-snapshot.json

  node collect_odds_api.mjs --sport football --event-id 4242135875 --bookmaker Stake \\
    --home-outcome home_ml --draw-outcome draw_ml --away-outcome away_ml \\
    --market ML --output odds-snapshot.json

The API key is read only from ODDS_API_KEY in .env (or the process environment).
The default bookmaker is Stake. Transient network, rate-limit, and 5xx failures
are retried three times by default. A failed run writes --error-output, or
<output>.error.json when that flag is omitted. --response and --events-response
are local mocked /v3/odds and /v3/events responses for tests; they never make
network requests.`;
}

function normalise(value) {
  return String(value).normalize('NFKC').toLowerCase().replace(/[‐‑‒–—]/g, '-').replace(/\s+/g, ' ').trim();
}

function slug(value) {
  return normalise(value).replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '') || 'selection';
}

function compactTeam(value) {
  return normalise(value).replace(/[^a-z0-9]+/g, '');
}

function teamTokens(value) {
  return normalise(value).replace(/[^a-z0-9]+/g, ' ').trim().split(/\s+/).filter(Boolean);
}

function teamMatches(providerName, requestedName) {
  if (normalise(providerName) === normalise(requestedName)) return true;
  const providerCompact = compactTeam(providerName);
  const requestedCompact = compactTeam(requestedName);
  if (providerCompact === requestedCompact) return true;
  if (requestedCompact.length < 3) return false;
  const providerTokens = teamTokens(providerName);
  const requestedTokens = teamTokens(requestedName);
  if (!providerTokens.length || !requestedTokens.length) return false;
  const providerTail = providerTokens.slice(-requestedTokens.length).join('');
  const requestedTail = requestedTokens.slice(-providerTokens.length).join('');
  return providerTail === requestedCompact || requestedTail === providerCompact;
}

function requestedParticipants(value) {
  const parts = String(value).split(/\s+-\s+/);
  return parts.length === 2 ? parts.map((item) => item.trim()) : null;
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

function errorKindForHttp(status) {
  if (status === 401 || status === 403) return 'authentication';
  if (status === 429) return 'rate_limit';
  if (TRANSIENT_HTTP_STATUSES.has(status)) return 'provider_unavailable';
  return 'http_error';
}

function retryDelay(response, attempt, retryDelaysMs) {
  const retryAfter = Number(response?.headers?.get?.('retry-after'));
  if (Number.isFinite(retryAfter) && retryAfter >= 0 && retryAfter <= 30) return retryAfter * 1000;
  return retryDelaysMs[Math.min(attempt - 1, retryDelaysMs.length - 1)] ?? 0;
}

export async function apiJson(path, params, apiKey, {
  fetchImpl = fetch,
  maxAttempts = 3,
  retryDelaysMs = DEFAULT_RETRY_DELAYS_MS,
  sleep = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds))
} = {}) {
  const url = new URL(`${API_BASE}${path}`);
  for (const [name, value] of Object.entries({ ...params, apiKey })) {
    if (value != null && value !== '') url.searchParams.set(name, String(value));
  }
  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    let response;
    try {
      response = await fetchImpl(url);
    } catch (error) {
      if (attempt < maxAttempts) {
        await sleep(retryDelaysMs[Math.min(attempt - 1, retryDelaysMs.length - 1)] ?? 0);
        continue;
      }
      fail(`request failed after ${attempt} attempt(s): ${error.message}`, {
        kind: 'network',
        retriable: true,
        attempts: attempt
      });
    }

    let data;
    try {
      data = await response.json();
    } catch {
      if (TRANSIENT_HTTP_STATUSES.has(response.status) && attempt < maxAttempts) {
        await sleep(retryDelay(response, attempt, retryDelaysMs));
        continue;
      }
      fail(`API returned non-JSON HTTP ${response.status}`, {
        kind: 'invalid_response',
        httpStatus: response.status,
        retriable: TRANSIENT_HTTP_STATUSES.has(response.status),
        attempts: attempt
      });
    }

    if (!response.ok) {
      const retriable = TRANSIENT_HTTP_STATUSES.has(response.status);
      if (retriable && attempt < maxAttempts) {
        await sleep(retryDelay(response, attempt, retryDelaysMs));
        continue;
      }
      fail(`API HTTP ${response.status}: ${data?.error || 'request failed'}`, {
        kind: errorKindForHttp(response.status),
        httpStatus: response.status,
        retriable,
        attempts: attempt
      });
    }
    return {
      data,
      remaining: response.headers.get('x-ratelimit-remaining'),
      attempts: attempt
    };
  }
  fail('request exhausted retries', { kind: 'network', retriable: true, attempts: maxAttempts });
}

function oddsNumber(value, label) {
  const odds = Number(value);
  if (!Number.isFinite(odds) || odds <= 1) fail(`${label} is not a valid decimal odds value`, { kind: 'invalid_response' });
  return odds;
}

function eventName(event) {
  return `${event.home} - ${event.away}`;
}

async function resolveEvent(args, apiKey, mockedEvents = null) {
  if (args.eventId) {
    const id = Number(args.eventId);
    if (!Number.isFinite(id)) fail('--event-id must be numeric', { kind: 'usage' });
    return { id, method: 'provider_event_id', attempts: 0 };
  }
  if (!args.event) fail('provide --event or --event-id', { kind: 'usage' });
  const response = mockedEvents == null
    ? await apiJson('/events', { sport: args.sport, bookmaker: args.bookmaker, status: 'pending', limit: 500 }, apiKey, { maxAttempts: args.retryAttempts })
    : { data: mockedEvents, attempts: 0 };
  const data = response.data;
  if (!Array.isArray(data)) fail('events response is not an array', { kind: 'invalid_response' });
  if (args.eventsOutput) {
    const snapshot = {
      schema_version: '1.0',
      provider: 'Odds-API.io',
      book: args.bookmaker,
      sport: args.sport,
      retrieved_at: new Date().toISOString(),
      events: data.map((item) => ({
        provider_event_id: item.id,
        display_name: eventName(item),
        start_time: item.date ?? null,
        competition: item.league?.name ?? null,
        status: item.status ?? null
      }))
    };
    await writeFile(args.eventsOutput, `${JSON.stringify(snapshot, null, 2)}\n`, 'utf8');
  }

  const exactMatches = data.filter((item) => normalise(eventName(item)) === normalise(args.event));
  if (exactMatches.length === 1) {
    return { id: exactMatches[0].id, method: 'exact_name', attempts: response.attempts };
  }
  if (exactMatches.length > 1) {
    fail(`event is ambiguous: ${args.event}; pass --event-id`, {
      kind: 'event_ambiguous',
      attempts: response.attempts
    });
  }

  const participants = requestedParticipants(args.event);
  const aliasMatches = participants
    ? data.filter((item) => teamMatches(item.home, participants[0]) && teamMatches(item.away, participants[1]))
    : [];
  if (aliasMatches.length === 1) {
    return { id: aliasMatches[0].id, method: 'conservative_team_alias', attempts: response.attempts };
  }
  if (aliasMatches.length > 1) {
    fail(`event aliases are ambiguous: ${args.event}; pass --event-id`, {
      kind: 'event_ambiguous',
      attempts: response.attempts
    });
  }
  fail(`event was not found for ${args.bookmaker}: ${args.event}; inspect pending events and retry with --event-id`, {
    kind: 'event_not_found',
    attempts: response.attempts
  });
}

function selectMarkets(event, bookmaker, names) {
  const markets = event.bookmakers?.[bookmaker];
  if (!Array.isArray(markets)) fail(`${bookmaker} has no odds for event ${event.id}`, { kind: 'market_unavailable' });
  const requested = names.length ? names : ['ML'];
  const selected = requested.map((name) => markets.find((market) => normalise(market.name) === normalise(name))).filter(Boolean);
  const missing = requested.filter((name) => !selected.some((market) => normalise(market.name) === normalise(name)));
  if (missing.length) fail(`${bookmaker} does not offer requested market(s): ${missing.join(', ')}`, { kind: 'market_unavailable' });
  return { selected, all: markets };
}

function marketDataForMl(event, bookmaker, market, args, retrievedAt, sourceUrl) {
  if (!args.homeOutcome || !args.awayOutcome) fail('ML import requires --home-outcome and --away-outcome from final_prediction.json', { kind: 'usage' });
  const row = market.odds?.[0];
  if (!row || row.home == null || row.away == null) fail(`${bookmaker} ML response is missing home/away prices`, { kind: 'invalid_response' });
  const prefix = `odds-api:${event.id}:${slug(bookmaker)}:${slug(market.name)}`;
  const data = [
    { bet_id: `${prefix}:home`, outcome_key: args.homeOutcome, decimal_odds: oddsNumber(row.home, 'home odds'), book: bookmaker, label: `${bookmaker} ${market.name} — ${event.home}`, retrieved_at: retrievedAt, market_updated_at: market.updatedAt ?? null, source_url: sourceUrl, provider: 'Odds-API.io', event_id: event.id, market_type: market.name },
    { bet_id: `${prefix}:away`, outcome_key: args.awayOutcome, decimal_odds: oddsNumber(row.away, 'away odds'), book: bookmaker, label: `${bookmaker} ${market.name} — ${event.away}`, retrieved_at: retrievedAt, market_updated_at: market.updatedAt ?? null, source_url: sourceUrl, provider: 'Odds-API.io', event_id: event.id, market_type: market.name }
  ];
  if (row.draw != null) {
    if (!args.drawOutcome) fail('three-way ML import requires --draw-outcome from final_prediction.json', { kind: 'usage' });
    data.splice(1, 0, { bet_id: `${prefix}:draw`, outcome_key: args.drawOutcome, decimal_odds: oddsNumber(row.draw, 'draw odds'), book: bookmaker, label: `${bookmaker} ${market.name} — draw`, retrieved_at: retrievedAt, market_updated_at: market.updatedAt ?? null, source_url: sourceUrl, provider: 'Odds-API.io', event_id: event.id, market_type: market.name });
  } else if (args.drawOutcome) {
    fail('draw outcome was supplied but the ML response has no draw price', { kind: 'invalid_response' });
  }
  return data;
}

async function writeFailureArtifact(args, error) {
  const output = args?.errorOutput || (args?.output ? `${args.output}.error.json` : null);
  if (!output) return null;
  const detail = error instanceof CollectorError ? error : new CollectorError(error.message);
  const artifact = {
    schema_version: '1.0',
    status: 'failed',
    provider: 'Odds-API.io',
    book: args.bookmaker ?? 'Stake',
    sport: args.sport ?? 'esports',
    requested_event: args.event ?? null,
    requested_event_id: args.eventId ?? null,
    events_output: args.eventsOutput ?? null,
    attempted_at: new Date().toISOString(),
    request_attempts: args._requestAttempts ?? {
      event_lookup: null,
      odds: null
    },
    error: {
      kind: detail.kind,
      message: detail.message,
      http_status: detail.httpStatus,
      retriable: detail.retriable,
      attempts: detail.attempts
    }
  };
  await writeFile(output, `${JSON.stringify(artifact, null, 2)}\n`, 'utf8');
  return output;
}

async function collect(args) {
  if (!args.output) fail('--output is required', { kind: 'usage' });
  args._requestAttempts = { event_lookup: 0, odds: 0 };
  let event;
  let remaining = null;
  let resolution;
  let oddsAttempts = 0;
  if (args.response) {
    if (args.eventsResponse) {
      const mockedEvents = JSON.parse(await readFile(args.eventsResponse, 'utf8'));
      resolution = await resolveEvent(args, null, mockedEvents);
      args._requestAttempts.event_lookup = resolution.attempts;
      const mockedOdds = JSON.parse(await readFile(args.response, 'utf8'));
      if (Number(mockedOdds.id) !== Number(resolution.id)) {
        fail('mocked events and odds responses resolve to different event IDs', { kind: 'invalid_response' });
      }
      event = mockedOdds;
    } else if (args.event) {
      fail('--event with --response requires --events-response so the event lookup remains mocked', { kind: 'usage' });
    } else {
      event = JSON.parse(await readFile(args.response, 'utf8'));
      resolution = { id: event.id, method: 'mocked_provider_event_id', attempts: 0 };
    }
  } else {
    if (args.eventsResponse) fail('--events-response is only valid together with --response', { kind: 'usage' });
    await loadEnv(args.envFile || '.env');
    const apiKey = process.env.ODDS_API_KEY;
    if (!apiKey) {
      fail('ODDS_API_KEY is missing; add it to ignored .env or export it in the process environment', {
        kind: 'authentication'
      });
    }
    resolution = await resolveEvent(args, apiKey);
    args._requestAttempts.event_lookup = resolution.attempts;
    const response = await apiJson('/odds', { eventId: resolution.id, bookmakers: args.bookmaker }, apiKey, {
      maxAttempts: args.retryAttempts
    });
    event = response.data;
    remaining = response.remaining;
    oddsAttempts = response.attempts;
    args._requestAttempts.odds = oddsAttempts;
  }
  if (!event || typeof event !== 'object' || !event.id || !event.home || !event.away) {
    fail('response is not a valid Odds-API.io event', { kind: 'invalid_response' });
  }
  const { selected, all } = selectMarkets(event, args.bookmaker, args.markets);
  if (selected.some((market) => normalise(market.name) !== 'ml')) {
    fail('only ML can currently be mapped to pipeline outcome keys; other API markets are retained as available_markets', {
      kind: 'market_not_mapped'
    });
  }
  const retrievedAt = new Date().toISOString();
  const sourceUrl = event.urls?.[args.bookmaker] || `${API_BASE}/odds`;
  const marketData = selected.flatMap((market) => marketDataForMl(event, args.bookmaker, market, args, retrievedAt, sourceUrl));
  const raw = JSON.stringify(event);
  const result = {
    schema_version: '1.1',
    status: 'success',
    collection: {
      event_resolution: resolution.method,
      event_lookup_attempts: resolution.attempts,
      odds_request_attempts: oddsAttempts
    },
    source: { book: args.bookmaker, provider: 'Odds-API.io', sport: args.sport, source_url: sourceUrl, provider_url: `${API_BASE}/odds`, retrieved_at: retrievedAt, response_sha256: createHash('sha256').update(raw).digest('hex'), rate_limit_remaining: remaining },
    event: { provider_event_id: event.id, display_name: eventName(event), participants: [event.home, event.away], start_time: event.date, competition: event.league?.name ?? null, status: event.status },
    coverage: { status: 'partial', captured_market_types: selected.map((market) => market.name), available_market_types: all.map((market) => market.name), unavailable_or_not_mapped: all.filter((market) => !selected.includes(market)).map((market) => market.name) },
    market_data: marketData
  };
  await writeFile(args.output, `${JSON.stringify(result, null, 2)}\n`, 'utf8');
  const staleFailureArtifact = args.errorOutput || `${args.output}.error.json`;
  try {
    await unlink(staleFailureArtifact);
  } catch (error) {
    if (error.code !== 'ENOENT') throw error;
  }
  process.stdout.write(`wrote ${args.output}: ${marketData.length} ${args.bookmaker} prices for event ${event.id}${remaining ? `; rate-limit remaining ${remaining}` : ''}\n`);
}

export async function runCli(argv = process.argv.slice(2)) {
  let args = {};
  try {
    args = parseArgs(argv);
    if (args.help) {
      process.stdout.write(`${usage()}\n`);
      return true;
    }
    await collect(args);
    return true;
  } catch (error) {
    let artifact = null;
    try {
      artifact = await writeFailureArtifact(args, error);
    } catch (artifactError) {
      process.stderr.write(`Odds-API collector: could not write failure artifact: ${artifactError.message}\n`);
    }
    process.stderr.write(`Odds-API collector: ${error.message}${artifact ? `; failure artifact ${artifact}` : ''}\n`);
    process.exitCode = error instanceof CollectorError ? 2 : 1;
    return false;
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  await runCli();
}

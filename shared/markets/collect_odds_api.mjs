#!/usr/bin/env node
/** Generic Odds-API.io collector. The implementation retains its original
 * LoL filename for backwards compatibility with existing automations. */
import { runCli } from './collect_odds_api_lol.mjs';

await runCli(process.argv.slice(2));

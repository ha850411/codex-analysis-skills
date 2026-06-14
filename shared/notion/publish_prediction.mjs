#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";

const API_BASE = "https://api.notion.com/v1";
const DEFAULT_NOTION_VERSION = "2026-03-11";
const RICH_TEXT_LIMIT = 1900;
const CREATE_CHILD_LIMIT = 90;
const APPEND_CHILD_LIMIT = 100;
const CARD_TABLE_MIN_COLUMNS = 5;
const CARD_TABLE_ALWAYS_COLUMNS = 7;
const CARD_TABLE_LONG_CELL_LENGTH = 36;
const CARD_TABLE_LONG_ROW_LENGTH = 140;

const CANONICAL_ALIASES = {
  title: ["title", "name", "match", "game", "對戰", "比賽", "標題"],
  sport: ["sport", "運動", "項目"],
  module: ["module", "skill", "模組"],
  event: ["event", "league", "competition", "tournament", "賽事", "聯盟", "賽區"],
  startTime: ["startTime", "matchTime", "time", "date", "台灣時間", "開賽時間", "時間"],
  bo: ["bo", "format", "seriesFormat", "賽制"],
  prediction: ["prediction", "predictedScore", "scorePrediction", "預測", "預測比分"],
  winner: ["winner", "predictedWinner", "勝方", "預測勝方"],
  winProbability: ["winProbability", "winProb", "win%", "勝率", "獨贏機率", "全場勝率", "1x2"],
  recommendation: ["recommendation", "pick", "mainPick", "推薦", "主推", "投注建議"],
  stake: ["stake", "unit", "注碼", "建議注碼"],
  confidence: ["confidence", "confidence%", "信心度", "信心指數"],
  risk: ["risk", "coreRisk", "keyRisk", "主要風險", "核心風險"],
  sourceStatus: ["sourceStatus", "dataStatus", "資料狀態"],
  analysisType: ["analysisType", "type", "分析類型"],
  generatedAt: ["generatedAt", "createdAt", "產生時間"],
  tags: ["tags", "labels", "標籤"],
  url: ["url", "sourceUrl", "連結", "來源連結"],
};

const PROPERTY_ALIASES = {
  title: ["Name", "Title", "對戰", "比賽", "名稱", "標題"],
  sport: ["Sport", "運動", "項目"],
  module: ["Module", "Skill", "模組"],
  event: ["Event", "League", "Competition", "Tournament", "賽事", "聯盟", "賽區"],
  startTime: ["Start Time", "Match Time", "Time", "Date", "台灣時間", "開賽時間", "時間", "日期"],
  bo: ["BO", "Format", "Series", "賽制"],
  prediction: ["Prediction", "Predicted Score", "Score", "預測", "預測比分"],
  winner: ["Winner", "Predicted Winner", "勝方", "預測勝方"],
  winProbability: ["Win%", "Win Probability", "Win Prob", "勝率", "獨贏機率", "全場勝率", "1X2 機率"],
  recommendation: ["Recommendation", "Pick", "Main Pick", "推薦", "主推", "投注建議"],
  stake: ["Stake", "Unit", "注碼", "建議注碼"],
  confidence: ["Confidence", "Confidence%", "信心度", "信心指數"],
  risk: ["Risk", "Core Risk", "Key Risk", "主要風險", "核心風險"],
  sourceStatus: ["Source Status", "Data Status", "資料狀態"],
  analysisType: ["Analysis Type", "Type", "分析類型"],
  generatedAt: ["Generated At", "Created At", "產生時間"],
  tags: ["Tags", "Labels", "標籤"],
  url: ["URL", "Source URL", "Link", "連結", "來源連結"],
};

const READ_ONLY_PROPERTY_TYPES = new Set([
  "created_by",
  "created_time",
  "formula",
  "last_edited_by",
  "last_edited_time",
  "rollup",
  "unique_id",
]);

function parseArgs(argv) {
  const args = {};

  for (let i = 0; i < argv.length; i += 1) {
    const raw = argv[i];

    if (!raw.startsWith("--")) {
      throw new Error(`Unexpected argument: ${raw}`);
    }

    const [flag, inlineValue] = raw.slice(2).split("=", 2);
    const camelFlag = flag.replace(/-([a-z])/g, (_, char) => char.toUpperCase());

    if (["dryRun", "help"].includes(camelFlag)) {
      args[camelFlag] = true;
      continue;
    }

    const value = inlineValue ?? argv[i + 1];
    if (value == null || value.startsWith("--")) {
      throw new Error(`Missing value for --${flag}`);
    }

    if (inlineValue == null) {
      i += 1;
    }

    args[camelFlag] = value;
  }

  return args;
}

function usage() {
  return `Usage:
  node shared/notion/publish_prediction.mjs --summary result.json --markdown analysis.md

Required environment:
  NOTION_TOKEN or NOTION_API_KEY
  NOTION_DATA_SOURCE_ID, NOTION_DATABASE_ID, or NOTION_PAGE_ID

Useful options:
  --module cs-analysis
  --sport CS2
  --title "Team A vs Team B"
  --table-layout auto|table|cards
  --env-file .env
  --data-source-id <id>
  --database-id <id>
  --page-id <id>
  --property-map '{"prediction":"預測比分","confidence":"信心度"}'
  --dry-run
`;
}

function unquoteEnvValue(value) {
  const trimmed = value.trim();
  if (
    (trimmed.startsWith('"') && trimmed.endsWith('"')) ||
    (trimmed.startsWith("'") && trimmed.endsWith("'"))
  ) {
    return trimmed.slice(1, -1);
  }

  return trimmed;
}

async function loadEnvFile(filePath) {
  if (!filePath) {
    return;
  }

  const resolvedPath = path.resolve(filePath);
  let raw;

  try {
    raw = await fs.readFile(resolvedPath, "utf8");
  } catch (error) {
    if (error.code === "ENOENT") {
      return;
    }
    throw error;
  }

  for (const line of raw.replace(/\r\n/g, "\n").split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) {
      continue;
    }

    const withoutExport = trimmed.startsWith("export ") ? trimmed.slice(7).trim() : trimmed;
    const separatorIndex = withoutExport.indexOf("=");
    if (separatorIndex === -1) {
      continue;
    }

    const key = withoutExport.slice(0, separatorIndex).trim();
    const value = unquoteEnvValue(withoutExport.slice(separatorIndex + 1));
    if (key && process.env[key] == null) {
      process.env[key] = value;
    }
  }
}

function envBool(name) {
  return /^(1|true|yes|on)$/i.test(process.env[name] ?? "");
}

function normalizeTableLayout(value) {
  const layout = String(value ?? "auto").trim().toLowerCase();
  if (!layout || layout === "auto") {
    return "auto";
  }
  if (["card", "cards", "list", "lists"].includes(layout)) {
    return "cards";
  }
  if (["table", "tables"].includes(layout)) {
    return "table";
  }

  throw new Error(`Invalid table layout: ${value}. Use auto, table, or cards.`);
}

async function readTextFile(filePath) {
  return fs.readFile(filePath, "utf8");
}

async function readJsonFile(filePath) {
  if (!filePath) {
    return {};
  }

  const raw = await readTextFile(filePath);
  return JSON.parse(raw);
}

function parseJsonObject(raw, label) {
  if (!raw) {
    return {};
  }

  try {
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      throw new Error("expected an object");
    }
    return parsed;
  } catch (error) {
    throw new Error(`Invalid ${label}: ${error.message}`);
  }
}

function normalizeName(value) {
  return String(value ?? "")
    .trim()
    .toLowerCase()
    .replace(/\s+/g, "")
    .replace(/[：:()（）_%]/g, "");
}

function isBlank(value) {
  return value == null || String(value).trim() === "";
}

function firstDefined(...values) {
  return values.find((value) => {
    if (Array.isArray(value)) {
      return value.length > 0;
    }
    return !isBlank(value);
  });
}

function getAliasValue(input, canonicalKey) {
  const aliases = CANONICAL_ALIASES[canonicalKey] ?? [canonicalKey];
  const normalizedToKey = new Map();

  for (const key of Object.keys(input)) {
    normalizedToKey.set(normalizeName(key), key);
  }

  for (const alias of aliases) {
    const originalKey = normalizedToKey.get(normalizeName(alias));
    if (originalKey && !isBlank(input[originalKey])) {
      return input[originalKey];
    }
  }

  return undefined;
}

function inferFromMarkdown(markdown) {
  const inferred = {};

  const heading = markdown.match(/^#{1,3}\s+(.+(?:\svs\s| @ ).+)$/im);
  if (heading) {
    inferred.title = stripMarkdown(heading[1]);
  }

  const prediction =
    markdown.match(/預測比分\s*\|?\s*([^|\n]+)/i) ??
    markdown.match(/\*\*預測比分[：:]\*\*\s*([^\n]+)/i) ??
    markdown.match(/預測比分[：:]\s*([^\n]+)/i);
  if (prediction) {
    inferred.prediction = stripMarkdown(prediction[1]);
  }

  const confidence =
    markdown.match(/信心(?:度|指數)\s*\|?\s*([0-9]+(?:\.[0-9]+)?%?)/i) ??
    markdown.match(/信心(?:度|指數)[：:]\s*([0-9]+(?:\.[0-9]+)?%?)/i);
  if (confidence) {
    inferred.confidence = confidence[1];
  }

  const recommendation =
    markdown.match(/主推[：:]\s*([^\n]+)/i) ??
    markdown.match(/推薦方向\s*\|?\s*([^|\n]+)/i) ??
    markdown.match(/推薦\s*\|?\s*([^|\n]+)/i);
  if (recommendation) {
    inferred.recommendation = stripMarkdown(recommendation[1]);
  }

  const risk =
    markdown.match(/核心風險\s*\|?\s*([^|\n]+)/i) ??
    markdown.match(/主要風險[\s\S]*?\n-\s*([^\n]+)/i);
  if (risk) {
    inferred.risk = stripMarkdown(risk[1]);
  }

  return inferred;
}

function normalizeRecord(summary, markdown, args) {
  const inferred = inferFromMarkdown(markdown);
  const merged = {
    ...inferred,
    ...summary,
  };

  const record = {};

  for (const canonicalKey of Object.keys(CANONICAL_ALIASES)) {
    record[canonicalKey] = getAliasValue(merged, canonicalKey);
  }

  record.module = firstDefined(args.module, record.module, summary.module);
  record.sport = firstDefined(args.sport, record.sport, summary.sport);
  record.title = firstDefined(args.title, record.title, summary.title, summary.match, inferred.title);
  record.generatedAt = firstDefined(record.generatedAt, new Date().toISOString());
  record.analysisType = firstDefined(record.analysisType, "pre-match");

  if (!record.title) {
    const sportPrefix = record.sport ? `${record.sport} ` : "";
    record.title = `${sportPrefix}Prediction ${new Date().toISOString().slice(0, 10)}`;
  }

  return {
    ...summary,
    ...record,
  };
}

function stripMarkdown(value) {
  return String(value ?? "")
    .replace(/\*\*/g, "")
    .replace(/`/g, "")
    .trim();
}

function toArray(value) {
  if (Array.isArray(value)) {
    return value.filter((item) => !isBlank(item)).map((item) => String(item).trim());
  }

  if (isBlank(value)) {
    return [];
  }

  return String(value)
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function extractNumber(value) {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }

  const match = String(value ?? "").match(/-?\d+(?:\.\d+)?/);
  return match ? Number(match[0]) : undefined;
}

function normalizeDate(value) {
  if (isBlank(value)) {
    return undefined;
  }

  const asDate = new Date(value);
  if (Number.isNaN(asDate.valueOf())) {
    return undefined;
  }

  return asDate.toISOString();
}

function richText(content, annotations = {}) {
  const text = {
    type: "text",
    text: { content: String(content ?? "").slice(0, RICH_TEXT_LIMIT) },
  };

  if (Object.keys(annotations).length > 0) {
    text.annotations = annotations;
  }

  return [text];
}

function textChunks(content, limit = RICH_TEXT_LIMIT) {
  const text = String(content ?? "");
  if (!text) {
    return [""];
  }

  const chunks = [];
  for (let index = 0; index < text.length; index += limit) {
    chunks.push(text.slice(index, index + limit));
  }

  return chunks;
}

function makeTextBlocks(type, content, options = {}) {
  const key = type;
  const chunks = textChunks(content);
  return chunks.map((chunk) => ({
    object: "block",
    type,
    [key]: {
      rich_text: richText(chunk, options.annotations),
      ...(options.extra ?? {}),
    },
  }));
}

function makeCodeBlocks(content, language = "markdown") {
  return textChunks(content).map((chunk) => ({
    object: "block",
    type: "code",
    code: {
      rich_text: richText(chunk),
      language,
    },
  }));
}

function splitMarkdownTableRow(line) {
  let trimmed = String(line ?? "").trim();
  if (trimmed.startsWith("|")) {
    trimmed = trimmed.slice(1);
  }
  if (trimmed.endsWith("|")) {
    trimmed = trimmed.slice(0, -1);
  }

  const cells = [];
  let cell = "";
  let escaped = false;

  for (const char of trimmed) {
    if (escaped) {
      cell += char;
      escaped = false;
      continue;
    }

    if (char === "\\") {
      escaped = true;
      continue;
    }

    if (char === "|") {
      cells.push(cell.trim());
      cell = "";
      continue;
    }

    cell += char;
  }

  cells.push(cell.trim());
  return cells;
}

function isMarkdownTableSeparator(cells) {
  return (
    cells.length > 0 &&
    cells.every((cell) => /^:?-{3,}:?$/.test(String(cell ?? "").trim()))
  );
}

function normalizeTableRows(rows, width) {
  return rows.map((row) => {
    const normalized = row.slice(0, width);
    while (normalized.length < width) {
      normalized.push("");
    }
    return normalized;
  });
}

function makeTableRowBlock(cells) {
  return {
    object: "block",
    type: "table_row",
    table_row: {
      cells: cells.map((cell) => richText(stripMarkdown(cell))),
    },
  };
}

function displayTableCell(cell) {
  return stripMarkdown(cell)
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/\\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function compactTableCell(cell) {
  return displayTableCell(cell).replace(/\s+/g, " ").trim();
}

function parseMarkdownTable(lines) {
  const rows = lines.map(splitMarkdownTableRow).filter((row) => row.length > 0);
  if (rows.length < 2) {
    return undefined;
  }

  const separatorIndex = rows.findIndex(isMarkdownTableSeparator);
  const hasColumnHeader = separatorIndex === 1;
  const dataRows = rows.filter((_, index) => index !== separatorIndex);
  if (dataRows.length === 0) {
    return undefined;
  }

  const width = Math.max(...dataRows.map((row) => row.length));
  if (!Number.isFinite(width) || width === 0) {
    return undefined;
  }

  return {
    rows: normalizeTableRows(dataRows, width),
    width,
    hasColumnHeader,
  };
}

function shouldRenderTableAsCards(parsed, tableLayout) {
  if (!parsed.hasColumnHeader) {
    return false;
  }

  const bodyRows = parsed.rows.slice(1);
  if (bodyRows.length === 0 || tableLayout === "table") {
    return false;
  }
  if (tableLayout === "cards") {
    return true;
  }

  const hasLongCell = bodyRows.some((row) =>
    row.some((cell) => compactTableCell(cell).length >= CARD_TABLE_LONG_CELL_LENGTH),
  );
  const hasLongRow = bodyRows.some(
    (row) =>
      row.reduce((length, cell) => length + compactTableCell(cell).length, 0) >=
      CARD_TABLE_LONG_ROW_LENGTH,
  );

  return (
    parsed.width >= CARD_TABLE_ALWAYS_COLUMNS ||
    (parsed.width >= CARD_TABLE_MIN_COLUMNS && (hasLongCell || hasLongRow))
  );
}

function makeTableCardBlocks(parsed) {
  const [headerRow, ...bodyRows] = parsed.rows;
  const headers = headerRow.map((header, index) => displayTableCell(header) || `欄位 ${index + 1}`);
  const blocks = [];

  for (const [rowIndex, row] of bodyRows.entries()) {
    const firstHeader = headers[0] || "項目";
    const title = displayTableCell(row[0]) || `${firstHeader} ${rowIndex + 1}`;
    blocks.push(...makeTextBlocks("heading_3", title));

    for (let cellIndex = 1; cellIndex < row.length; cellIndex += 1) {
      const value = displayTableCell(row[cellIndex]);
      if (!value) {
        continue;
      }

      const label = headers[cellIndex] || `欄位 ${cellIndex + 1}`;
      const content = value.includes("\n") ? `${label}:\n${value}` : `${label}: ${value}`;
      blocks.push(...makeTextBlocks("bulleted_list_item", content));
    }

    if (rowIndex < bodyRows.length - 1) {
      blocks.push({ object: "block", type: "divider", divider: {} });
    }
  }

  return blocks;
}

function makeTableBlocks(lines, options = {}) {
  const parsed = parseMarkdownTable(lines);
  if (!parsed) {
    return makeCodeBlocks(lines.join("\n"), "markdown");
  }

  const tableLayout = normalizeTableLayout(options.tableLayout);
  if (shouldRenderTableAsCards(parsed, tableLayout)) {
    return makeTableCardBlocks(parsed);
  }

  const blocks = [];
  const rowLimit = 100;
  const [headerRow, ...bodyRows] = parsed.rows;
  const rowGroups =
    parsed.hasColumnHeader && bodyRows.length > rowLimit - 1
      ? bodyRows.reduce((groups, row, index) => {
          if (index % (rowLimit - 1) === 0) {
            groups.push([headerRow]);
          }
          groups[groups.length - 1].push(row);
          return groups;
        }, [])
      : [];
  const groups = rowGroups.length > 0 ? rowGroups : [];

  if (groups.length === 0) {
    for (let index = 0; index < parsed.rows.length; index += rowLimit) {
      groups.push(parsed.rows.slice(index, index + rowLimit));
    }
  }

  for (const group of groups) {
    if (group.length === 0) {
      continue;
    }

    blocks.push({
      object: "block",
      type: "table",
      table: {
        table_width: parsed.width,
        has_column_header: parsed.hasColumnHeader,
        has_row_header: false,
        children: group.map(makeTableRowBlock),
      },
    });
  }

  return blocks;
}

function summaryBlocks(record) {
  const items = [
    ["模組", record.module],
    ["項目", record.sport],
    ["賽事", record.event],
    ["時間", record.startTime],
    ["賽制", record.bo],
    ["預測", record.prediction],
    ["勝方", record.winner],
    ["勝率", record.winProbability],
    ["推薦", record.recommendation],
    ["注碼", record.stake],
    ["信心度", record.confidence],
    ["核心風險", record.risk],
    ["資料狀態", record.sourceStatus],
  ].filter(([, value]) => !isBlank(value));

  const blocks = [
    ...makeTextBlocks("heading_2", "匯出摘要"),
    ...items.flatMap(([label, value]) => makeTextBlocks("bulleted_list_item", `${label}: ${value}`)),
    { object: "block", type: "divider", divider: {} },
  ];

  return blocks;
}

function markdownToBlocks(markdown, options = {}) {
  const blocks = [];
  const lines = String(markdown ?? "").replace(/\r\n/g, "\n").split("\n");
  let paragraph = [];
  let table = [];
  let fencedCode = [];
  let fenceLanguage = "plain text";
  let inFence = false;

  const flushParagraph = () => {
    if (paragraph.length === 0) {
      return;
    }

    blocks.push(...makeTextBlocks("paragraph", paragraph.join("\n").trim()));
    paragraph = [];
  };

  const flushTable = () => {
    if (table.length === 0) {
      return;
    }

    blocks.push(...makeTableBlocks(table, options));
    table = [];
  };

  const flushFence = () => {
    blocks.push(...makeCodeBlocks(fencedCode.join("\n"), fenceLanguage || "plain text"));
    fencedCode = [];
    fenceLanguage = "plain text";
  };

  for (const line of lines) {
    const fenceMatch = line.match(/^```(\w+)?\s*$/);
    if (fenceMatch) {
      if (inFence) {
        flushFence();
        inFence = false;
      } else {
        flushParagraph();
        flushTable();
        fenceLanguage = fenceMatch[1] || "plain text";
        inFence = true;
      }
      continue;
    }

    if (inFence) {
      fencedCode.push(line);
      continue;
    }

    if (/^\s*\|.*\|\s*$/.test(line)) {
      flushParagraph();
      table.push(line);
      continue;
    }

    flushTable();

    if (!line.trim()) {
      flushParagraph();
      continue;
    }

    const heading = line.match(/^(#{1,3})\s+(.+)$/);
    if (heading) {
      flushParagraph();
      const level = Math.min(heading[1].length, 3);
      blocks.push(...makeTextBlocks(`heading_${level}`, stripMarkdown(heading[2])));
      continue;
    }

    if (/^\s*---+\s*$/.test(line)) {
      flushParagraph();
      blocks.push({ object: "block", type: "divider", divider: {} });
      continue;
    }

    const bullet = line.match(/^\s*[-*]\s+(.+)$/);
    if (bullet) {
      flushParagraph();
      blocks.push(...makeTextBlocks("bulleted_list_item", stripMarkdown(bullet[1])));
      continue;
    }

    const numbered = line.match(/^\s*\d+\.\s+(.+)$/);
    if (numbered) {
      flushParagraph();
      blocks.push(...makeTextBlocks("numbered_list_item", stripMarkdown(numbered[1])));
      continue;
    }

    paragraph.push(line);
  }

  if (inFence) {
    flushFence();
  }
  flushParagraph();
  flushTable();

  return blocks;
}

function parsePropertyMap(args) {
  return {
    ...parseJsonObject(process.env.NOTION_PROPERTY_MAP, "NOTION_PROPERTY_MAP"),
    ...parseJsonObject(args.propertyMap, "--property-map"),
  };
}

function canonicalForProperty(propertyName, propertyMap) {
  const normalizedProperty = normalizeName(propertyName);

  for (const [canonical, mappedName] of Object.entries(propertyMap)) {
    if (normalizeName(mappedName) === normalizedProperty) {
      return canonical;
    }
  }

  for (const [canonical, aliases] of Object.entries(PROPERTY_ALIASES)) {
    if (aliases.some((alias) => normalizeName(alias) === normalizedProperty)) {
      return canonical;
    }
  }

  return undefined;
}

function propertyValueForType(type, value) {
  if (isBlank(value) && !Array.isArray(value)) {
    return undefined;
  }

  switch (type) {
    case "title":
      return { title: richText(value) };
    case "rich_text":
      return { rich_text: richText(value) };
    case "select":
      return { select: { name: String(value).trim().slice(0, 100) } };
    case "status":
      return { status: { name: String(value).trim().slice(0, 100) } };
    case "multi_select": {
      const options = toArray(value).slice(0, 20);
      return options.length ? { multi_select: options.map((name) => ({ name: name.slice(0, 100) })) } : undefined;
    }
    case "number": {
      const number = extractNumber(value);
      return number == null ? undefined : { number };
    }
    case "date": {
      const start = normalizeDate(value);
      return start ? { date: { start } } : undefined;
    }
    case "checkbox":
      return { checkbox: /^(1|true|yes|on|y)$/i.test(String(value)) };
    case "url":
      return { url: String(value).trim() };
    case "email":
      return { email: String(value).trim() };
    case "phone_number":
      return { phone_number: String(value).trim() };
    default:
      return undefined;
  }
}

function buildProperties(record, schema, propertyMap) {
  if (!schema) {
    return {
      title: {
        title: richText(record.title),
      },
    };
  }

  const properties = {};
  let titleWasSet = false;

  for (const [propertyName, definition] of Object.entries(schema)) {
    const type = definition.type;
    if (READ_ONLY_PROPERTY_TYPES.has(type)) {
      continue;
    }

    const canonical = type === "title" ? "title" : canonicalForProperty(propertyName, propertyMap);
    if (!canonical) {
      continue;
    }

    const value = canonical === "tags" ? record.tags : record[canonical];
    const converted = propertyValueForType(type, value);
    if (!converted) {
      continue;
    }

    properties[propertyName] = converted;
    if (type === "title") {
      titleWasSet = true;
    }
  }

  if (!titleWasSet) {
    const titleProperty = Object.entries(schema).find(([, definition]) => definition.type === "title");
    if (titleProperty) {
      properties[titleProperty[0]] = { title: richText(record.title) };
    }
  }

  return properties;
}

function configuredTarget(args) {
  const dataSourceId = args.dataSourceId || process.env.NOTION_DATA_SOURCE_ID;
  const databaseId = args.databaseId || process.env.NOTION_DATABASE_ID;
  const pageId = args.pageId || process.env.NOTION_PAGE_ID;

  if (dataSourceId) {
    return { type: "data_source_id", id: dataSourceId };
  }

  if (databaseId) {
    return { type: "database_id", id: databaseId };
  }

  if (pageId) {
    return { type: "page_id", id: pageId };
  }

  return undefined;
}

async function notionRequest({ method, path, token, notionVersion, body }) {
  const url = `${API_BASE}${path}`;
  const headers = {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
    "Notion-Version": notionVersion,
  };

  for (let attempt = 0; attempt < 4; attempt += 1) {
    const response = await fetch(url, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });

    const text = await response.text();
    const payload = text ? JSON.parse(text) : {};

    if (response.ok) {
      return payload;
    }

    if ([429, 500, 502, 503, 504, 529].includes(response.status) && attempt < 3) {
      const retryAfter = Number(response.headers.get("retry-after") ?? 0);
      const delayMs = retryAfter > 0 ? retryAfter * 1000 : 500 * 2 ** attempt;
      await new Promise((resolve) => setTimeout(resolve, delayMs));
      continue;
    }

    const message = payload?.message ? ` ${payload.message}` : "";
    throw new Error(`Notion API ${method} ${path} failed (${response.status}).${message}`);
  }

  throw new Error(`Notion API ${method} ${path} failed after retries.`);
}

async function resolveTarget({ target, token, notionVersion, dryRun }) {
  if (!target) {
    throw new Error("Missing Notion target. Set NOTION_DATA_SOURCE_ID, NOTION_DATABASE_ID, or NOTION_PAGE_ID.");
  }

  if (target.type === "page_id") {
    return {
      parent: { type: "page_id", page_id: target.id },
      schema: null,
      resolvedTarget: target,
    };
  }

  if (dryRun && !token) {
    const parent =
      target.type === "data_source_id"
        ? { type: "data_source_id", data_source_id: target.id }
        : { database_id: target.id };

    return {
      parent,
      schema: null,
      resolvedTarget: target,
    };
  }

  if (target.type === "data_source_id") {
    const dataSource = await notionRequest({
      method: "GET",
      path: `/data_sources/${target.id}`,
      token,
      notionVersion,
    });

    return {
      parent: { type: "data_source_id", data_source_id: dataSource.id },
      schema: dataSource.properties,
      resolvedTarget: { type: "data_source_id", id: dataSource.id },
    };
  }

  const database = await notionRequest({
    method: "GET",
    path: `/databases/${target.id}`,
    token,
    notionVersion,
  });

  const dataSources = database.data_sources ?? [];
  if (dataSources.length > 0) {
    const desiredName = process.env.NOTION_DATA_SOURCE_NAME;
    const selected =
      (desiredName && dataSources.find((source) => source.name === desiredName)) ?? dataSources[0];

    const dataSource = await notionRequest({
      method: "GET",
      path: `/data_sources/${selected.id}`,
      token,
      notionVersion,
    });

    return {
      parent: { type: "data_source_id", data_source_id: dataSource.id },
      schema: dataSource.properties,
      resolvedTarget: { type: "data_source_id", id: dataSource.id },
    };
  }

  return {
    parent: { database_id: target.id },
    schema: database.properties ?? null,
    resolvedTarget: target,
  };
}

async function createPage({ token, notionVersion, parent, properties, blocks }) {
  const firstChildren = blocks.slice(0, CREATE_CHILD_LIMIT);
  const page = await notionRequest({
    method: "POST",
    path: "/pages",
    token,
    notionVersion,
    body: {
      parent,
      properties,
      children: firstChildren,
    },
  });

  const remaining = blocks.slice(CREATE_CHILD_LIMIT);
  for (let index = 0; index < remaining.length; index += APPEND_CHILD_LIMIT) {
    const children = remaining.slice(index, index + APPEND_CHILD_LIMIT);
    await notionRequest({
      method: "PATCH",
      path: `/blocks/${page.id}/children`,
      token,
      notionVersion,
      body: { children },
    });
  }

  return page;
}

function pageUrl(page) {
  if (page?.url) {
    return page.url;
  }

  if (page?.id) {
    return `https://www.notion.so/${page.id.replace(/-/g, "")}`;
  }

  return undefined;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help) {
    process.stdout.write(usage());
    return;
  }

  await loadEnvFile(args.envFile || process.env.NOTION_ENV_FILE || ".env");

  const dryRun = Boolean(args.dryRun) || envBool("NOTION_DRY_RUN");
  const token =
    args.token ||
    process.env.NOTION_TOKEN ||
    process.env.NOTION_API_KEY ||
    process.env.NOTION_ACCESS_TOKEN;

  if (!token && !dryRun) {
    throw new Error("Missing Notion token. Set NOTION_TOKEN or NOTION_API_KEY.");
  }

  const notionVersion = args.notionVersion || process.env.NOTION_VERSION || DEFAULT_NOTION_VERSION;
  const summary = await readJsonFile(args.summary);
  const markdown = args.markdown ? await readTextFile(args.markdown) : String(summary.markdown ?? "");
  const record = normalizeRecord(summary, markdown, args);
  const target = configuredTarget(args);
  const propertyMap = parsePropertyMap(args);
  const tableLayout = normalizeTableLayout(args.tableLayout || process.env.NOTION_TABLE_LAYOUT);
  const resolved = await resolveTarget({ target, token, notionVersion, dryRun });
  const properties = buildProperties(record, resolved.schema, propertyMap);
  const bodyBlocks = [
    ...summaryBlocks(record),
    ...makeTextBlocks("heading_2", "完整分析"),
    ...markdownToBlocks(markdown, { tableLayout }),
  ];

  if (dryRun) {
    process.stdout.write(
      `${JSON.stringify(
        {
          dryRun: true,
          notionVersion,
          target: resolved.resolvedTarget,
          parent: resolved.parent,
          title: record.title,
          tableLayout,
          properties,
          blockCount: bodyBlocks.length,
        },
        null,
        2,
      )}\n`,
    );
    return;
  }

  const page = await createPage({
    token,
    notionVersion,
    parent: resolved.parent,
    properties,
    blocks: bodyBlocks,
  });

  process.stdout.write(
    `${JSON.stringify(
      {
        ok: true,
        id: page.id,
        url: pageUrl(page),
        title: record.title,
        tableLayout,
        blockCount: bodyBlocks.length,
      },
      null,
      2,
    )}\n`,
  );
}

main().catch((error) => {
  process.stderr.write(`${error.message}\n`);
  process.exitCode = 1;
});

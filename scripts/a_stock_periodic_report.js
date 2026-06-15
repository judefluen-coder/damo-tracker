#!/usr/bin/env node

const fs = require("fs");
const path = require("path");

const REPORT_DIR = process.env.A_STOCK_REPORT_DIR || path.join(process.cwd(), "reports");
const WORKSPACE_DIR = process.env.DAMO_WORKSPACE || process.cwd();
const DAMO_RUN_DIR = path.join(WORKSPACE_DIR, "damo_runs");
const modeArg = (process.argv[2] || "weekly").toLowerCase();
const mode =
  modeArg === "week" || modeArg === "weekly"
    ? "weekly"
    : modeArg === "month" || modeArg === "monthly"
      ? "monthly"
      : null;

if (!mode) {
  console.error("Usage: a_stock_periodic_report.js weekly|monthly");
  process.exit(64);
}

function parseDay(input) {
  const raw = String(input || "").replace(/-/g, "");
  const m = raw.match(/^(\d{4})(\d{2})(\d{2})$/);
  if (!m) throw new Error(`Invalid date: ${input}`);
  return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
}

function ymd(date) {
  const yyyy = date.getFullYear();
  const mm = String(date.getMonth() + 1).padStart(2, "0");
  const dd = String(date.getDate()).padStart(2, "0");
  return `${yyyy}${mm}${dd}`;
}

function isoDay(date) {
  const raw = ymd(date);
  return `${raw.slice(0, 4)}-${raw.slice(4, 6)}-${raw.slice(6, 8)}`;
}

function addDays(date, n) {
  const next = new Date(date);
  next.setDate(next.getDate() + n);
  return next;
}

function periodFor(kind) {
  const today = process.env.A_STOCK_TODAY
    ? parseDay(process.env.A_STOCK_TODAY)
    : new Date();

  let start;
  let end;
  if (kind === "weekly") {
    end = today;
    start = addDays(today, -7);
  } else {
    start = new Date(today.getFullYear(), today.getMonth() - 1, 1);
    end = new Date(today.getFullYear(), today.getMonth(), 0);
  }

  if (process.env.A_STOCK_PERIOD_START) start = parseDay(process.env.A_STOCK_PERIOD_START);
  if (process.env.A_STOCK_PERIOD_END) end = parseDay(process.env.A_STOCK_PERIOD_END);
  return { start, end };
}

function between(day, start, end) {
  return day >= ymd(start) && day <= ymd(end);
}

function clean(line) {
  return String(line || "")
    .replace(/[*_`#>]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function firstMatch(text, regex) {
  const m = text.match(regex);
  return m ? clean(m[1]) : "";
}

function parseDaily(file, text) {
  const date = file.match(/(\d{8})/)[1];
  const headline = firstMatch(text, /^>\s*(.+)$/m);
  const countsMatch = headline.match(/买入[:：]\s*(\d+).*?观望[:：]\s*(\d+).*?卖出[:：]\s*(\d+)/);
  const counts = countsMatch
    ? {
        buy: Number(countsMatch[1]),
        watch: Number(countsMatch[2]),
        sell: Number(countsMatch[3]),
      }
    : { buy: 0, watch: 0, sell: 0 };

  const rows = [];
  const rowRegex = /\*\*([^*(]+)(?:\((\d{6})\))?\*\*:\s*([^|]+)\|\s*评分\s*([0-9.-]+)\s*\|\s*([^\n]+)/g;
  let m;
  while ((m = rowRegex.exec(text))) {
    rows.push({
      name: clean(m[1]),
      code: m[2] || "",
      action: clean(m[3]),
      score: Number(m[4]),
      bias: clean(m[5]),
      date,
    });
  }

  return { date, file, headline, counts, rows };
}

function parseMarket(file, text) {
  const date = file.match(/(\d{8})/)[1];
  const summary = firstMatch(text, /^>\s*(.+)$/m);
  const light = firstMatch(text, /大盘红绿灯[^：]*：\s*([a-zA-Z]+)[^|]*\|\s*[^0-9]*(\d+\/100)/);
  const advice = firstMatch(text, /操作建议[^：]*：\s*([^\n]+)/);
  const position = firstMatch(text, /仓位区间[^：]*：\s*([^\n]+)/);
  const sectors = [];
  const top = text.match(/#### 领涨板块 Top 5([\s\S]*?)(?:####|###|$)/);
  if (top) {
    for (const row of top[1].split("\n")) {
      const m = row.match(/^\|\s*\d+\s*\|\s*([^|]+)\|\s*([+-]?[0-9.]+%)/);
      if (m) sectors.push({ name: clean(m[1]), change: clean(m[2]) });
    }
  }
  return { date, file, summary, light, advice, position, sectors };
}

function loadReports(kind) {
  const { start, end } = periodFor(kind);
  const daily = [];
  const markets = [];

  for (const file of fs.readdirSync(REPORT_DIR).sort()) {
    const m = file.match(/^(report|market_review)_(\d{8})\.md$/);
    if (!m || !between(m[2], start, end)) continue;
    const fullPath = path.join(REPORT_DIR, file);
    const text = fs.readFileSync(fullPath, "utf8");
    if (m[1] === "report") daily.push(parseDaily(file, text));
    if (m[1] === "market_review") markets.push(parseMarket(file, text));
  }

  if (!daily.length && !markets.length) {
    console.error(`No A-stock reports found in ${REPORT_DIR} for ${isoDay(start)} to ${isoDay(end)}.`);
    process.exit(2);
  }

  return { start, end, daily, markets };
}

function topStocks(daily) {
  const map = new Map();
  for (const report of daily) {
    for (const row of report.rows) {
      const key = row.code ? `${row.name}(${row.code})` : row.name;
      const item =
        map.get(key) ||
        {
          key,
          count: 0,
          scores: [],
          lastAction: "",
          lastBias: "",
          lastDate: "",
        };
      item.count += 1;
      if (Number.isFinite(row.score)) item.scores.push(row.score);
      item.lastAction = row.action;
      item.lastBias = row.bias;
      item.lastDate = row.date;
      map.set(key, item);
    }
  }
  return [...map.values()].map((item) => ({
    ...item,
    avgScore: item.scores.length
      ? Math.round((item.scores.reduce((sum, score) => sum + score, 0) / item.scores.length) * 10) / 10
      : 0,
  }));
}

function topSectors(markets) {
  const map = new Map();
  for (const market of markets) {
    for (const [index, sector] of market.sectors.entries()) {
      const item = map.get(sector.name) || { name: sector.name, count: 0, bestRank: 99, lastChange: "" };
      item.count += 1;
      item.bestRank = Math.min(item.bestRank, index + 1);
      item.lastChange = sector.change;
      map.set(sector.name, item);
    }
  }
  return [...map.values()].sort((a, b) => b.count - a.count || a.bestRank - b.bestRank).slice(0, 8);
}

function readJsonSafe(file) {
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch {
    return null;
  }
}

function overlaps(range, start, end) {
  if (!Array.isArray(range) || range.length < 2) return false;
  const rangeStart = String(range[0] || "").replace(/-/g, "");
  const rangeEnd = String(range[1] || "").replace(/-/g, "");
  return rangeEnd >= ymd(start) && rangeStart <= ymd(end);
}

function stockKey(item) {
  const name = clean(item["股票名称"] || item.name || "");
  const code = clean(item["股票代码"] || item.code || "");
  return code && !/原文未提及|未知|无|-/.test(code) ? `${name} ${code}` : name;
}

function loadDamoRuns(start, end) {
  const candidates = [];
  const seenFiles = new Set();
  const pushFile = (file) => {
    if (seenFiles.has(file) || !fs.existsSync(file)) return;
    seenFiles.add(file);
    const result = readJsonSafe(file);
    if (!result || !overlaps(result.date_range, start, end)) return;
    candidates.push({
      file,
      mtimeMs: fs.statSync(file).mtimeMs,
      range: result.date_range,
      total: Array.isArray(result.videos) ? result.videos.length : 0,
      failed: Array.isArray(result.failed) ? result.failed.length : Array.isArray(result.failures) ? result.failures.length : 0,
      partial: Array.isArray(result.partial) ? result.partial.length : 0,
      raw: Array.isArray(result.raw_stocks) ? result.raw_stocks.length : 0,
      stocks: Array.isArray(result.stocks) ? result.stocks : [],
    });
  };

  if (fs.existsSync(DAMO_RUN_DIR)) {
    for (const file of fs.readdirSync(DAMO_RUN_DIR)) {
      if (/^damo_result_.*\.json$/.test(file)) pushFile(path.join(DAMO_RUN_DIR, file));
    }
  }
  pushFile(path.join(WORKSPACE_DIR, "damo_result.json"));

  const byDay = new Map();
  for (const run of candidates.sort((a, b) => a.mtimeMs - b.mtimeMs)) {
    const key = Array.isArray(run.range) ? run.range.join("_") : String(run.mtimeMs);
    byDay.set(key, run);
  }
  return [...byDay.values()].sort((a, b) => String(a.range?.[0] || "").localeCompare(String(b.range?.[0] || "")));
}

function renderDamoSection(start, end) {
  const runs = loadDamoRuns(start, end);
  if (!runs.length) {
    return [
      "## 大摩追踪信号",
      "- 本周期内未找到已归档的大摩追踪结果。若本周新增运行，结果会从 damo_runs/ 自动并入周报。",
      "",
    ];
  }

  const totals = runs.reduce(
    (acc, run) => ({
      videos: acc.videos + run.total,
      failed: acc.failed + run.failed,
      partial: acc.partial + run.partial,
      raw: acc.raw + run.raw,
    }),
    { videos: 0, failed: 0, partial: 0, raw: 0 },
  );
  const stockMap = new Map();
  for (const run of runs) {
    for (const stock of run.stocks) {
      const key = stockKey(stock);
      if (!key) continue;
      const existing = stockMap.get(key);
      const item = {
        key,
        rating: clean(stock["评级"] || ""),
        target: clean(stock["目标价"] || ""),
        reason: clean(stock["推荐理由"] || ""),
        source: clean(stock["来源视频"] || ""),
        date: clean(stock["发布日期"] || run.range?.[1] || ""),
        partial: stock._content_quality === "partial",
      };
      if (!existing || item.reason.length > existing.reason.length) stockMap.set(key, item);
    }
  }
  const stocks = [...stockMap.values()].slice(0, 12);

  const lines = ["## 大摩追踪信号"];
  lines.push(
    `- 本周纳入大摩追踪 ${runs.length} 次；扫描 ${totals.videos} 个视频，截断但已分析 ${totals.partial} 个，完全失败 ${totals.failed} 个，raw 候选 ${totals.raw} 个，去重标的 ${stockMap.size} 支。`,
  );
  if (stocks.length) {
    lines.push("- 可跟踪标的：");
    for (const item of stocks) {
      const target = item.target && item.target !== "原文未提及" ? `，目标价 ${item.target}` : "";
      const partial = item.partial ? "，截断片段" : "";
      const source = item.source ? `；来源：${item.date} ${item.source}` : "";
      lines.push(`  - ${item.key}：${item.rating || "评级未提及"}${target}${partial}；${item.reason || "原文未提及"}${source}`);
    }
  } else {
    lines.push("- 本周大摩追踪未提取到可发布的A股/港股推荐。");
  }
  lines.push("");
  return lines;
}

function render(kind) {
  const { start, end, daily, markets } = loadReports(kind);
  const stocks = topStocks(daily);
  const sectors = topSectors(markets);
  const counts = daily.reduce(
    (acc, item) => ({
      buy: acc.buy + item.counts.buy,
      watch: acc.watch + item.counts.watch,
      sell: acc.sell + item.counts.sell,
    }),
    { buy: 0, watch: 0, sell: 0 },
  );

  const strongest = stocks
    .filter((item) => !/卖出|减仓|清仓|看空/.test(`${item.lastAction}${item.lastBias}`))
    .sort((a, b) => b.avgScore - a.avgScore || b.count - a.count)
    .slice(0, 6);
  const risks = stocks
    .filter((item) => /卖出|减仓|看空/.test(`${item.lastAction}${item.lastBias}`) || item.avgScore < 45)
    .sort((a, b) => a.avgScore - b.avgScore || b.count - a.count)
    .slice(0, 6);
  const marketTone = markets
    .slice(-3)
    .map((item) => item.summary || item.advice || item.light)
    .filter(Boolean)
    .join("；");

  const title = kind === "weekly" ? "A股周度报告" : "A股月度报告";
  const lines = [];
  lines.push(`# 【呱呱】${title}`);
  lines.push("");
  lines.push(`> 范围：${isoDay(start)} 至 ${isoDay(end)}；日报 ${daily.length} 份，大盘复盘 ${markets.length} 份。`);
  lines.push("");
  lines.push("## 一句话结论");
  if (markets.length) {
    lines.push(`- 市场：${marketTone || markets[markets.length - 1].summary || "已有大盘复盘，但未提取到摘要。"}`);
  }
  lines.push(`- 个股：周期内累计信号为买入 ${counts.buy}、观望 ${counts.watch}、卖出 ${counts.sell}。若买入信号偏少，优先按复盘仓位建议控制节奏。`);
  lines.push("");

  if (markets.length) {
    lines.push("## 大盘与板块");
    for (const market of markets.slice(-5)) {
      const bits = [market.summary, market.advice, market.position].filter(Boolean).join("；");
      lines.push(`- ${isoDay(parseDay(market.date))}：${bits || "复盘已生成，但摘要字段为空。"}`);
    }
    if (sectors.length) {
      lines.push("");
      lines.push("高频领涨方向：");
      for (const item of sectors) {
        lines.push(`- ${item.name}：出现 ${item.count} 次，最好排名第 ${item.bestRank}，最近涨幅 ${item.lastChange}`);
      }
    }
    lines.push("");
  }

  if (stocks.length) {
    lines.push("## 个股信号");
    if (strongest.length) {
      lines.push("相对强势/可继续跟踪：");
      for (const item of strongest) {
        lines.push(`- ${item.key}：出现 ${item.count} 次，均分 ${item.avgScore}，最新 ${item.lastAction}/${item.lastBias}（${isoDay(parseDay(item.lastDate))}）`);
      }
    }
    if (risks.length) {
      lines.push("");
      lines.push("风险或弱势名单：");
      for (const item of risks) {
        lines.push(`- ${item.key}：出现 ${item.count} 次，均分 ${item.avgScore}，最新 ${item.lastAction}/${item.lastBias}（${isoDay(parseDay(item.lastDate))}）`);
      }
    }
    lines.push("");
  }

  if (kind === "weekly") {
    lines.push(...renderDamoSection(start, end));
  }

  lines.push("## 每日摘要");
  const allDates = [...new Set([...daily.map((item) => item.date), ...markets.map((item) => item.date)])].sort();
  for (const date of allDates) {
    const d = daily.find((item) => item.date === date);
    const m = markets.find((item) => item.date === date);
    const dailyText = d ? d.headline || `个股 ${d.rows.length} 只` : "无个股日报";
    const marketText = m ? m.summary || m.advice || "有大盘复盘" : "无大盘复盘";
    lines.push(`- ${isoDay(parseDay(date))}：${dailyText}；${marketText}`);
  }
  lines.push("");

  lines.push("## 来源文件");
  for (const item of daily) lines.push(`- ${path.join(REPORT_DIR, item.file)}`);
  for (const item of markets) lines.push(`- ${path.join(REPORT_DIR, item.file)}`);
  if (kind === "weekly" && fs.existsSync(DAMO_RUN_DIR)) lines.push(`- ${DAMO_RUN_DIR}`);
  lines.push("");
  lines.push("提示：以上内容由本地日报与大盘复盘聚合生成，仅作复盘参考，不构成投资建议。");

  const output = lines.join("\n");
  const outputName = `periodic_${kind}_${ymd(start)}_${ymd(end)}.md`;
  fs.writeFileSync(path.join(REPORT_DIR, outputName), output);
  return output;
}

process.stdout.write(render(mode));
process.stdout.write("\n");

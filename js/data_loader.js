/**
 * data_loader.js — Shared utility for all Marketing Agents dashboards
 * 
 * Usage (from any sub-dashboard HTML):
 *   <script src="../js/data_loader.js"></script>
 *   <script>
 *     DataLoader.load('trend_analyser').then(data => render(data));
 *   </script>
 *
 * Usage (from index.html at root):
 *   <script src="js/data_loader.js"></script>
 *   <script>
 *     DataLoader.loadAll().then(all => renderSummary(all));
 *   </script>
 */

const DataLoader = (() => {

  const AGENTS = {
    trend_analyser:    { label: 'Trend Analyser',       paths: ['trend_analyser/output/latest.json'] },
    customer_behaviour:{ label: 'Customer Behaviour',   paths: ['customer_behaviour/output/latest.json'] },
    competitor:        { label: 'Competitor Analysis',  paths: ['competitor_analysis/output/latest.json'] },
    seo:               { label: 'SEO Agent',            paths: ['seo_agent/output/latest.json'] },
  };

  const SCHEDULER_LOG = 'scheduler_log.txt';
  const SNAPSHOT_PATH = 'shared/intelligence_snapshot.json';

  async function fetchJSON(path) {
    const attempts = [path, path.replace(/^.*?\//, '')];
    for (const p of attempts) {
      try {
        const res = await fetch(p);
        if (res.ok) return await res.json();
      } catch (_) {}
    }
    return null;
  }

  async function fetchText(path) {
    const attempts = [path, path.replace(/^.*?\//, '')];
    for (const p of attempts) {
      try {
        const res = await fetch(p);
        if (res.ok) return await res.text();
      } catch (_) {}
    }
    return null;
  }

  /** Load data for a single agent */
  async function load(agentKey) {
    const agent = AGENTS[agentKey];
    if (!agent) throw new Error(`Unknown agent: ${agentKey}`);
    for (const path of agent.paths) {
      const data = await fetchJSON(path);
      if (data) return { ok: true, data, agent: agentKey, label: agent.label };
    }
    return { ok: false, data: null, agent: agentKey, label: agent.label };
  }

  /** Load data for all agents in parallel */
  async function loadAll() {
    const results = await Promise.all(Object.keys(AGENTS).map(load));
    const out = {};
    results.forEach(r => { out[r.agent] = r; });
    return out;
  }

  /** Load shared intelligence snapshot */
  async function loadSnapshot() {
    const data = await fetchJSON(SNAPSHOT_PATH);
    if (!data) return null;
    return data;
  }

  /** Load and parse scheduler_log.txt */
  async function loadSchedulerLog() {
    const text = await fetchText(SCHEDULER_LOG);
    if (!text) return null;
    return parseSchedulerLog(text);
  }

  function parseSchedulerLog(text) {
    const lines = text.trim().split('\n');
    const runs = [];
    let currentRun = null;

    for (const raw of lines) {
      const line = raw.replace(/\x1b\[[0-9;]*m/g, '').trim();
      if (!line) continue;

      const tsMatch = line.match(/^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]\s+(.*)/);
      if (!tsMatch) continue;

      const timestamp = tsMatch[1];
      const msg = tsMatch[2].trim();

      if (msg.includes('[START]')) {
        const taskName = msg.replace('[START]', '').trim();
        currentRun = { task: taskName, start: timestamp, status: 'running', lines: [], duration: null };
        runs.push(currentRun);
      } else if (currentRun && (msg.includes('[OK]') || msg.includes('[FAIL]') || msg.includes('[TIMEOUT]'))) {
        const durMatch = msg.match(/\((\d+)s\)/);
        currentRun.duration = durMatch ? parseInt(durMatch[1]) : 0;
        currentRun.status = msg.includes('[OK]') ? 'ok' : msg.includes('[TIMEOUT]') ? 'timeout' : 'fail';
        currentRun.end = timestamp;
        currentRun = null;
      } else if (msg.startsWith('=') && msg.includes('Marketing Agents Scheduler')) {
        // Scheduler restart boundary
      } else if (msg.startsWith('[START]') || msg.startsWith('[END]')) {
        // ignore wrapper lines
      }
    }

    // Build per-task summaries
    const taskMap = {};
    for (const run of runs) {
      if (!taskMap[run.task]) {
        taskMap[run.task] = { task: run.task, runs: [], lastStatus: null, lastRun: null, successCount: 0, failCount: 0 };
      }
      const entry = taskMap[run.task];
      entry.runs.push(run);
      entry.lastStatus = run.status;
      entry.lastRun = run.end || run.start;
      if (run.status === 'ok') entry.successCount++;
      else if (run.status === 'fail' || run.status === 'timeout') entry.failCount++;
    }

    // Get last scheduler start time
    const startLines = lines.filter(l => l.includes('Scheduler running'));
    const lastStart = startLines.length ? startLines[startLines.length - 1].match(/\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]/)?.[1] : null;

    return {
      tasks: Object.values(taskMap),
      recentRuns: runs.slice(-50),
      lastSchedulerStart: lastStart,
      totalRuns: runs.length,
      rawLines: lines,
    };
  }

  /** Format a date string nicely */
  function fmtDate(str) {
    if (!str) return '—';
    try {
      return new Date(str).toLocaleString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
    } catch (_) { return str; }
  }

  /** Format number with commas */
  function fmtNum(n) {
    return typeof n === 'number' ? n.toLocaleString() : (n || '—');
  }

  return { load, loadAll, loadSnapshot, loadSchedulerLog, AGENTS, fmtDate, fmtNum };
})();
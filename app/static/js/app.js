const botSelect = document.getElementById("bot-select");
const runBtn = document.getElementById("run-btn");
const refreshBtn = document.getElementById("refresh-btn");
const runsBody = document.getElementById("runs-body");
const launchStatus = document.getElementById("launch-status");
let pollTimer = null;

function selectedMode() {
  const checked = document.querySelector('input[name="browser-mode"]:checked');
  return checked ? checked.value : "headless";
}

function formatTime(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function truncate(value, n = 28) {
  if (!value) return "—";
  return value.length > n ? `${value.slice(0, n)}…` : value;
}

async function fetchJSON(url, options) {
  const res = await fetch(url, options);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed (${res.status})`);
  }
  return res.json();
}

async function loadBots() {
  const data = await fetchJSON("/api/bots");
  botSelect.innerHTML = "";
  if (!data.bots.length) {
    botSelect.innerHTML = '<option value="">No bots registered</option>';
    runBtn.disabled = true;
    return;
  }
  for (const bot of data.bots) {
    const opt = document.createElement("option");
    opt.value = bot.id;
    opt.textContent = `${bot.name} [${bot.engine}]`;
    botSelect.appendChild(opt);
  }
}

function renderRuns(runs) {
  if (!runs.length) {
    runsBody.innerHTML = '<tr><td colspan="6" class="empty">No runs yet</td></tr>';
    return;
  }

  runsBody.innerHTML = runs
    .map((run) => {
      const detail = run.error_details || run.result_message || "—";
      return `
        <tr>
          <td>${formatTime(run.started_at || run.created_at)}</td>
          <td>${escapeHtml(run.bot_name)}</td>
          <td>${escapeHtml(run.browser_mode)}</td>
          <td><span class="badge ${escapeHtml(run.status)}">${escapeHtml(run.status)}</span></td>
          <td class="mono" title="${escapeHtml(run.challenge_id || "")}">${escapeHtml(truncate(run.challenge_id))}</td>
          <td class="details">${escapeHtml(detail)}</td>
        </tr>`;
    })
    .join("");
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

async function loadRuns() {
  const data = await fetchJSON("/api/runs?limit=100");
  renderRuns(data.runs);
  const active = data.runs.some((r) => r.status === "running" || r.status === "pending");
  if (active) {
    schedulePoll(2500);
  }
}

function schedulePoll(ms) {
  clearTimeout(pollTimer);
  pollTimer = setTimeout(async () => {
    try {
      await loadRuns();
    } catch (err) {
      launchStatus.textContent = err.message;
    }
  }, ms);
}

async function startRun() {
  const botId = botSelect.value;
  if (!botId) return;

  runBtn.disabled = true;
  launchStatus.textContent = "Starting run…";

  try {
    const data = await fetchJSON("/api/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        bot_id: botId,
        browser_mode: selectedMode(),
      }),
    });
    launchStatus.textContent = `Run ${data.run.id} queued (${data.run.browser_mode}).`;
    await loadRuns();
    schedulePoll(1500);
  } catch (err) {
    launchStatus.textContent = err.message;
  } finally {
    runBtn.disabled = false;
  }
}

runBtn.addEventListener("click", startRun);
refreshBtn.addEventListener("click", () => {
  loadRuns().catch((err) => {
    launchStatus.textContent = err.message;
  });
});

Promise.all([loadBots(), loadRuns()]).catch((err) => {
  launchStatus.textContent = err.message;
  runsBody.innerHTML = `<tr><td colspan="6" class="empty">${escapeHtml(err.message)}</td></tr>`;
});

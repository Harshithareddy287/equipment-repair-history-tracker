(() => {
  "use strict";

  const TILE_RULES = ["repeat_failure", "low_stock", "shortfall", "unknown_part"];
  const TONE = {
    repeat_failure: "c-pink",
    low_stock: "c-butter",
    shortfall: "c-peach",
    unknown_part: "c-lav",
  };

  const modeSelect = document.getElementById("mode-select");
  const themeToggle = document.getElementById("theme-toggle");
  const ownerView = document.getElementById("owner-view");
  const recordsView = document.getElementById("records-view");
  const techView = document.getElementById("technical-view");
  const recordsCount = document.getElementById("records-count");
  const recordsFilter = document.getElementById("records-filter");
  const visitsSort = document.getElementById("visits-sort");
  const stockSort = document.getElementById("stock-sort");
  const visitsTableBody = document.querySelector("#visits-table tbody");
  const stockTableBody = document.querySelector("#stock-table tbody");
  let recordsCache = null;
  const tiles = document.getElementById("tiles");
  const flagList = document.getElementById("flag-list");
  const stockList = document.getElementById("stock-list");
  const ruleNote = document.getElementById("rule-note");
  const status = document.getElementById("status");
  const searchForm = document.getElementById("search-form");
  const lookupInput = document.getElementById("lookup-search");
  const detailTitle = document.getElementById("detail-title");
  const detailEmpty = document.getElementById("detail-empty");
  const detailCard = document.getElementById("detail-card");
  const dbLabel = document.getElementById("db-label");
  const termOut = document.getElementById("term-out");
  const cliForm = document.getElementById("cli-form");
  const cliInput = document.getElementById("cli-input");

  function setMode(mode) {
    if (!["owner", "records", "technical"].includes(mode)) mode = "owner";
    ownerView.hidden = mode !== "owner";
    recordsView.hidden = mode !== "records";
    techView.hidden = mode !== "technical";
    ownerView.classList.toggle("is-active", mode === "owner");
    recordsView.classList.toggle("is-active", mode === "records");
    techView.classList.toggle("is-active", mode === "technical");
    modeSelect.value = mode;
    try { localStorage.setItem("tracker-mode", mode); } catch { /* ignore */ }
    if (mode === "technical") cliInput.focus();
    if (mode === "records") loadRecords();
  }

  modeSelect.addEventListener("change", () => setMode(modeSelect.value));

  function themeIsDark() {
    return document.documentElement.getAttribute("data-theme") === "dark";
  }

  function setTheme(dark) {
    document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
    themeToggle.setAttribute("aria-pressed", String(dark));
    themeToggle.setAttribute("aria-label", dark ? "Switch to light mode" : "Switch to dark mode");
    themeToggle.title = dark ? "Light mode" : "Dark mode";
    try { localStorage.setItem("tracker-theme", dark ? "dark" : "light"); } catch { /* ignore */ }
  }

  themeToggle.addEventListener("click", () => setTheme(!themeIsDark()));
  setTheme(themeIsDark());

  function showStatus(kind, text) {
    status.hidden = !text;
    status.className = `status ${kind}`;
    status.textContent = text || "";
  }

  async function getJson(url) {
    const res = await fetch(url);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.error || `Request failed (${res.status})`);
    }
    return data;
  }

  function fillTiles(counts) {
    TILE_RULES.forEach((rule) => {
      const tile = tiles.querySelector(`[data-rule="${rule}"]`);
      if (tile) tile.querySelector("b").textContent = String(counts[rule] ?? 0);
    });
  }

  function fillSettings(settings) {
    if (!settings) {
      ruleNote.textContent = "";
      return;
    }
    ruleNote.textContent = `Repeat failure is ${settings.repeat_failure_count} visits in ${settings.repeat_failure_window_days} days. Low stock is at or under the reorder level.`;
  }

  function idButton(value, onClick) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "id";
    button.textContent = value;
    button.addEventListener("click", onClick);
    return button;
  }

  function renderFlags(flags) {
    flagList.replaceChildren();
    if (!flags.length) {
      const empty = document.createElement("p");
      empty.className = "note";
      empty.textContent = "No flags in the saved history.";
      flagList.append(empty);
      return;
    }
    flags.forEach((flag) => {
      const row = document.createElement("div");
      row.className = "row";
      const key = document.createElement("span");
      key.className = `k ${TONE[flag.rule] || "c-sky"}`;
      key.textContent = flag.label;
      const who = flag.serial_number || flag.part_number || "—";
      const id = flag.serial_number
        ? idButton(who, () => lookupHistory(flag.serial_number))
        : flag.part_number
          ? idButton(who, () => lookupPart(flag.part_number))
          : Object.assign(document.createElement("span"), { className: "id", textContent: who });
      const msg = document.createElement("span");
      msg.textContent = flag.message;
      row.append(key, id, msg);
      flagList.append(row);
    });
  }

  function renderStock(rows) {
    stockList.replaceChildren();
    if (!rows.length) {
      const empty = document.createElement("p");
      empty.className = "note";
      empty.textContent = "No parts are at or under their reorder level.";
      stockList.append(empty);
      return;
    }
    rows.forEach((row) => {
      const item = document.createElement("div");
      item.className = "row";
      const key = document.createElement("span");
      key.className = `k ${TONE[row.status] || "c-butter"}`;
      key.textContent = row.status === "shortfall" ? "Shortfall" : "Low stock";
      const id = idButton(row.part_number, () => lookupPart(row.part_number));
      const msg = document.createElement("span");
      msg.textContent = `${row.quantity_on_hand} on hand, reorder at ${row.reorder_level}`;
      item.append(key, id, msg);
      stockList.append(item);
    });
  }

  function showDetail(title, card) {
    detailTitle.textContent = title;
    detailEmpty.hidden = true;
    detailEmpty.textContent = "";
    detailCard.hidden = false;
    detailCard.replaceChildren(...card);
  }

  function showDetailEmpty(message) {
    detailTitle.textContent = "Lookup";
    detailCard.hidden = true;
    detailCard.replaceChildren();
    detailEmpty.hidden = false;
    detailEmpty.textContent = message;
  }

  function renderHistory(data) {
    if (!data.rows || !data.rows.length) {
      showDetailEmpty(data.text || `No history for ${data.serial}.`);
      return;
    }
    const head = document.createElement("div");
    const k = document.createElement("span");
    k.className = "k";
    k.textContent = `${data.rows.length} saved visit row${data.rows.length === 1 ? "" : "s"}`;
    const serial = document.createElement("span");
    serial.className = "serial";
    serial.textContent = data.serial;
    head.append(k, serial);
    const log = document.createElement("div");
    log.className = "log";
    data.rows.forEach((row) => {
      const line = document.createElement("div");
      const date = document.createElement("span");
      date.className = "m";
      date.textContent = row.visit_date;
      const rest = document.createElement("span");
      const part = row.part_number ? `  ${row.part_number} x${row.quantity}` : "";
      rest.textContent = `${row.visit_id}  ${row.technician}  ${row.problem_code}  ${row.outcome}${part}`;
      line.append(date, rest);
      log.append(line);
    });
    showDetail("Machine history", [head, log]);
    lookupInput.value = data.serial;
  }

  function renderPart(data) {
    if (!data.found) {
      showDetailEmpty(data.text || `No stock record or usage for ${data.part_number}.`);
      return;
    }
    const head = document.createElement("div");
    const k = document.createElement("span");
    k.className = "k";
    k.textContent = data.stock ? data.stock.description : "Part used on a visit, not in the stock list";
    const serial = document.createElement("span");
    serial.className = "serial";
    serial.textContent = data.part_number;
    head.append(k, serial);
    const nodes = [head];
    if (data.stock) {
      const nums = document.createElement("div");
      nums.className = "nums";
      [
        [String(data.stock.quantity_on_hand), "on hand"],
        [String(data.stock.reorder_level), "reorder at"],
        [String(data.uses.length), data.uses.length === 1 ? "visit used" : "visits used"],
      ].forEach(([value, label]) => {
        const cell = document.createElement("div");
        const b = document.createElement("b");
        b.textContent = value;
        const span = document.createElement("span");
        span.textContent = label;
        cell.append(b, span);
        nums.append(cell);
      });
      nodes.push(nums);
      if (data.stock.status !== "ok") {
        const stamp = document.createElement("span");
        stamp.className = `stamp ${data.stock.status === "shortfall" ? "c-pink" : "c-butter"}`;
        stamp.textContent = data.stock.status === "shortfall" ? "Below zero" : "At or under reorder level";
        nodes.push(stamp);
      }
    }
    if (data.uses.length) {
      const log = document.createElement("div");
      log.className = "log";
      data.uses.forEach((row) => {
        const line = document.createElement("div");
        const date = document.createElement("span");
        date.className = "m";
        date.textContent = row.visit_date;
        const rest = document.createElement("span");
        rest.textContent = `${row.visit_id}  ${row.serial_number}  ${row.technician}  x${row.quantity}`;
        line.append(date, rest);
        log.append(line);
      });
      nodes.push(log);
    }
    showDetail("Part", nodes);
    lookupInput.value = data.part_number;
  }

  async function loadOverview() {
    showStatus("", "");
    try {
      const data = await getJson("/api/overview");
      dbLabel.textContent = data.db_path || "database";
      fillTiles(data.counts || {});
      fillSettings(data.settings);
      renderFlags(data.flags || []);
      renderStock(data.stock || []);
      if (data.empty) {
        showStatus("warn", data.hint || "No visits in this database yet.");
      }
    } catch (err) {
      dbLabel.textContent = "unavailable";
      showStatus("bad", err.message);
    }
  }

  async function lookupHistory(serial) {
    const value = (serial || "").trim();
    if (!value) return;
    try {
      const data = await getJson(`/api/history?serial=${encodeURIComponent(value)}`);
      renderHistory(data);
    } catch (err) {
      showDetailEmpty(err.message);
    }
  }

  async function lookupPart(partNumber) {
    const value = (partNumber || "").trim();
    if (!value) return;
    try {
      const data = await getJson(`/api/part?part=${encodeURIComponent(value)}`);
      renderPart(data);
    } catch (err) {
      showDetailEmpty(err.message);
    }
  }

  function renderMatches(data) {
    const machine = data.machine && data.machine.rows && data.machine.rows.length ? data.machine : null;
    const parts = data.parts || [];
    if (machine && !parts.length) {
      renderHistory(machine);
      return;
    }
    if (!machine && parts.length === 1) {
      renderPart(parts[0]);
      return;
    }
    if (!machine && !parts.length) {
      showDetailEmpty(`No machine or part matched “${data.query}”. Try a serial, a part number, or a name such as Fan.`);
      return;
    }
    const list = document.createElement("div");
    list.className = "list";
    if (machine) {
      const row = document.createElement("div");
      row.className = "row";
      const key = document.createElement("span");
      key.className = "k c-sky";
      key.textContent = "Machine";
      const id = idButton(machine.serial, () => renderHistory(machine));
      const msg = document.createElement("span");
      msg.textContent = `${machine.rows.length} saved visit row${machine.rows.length === 1 ? "" : "s"}`;
      row.append(key, id, msg);
      list.append(row);
    }
    parts.forEach((item) => {
      const row = document.createElement("div");
      row.className = "row";
      const key = document.createElement("span");
      key.className = `k ${item.stock ? TONE[item.stock.status] || "c-lav" : "c-lav"}`;
      key.textContent = item.stock ? item.stock.description : "Unknown part";
      const id = idButton(item.part_number, () => renderPart(item));
      const msg = document.createElement("span");
      msg.textContent = item.stock
        ? `${item.stock.quantity_on_hand} on hand, reorder at ${item.stock.reorder_level}`
        : item.text;
      row.append(key, id, msg);
      list.append(row);
    });
    showDetail("Matches", [list]);
    lookupInput.value = data.query;
  }

  async function lookupEither(query) {
    const value = (query || "").trim();
    if (!value) return;
    try {
      renderMatches(await getJson(`/api/search?q=${encodeURIComponent(value)}`));
    } catch (err) {
      showDetailEmpty(err.message);
    }
  }

  searchForm.addEventListener("submit", (event) => {
    event.preventDefault();
    lookupEither(lookupInput.value);
  });

  function rowMatches(values, needle) {
    if (!needle) return true;
    return values.some((value) => String(value ?? "").toLowerCase().includes(needle));
  }

  function cell(text, asButton, onClick) {
    const td = document.createElement("td");
    if (asButton && text) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = text;
      button.addEventListener("click", onClick);
      td.append(button);
    } else {
      td.textContent = text == null || text === "" ? "—" : text;
    }
    return td;
  }

  function compareText(a, b) {
    return String(a ?? "").localeCompare(String(b ?? ""), undefined, { numeric: true, sensitivity: "base" });
  }

  function compareNumber(a, b) {
    return (Number(a) || 0) - (Number(b) || 0);
  }

  function sortVisits(rows, key) {
    const sorted = rows.slice();
    const by = {
      "date-desc": (a, b) => compareText(b.visit_date, a.visit_date) || compareText(b.visit_id, a.visit_id),
      "date-asc": (a, b) => compareText(a.visit_date, b.visit_date) || compareText(a.visit_id, b.visit_id),
      serial: (a, b) => compareText(a.serial_number, b.serial_number) || compareText(a.visit_date, b.visit_date),
      technician: (a, b) => compareText(a.technician, b.technician) || compareText(a.visit_date, b.visit_date),
      outcome: (a, b) => compareText(a.outcome, b.outcome) || compareText(a.visit_date, b.visit_date),
      part: (a, b) => compareText(a.part_number, b.part_number) || compareText(a.visit_date, b.visit_date),
    };
    sorted.sort(by[key] || by["date-desc"]);
    return sorted;
  }

  function sortStock(rows, key) {
    const rank = { shortfall: 0, low_stock: 1, ok: 2 };
    const sorted = rows.slice();
    const by = {
      status: (a, b) => (rank[a.status] ?? 9) - (rank[b.status] ?? 9) || compareText(a.part_number, b.part_number),
      part: (a, b) => compareText(a.part_number, b.part_number),
      name: (a, b) => compareText(a.description, b.description),
      "on-hand-asc": (a, b) => compareNumber(a.quantity_on_hand, b.quantity_on_hand),
      "on-hand-desc": (a, b) => compareNumber(b.quantity_on_hand, a.quantity_on_hand),
    };
    sorted.sort(by[key] || by.status);
    return sorted;
  }

  function renderRecordTables() {
    if (!recordsCache) return;
    const needle = recordsFilter.value.trim().toLowerCase();
    const visits = sortVisits((recordsCache.visits || []).filter((row) => rowMatches([
      row.visit_date, row.visit_id, row.serial_number, row.equipment_type,
      row.technician, row.problem_code, row.outcome, row.part_number, row.quantity,
    ], needle)), visitsSort.value);
    const stock = sortStock((recordsCache.stock || []).filter((row) => rowMatches([
      row.part_number, row.description, row.quantity_on_hand, row.reorder_level, row.status,
    ], needle)), stockSort.value);

    visitsTableBody.replaceChildren();
    if (!visits.length) {
      const tr = document.createElement("tr");
      tr.className = "empty-row";
      const td = document.createElement("td");
      td.colSpan = 9;
      td.textContent = needle ? "No visits match that filter." : "No visits saved.";
      tr.append(td);
      visitsTableBody.append(tr);
    } else {
      visits.forEach((row) => {
        const tr = document.createElement("tr");
        tr.append(
          cell(row.visit_date),
          cell(row.visit_id),
          cell(row.serial_number, true, () => { setMode("owner"); lookupHistory(row.serial_number); }),
          cell(row.equipment_type),
          cell(row.technician),
          cell(row.problem_code),
          cell(row.outcome),
          cell(row.part_number, Boolean(row.part_number), () => { setMode("owner"); lookupPart(row.part_number); }),
          cell(row.quantity),
        );
        visitsTableBody.append(tr);
      });
    }

    stockTableBody.replaceChildren();
    if (!stock.length) {
      const tr = document.createElement("tr");
      tr.className = "empty-row";
      const td = document.createElement("td");
      td.colSpan = 5;
      td.textContent = needle ? "No stock rows match that filter." : "No stock saved.";
      tr.append(td);
      stockTableBody.append(tr);
    } else {
      stock.forEach((row) => {
        const tr = document.createElement("tr");
        if (row.status !== "ok") tr.classList.add("hit");
        const statusLabel = row.status === "shortfall" ? "Shortfall" : row.status === "low_stock" ? "Low stock" : "OK";
        tr.append(
          cell(row.part_number, true, () => { setMode("owner"); lookupPart(row.part_number); }),
          cell(row.description),
          cell(row.quantity_on_hand),
          cell(row.reorder_level),
          cell(statusLabel),
        );
        stockTableBody.append(tr);
      });
    }

    const counts = recordsCache.counts || {};
    recordsCount.textContent = needle
      ? `Showing ${visits.length} of ${counts.visit_rows || 0} visit rows and ${stock.length} of ${counts.stock || 0} stock parts.`
      : `${counts.visits || 0} visits (${counts.visit_rows || 0} rows) and ${counts.stock || 0} stock parts.`;
  }

  async function loadRecords() {
    if (!recordsCache) {
      recordsCount.textContent = "Loading records…";
      try {
        recordsCache = await getJson("/api/records");
      } catch (err) {
        recordsCount.textContent = err.message;
        return;
      }
    }
    renderRecordTables();
  }

  document.getElementById("records-filter-form").addEventListener("submit", (event) => {
    event.preventDefault();
    renderRecordTables();
  });
  recordsFilter.addEventListener("input", renderRecordTables);
  visitsSort.addEventListener("change", renderRecordTables);
  stockSort.addEventListener("change", renderRecordTables);

  function appendTerm(kind, text) {
    const block = document.createElement("div");
    block.className = kind;
    block.textContent = text;
    termOut.append(block);
    termOut.scrollTop = termOut.scrollHeight;
  }

  async function runGuided(command) {
    const text = command.trim();
    if (!text) return;
    appendTerm("cmd", `$ ${text}`);
    try {
      const res = await fetch("/api/guided", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command: text }),
      });
      const data = await res.json().catch(() => ({}));
      const out = data.output || data.error || `Request failed (${res.status})`;
      appendTerm(data.ok ? "" : "err", out.replace(/\n$/, ""));
    } catch (err) {
      appendTerm("err", err.message);
    }
  }

  cliForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const value = cliInput.value;
    cliInput.value = "";
    runGuided(value);
  });

  document.getElementById("command-chips").addEventListener("click", (event) => {
    const chip = event.target.closest("[data-command]");
    if (!chip) return;
    cliInput.value = chip.dataset.command;
    runGuided(chip.dataset.command);
  });

  appendTerm("muted", "Guided mode. Allowed: help, version, history SERIAL, report.\nFree-form CLI is not available yet. Load CSVs with the real service-tracker command.");

  try {
    setMode(localStorage.getItem("tracker-mode") || "owner");
  } catch {
    setMode("owner");
  }

  loadOverview();
})();

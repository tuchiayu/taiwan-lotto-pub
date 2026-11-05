"use strict";

const form = document.querySelector("[data-range-form]");

if (form) {
  form.dataset.enhanced = "";
  const rangeInputs = [...form.querySelectorAll('input[name="range"]')];
  const panels = [...form.querySelectorAll("[data-range-panel]")];
  const game = form.querySelector("#game");
  const start = form.querySelector("#start");
  const end = form.querySelector("#end");

  const updateDateBounds = () => {
    if (!start || !end) return;
    const earliest = start.dataset.earliest || "";
    const latest = start.dataset.latest || "";
    start.min = earliest;
    start.max = end.value || latest;
    end.min = start.value || earliest;
    end.max = latest;
  };

  const updateRange = () => {
    const selected = rangeInputs.find((input) => input.checked)?.value || "all";
    for (const panel of panels) {
      const active = panel.dataset.rangePanel === selected;
      panel.hidden = !active;
      for (const input of panel.querySelectorAll("input")) {
        input.disabled = !active;
        input.required = active && input.hasAttribute("data-required");
      }
    }
    updateDateBounds();
  };

  if (start && end) {
    start.dataset.earliest = start.min;
    start.dataset.latest = start.max;
    start.addEventListener("change", updateDateBounds);
    end.addEventListener("change", updateDateBounds);
  }
  if (game && start && end) {
    game.addEventListener("change", () => {
      const option = game.selectedOptions[0];
      start.value = "";
      end.value = "";
      start.dataset.earliest = option?.dataset.historyStart || "";
      start.dataset.latest = option?.dataset.latestDate || "";
      updateDateBounds();
    });
  }
  for (const input of rangeInputs) input.addEventListener("change", updateRange);
  updateRange();
}

const results = document.querySelector("[data-stats-results]");

if (results) {
  const tabs = [...results.querySelectorAll('[role="tab"]')];
  const panels = [...results.querySelectorAll("[data-table-panel]")];
  const tableInput = document.querySelector("[data-active-table-input]");
  const sortStatus = results.querySelector("[data-sort-status]");
  const positions = new Map();
  let activeTable = results.dataset.activeTable || "main";

  const panelFor = (name) => panels.find((panel) => panel.dataset.tablePanel === name);

  const savePosition = (name) => {
    const scroll = panelFor(name)?.querySelector("[data-table-scroll]");
    if (scroll) positions.set(name, { top: scroll.scrollTop, left: scroll.scrollLeft });
  };

  const restorePosition = (name) => {
    const scroll = panelFor(name)?.querySelector("[data-table-scroll]");
    const position = positions.get(name);
    if (scroll && position) {
      scroll.scrollTop = position.top;
      scroll.scrollLeft = position.left;
    }
  };

  const activateTable = (name, { updateUrl = false, focus = false } = {}) => {
    if (!panelFor(name)) name = "main";
    savePosition(activeTable);
    activeTable = name;
    results.dataset.activeTable = name;
    if (tableInput) tableInput.value = name;

    for (const tab of tabs) {
      const selected = tab.id === `${name}-tab`;
      tab.setAttribute("aria-selected", String(selected));
      tab.tabIndex = selected ? 0 : -1;
      if (selected && focus) tab.focus();
    }
    for (const panel of panels) panel.hidden = panel.dataset.tablePanel !== name;

    const activePanel = panelFor(name);
    if (sortStatus && activePanel) sortStatus.textContent = activePanel.dataset.sortLabel;
    restorePosition(name);

    if (updateUrl) {
      const url = new URL(window.location.href);
      url.searchParams.set("table", name);
      history.pushState({ table: name }, "", url);
    }
  };

  for (const tab of tabs) {
    tab.addEventListener("click", (event) => {
      if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      activateTable(tab.id.replace("-tab", ""), { updateUrl: true });
    });
    tab.addEventListener("keydown", (event) => {
      const current = tabs.indexOf(tab);
      let target = null;
      if (event.key === "ArrowRight") target = tabs[(current + 1) % tabs.length];
      if (event.key === "ArrowLeft") target = tabs[(current - 1 + tabs.length) % tabs.length];
      if (event.key === "Home") target = tabs[0];
      if (event.key === "End") target = tabs[tabs.length - 1];
      if (!target) return;
      event.preventDefault();
      activateTable(target.id.replace("-tab", ""), { updateUrl: true, focus: true });
    });
  }

  const sortLabels = {
    number: "號碼",
    count: "開出次數",
    rate: "開出率",
    expected_difference: "與理論差異",
    last_seen_date: "最近開出",
    current_missing_draws: "連續未開",
    longest_missing_draws: "最長未開",
  };

  const updateSortLinks = (panel) => {
    const table = panel.dataset.tablePanel;
    const currentField = panel.dataset.sortField;
    const currentOrder = panel.dataset.sortOrder;
    for (const link of panel.querySelectorAll("[data-sort-link]")) {
      const field = link.dataset.sortField;
      const nextOrder = field === currentField
        ? (currentOrder === "asc" ? "desc" : "asc")
        : (field === "number" ? "asc" : "desc");
      const url = new URL(window.location.href);
      url.searchParams.set("table", table);
      url.searchParams.set(`${table}_sort`, field);
      url.searchParams.set(`${table}_order`, nextOrder);
      link.href = url.toString();
    }
  };

  const sortPanel = (panel, field, order) => {
    const body = panel.querySelector("tbody");
    if (!body) return;
    const scroll = panel.querySelector("[data-table-scroll]");
    const scrollTop = scroll?.scrollTop || 0;
    const scrollLeft = scroll?.scrollLeft || 0;
    const fieldIndex = [...panel.querySelectorAll("thead th")].findIndex(
      (header) => header.querySelector("[data-sort-link]")?.dataset.sortField === field,
    );
    const rows = [...body.rows];
    rows.sort((left, right) => {
      const leftNumber = Number(left.cells[0].dataset.sortValue);
      const rightNumber = Number(right.cells[0].dataset.sortValue);
      const leftValue = left.cells[fieldIndex].dataset.sortValue ?? "";
      const rightValue = right.cells[fieldIndex].dataset.sortValue ?? "";
      if (field === "last_seen_date" && (!leftValue || !rightValue)) {
        if (!leftValue && !rightValue) return leftNumber - rightNumber;
        return leftValue ? -1 : 1;
      }
      const numeric = field !== "last_seen_date";
      const comparison = numeric
        ? Number(leftValue) - Number(rightValue)
        : leftValue.localeCompare(rightValue);
      return comparison === 0 ? leftNumber - rightNumber : (order === "asc" ? comparison : -comparison);
    });
    for (const row of rows) body.append(row);
    if (scroll) {
      scroll.scrollTop = scrollTop;
      scroll.scrollLeft = scrollLeft;
      requestAnimationFrame(() => {
        scroll.scrollTop = scrollTop;
        scroll.scrollLeft = scrollLeft;
      });
    }

    panel.dataset.sortField = field;
    panel.dataset.sortOrder = order;
    panel.dataset.sortLabel = `${sortLabels[field]}，${order === "asc" ? "由小到大" : "由大到小"}`;
    for (const header of panel.querySelectorAll("thead th")) {
      const link = header.querySelector("[data-sort-link]");
      const selected = link?.dataset.sortField === field;
      if (selected) header.setAttribute("aria-sort", order === "asc" ? "ascending" : "descending");
      else header.removeAttribute("aria-sort");
      const icon = link?.querySelector(".sort-icon");
      if (icon) icon.textContent = selected ? (order === "asc" ? "▲" : "▼") : "↕";
    }
    if (sortStatus && panel.dataset.tablePanel === activeTable) {
      sortStatus.textContent = panel.dataset.sortLabel;
    }
    updateSortLinks(panel);
  };

  for (const panel of panels) {
    updateSortLinks(panel);
    for (const link of panel.querySelectorAll("[data-sort-link]")) {
      link.addEventListener("click", (event) => {
        if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
        event.preventDefault();
        const field = link.dataset.sortField;
        const order = panel.dataset.sortField === field
          ? (panel.dataset.sortOrder === "asc" ? "desc" : "asc")
          : (field === "number" ? "asc" : "desc");
        sortPanel(panel, field, order);
        const url = new URL(window.location.href);
        const table = panel.dataset.tablePanel;
        url.searchParams.set("table", table);
        url.searchParams.set(`${table}_sort`, field);
        url.searchParams.set(`${table}_order`, order);
        history.replaceState({ table }, "", url);
        for (const currentPanel of panels) updateSortLinks(currentPanel);
      });
    }
  }

  window.addEventListener("popstate", () => {
    const parameters = new URL(window.location.href).searchParams;
    // Restore the visible panel and its scroll position before sorting its rows.
    activateTable(parameters.get("table") || "main");
    for (const panel of panels) {
      const table = panel.dataset.tablePanel;
      const rawField = parameters.get(`${table}_sort`);
      const field = rawField && rawField in sortLabels ? rawField : "count";
      const order = parameters.get(`${table}_order`) === "asc" ? "asc" : "desc";
      sortPanel(panel, field, order);
    }
  });
}

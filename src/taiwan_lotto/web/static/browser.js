"use strict";

const dateForm = document.querySelector("[data-date-form]");

if (dateForm) {
  const game = dateForm.querySelector("#game");
  const start = dateForm.querySelector("#start");
  const end = dateForm.querySelector("#end");

  const updateBounds = () => {
    if (!start || !end) return;
    const earliest = start.dataset.earliest || "";
    const latest = start.dataset.latest || "";
    start.min = earliest;
    start.max = end.value || latest;
    end.min = start.value || earliest;
    end.max = latest;
  };

  if (game && start && end) {
    start.dataset.earliest = start.min;
    start.dataset.latest = start.max;
    start.addEventListener("change", updateBounds);
    end.addEventListener("change", updateBounds);
    game.addEventListener("change", () => {
      const option = game.selectedOptions[0];
      start.value = "";
      end.value = "";
      start.dataset.earliest = option?.dataset.historyStart || "";
      start.dataset.latest = option?.dataset.latestDate || "";
      updateBounds();
    });
  }
}

if (window.location.hash === "#results") {
  window.addEventListener("load", () => {
    document.querySelector("#results")?.focus({ preventScroll: true });
  });
}

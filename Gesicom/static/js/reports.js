"use strict";
(() => {
  let charts = [];
  const read = (id) => JSON.parse(document.getElementById(id).textContent);
  const palette = ["#39a900", "#00324d", "#78b4c6", "#b7ce96", "#e7ca73", "#8ba0ba"];
  const filter = (name, value) => {
    const form = document.querySelector(".reports-workspace [data-live-form]");
    if (!form) return;
    form.elements.namedItem(name).value = value;
    form.requestSubmit();
  };
  const initialize = () => {
    if (typeof Chart === "undefined") return;
    charts.forEach((chart) => chart.destroy());
    charts = [];
    const region = document.querySelector("[data-report-results]");
    if (!region) return;
    Chart.defaults.font.family = "Work Sans, Arial, sans-serif";
    Chart.defaults.font.size = 10;
    Chart.defaults.color = "#687d89";
    Chart.defaults.borderColor = "#edf1f4";
    const motion = matchMedia("(prefers-reduced-motion: reduce)").matches;
    const common = {
      responsive: true,
      maintainAspectRatio: false,
      animation: {duration: motion ? 0 : 350},
      plugins: {legend: {labels: {usePointStyle: true, pointStyle: "rectRounded", boxWidth: 7, padding: 16, font: {size: 9}}}}
    };
    const scales = {y: {beginAtZero: true, border: {display: false}, ticks: {precision: 0}}, x: {grid: {display: false}, border: {display: false}}};
    const create = (id, config) => {
      const canvas = document.getElementById(id);
      canvas.closest("[data-chart-shell]").hidden = false;
      charts.push(new Chart(canvas, config));
    };
    create("chartTrimestres", {type: "bar", data: {labels: read("trimestres_labels_json"), datasets: [
      {label: "Registradas", data: read("datos_trimestrales_nuevas_json"), backgroundColor: "#dceecf", hoverBackgroundColor: "#39a900", borderRadius: 4, maxBarThickness: 40},
      {label: "Aprobadas", data: read("datos_trimestrales_aprobadas_json"), type: "line", borderColor: "#278000", backgroundColor: "#278000", borderWidth: 2, pointRadius: 3, tension: .2}
    ]}, options: {...common, scales}});
    const doughnut = (id, labels, data, colors, name, codes) => create(id, {
      type: "doughnut", data: {labels, datasets: [{data, backgroundColor: colors, borderWidth: 4, borderColor: "#ffffff", hoverOffset: 6}]},
      options: {...common, cutout: "70%", plugins: {legend: {...common.plugins.legend, position: "bottom"}},
        onHover: (event, elements) => {if (event.native?.target) event.native.target.style.cursor = elements.length ? "pointer" : "default";},
        onClick: (_event, elements) => {if (elements.length) filter(name, codes[elements[0].index]);}}
    });
    doughnut("chartCategorias", read("categorias_labels_json"), read("categorias_data_json"), palette, "proyecto", read("proyectos_codes"));
    create("chartUsuarios", {type: "bar", data: {labels: read("usuarios_labels_json"), datasets: [{label: "Evidencias", data: read("usuarios_data_json"), backgroundColor: "#00324d", borderRadius: 4, maxBarThickness: 35}]}, options: {...common, scales, plugins: {legend: {display: false}}}});
    doughnut("chartEstado", ["Aprobadas", "En revisión", "Rechazadas"], read("status_chart"), ["#39a900", "#ebc867", "#c57c73"], "estado", ["aprobada", "pendiente", "rechazada"]);
    region.querySelectorAll(".chart-data").forEach((detail) => {detail.open = false;});
  };
  initialize();
  document.addEventListener("workspace:updated", (event) => {
    if (event.detail.scope.matches(".reports-workspace")) initialize();
  });
  let printDetails = [];
  window.addEventListener("beforeprint", () => {
    printDetails = [...document.querySelectorAll(".chart-data")].map((item) => [item, item.open]);
    printDetails.forEach(([item]) => {item.open = true;});
  });
  window.addEventListener("afterprint", () => {printDetails.forEach(([item, wasOpen]) => {item.open = wasOpen;});});
})();

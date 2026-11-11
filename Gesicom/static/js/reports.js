"use strict";
(() => {
  const read = (id) => JSON.parse(document.getElementById(id).textContent);
  Chart.defaults.font.family = "Work Sans, Arial, sans-serif";
  Chart.defaults.font.size = 10;
  Chart.defaults.color = "#81909c";
  Chart.defaults.borderColor = "#edf1f4";
  Chart.defaults.animation.duration = matchMedia(
    "(prefers-reduced-motion: reduce)",
  ).matches
    ? 0
    : 550;
  const palette = [
    "#39a900",
    "#00324d",
    "#78b4c6",
    "#b7ce96",
    "#e7ca73",
    "#8ba0ba",
  ];
  const common = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        labels: {
          usePointStyle: true,
          pointStyle: "rectRounded",
          boxWidth: 7,
          boxHeight: 7,
          padding: 16,
          font: { size: 9 },
        },
      },
    },
  };
  const scales = {
    y: {
      beginAtZero: true,
      border: { display: false },
      ticks: { precision: 0, padding: 10 },
    },
    x: {
      grid: { display: false },
      border: { display: false },
      ticks: { padding: 8 },
    },
  };
  new Chart(document.getElementById("chartTrimestres"), {
    type: "bar",
    data: {
      labels: read("trimestres_labels_json"),
      datasets: [
        {
          label: "Registradas",
          data: read("datos_trimestrales_nuevas_json"),
          backgroundColor: "#dceecf",
          hoverBackgroundColor: "#39a900",
          borderRadius: 4,
          maxBarThickness: 40,
        },
        {
          label: "Aprobadas",
          data: read("datos_trimestrales_aprobadas_json"),
          type: "line",
          borderColor: "#39a900",
          backgroundColor: "#39a900",
          borderWidth: 2,
          tension: 0.3,
          pointRadius: 3,
        },
      ],
    },
    options: { ...common, scales },
  });
  new Chart(document.getElementById("chartCategorias"), {
    type: "doughnut",
    data: {
      labels: read("categorias_labels_json"),
      datasets: [
        {
          data: read("categorias_data_json"),
          backgroundColor: palette,
          borderWidth: 4,
          borderColor: "#ffffff",
          hoverOffset: 6,
        },
      ],
    },
    options: {
      ...common,
      cutout: "73%",
      plugins: { legend: { ...common.plugins.legend, position: "bottom" } },
    },
  });
  new Chart(document.getElementById("chartUsuarios"), {
    type: "bar",
    data: {
      labels: read("usuarios_labels_json"),
      datasets: [
        {
          label: "Evidencias",
          data: read("usuarios_data_json"),
          backgroundColor: "#00324d",
          hoverBackgroundColor: "#39a900",
          borderRadius: 4,
          maxBarThickness: 35,
        },
      ],
    },
    options: { ...common, scales, plugins: { legend: { display: false } } },
  });
  new Chart(document.getElementById("chartEstado"), {
    type: "doughnut",
    data: {
      labels: ["Aprobadas", "En revisión", "Rechazadas"],
      datasets: [
        {
          data: read("status_chart"),
          backgroundColor: ["#39a900", "#ebc867", "#c57c73"],
          borderWidth: 4,
          borderColor: "#ffffff",
          hoverOffset: 6,
        },
      ],
    },
    options: {
      ...common,
      cutout: "73%",
      plugins: { legend: { ...common.plugins.legend, position: "bottom" } },
    },
  });
})();

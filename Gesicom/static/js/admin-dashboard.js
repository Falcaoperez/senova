"use strict";
(() => {
  let chart;
  const render = () => {
    chart?.destroy();
    const canvas = document.querySelector("#operations-chart");
    const source = document.querySelector("#operations-chart-data");
    if (!canvas || !source) return;
    const data = JSON.parse(source.textContent);
    if (typeof Chart === "undefined") return;
    chart = new Chart(canvas, {
      type: "line",
      data: {
        labels: data.labels,
        datasets: [{
          label: "Evidencias",
          data: data.valores,
          borderColor: "#278600",
          backgroundColor: "rgba(57,169,0,.09)",
          fill: true,
          borderWidth: 2.5,
          tension: .28,
          pointRadius: 0,
          pointHoverRadius: 5,
          pointBackgroundColor: "#278600"
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: matchMedia("(prefers-reduced-motion: reduce)").matches ? false : {
          duration: 500
        },
        interaction: {
          mode: "index",
          intersect: false
        },
        plugins: {
          legend: {
            display: false
          },
          tooltip: {
            displayColors: false,
            backgroundColor: "#00324d",
            padding: 12,
            titleFont: {
              family: "Work Sans"
            },
            bodyFont: {
              family: "Work Sans"
            }
          }
        },
        scales: {
          x: {
            grid: {
              display: false
            },
            border: {
              display: false
            },
            ticks: {
              maxTicksLimit: 7,
              maxRotation: 0,
              color: "#6e7d85",
              font: {
                family: "Work Sans",
                size: 11
              }
            }
          },
          y: {
            beginAtZero: true,
            border: {
              display: false
            },
            grid: {
              color: "#eef2f1"
            },
            ticks: {
              precision: 0,
              maxTicksLimit: 5,
              color: "#6e7d85",
              font: {
                family: "Work Sans",
                size: 11
              }
            }
          }
        }
      }
    });
  };
  render();
  document.addEventListener("workspace:updated", render);
})();

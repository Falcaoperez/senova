"use strict";
(() => {
  const clock = document.querySelector("[data-colombia-clock]");
  if (!clock) return;
  let timeFormat, dateFormat;
  try {
    timeFormat = new Intl.DateTimeFormat("es-CO", {
      timeZone: "America/Bogota",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hourCycle: "h23",
    });
    dateFormat = new Intl.DateTimeFormat("es-CO", {
      timeZone: "America/Bogota",
      weekday: "long",
      day: "numeric",
      month: "long",
      year: "numeric",
    });
  } catch {
    return;
  }
  const time = clock.querySelector("[data-clock-time]");
  const date = clock.querySelector("[data-clock-date]");
  const instant = clock.querySelector("[data-clock-instant]");
  let timer,
    stopped = false;
  const update = () => {
    clearTimeout(timer);
    if (stopped || document.hidden) return;
    const now = new Date();
    time.textContent = timeFormat.format(now);
    date.textContent = dateFormat.format(now);
    instant.dateTime = now.toISOString();
    timer = setTimeout(update, 1000 - (Date.now() % 1000));
  };
  document.addEventListener("visibilitychange", update);
  window.addEventListener("pagehide", () => {
    stopped = true;
    clearTimeout(timer);
  });
  window.addEventListener("pageshow", () => {
    stopped = false;
    update();
  });
  update();
})();

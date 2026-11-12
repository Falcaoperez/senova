"use strict";
(() => {
  const menu = document.querySelector("[data-notifications-summary]");
  if (!menu) return;
  const list = menu.querySelector("[data-notification-items]");
  const template = menu.querySelector("[data-notification-template]");
  const status = menu.querySelector("[data-notification-status]");
  const retry = menu.querySelector("[data-notification-retry]");
  const summary = menu.querySelector("summary");
  const interval = 45000;
  let timer,
    controller,
    paused = false,
    stopped = false,
    failures = 0;
  let pending = false,
    pendingDetails = false,
    notBefore = 0,
    signature;
  const available = () =>
    !paused && !stopped && !document.hidden && navigator.onLine !== false;
  const schedule = (delay = interval) => {
    clearTimeout(timer);
    if (available())
      timer = setTimeout(
        () => refresh(menu.open),
        Math.min(Math.max(delay, notBefore - Date.now()), 2147483647),
      );
  };
  const render = (items) => {
    if (!Array.isArray(items) || items.length > 4) throw new Error();
    const nextSignature = JSON.stringify(items);
    if (signature === nextSignature) return;
    const focused = document.activeElement.closest("[data-notification-id]")
      ?.dataset.notificationId;
    const fragment = document.createDocumentFragment();
    for (const item of items) {
      const id = String(item.id);
      const url = new URL(item.abrir_url, location.origin);
      if (
        !/^[1-9]\d{0,18}$/.test(id) ||
        url.origin !== location.origin ||
        !/^https?:$/.test(url.protocol) ||
        !url.pathname.endsWith(`/${id}/abrir/`) ||
        url.username ||
        url.password ||
        url.search ||
        url.hash ||
        typeof item.titulo !== "string" ||
        typeof item.fecha !== "string"
      ) {
        throw new Error();
      }
      const form = template.content.firstElementChild.cloneNode(true);
      form.action = url.href;
      form.dataset.notificationId = id;
      form.querySelector("strong").textContent = item.titulo;
      form.querySelector("small").textContent =
        item.fecha + (item.leida ? "" : " · Sin leer");
      fragment.append(form);
    }
    if (!items.length) {
      const empty = document.createElement("p");
      empty.className = "password-help";
      empty.textContent = "Estás al día. Aquí aparecerán los nuevos avisos.";
      fragment.append(empty);
    }
    list.replaceChildren(fragment);
    signature = nextSignature;
    if (focused && menu.open) {
      (
        list.querySelector(`[data-notification-id="${focused}"] button`) ||
        summary
      ).focus();
    }
  };
  const refresh = async (details = menu.open) => {
    if (!available()) return;
    if (Date.now() < notBefore) {
      schedule(notBefore - Date.now());
      return;
    }
    if (details) {
      list.setAttribute("aria-busy", "true");
      status.hidden = false;
      status.textContent = "Actualizando avisos…";
    }
    if (controller) {
      pending = true;
      pendingDetails ||= details;
      return;
    }
    clearTimeout(timer);
    const ownController = new AbortController();
    controller = ownController;
    const timeout = setTimeout(() => ownController.abort(), 10000);
    retry.disabled = false;
    try {
      const url = new URL(menu.dataset.notificationsSummary, location.origin);
      if (details) url.searchParams.set("detalle", "1");
      const response = await fetch(url, {
        credentials: "same-origin",
        cache: "no-store",
        headers: { Accept: "application/json" },
        signal: ownController.signal,
      });
      if (response.status === 401) {
        const data = await response.json();
        const login = new URL(data.login_url || "/login/", location.origin);
        stopped = true;
        if (
          login.origin === location.origin &&
          /^https?:$/.test(login.protocol)
        )
          location.assign(login.href);
        else location.assign("/login/");
        return;
      }
      if (!response.ok) {
        const after = response.headers.get("Retry-After");
        const seconds = after && /^\d+$/.test(after) ? Number(after) : NaN;
        const date = after ? Date.parse(after) : NaN;
        if (Number.isFinite(seconds)) notBefore = Date.now() + seconds * 1000;
        else if (Number.isFinite(date)) notBefore = date;
        throw new Error();
      }
      const data = await response.json();
      if (ownController.signal.aborted || !available()) return;
      if (!Number.isSafeInteger(data.pendientes) || data.pendientes < 0)
        throw new Error();
      if (details) render(data.recientes);
      document.querySelectorAll("[data-unread-count]").forEach((badge) => {
        badge.textContent =
          data.pendientes > 99 ? "99+" : String(data.pendientes);
        badge.hidden = !data.pendientes;
      });
      summary.setAttribute(
        "aria-label",
        `Notificaciones: ${data.pendientes} sin leer`,
      );
      failures = 0;
      notBefore = 0;
      if (details) {
        status.textContent = "Avisos actualizados.";
        retry.hidden = true;
      }
    } catch {
      if (ownController.signal.aborted && !available()) return;
      failures++;
      if (menu.open) {
        status.hidden = false;
        status.textContent =
          "No se pudieron actualizar los avisos. Puedes consultar la bandeja o volver a intentarlo.";
        retry.hidden = false;
        retry.disabled = Date.now() < notBefore;
      }
    } finally {
      clearTimeout(timeout);
      controller = null;
      list.removeAttribute("aria-busy");
      if (pending && available()) {
        const detailsNext = pendingDetails;
        pending = pendingDetails = false;
        refresh(detailsNext);
      } else {
        pending = pendingDetails = false;
        schedule(Math.min(interval * 2 ** failures, 300000));
      }
    }
  };
  const pause = () => {
    clearTimeout(timer);
    pending = pendingDetails = false;
    controller?.abort();
  };
  retry.addEventListener("click", () => refresh(true));
  menu.addEventListener("toggle", () => {
    if (menu.open) refresh(true);
  });
  document.addEventListener("visibilitychange", () =>
    document.hidden ? pause() : refresh(),
  );
  window.addEventListener("offline", pause);
  window.addEventListener("online", () => refresh());
  window.addEventListener("pagehide", () => {
    paused = true;
    pause();
  });
  window.addEventListener("pageshow", (event) => {
    paused = false;
    if (event.persisted) refresh();
  });
  document.addEventListener("click", (event) => {
    if (!menu.contains(event.target)) menu.open = false;
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") menu.open = false;
  });
  schedule();
})();

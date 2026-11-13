"use strict";
(() => {
  const scope = document.querySelector("[data-inbox]");
  if (!scope) return;
  let busy = false,
    paused = false,
    controller;
  const locked = new Map();
  const feedback = document.createElement("div");
  feedback.className = "inbox-feedback";
  feedback.hidden = true;
  const message = document.createElement("p");
  const refresh = document.createElement("button");
  refresh.type = "button";
  refresh.className = "button button-secondary button-sm";
  refresh.textContent = "Actualizar bandeja";
  feedback.append(message, refresh);
  scope.prepend(feedback);
  const announce = (text, error = false) => {
    feedback.hidden = false;
    feedback.classList.toggle("is-error", error);
    message.setAttribute("role", error ? "alert" : "status");
    message.textContent = text;
    refresh.hidden = !error;
  };
  const refreshInbox = () => {
    scope.dispatchEvent(
      new CustomEvent("workspace:refresh", { detail: { focus: true } }),
    );
    document.dispatchEvent(new Event("notifications:changed"));
  };
  const lockControls = () => {
    if (!busy) return;
    scope
      .querySelectorAll(
        "[data-inbox-action] button, input[name=avisos], [data-notice-all]",
      )
      .forEach((control) => {
        if (!locked.has(control)) locked.set(control, control.disabled);
        control.disabled = true;
      });
  };
  const unlockControls = () => {
    for (const [control, disabled] of locked) {
      if (control.isConnected) control.disabled = disabled;
    }
    locked.clear();
  };
  document.addEventListener("workspace:updated", lockControls);
  scope.addEventListener("change", lockControls);
  refresh.addEventListener("click", refreshInbox);
  scope.addEventListener("submit", async (event) => {
    const form = event.target.closest("[data-inbox-action]");
    if (!form || event.defaultPrevented) return;
    event.preventDefault();
    if (busy || paused) return;
    const url = new URL(form.action, location.origin);
    if (
      url.origin !== location.origin ||
      !/^https?:$/.test(url.protocol) ||
      !/^\/notificaciones\/(?:leidas|seleccion|[1-9]\d{0,18}\/lectura)\/$/.test(
        url.pathname,
      ) ||
      url.username ||
      url.password ||
      url.search ||
      url.hash
    ) {
      announce(
        "No se pudo actualizar la lectura. Actualiza la página para continuar.",
        true,
      );
      return;
    }
    const data = new FormData(form);
    if (event.submitter?.name)
      data.append(event.submitter.name, event.submitter.value);
    busy = true;
    form.setAttribute("aria-busy", "true");
    lockControls();
    announce("Actualizando lectura…");
    const ownController = new AbortController();
    controller = ownController;
    const timeout = setTimeout(() => ownController.abort(), 15000);
    try {
      const response = await fetch(url, {
        method: "POST",
        body: data,
        credentials: "same-origin",
        cache: "no-store",
        headers: { Accept: "application/json", "X-Inbox-Action": "1" },
        signal: ownController.signal,
      });
      if (paused) return;
      const destination = new URL(response.url);
      if (
        response.redirected &&
        destination.origin === location.origin &&
        destination.pathname === "/login/"
      ) {
        location.assign(response.url);
        return;
      }
      const result = await response.json();
      if (!response.ok) {
        announce(
          typeof result.error === "string"
            ? result.error.slice(0, 500)
            : "No se pudo actualizar la lectura.",
          true,
        );
        return;
      }
      if (
        !Number.isSafeInteger(result.actualizados) ||
        result.actualizados < 0 ||
        typeof result.mensaje !== "string"
      ) {
        throw new Error();
      }
      announce(result.mensaje.slice(0, 500));
      refreshInbox();
    } catch {
      if (!paused)
        announce(
          "No pudimos confirmar el cambio. Actualiza la bandeja antes de volver a intentarlo.",
          true,
        );
    } finally {
      clearTimeout(timeout);
      busy = false;
      controller = null;
      form.removeAttribute("aria-busy");
      unlockControls();
    }
  });
  window.addEventListener("pagehide", () => {
    paused = true;
    controller?.abort();
  });
  window.addEventListener("pageshow", (event) => {
    paused = false;
    if (event.persisted) {
      busy = false;
      unlockControls();
      refreshInbox();
    }
  });
})();

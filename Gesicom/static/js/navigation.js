"use strict";
(() => {
  const scope = document.querySelector("[data-live-scope]");
  const form = scope?.querySelector("[data-live-form]");
  if (!form) return;
  const $ = (selector, root = scope) => root.querySelector(selector);
  const $$ = (selector, root = scope) => [...root.querySelectorAll(selector)];
  const path = location.pathname;
  const documentKey = `${performance.timeOrigin}:${path}`;
  let appliedURL = new URL(location.href),
    appliedIndex = 0,
    restoring = false;
  let controller,
    timer,
    failed,
    editRevision = 0,
    applying = false;
  const stateFor = (index) => ({
    ...(typeof history.state === "object" && history.state
      ? history.state
      : {}),
    gesicomWorkspace: { document: documentKey, index },
  });
  const indexOf = (state) => {
    const entry = state?.gesicomWorkspace;
    return entry?.document === documentKey && Number.isSafeInteger(entry.index)
      ? entry.index
      : null;
  };
  history.replaceState(stateFor(0), "", appliedURL);
  const safeURL = (value) => {
    try {
      const url = new URL(value, location.origin);
      return url.origin === location.origin &&
        url.pathname === path &&
        /^https?:$/.test(url.protocol)
        ? url
        : null;
    } catch {
      return null;
    }
  };
  const restoreFilters = (url) => {
    for (const control of form.elements) {
      if (control.name)
        control.value =
          url.searchParams.get(control.name) ||
          control.dataset.defaultValue ||
          "";
    }
  };
  const rollbackHistory = () => {
    if (location.href === appliedURL.href) return;
    const current = indexOf(history.state);
    if (current !== null && current !== appliedIndex) {
      restoring = true;
      history.go(appliedIndex - current);
    } else {
      history.replaceState(stateFor(appliedIndex), "", appliedURL);
    }
  };
  const feedback = document.createElement("div");
  feedback.className = "workspace-feedback";
  feedback.hidden = true;
  const message = document.createElement("p");
  const retry = document.createElement("button");
  retry.type = "button";
  retry.className = "button button-secondary button-sm";
  retry.textContent = "Reintentar actualización";
  feedback.append(message, retry);
  scope.prepend(feedback);
  const status = $("[data-live-status]");
  const showFeedback = (text, error = false) => {
    message.setAttribute("role", error ? "alert" : "status");
    message.textContent = text;
    feedback.classList.toggle("is-error", error);
    feedback.hidden = false;
    retry.hidden = !failed;
    if (status) status.textContent = "";
  };
  const stopPending = () => {
    const previous = controller;
    controller = null;
    previous?.abort();
    scope.removeAttribute("aria-busy");
  };
  const update = async (value, push = true) => {
    const url = safeURL(value);
    if (!url || restoring) return;
    stopPending();
    if (
      $('[data-dirty="true"]') &&
      !confirm(
        "Tienes cambios sin guardar. ¿Quieres descartarlos y actualizar la lista?",
      )
    ) {
      restoreFilters(appliedURL);
      rollbackHistory();
      return;
    }
    restoreFilters(url);
    const focusResults = document.activeElement === retry;
    const requestController = new AbortController();
    controller = requestController;
    const revision = editRevision;
    let timedOut = false;
    const timeout = setTimeout(() => {
      timedOut = true;
      requestController.abort();
    }, 15000);
    feedback.hidden = true;
    scope.setAttribute("aria-busy", "true");
    if (status) status.textContent = "Actualizando resultados…";
    try {
      const response = await fetch(url, {
        credentials: "same-origin",
        cache: "no-store",
        signal: requestController.signal,
        headers: { "X-Workspace-Fragment": "1" },
      });
      if (requestController !== controller) return;
      if (response.redirected && new URL(response.url).pathname === "/login/") {
        location.assign(response.url);
        return;
      }
      if (!response.ok) throw new Error();
      const html = new DOMParser().parseFromString(
        await response.text(),
        "text/html",
      );
      if (requestController !== controller || revision !== editRevision) return;
      const pairs = $$("[data-live-region]").map((current) => [
        current,
        html.querySelector(
          `[data-live-region="${current.dataset.liveRegion}"]`,
        ),
      ]);
      if (!pairs.length || pairs.some(([, next]) => !next)) throw new Error();
      const focused =
        pairs.find(([current]) =>
          current.contains(document.activeElement),
        )?.[1] || (focusResults ? pairs[0][1] : null);
      // Retirar un campo enfocado puede emitir change; ese evento pertenece a la edición ya confirmada.
      applying = true;
      try {
        pairs.forEach(([current, next]) => current.replaceWith(next));
      } finally {
        applying = false;
      }
      if (push && url.href !== appliedURL.href) {
        appliedIndex++;
        history.pushState(stateFor(appliedIndex), "", url);
      } else if (!push) {
        const target = indexOf(history.state);
        if (target !== null) appliedIndex = target;
        else {
          appliedIndex = 0;
          history.replaceState(stateFor(0), "", url);
        }
      }
      appliedURL = url;
      failed = null;
      if (status) status.textContent = "Resultados actualizados.";
      document.dispatchEvent(
        new CustomEvent("workspace:updated", { detail: { scope } }),
      );
      if (focused) {
        focused.tabIndex = -1;
        focused.focus({ preventScroll: true });
        focused.scrollIntoView({ block: "start" });
      }
    } catch (error) {
      if (
        requestController !== controller ||
        (error.name === "AbortError" && !timedOut)
      )
        return;
      failed = { url, index: push ? null : indexOf(history.state) };
      restoreFilters(appliedURL);
      rollbackHistory();
      showFeedback(
        timedOut
          ? "La actualización tardó demasiado. Conservamos los resultados anteriores."
          : "No se pudo actualizar la lista. Conservamos los resultados anteriores.",
        true,
      );
      if (focusResults) retry.focus();
    } finally {
      clearTimeout(timeout);
      if (requestController === controller) {
        controller = null;
        scope.removeAttribute("aria-busy");
      }
    }
  };
  retry.addEventListener("click", () => {
    if (!failed || restoring) return;
    if (failed.index !== null && failed.index !== appliedIndex)
      history.go(failed.index - appliedIndex);
    else update(failed.url);
  });
  const submit = () => {
    const url = new URL(form.action || location.href);
    url.search = new URLSearchParams(new FormData(form)).toString();
    update(url);
  };
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    clearTimeout(timer);
    submit();
  });
  form.addEventListener("input", (event) => {
    if (!event.target.matches("[data-live-input]")) return;
    clearTimeout(timer);
    if ($('[data-dirty="true"]')) {
      failed = null;
      showFeedback(
        "Hay cambios sin guardar. Usa el botón de filtros para cambiar la lista.",
      );
      return;
    }
    timer = setTimeout(submit, 400);
  });
  form.addEventListener("change", (event) => {
    if (event.target.matches("select, input[type=month], input[type=date]")) {
      clearTimeout(timer);
      submit();
    }
  });
  scope.addEventListener("click", (event) => {
    const link = event.target.closest("[data-live-link]");
    if (
      !link ||
      event.ctrlKey ||
      event.metaKey ||
      event.shiftKey ||
      event.altKey ||
      event.button
    )
      return;
    const url = safeURL(link.href);
    if (!url) return;
    event.preventDefault();
    clearTimeout(timer);
    update(url);
  });
  const trackEdit = (event) => {
    if (applying) return;
    const dirtyForm = event.target.closest(
      "[data-account-actions], [data-observation-form]",
    );
    if (!dirtyForm) return;
    const dirty = dirtyForm.matches("[data-account-actions]")
      ? $$("select[name^=role_]", dirtyForm).some(
          (field) => field.value !== "__keep__",
        )
      : $$("textarea", dirtyForm).some(
          (field) => field.value !== field.defaultValue,
        );
    dirtyForm.dataset.dirty = String(dirty);
    editRevision++;
    clearTimeout(timer);
    if (controller) {
      stopPending();
      restoreFilters(appliedURL);
      rollbackHistory();
      failed = null;
      showFeedback("La actualización se detuvo para conservar tu edición.");
    }
  };
  scope.addEventListener("input", trackEdit);
  scope.addEventListener("change", trackEdit);
  window.addEventListener("popstate", (event) => {
    clearTimeout(timer);
    if (restoring) {
      restoring = false;
      restoreFilters(appliedURL);
      return;
    }
    update(location.href, false);
  });
  window.addEventListener("pagehide", () => {
    clearTimeout(timer);
    stopPending();
  });
  window.addEventListener("beforeunload", (event) => {
    if ($('[data-dirty="true"]')) {
      event.preventDefault();
      event.returnValue = "";
    }
  });
  document.addEventListener("submit", (event) => {
    if (
      event.target.matches("[data-account-actions]") &&
      !event.defaultPrevented
    )
      delete event.target.dataset.dirty;
  });
})();

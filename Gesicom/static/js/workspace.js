"use strict";
(() => {
  const $ = (s, root = document) => root.querySelector(s);
  const $$ = (s, root = document) => [...root.querySelectorAll(s)];
  const notify = (message) => {
    const item = document.createElement("div");
    item.className = "toast is-error";
    item.setAttribute("role", "alert");
    item.textContent = message;
    $("#toast-region")?.append(item);
    setTimeout(() => item.remove(), 6500);
  };
  const safeURL = (value) => {
    const url = new URL(value, location.origin);
    return url.origin === location.origin && /^https?:$/.test(url.protocol) ? url : null;
  };
  const expiredSession = (response) => {
    if (response.redirected && new URL(response.url).pathname === "/login/") {
      location.assign(response.url);
      return true;
    }
    return false;
  };
  const dialog = $("#command-dialog");
  const trigger = $("#global-search");
  if (dialog && trigger && typeof dialog.showModal === "function") {
    const query = $("#command-query"),
      list = $("#command-results"),
      status = $("#command-status");
    const actions = JSON.parse($("#workspace-actions").textContent);
    let active = -1,
      timer, controller, generation = 0;
    const normalize = (value) => value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase(
      "es");
    const select = (index) => {
      const items = $$("[role=option]", list);
      active = items.length ? (index + items.length) % items.length : -1;
      items.forEach((item, i) => item.setAttribute("aria-selected", String(i === active)));
      if (active >= 0) {
        query.setAttribute("aria-activedescendant", items[active].id);
        items[active].scrollIntoView({
          block: "nearest"
        });
      } else query.removeAttribute("aria-activedescendant");
    };
    const render = (items) => {
      list.replaceChildren();
      active = -1;
      query.removeAttribute("aria-activedescendant");
      items.forEach((item, index) => {
        const url = safeURL(item.url);
        if (!url) return;
        const link = document.createElement("a");
        link.href = url.href;
        link.id = `command-option-${index}`;
        link.className = "command-option";
        link.setAttribute("role", "option");
        link.setAttribute("aria-selected", "false");
        link.tabIndex = -1;
        const symbol = document.createElement("span");
        symbol.className = "command-result-symbol";
        symbol.textContent = item.tipo ? item.tipo.slice(0, 1) : "↗";
        const text = document.createElement("span"),
          title = document.createElement("strong"),
          detail = document.createElement("small");
        title.textContent = item.titulo;
        detail.textContent = item.detalle;
        text.append(title, detail);
        link.append(symbol, text);
        link.addEventListener("pointermove", () => select(index));
        list.append(link);
      });
    };
    const search = async () => {
      controller?.abort();
      const ownGeneration = ++generation;
      const value = query.value.trim(),
        term = normalize(value);
      const shortcuts = actions.filter((item) => normalize(item.titulo).includes(term)).slice(0, 8);
      render(shortcuts);
      if (value.length < 2) {
        status.textContent = value ? "Escribe al menos 2 caracteres para buscar registros." :
          "Accesos rápidos · también puedes escribir para buscar";
        return;
      }
      status.textContent = "Buscando en tu espacio…";
      controller = new AbortController();
      try {
        const url = new URL(dialog.dataset.searchUrl, location.origin);
        url.searchParams.set("q", value);
        const response = await fetch(url, {
          credentials: "same-origin",
          cache: "no-store",
          signal: controller.signal
        });
        const result = await response.json();
        if (ownGeneration !== generation || !dialog.open) return;
        if (response.status === 401) {
          const login = safeURL(result.login_url || "/login/");
          if (login) location.assign(login.href);
          return;
        }
        if (!response.ok) throw new Error(result.error || "No se pudo completar la búsqueda.");
        const items = [...shortcuts, ...result.resultados];
        render(items);
        status.textContent = items.length ?
          `${items.length} resultados · usa las flechas para navegar` :
          "No encontramos resultados. Prueba con otro nombre.";
      } catch (error) {
        if (error.name !== "AbortError" && ownGeneration === generation) status.textContent = error
          .message;
      }
    };
    trigger.hidden = false;
    trigger.addEventListener("click", () => {
      if (dialog.open) return;
      dialog.showModal();
      query.value = "";
      query.focus();
      search();
    });
    $("[data-command-close]", dialog).addEventListener("click", () => dialog.close());
    dialog.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        dialog.close();
      }
    });
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) dialog.close();
    });
    dialog.addEventListener("close", () => {
      clearTimeout(timer);
      controller?.abort();
      generation++;
      trigger.focus();
    });
    query.addEventListener("input", () => {
      clearTimeout(timer);
      controller?.abort();
      generation++;
      render([]);
      status.textContent = "Preparando búsqueda…";
      query.removeAttribute("aria-activedescendant");
      timer = setTimeout(search, 280);
    });
    query.addEventListener("keydown", (event) => {
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        const last = $$("[role=option]", list).length - 1;
        select(active < 0 ? (event.key === "ArrowDown" ? 0 : last) : active + (event.key ===
          "ArrowDown" ? 1 : -1));
      } else if (event.key === "Enter") {
        event.preventDefault();
        const items = $$("[role=option]", list);
        (items[active] || items[0])?.click();
      }
    });
    document.addEventListener("keydown", (event) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        dialog.open ? dialog.close() : trigger.click();
      }
    });
  }

  // Progressive enhancement: the existing GET views remain the single source of table contents.
  $$("[data-live-scope]").forEach((scope) => {
    const form = $("[data-live-form]", scope);
    if (!form) return;
    let controller, timer;
    const restoreFilters = (url) => {
      for (const control of form.elements) {
        if (control.name) control.value = url.searchParams.get(control.name) || control.dataset
          .defaultValue || "";
      }
    };
    const update = async (url, push = true) => {
      if (!safeURL(url.href) || url.pathname !== location.pathname) return;
      if ($('[data-dirty="true"]', scope) && !confirm(
          "Tienes cambios sin guardar. ¿Quieres descartarlos y actualizar la lista?")) {
        restoreFilters(new URL(location.href));
        return;
      }
      controller?.abort();
      const requestController = new AbortController();
      controller = requestController;
      scope.setAttribute("aria-busy", "true");
      try {
        const response = await fetch(url, {
          credentials: "same-origin",
          cache: "no-store",
          signal: controller.signal
        });
        if (expiredSession(response)) return;
        if (!response.ok) throw new Error("No se pudo actualizar la lista. Intenta de nuevo.");
        const html = new DOMParser().parseFromString(await response.text(), "text/html");
        if (requestController !== controller) return;
        const pairs = $$("[data-live-region]", scope).map((current) => [current, $(
          `[data-live-region="${current.dataset.liveRegion}"]`, html)]);
        if (!pairs.length || pairs.some(([, next]) => !next)) throw new Error(
          "Recarga la página para continuar.");
        pairs.forEach(([current, next]) => current.replaceWith(next));
        if (push) history.pushState({}, "", url);
        $("[data-live-status]", scope).textContent = "Resultados actualizados.";
        document.dispatchEvent(new CustomEvent("workspace:updated", {
          detail: {
            scope
          }
        }));
      } catch (error) {
        if (error.name !== "AbortError") notify(error.message);
      } finally {
        if (controller === requestController) scope.removeAttribute("aria-busy");
      }
    };
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
      timer = setTimeout(submit, 400);
    });
    form.addEventListener("change", (event) => {
      if (event.target.matches("select, input[type=month]")) {
        clearTimeout(timer);
        submit();
      }
    });
    scope.addEventListener("click", (event) => {
      const link = event.target.closest("[data-live-link]");
      if (!link || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || event.button)
        return;
      const url = safeURL(link.href);
      if (!url || url.pathname !== location.pathname) return;
      event.preventDefault();
      clearTimeout(timer);
      restoreFilters(url);
      update(url);
    });
    scope.addEventListener("input", (event) => {
      const dirtyForm = event.target.closest("[data-account-actions], [data-observation-form]");
      if (!dirtyForm) return;
      const dirty = dirtyForm.matches("[data-account-actions]") ?
        $$("select[name^=role_]", dirtyForm).some((select) => select.value !== "__keep__") :
        $$("textarea", dirtyForm).some((input) => input.value !== input.defaultValue);
      dirtyForm.dataset.dirty = String(dirty);
    });
    window.addEventListener("popstate", () => {
      clearTimeout(timer);
      const url = new URL(location.href);
      restoreFilters(url);
      update(url, false);
    });
  });

  const refreshSelection = (form) => {
    const controls = $$("input[name=usuarios]:not(:disabled)", form);
    const count = controls.filter((input) => input.checked).length;
    $("[data-selection-count]", form).textContent = `${count} seleccionada${count === 1 ? "" : "s"}`;
    const all = $("[data-select-all]", form);
    all.checked = count > 0 && count === controls.length;
    all.indeterminate = count > 0 && count < controls.length;
    all.disabled = !controls.length;
    $$("[data-selection-action]", form).forEach((button) => {
      button.disabled = !count;
    });
  };
  const initialize = () => $$("[data-account-actions]").forEach(refreshSelection);
  initialize();
  document.addEventListener("workspace:updated", initialize);
  document.addEventListener("change", (event) => {
    const form = event.target.closest("[data-account-actions]");
    if (!form) return;
    if (event.target.matches("[data-select-all]")) {
      $$("input[name=usuarios]:not(:disabled)", form).forEach((input) => {
        input.checked = event.target.checked;
      });
    }
    refreshSelection(form);
  });
  const refreshNotices = () => {
    const form = $("[data-notice-selection]");
    if (!form) return;
    const controls = [...form.elements].filter((el) => el.name === "avisos");
    const count = controls.filter((el) => el.checked).length;
    $("[data-notice-count]", form).textContent = `${count} seleccionados`;
    const all = $("[data-notice-all]", form);
    all.checked = count > 0 && count === controls.length;
    all.indeterminate = count > 0 && count < controls.length;
    $$("[data-notice-action]", form).forEach((button) => { button.disabled = !count; });
  };
  refreshNotices();
  document.addEventListener("workspace:updated", refreshNotices);
  document.addEventListener("change", (event) => {
    if (event.target.matches("[data-notice-all]")) {
      [...event.target.form.elements].filter((el) => el.name === "avisos").forEach((el) => {
        el.checked = event.target.checked;
      });
    }
    if (event.target.matches("[data-notice-all], input[name=avisos]")) refreshNotices();
  });
  const permissionForm = $("[data-permission-editor]");
  if (permissionForm) {
    const choices = $$("select[name^=perm_]", permissionForm);
    const initial = new Map(choices.map((field) => [field.name, field.value]));
    permissionForm.addEventListener("change", () => {
      const count = choices.filter((field) => field.value !== initial.get(field.name)).length;
      $("[data-permission-status]", permissionForm).textContent = count ?
        `${count} cambio(s) por guardar. Se aplicarán a todo el grupo.` : "Los permisos no tienen cambios.";
    });
  }
  const confirmation = $("#account-confirm");
  const approved = new WeakSet();
  let pending;
  document.addEventListener("submit", (event) => {
    const form = event.target.closest("[data-account-actions]");
    if (!form || !confirmation || !confirmation.showModal) return;
    if (approved.has(form)) {
      approved.delete(form);
      delete form.dataset.dirty;
      return;
    }
    event.preventDefault();
    const button = event.submitter;
    const action = button?.value || "roles";
    const count = action === "roles" ?
      $$("select[name^=role_]", form).filter((input) => input.value !== "__keep__").length :
      $$("input[name=usuarios]:checked", form).length;
    if (!count) {
      notify(action === "roles" ? "Selecciona al menos un cambio de rol." :
        "Selecciona al menos una cuenta.");
      return;
    }
    pending = {
      form,
      button
    };
    $("[data-confirm-description]", confirmation).textContent = action === "roles" ?
      `Vas a actualizar los roles de ${count} cuenta(s). Los roles elegidos sustituirán los actuales.` :
      `Vas a ${action} ${count} cuenta(s).`;
    confirmation.showModal();
    $("[data-account-cancel]", confirmation).focus();
  });
  if (confirmation) {
    $("[data-account-cancel]", confirmation).addEventListener("click", () => confirmation.close());
    $("[data-account-accept]", confirmation).addEventListener("click", () => {
      const {
        form,
        button
      } = pending;
      approved.add(form);
      confirmation.close("accepted");
      form.requestSubmit(button);
    });
    confirmation.addEventListener("close", () => {
      if (confirmation.returnValue !== "accepted" && pending) $("[name=contrasena_actual]", pending
        .form).value = "";
      confirmation.returnValue = "";
      pending = null;
    });
  }
})();

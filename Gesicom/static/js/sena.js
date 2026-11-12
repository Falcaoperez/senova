"use strict";
(() => {
  const $ = (s, root = document) => root.querySelector(s);
  const $$ = (s, root = document) => [...root.querySelectorAll(s)];
  const toast = (message, error = false) => {
    const region = $("#toast-region");
    if (!region) return;
    const item = document.createElement("div");
    item.className = "toast" + (error ? " is-error" : "");
    item.textContent = message;
    item.setAttribute("role", error ? "alert" : "status");
    region.appendChild(item);
    setTimeout(() => item.remove(), 6500);
  };
  const toggle = $("[data-nav-toggle]"),
    sidebar = $("#main-navigation");
  const mobile = matchMedia("(max-width: 800px)");
  const setNav = (open) => {
    if (!toggle || !sidebar) return;
    document.body.classList.toggle("nav-open", open);
    toggle.setAttribute("aria-expanded", String(open));
    toggle.setAttribute(
      "aria-label",
      open ? "Cerrar menú de navegación" : "Abrir menú de navegación",
    );
    sidebar.inert = mobile.matches && !open;
    if (open) $("a, button", sidebar)?.focus();
    else if (sidebar.contains(document.activeElement)) toggle.focus();
  };
  if (sidebar) {
    sidebar.inert = mobile.matches;
    mobile.addEventListener("change", () => setNav(false));
    toggle?.addEventListener("click", () =>
      setNav(!document.body.classList.contains("nav-open")),
    );
    $$("[data-nav-close]").forEach((el) =>
      el.addEventListener("click", () => setNav(false)),
    );
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        setNav(false);
        $$("details[open]").forEach((el) => (el.open = false));
      }
      if (
        event.key === "Tab" &&
        mobile.matches &&
        document.body.classList.contains("nav-open")
      ) {
        const controls = $$("a,button", sidebar),
          first = controls[0],
          last = controls.at(-1);
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        }
        if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
      if (
        event.key === "/" &&
        !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName) &&
        !document.activeElement.isContentEditable
      ) {
        const search = $("#global-search");
        if (search) {
          event.preventDefault();
          search.click();
        }
      }
    });
  }
  document.addEventListener("click", (event) => {
    $$("details.account-menu[open]").forEach((el) => {
      if (!el.contains(event.target)) el.open = false;
    });
  });
  $$("[data-dismiss]").forEach((button) =>
    button.addEventListener("click", () => button.closest(".alert").remove()),
  );
  $$("[data-password-toggle]").forEach((button) =>
    button.addEventListener("click", () => {
      const input = document.getElementById(button.dataset.passwordToggle);
      if (!input) return;
      const visible = input.type === "password";
      input.type = visible ? "text" : "password";
      button.setAttribute("aria-pressed", String(visible));
      button.setAttribute(
        "aria-label",
        visible ? "Ocultar contraseña" : "Mostrar contraseña",
      );
    }),
  );
  $$("[data-password-strength]").forEach((input) =>
    input.addEventListener("input", () => {
      const meter = $(".password-meter span", input.closest(".field"));
      if (!meter) return;
      const value = input.value;
      const score = [
        value.length >= 8,
        value.length >= 12,
        /[0-9]/.test(value),
        /[^a-zA-Z0-9]/.test(value),
      ].filter(Boolean).length;
      meter.style.width = (value ? Math.max(1, score) * 25 : 0) + "%";
      meter.style.background = score < 2 ? "#bf7b29" : "#39a900";
    }),
  );
  $$("[data-confirm-password]").forEach((input) => {
    const original = document.getElementById(input.dataset.confirmPassword);
    const validate = () =>
      input.setCustomValidity(
        input.value && input.value !== original?.value
          ? "Las contraseñas no coinciden."
          : "",
      );
    input.addEventListener("input", validate);
    original?.addEventListener("input", validate);
  });
  $$("[data-dropzone]").forEach((zone) => {
    const input = $("[data-file-input]", zone),
      label = $("[data-file-label]", zone);
    const selection = $("[data-upload-selection]", zone),
      image = $("[data-upload-image]", zone);
    const status = $("[data-upload-message]", zone),
      clear = $("[data-file-clear]", zone);
    const allowed = input.accept
      .toLowerCase()
      .split(",")
      .map((value) => value.trim());
    let reader,
      generation = 0;
    const update = () => {
      reader?.abort();
      const ownGeneration = ++generation,
        file = input.files?.[0];
      if (image) {
        image.hidden = true;
        image.removeAttribute("src");
      }
      if (selection) selection.hidden = !file;
      let error = "";
      if (file) {
        const extension = "." + file.name.split(".").pop().toLowerCase();
        if (!allowed.includes(extension))
          error =
            "Este formato no está permitido. Selecciona un documento, imagen o comprimido compatible.";
        else if (!file.size)
          error = "El archivo está vacío. Selecciona uno con contenido.";
        else if (file.size > Number(input.dataset.maxBytes || 10485760))
          error = "El archivo supera el límite de 10 MB.";
      }
      input.setCustomValidity(error);
      zone.classList.toggle("is-invalid", Boolean(error));
      const unit =
        !file || file.size < 1024 ? 1 : file.size < 1048576 ? 1024 : 1048576;
      const suffix = unit === 1 ? "B" : unit === 1024 ? "KB" : "MB";
      label.textContent = file
        ? `${file.name} · ${new Intl.NumberFormat("es-CO", { maximumFractionDigits: 1 }).format(file.size / unit)} ${suffix}`
        : "";
      if (status)
        status.textContent =
          error ||
          (file ? "Selección lista. El formato se verificará al guardar." : "");
      if (!error && file && image && /\.(jpe?g|png)$/i.test(file.name)) {
        reader = new FileReader();
        reader.addEventListener("load", () => {
          if (generation !== ownGeneration) return;
          image.src = reader.result;
          image.hidden = false;
        });
        image.onerror = () => {
          if (generation !== ownGeneration) return;
          image.hidden = true;
          if (status)
            status.textContent =
              "No se pudo generar una vista previa. El formato se verificará al guardar.";
        };
        reader.readAsDataURL(file);
      }
    };
    input.addEventListener("change", update);
    clear?.addEventListener("click", () => {
      input.value = "";
      input.dispatchEvent(new Event("change", { bubbles: true }));
      input.focus();
    });
    ["dragenter", "dragover"].forEach((type) =>
      zone.addEventListener(type, (event) => {
        event.preventDefault();
        zone.classList.add("is-dragging");
      }),
    );
    ["dragleave", "drop"].forEach((type) =>
      zone.addEventListener(type, (event) => {
        event.preventDefault();
        zone.classList.remove("is-dragging");
      }),
    );
    zone.addEventListener("drop", (event) => {
      const files = event.dataTransfer?.files;
      if (!files?.length) return;
      if (files.length !== 1) {
        input.setCustomValidity("Selecciona un solo archivo por evidencia.");
        zone.classList.add("is-invalid");
        if (selection) selection.hidden = false;
        if (status)
          status.textContent =
            "Solo se puede adjuntar un archivo. Selecciona uno o reúne los documentos en un comprimido.";
        return;
      }
      const transfer = new DataTransfer();
      transfer.items.add(files[0]);
      input.files = transfer.files;
      input.dispatchEvent(new Event("change", { bubbles: true }));
    });
  });
  const errorSummary = $("[data-error-summary]");
  errorSummary?.focus();
  $$("[data-submit]").forEach((form) =>
    form.addEventListener("submit", () => {
      const button = $("button[type=submit]", form);
      if (button) {
        button.disabled = true;
        button.textContent = "Guardando…";
      }
    }),
  );
  document.addEventListener("submit", async (event) => {
    const form = event.target.closest(
      "[data-remote-form], [data-observation-form]",
    );
    if (!form) return;
    event.preventDefault();
    const button = $("button[type=submit]", form),
      error = $("[data-form-error]", form);
    if (error) error.hidden = true;
    if (button) {
      button.disabled = true;
      button.setAttribute("aria-busy", "true");
    }
    try {
      const response = await fetch(form.action, {
        method: "POST",
        body: new FormData(form),
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      const result = await response.json().catch(() => {
        throw new Error(
          "No se pudo procesar la respuesta. Recarga la página e intenta de nuevo.",
        );
      });
      if (response.status === 401 && result.login_url) {
        const login = new URL(result.login_url, location.origin);
        if (login.origin === location.origin) {
          location.assign(login);
          return;
        }
      }
      if (!response.ok || result.error)
        throw new Error(result.error || "No se pudo guardar el cambio.");
      if (form.hasAttribute("data-observation-form")) {
        form.dataset.dirty = "false";
        $$("textarea", form).forEach((input) => {
          input.defaultValue = input.value;
        });
        if (Number.isInteger(result.version)) {
          $$(
            "input[name=version]",
            form.closest("[data-evidence-record]") || form,
          ).forEach((input) => {
            input.value = String(result.version);
          });
        }
        toast("Observaciones guardadas correctamente.");
      } else {
        const target = new URL(form.dataset.redirect, location.origin);
        if (form.hasAttribute("data-email-redirect"))
          target.searchParams.set("email", new FormData(form).get("email"));
        location.assign(target);
      }
    } catch (exception) {
      const message =
        exception.message ||
        "No se pudo establecer conexión. Intenta nuevamente.";
      if (error) {
        error.textContent = message;
        error.hidden = false;
      } else toast(message, true);
    } finally {
      if (button) {
        button.disabled = false;
        button.removeAttribute("aria-busy");
      }
    }
  });
  $$("[data-tabs]").forEach((group) => {
    const tabs = $$("[role=tab]", group);
    const activate = (tab, focus = false) => {
      tabs.forEach((t) => {
        const active = t === tab;
        t.setAttribute("aria-selected", String(active));
        t.tabIndex = active ? 0 : -1;
        const panel = document.getElementById(t.getAttribute("aria-controls"));
        if (panel) panel.hidden = !active;
      });
      if (focus) tab.focus();
    };
    tabs.forEach((tab, index) => {
      tab.addEventListener("click", () => activate(tab));
      tab.addEventListener("keydown", (event) => {
        let next = index;
        if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
        else if (event.key === "ArrowLeft")
          next = (index - 1 + tabs.length) % tabs.length;
        else if (event.key === "Home") next = 0;
        else if (event.key === "End") next = tabs.length - 1;
        else return;
        event.preventDefault();
        activate(tabs[next], true);
      });
    });
    activate(tabs[0]);
  });
  $$("[data-local-search]").forEach((input) =>
    input.addEventListener("input", () => {
      const target = document.getElementById(input.dataset.localSearch);
      if (!target) return;
      const query = input.value.toLocaleLowerCase("es");
      $$("tbody tr", target).forEach(
        (row) =>
          (row.hidden = !row.textContent
            .toLocaleLowerCase("es")
            .includes(query)),
      );
    }),
  );
  $$("[data-confirm]").forEach((form) =>
    form.addEventListener("submit", (event) => {
      if (!confirm(form.dataset.confirm)) event.preventDefault();
    }),
  );
  $$("[data-print]").forEach((button) =>
    button.addEventListener("click", () => window.print()),
  );
  $$("[data-text-preview]").forEach(async (pre) => {
    const note = $("[data-text-status]", pre.closest(".text-preview-wrap"));
    pre.textContent = "Cargando la vista de texto…";
    try {
      const response = await fetch(pre.dataset.textPreview, {
        credentials: "same-origin",
        cache: "no-store",
      });
      if (!response.ok) throw new Error();
      pre.textContent = await response.text();
      if (note)
        note.textContent =
          response.headers.get("X-Preview-Truncated") === "1"
            ? "Se muestran los primeros 64 KB. Descarga el archivo para consultar el contenido completo."
            : "Vista del contenido de texto.";
    } catch {
      pre.textContent =
        "No se pudo cargar la vista previa. Intenta de nuevo o consulta el archivo desde su descarga.";
      if (note) note.textContent = "Vista previa no disponible.";
    }
  });
  window.addEventListener("pageshow", (event) => {
    if (event.persisted)
      $$("[data-submit] button:disabled").forEach((button) => {
        button.disabled = false;
        location.reload();
      });
  });
})();
// La bandeja se actualiza sin recargar ni multiplicar consultas por segundo.
(() => {
  const menu = document.querySelector("[data-notifications-summary]");
  if (menu) {
    const update = async () => {
      if (document.hidden) return;
      try {
        const response = await fetch(menu.dataset.notificationsSummary, {
          credentials: "same-origin",
          headers: { Accept: "application/json" },
        });
        if (response.status === 401) {
          const data = await response.json();
          const login = data.login_url || "/login/";
          location.assign(
            login.startsWith("/") && !login.startsWith("//")
              ? login
              : "/login/",
          );
          return;
        }
        if (!response.ok) return;
        const data = await response.json();
        document.querySelectorAll("[data-unread-count]").forEach((el) => {
          el.textContent = data.pendientes;
          el.hidden = !data.pendientes;
        });
      } catch {
        /* La navegación sigue disponible si la conexión se interrumpe. */
      }
    };
    setInterval(update, 45000);
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) update();
    });
    menu.addEventListener("toggle", () => {
      if (menu.open) update();
    });
    document.addEventListener("click", (e) => {
      if (!menu.contains(e.target)) menu.open = false;
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") menu.open = false;
    });
  }
  const expiry = document.querySelector("[data-pin-expiry]");
  if (expiry) {
    const deadline = Date.parse(expiry.dataset.pinExpiry);
    const tick = () => {
      const seconds = Math.max(0, Math.floor((deadline - Date.now()) / 1000));
      expiry.textContent = seconds
        ? `El PIN caduca en ${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}.`
        : "El PIN ha caducado. Solicita uno nuevo.";
    };
    if (Number.isFinite(deadline)) {
      tick();
      setInterval(tick, 1000);
    }
  }
})();

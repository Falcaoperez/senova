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
          search.focus();
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
    const update = () => {
      const file = input.files?.[0];
      input.setCustomValidity(
        file && file.size > 10 * 1024 * 1024
          ? "El archivo supera el límite de 10 MB."
          : "",
      );
      label.textContent = file
        ? `${file.name} · ${(file.size / 1024 / 1024).toFixed(2)} MB`
        : "";
      if (file && file.size > 10 * 1024 * 1024) input.reportValidity();
    };
    input.addEventListener("change", update);
    ["dragenter", "dragover"].forEach((type) =>
      zone.addEventListener(type, (e) => {
        e.preventDefault();
        zone.classList.add("is-dragging");
      }),
    );
    ["dragleave", "drop"].forEach((type) =>
      zone.addEventListener(type, (e) => {
        e.preventDefault();
        zone.classList.remove("is-dragging");
      }),
    );
    zone.addEventListener("drop", (event) => {
      if (event.dataTransfer.files.length) {
        const transfer = new DataTransfer();
        transfer.items.add(event.dataTransfer.files[0]);
        input.files = transfer.files;
        update();
      }
    });
  });
  $$("[data-submit]").forEach((form) =>
    form.addEventListener("submit", () => {
      const button = $("button[type=submit]", form);
      if (button) {
        button.disabled = true;
        button.textContent = "Guardando…";
      }
    }),
  );
  $$("[data-remote-form], [data-observation-form]").forEach((form) =>
    form.addEventListener("submit", async (event) => {
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
        if (!response.ok || result.error)
          throw new Error(result.error || "No se pudo guardar el cambio.");
        if (form.hasAttribute("data-observation-form"))
          toast("Observaciones guardadas correctamente.");
        else {
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
    }),
  );
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
    try {
      const response = await fetch(pre.dataset.textPreview);
      if (!response.ok) throw new Error();
      pre.textContent = await response.text();
    } catch {
      pre.textContent =
        "No se pudo cargar la vista previa. Descarga el archivo para consultarlo.";
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
          location.assign(login.startsWith("/") && !login.startsWith("//") ? login : "/login/");
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

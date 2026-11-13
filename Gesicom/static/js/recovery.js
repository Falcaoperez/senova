/* Recuperación progresiva: cada envío sensible requiere una acción explícita. */
(() => {
  const form = document.querySelector("[data-recovery-form]");
  if (!form || !window.fetch || !window.AbortController) return;
  const button = form.querySelector("button[type=submit]");
  const label = form.querySelector("[data-recovery-label]");
  const originalLabel = label.textContent;
  const error = form.querySelector("[data-form-error]");
  const status = form.querySelector("[data-recovery-status]");
  const uncertainPanel = form.querySelector("[data-recovery-uncertain]");
  const wait = form.querySelector("[data-recovery-wait]");
  const expiry = form.querySelector("[data-pin-expiry]");
  const deadline = expiry ? Date.parse(expiry.dataset.pinExpiry) : NaN;
  const fields = [...form.querySelectorAll("input:not([type=hidden])")];
  const previousReadonly = new Map(
    fields.map((field) => [field, field.readOnly]),
  );
  let busy = false,
    uncertain = false,
    navigating = false,
    waitUntil = 0,
    timer,
    controller;

  const localURL = (value) => {
    const url = new URL(value, location.origin);
    if (url.origin !== location.origin || url.username || url.password)
      throw new Error("Destino no válido.");
    return url;
  };
  const displayError = (message) => {
    error.textContent = message;
    error.hidden = false;
    error.focus();
  };
  const update = () => {
    clearTimeout(timer);
    const remaining = Math.max(0, Math.ceil((waitUntil - Date.now()) / 1000));
    button.disabled = busy || uncertain || navigating || remaining > 0;
    button.setAttribute("aria-busy", String(busy));
    form.setAttribute("aria-busy", String(busy));
    label.textContent = busy ? form.dataset.pendingLabel : originalLabel;
    wait.hidden = remaining === 0;
    wait.textContent = remaining
      ? `Puedes volver a intentarlo en ${remaining} segundos.`
      : "";
    if (expiry && Number.isFinite(deadline)) {
      const seconds = Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
      expiry.textContent = seconds
        ? `El PIN caduca en ${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}.`
        : "El PIN ha caducado. Solicita uno nuevo.";
    }
    if (
      !document.hidden &&
      (remaining > 0 || (Number.isFinite(deadline) && deadline > Date.now()))
    )
      timer = setTimeout(update, 1000);
  };
  const clearSecrets = () => {
    fields
      .filter(
        (field) =>
          field.autocomplete === "new-password" || field.name === "codigo",
      )
      .forEach((field) => {
        field.value = "";
      });
  };
  const unconfirmed = () => {
    uncertain = true;
    uncertainPanel.hidden = false;
    displayError(
      form.dataset.recoveryStep === "password"
        ? "No pudimos confirmar la respuesta. Es posible que la contraseña ya se haya actualizado. Comprueba el inicio de sesión con la nueva contraseña."
        : "No pudimos confirmar la respuesta. Comprueba el siguiente paso antes de volver a solicitar o verificar un PIN.",
    );
    clearSecrets();
  };
  const retryDeadline = (value) => {
    if (!value) return 0;
    const seconds = /^\d+$/.test(value) ? Number(value) : NaN;
    const date = Number.isSafeInteger(seconds)
      ? Date.now() + seconds * 1000
      : Date.parse(value);
    return Number.isFinite(date) && date > Date.now() ? date : 0;
  };
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (
      busy ||
      uncertain ||
      navigating ||
      waitUntil > Date.now() ||
      !form.reportValidity()
    )
      return;
    if (!navigator.onLine) {
      displayError(
        "Estás sin conexión. Conéctate y vuelve a pulsar el botón; tus datos siguen en el formulario.",
      );
      return;
    }
    busy = true;
    error.hidden = true;
    status.textContent = form.dataset.pendingLabel;
    controller = new AbortController();
    const current = controller;
    const timeout = setTimeout(() => current.abort(), 15000);
    fields.forEach((field) => {
      field.readOnly = true;
    });
    update();
    try {
      const response = await fetch(localURL(form.action), {
        method: "POST",
        credentials: "same-origin",
        body: new FormData(form),
        headers: { Accept: "application/json" },
        signal: current.signal,
      });
      const result = await response.json();
      if (current.signal.aborted) throw new Error("Petición interrumpida.");
      if (!result || typeof result !== "object" || Array.isArray(result))
        throw new Error("Respuesta incompleta.");
      if (!response.ok || result.error) {
        if (
          response.status >= 500 ||
          typeof result.error !== "string" ||
          !result.error.trim()
        )
          throw new Error("Resultado no confirmado.");
        if (response.status === 429)
          waitUntil = retryDeadline(response.headers.get("Retry-After"));
        displayError(result.error);
        return;
      }
      if (typeof result.mensaje !== "string" || !result.mensaje.trim())
        throw new Error("Respuesta incompleta.");
      status.textContent = result.mensaje;
      navigating = true;
      location.assign(localURL(form.dataset.redirect));
    } catch {
      unconfirmed();
    } finally {
      clearTimeout(timeout);
      busy = false;
      fields.forEach((field) => {
        field.readOnly = previousReadonly.get(field);
      });
      status.textContent = "";
      update();
    }
  });
  form
    .querySelector("input[name=codigo]")
    ?.addEventListener("paste", (event) => {
      if (busy || uncertain) return;
      const code = event.clipboardData?.getData("text").replace(/[\s-]/g, "");
      if (/^[0-9]{6}$/.test(code || "")) {
        event.preventDefault();
        event.target.value = code;
        event.target.dispatchEvent(new Event("input", { bubbles: true }));
      }
    });
  document.addEventListener("visibilitychange", update);
  window.addEventListener("pagehide", () => {
    controller?.abort();
    clearTimeout(timer);
    clearSecrets();
  });
  window.addEventListener("pageshow", (event) => {
    if (event.persisted) location.replace(localURL(form.dataset.recoveryPage));
  });
  if (!error.hidden) error.focus();
  update();
})();

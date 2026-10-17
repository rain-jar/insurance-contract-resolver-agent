(() => {
  const fileInput = document.querySelector("[data-file-input]");
  const fileSummary = document.querySelector("[data-file-summary]");
  if (fileInput && fileSummary) {
    fileInput.addEventListener("change", () => {
      const count = fileInput.files.length;
      fileSummary.textContent = count ? `${count} file${count === 1 ? "" : "s"} selected` : "No files selected";
    });
  }

  document.querySelectorAll("[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (!window.confirm(form.dataset.confirm)) event.preventDefault();
    });
  });

  const processing = document.querySelector("[data-status-url]");
  if (processing) {
    const poll = async () => {
      try {
        const response = await fetch(processing.dataset.statusUrl, { headers: { Accept: "application/json" } });
        if (!response.ok) return;
        const state = await response.json();
        if (state.status === "COMPLETED" || state.status === "FAILED") {
          window.location.reload();
          return;
        }
      } catch (_) {
        // A transient local-server interruption is handled by the next poll.
      }
      window.setTimeout(poll, 1400);
    };
    window.setTimeout(poll, 900);
  }
})();

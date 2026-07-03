const resultEl = document.querySelector("#result");

function showResult(value) {
  resultEl.textContent = JSON.stringify(value, null, 2);
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(body.detail || response.statusText);
  }
  return body;
}

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    const mode = tab.dataset.mode;
    document.querySelectorAll(".tab").forEach((item) => item.classList.toggle("is-active", item === tab));
    document.querySelectorAll(".panel").forEach((panel) => {
      panel.classList.toggle("is-active", panel.dataset.panel === mode);
    });
  });
});

document.querySelector("#single-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const ip = document.querySelector("#single-ip").value.trim();
  const includeSources = document.querySelector("#single-sources").checked;
  try {
    showResult(await requestJson(`/v1/ip/${encodeURIComponent(ip)}?include_sources=${includeSources}`));
  } catch (error) {
    showResult({ error: error.message });
  }
});

document.querySelector("#batch-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const ips = document
    .querySelector("#batch-ips")
    .value.split(/\s+/)
    .map((item) => item.trim())
    .filter(Boolean);
  const includeSources = document.querySelector("#batch-sources").checked;
  try {
    showResult(
      await requestJson("/v1/ip/batch", {
        method: "POST",
        body: JSON.stringify({ ips, include_sources: includeSources }),
      }),
    );
  } catch (error) {
    showResult({ error: error.message });
  }
});

document.querySelector("#cidr-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const cidr = document.querySelector("#cidr-value").value.trim();
  try {
    showResult(await requestJson(`/v1/cidr/${encodeURIComponent(cidr)}`));
  } catch (error) {
    showResult({ error: error.message });
  }
});

document.querySelector("#copy-result").addEventListener("click", async () => {
  await navigator.clipboard.writeText(resultEl.textContent);
});

showResult({ ready: true, examples: ["8.8.8.8", "1.1.1.1", "2606:4700:4700::1111"] });


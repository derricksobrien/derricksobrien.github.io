const form = document.getElementById("booking-form");
const statusEl = document.getElementById("booking-status");
const apiBaseInput = document.getElementById("api-base");
const labSelect = document.getElementById("lab-select");

const accessForm = document.getElementById("access-form");
const accessApiBaseInput = document.getElementById("access-api-base");
const accessTokenInput = document.getElementById("access-token");
const accessStatus = document.getElementById("access-status");
const accessPanel = document.getElementById("access-panel");
const accessLabTitle = document.getElementById("access-lab-title");
const accessWindow = document.getElementById("access-window");
const accessInstructions = document.getElementById("access-instructions");
const accessLabRepo = document.getElementById("access-lab-repo");
const accessCatalogLink = document.getElementById("access-catalog-link");

const API_BASE_KEY = "nexetra_booking_api_base";

const LAB_QUERY_TO_LABEL = {
  anthropic: "Claude API in Action",
  nvidia: "GPU Inference Live",
  openclaw: "Inside the OpenClaw Cluster"
};

function getApiBaseValue() {
  if (!apiBaseInput) {
    return "";
  }
  return apiBaseInput.value.trim().replace(/\/$/, "");
}

function syncApiInputs(baseValue) {
  if (apiBaseInput) {
    apiBaseInput.value = baseValue;
  }
  if (accessApiBaseInput) {
    accessApiBaseInput.value = baseValue;
  }
}

function applyLabPreselection() {
  if (!labSelect) {
    return;
  }
  const query = new URLSearchParams(window.location.search);
  const requestedLab = (query.get("lab") || "").toLowerCase();
  const targetLabel = LAB_QUERY_TO_LABEL[requestedLab];
  if (!targetLabel) {
    return;
  }
  const targetOption = Array.from(labSelect.options).find((option) => option.text === targetLabel);
  if (targetOption) {
    labSelect.value = targetOption.value;
  }
}

function setStatus(el, state, message) {
  if (!el) {
    return;
  }
  el.dataset.state = state;
  el.textContent = message;
}

function renderAccessPanel(accessPayload) {
  if (!accessPanel || !accessLabTitle || !accessWindow || !accessInstructions || !accessLabRepo || !accessCatalogLink) {
    return;
  }

  accessLabTitle.textContent = `${accessPayload.labTitle} access ready`;
  accessWindow.textContent = `Token expires: ${accessPayload.expiresAtUtc}`;

  accessInstructions.innerHTML = "";
  (accessPayload.instructions || []).forEach((line) => {
    const li = document.createElement("li");
    li.textContent = line;
    accessInstructions.appendChild(li);
  });

  accessLabRepo.href = accessPayload.repoUrl || "#";
  accessCatalogLink.href = accessPayload.catalogPath || "../index.html";
  accessCatalogLink.textContent = accessPayload.catalogLabel || "Open related catalog path";

  accessPanel.style.display = "block";
}

function parseErrorResponse(response, fallback) {
  return response.json()
    .then((result) => result.error || fallback)
    .catch(() => fallback);
}

if (apiBaseInput) {
  const savedBase = window.localStorage.getItem(API_BASE_KEY) || "";
  if (savedBase) {
    syncApiInputs(savedBase);
  }
}

applyLabPreselection();

if (form) {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!statusEl) {
      return;
    }

    const submitButton = document.getElementById("booking-submit");
    const apiBase = getApiBaseValue();
    syncApiInputs(apiBase);
    window.localStorage.setItem(API_BASE_KEY, apiBase);

    if (!apiBase) {
      setStatus(statusEl, "error", "Enter your backend API endpoint first.");
      return;
    }

    const payload = {
      name: form.elements.name.value.trim(),
      email: form.elements.email.value.trim(),
      lab: form.elements.lab.value,
      timezone: form.elements.timezone.value.trim(),
      slot: form.elements.slot.value,
      goal: form.elements.goal.value.trim(),
      sourcePage: window.location.href
    };

    if (submitButton) {
      submitButton.disabled = true;
    }

    setStatus(statusEl, "", "Sending booking request...");

    try {
      const response = await fetch(`${apiBase}/api/bookings`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        credentials: "include",
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        const errorMessage = await parseErrorResponse(response, "Booking request failed.");
        throw new Error(errorMessage);
      }

      const result = await response.json();
      const tokenMessage = result.accessToken
        ? ` Access token: ${result.accessToken}`
        : "";
      setStatus(statusEl, "success", `Request captured. Booking ID: ${result.bookingId}.${tokenMessage}`);

      if (accessTokenInput && result.accessToken) {
        accessTokenInput.value = result.accessToken;
      }

      if (result.accessPath && accessApiBaseInput) {
        accessApiBaseInput.value = apiBase;
      }

      form.reset();
      syncApiInputs(apiBase);
      applyLabPreselection();
    } catch (error) {
      setStatus(statusEl, "error", error.message || "Something went wrong while sending your request.");
    } finally {
      if (submitButton) {
        submitButton.disabled = false;
      }
    }
  });
}

if (accessForm) {
  accessForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!accessApiBaseInput || !accessTokenInput || !accessStatus) {
      return;
    }

    const submitButton = document.getElementById("access-submit");
    const apiBase = accessApiBaseInput.value.trim().replace(/\/$/, "");
    const accessToken = accessTokenInput.value.trim();

    if (!apiBase || !accessToken) {
      setStatus(accessStatus, "error", "Enter both API endpoint and access token.");
      return;
    }

    syncApiInputs(apiBase);
    window.localStorage.setItem(API_BASE_KEY, apiBase);

    if (submitButton) {
      submitButton.disabled = true;
    }

    setStatus(accessStatus, "", "Checking access token...");

    try {
      const response = await fetch(`${apiBase}/api/access/${encodeURIComponent(accessToken)}`, {
        method: "GET",
        credentials: "include"
      });

      if (!response.ok) {
        const errorMessage = await parseErrorResponse(response, "Access lookup failed.");
        throw new Error(errorMessage);
      }

      const result = await response.json();
      renderAccessPanel(result);
      setStatus(accessStatus, "success", "Access unlocked. Use the links to enter your lab and instructions.");
    } catch (error) {
      if (accessPanel) {
        accessPanel.style.display = "none";
      }
      setStatus(accessStatus, "error", error.message || "Unable to load access right now.");
    } finally {
      if (submitButton) {
        submitButton.disabled = false;
      }
    }
  });
}
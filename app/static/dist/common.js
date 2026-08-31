export class ApiError extends Error {
    status;
    data;
    constructor(message, status, data) {
        super(message);
        this.status = status;
        this.data = data;
        this.name = "ApiError";
    }
}
export function byId(id) {
    const element = document.querySelector(`#${CSS.escape(id)}`);
    if (!element) {
        throw new Error(`Missing page element: ${id}`);
    }
    return element;
}
export function formatValue(value, fallback = "--") {
    return value === null || value === undefined || value === ""
        ? fallback
        : String(value);
}
export function numberFormat(value) {
    return Number(value || 0).toLocaleString();
}
let toastTimer;
export function toast(message) {
    const container = byId("toast");
    container.textContent = message;
    container.classList.remove("loading");
    container.classList.add("show");
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => container.classList.remove("show"), 2800);
}
export function loadingToast(message) {
    const container = byId("toast");
    const spinner = document.createElement("span");
    const label = document.createElement("span");
    spinner.className = "toast-spinner";
    spinner.setAttribute("aria-hidden", "true");
    label.textContent = message;
    container.replaceChildren(spinner, label);
    container.classList.add("show", "loading");
    window.clearTimeout(toastTimer);
}
export function hideLoadingToast() {
    const container = byId("toast");
    if (container.classList.contains("loading")) {
        container.classList.remove("show", "loading");
    }
}
export function beginAction(control, message) {
    if (control.disabled || control.dataset.actionBusy === "true") {
        return undefined;
    }
    control.dataset.actionBusy = "true";
    control.classList.add("action-busy");
    control.setAttribute("aria-busy", "true");
    control.disabled = true;
    loadingToast(message);
    let finished = false;
    return (keepLoading = false) => {
        if (finished) {
            return;
        }
        finished = true;
        delete control.dataset.actionBusy;
        control.classList.remove("action-busy");
        control.removeAttribute("aria-busy");
        control.disabled = false;
        if (!keepLoading) {
            hideLoadingToast();
        }
    };
}
export async function getJson(path, options = {}) {
    const response = await fetch(path, {
        cache: "no-store",
        ...options,
        headers: {
            Accept: "application/json",
            ...options.headers,
        },
    });
    if (!response.ok) {
        const data = await response.json().catch(() => ({
            msg: `${response.status} ${response.statusText}`,
        }));
        throw new ApiError(data.msg || `${response.status} ${response.statusText}`, response.status, data);
    }
    return response.json();
}
export function postJson(path, body) {
    return getJson(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body ?? {}),
    });
}
const inflightRequests = new Set();
export async function singleFlight(key, work) {
    if (inflightRequests.has(key)) {
        return undefined;
    }
    inflightRequests.add(key);
    try {
        return await work();
    }
    finally {
        inflightRequests.delete(key);
    }
}
export function runPeriodic(work, delay) {
    const run = async () => {
        try {
            await work();
        }
        finally {
            window.setTimeout(run, typeof delay === "function" ? delay() : delay);
        }
    };
    void run();
}
export async function syncPhoneClock() {
    const now = new Date();
    await postJson("/api/sync_phone_time", {
        epochMs: now.getTime(),
        timezoneOffsetMinutes: now.getTimezoneOffset(),
    });
}
export function downloadBlob(blob, name) {
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = name;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 4000);
}
export function errorMessage(error) {
    return error instanceof Error ? error.message : "Request failed";
}
function restoreTheme() {
    try {
        const theme = localStorage.getItem("ss-theme");
        if (theme === "light" || theme === "dark" || theme === "default") {
            document.documentElement.setAttribute("data-theme", theme);
        }
    }
    catch {
        // Browser storage is optional.
    }
}
let heartbeatBusy = false;
let heartbeatFailures = 0;
function showConnectionWarning(show) {
    byId("connectionWarning").classList.toggle("show", show);
}
async function connectionHeartbeat() {
    if (heartbeatBusy) {
        return;
    }
    heartbeatBusy = true;
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), 2500);
    try {
        const response = await fetch(`/healthz?_=${Date.now()}`, {
            cache: "no-store",
            signal: controller.signal,
        });
        if (!response.ok) {
            throw new Error("Health check failed");
        }
        heartbeatFailures = 0;
        showConnectionWarning(false);
    }
    catch {
        heartbeatFailures += 1;
        if (heartbeatFailures >= 2) {
            showConnectionWarning(true);
        }
    }
    finally {
        window.clearTimeout(timer);
        heartbeatBusy = false;
    }
}
window.addEventListener("offline", () => showConnectionWarning(true));
window.addEventListener("online", () => void connectionHeartbeat());
restoreTheme();
runPeriodic(connectionHeartbeat, 5000);
byId("host").textContent = location.host || "control.skyseeker";
void syncPhoneClock().catch(() => undefined);
document.querySelectorAll(".acc-head").forEach((header) => {
    header.addEventListener("click", () => {
        header.closest(".acc")?.classList.toggle("open");
    });
});

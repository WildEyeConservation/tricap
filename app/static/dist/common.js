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
export async function getJson(path, options = {}, timeoutMs = 8000) {
    const controller = new AbortController();
    const abort = () => controller.abort();
    const callerSignal = options.signal;
    if (callerSignal?.aborted) {
        abort();
    }
    else {
        callerSignal?.addEventListener("abort", abort, { once: true });
    }
    const timer = window.setTimeout(abort, timeoutMs);
    try {
        const response = await fetch(path, {
            cache: "no-store",
            ...options,
            headers: {
                Accept: "application/json",
                ...options.headers,
            },
            signal: controller.signal,
        });
        if (!response.ok) {
            const data = await response.json().catch(() => ({
                msg: `${response.status} ${response.statusText}`,
            }));
            throw new ApiError(data.msg || `${response.status} ${response.statusText}`, response.status, data);
        }
        return await response.json();
    }
    catch (error) {
        if (controller.signal.aborted) {
            throw new ApiError("Request timed out", 0, { msg: "Request timed out" });
        }
        throw error;
    }
    finally {
        window.clearTimeout(timer);
        callerSignal?.removeEventListener("abort", abort);
    }
}
export function postJson(path, body, timeoutMs = 8000) {
    return getJson(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body ?? {}),
    }, timeoutMs);
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
// Mirrors default.cfg; used for any key the page did not supply.
const UI_CONFIG_DEFAULTS = {
    status_poll_ms: 1000,
    sensors_poll_ms: 2000,
    sensors_poll_capturing_ms: 5000,
    background_poll_ms: 15000,
    uplink_poll_ms: 10000,
    netbird_poll_ms: 20000,
    backup_poll_ms: 2000,
    verify_poll_ms: 1000,
    heartbeat_ms: 5000,
};
function readUiConfig() {
    const config = { ...UI_CONFIG_DEFAULTS };
    const block = document.getElementById("ui-config");
    if (!block?.textContent) {
        return config;
    }
    let supplied;
    try {
        supplied = JSON.parse(block.textContent);
    }
    catch {
        return config;
    }
    if (typeof supplied !== "object" || supplied === null) {
        return config;
    }
    for (const key of Object.keys(UI_CONFIG_DEFAULTS)) {
        const value = supplied[key];
        if (typeof value === "number" && Number.isFinite(value) && value > 0) {
            config[key] = value;
        }
    }
    return config;
}
export const uiConfig = readUiConfig();
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
runPeriodic(connectionHeartbeat, uiConfig.heartbeat_ms);
byId("host").textContent = location.host || "control.skyseeker";
void syncPhoneClock().catch(() => undefined);
document.querySelectorAll(".acc-head").forEach((header) => {
    header.addEventListener("click", () => {
        header.closest(".acc")?.classList.toggle("open");
    });
});

export interface ApiErrorData {
  code?: string;
  msg?: string;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly data: ApiErrorData,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export type ActionControl = HTMLButtonElement;
export type FinishAction = (keepLoading?: boolean) => void;

export let actionBusyCount = 0;
let actionStateListener: (() => void) | undefined;

export function setActionStateListener(listener: () => void): void {
  actionStateListener = listener;
}

export function byId<T extends HTMLElement = HTMLElement>(id: string): T {
  const element = document.querySelector<T>(`#${CSS.escape(id)}`);
  if (!element) {
    throw new Error(`Missing page element: ${id}`);
  }
  return element;
}

export function formatValue(value: unknown, fallback = "--"): string {
  return value === null || value === undefined || value === ""
    ? fallback
    : String(value);
}

export function numberFormat(value: unknown): string {
  return Number(value || 0).toLocaleString();
}

let toastTimer: number | undefined;

export function toast(message: string): void {
  const container = byId("toast");
  container.textContent = message;
  container.classList.remove("loading");
  container.classList.add("show");
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => container.classList.remove("show"), 2800);
}

export function loadingToast(message: string): void {
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

export function hideLoadingToast(): void {
  const container = byId("toast");
  if (container.classList.contains("loading")) {
    container.classList.remove("show", "loading");
  }
}

export function beginAction(
  control: ActionControl,
  message: string,
): FinishAction | undefined {
  if (control.disabled || control.dataset.actionBusy === "true") {
    return undefined;
  }

  control.dataset.actionBusy = "true";
  control.classList.add("action-busy");
  control.setAttribute("aria-busy", "true");
  control.disabled = true;
  actionBusyCount += 1;
  actionStateListener?.();
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
    actionBusyCount -= 1;
    actionStateListener?.();
    if (!keepLoading) {
      hideLoadingToast();
    }
  };
}

export async function getJson<T>(
  path: string,
  options: RequestInit = {},
  timeoutMs = 8000,
): Promise<T> {
  const controller = new AbortController();
  const abort = (): void => controller.abort();
  const callerSignal = options.signal;
  if (callerSignal?.aborted) {
    abort();
  } else {
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
      const data: ApiErrorData = await response.json().catch(() => ({
        msg: `${response.status} ${response.statusText}`,
      }));
      throw new ApiError(
        data.msg || `${response.status} ${response.statusText}`,
        response.status,
        data,
      );
    }

    return await response.json();
  } catch (error) {
    if (controller.signal.aborted) {
      throw new ApiError("Request timed out", 0, { msg: "Request timed out" });
    }
    throw error;
  } finally {
    window.clearTimeout(timer);
    callerSignal?.removeEventListener("abort", abort);
  }
}

export function postJson<TResponse, TBody extends object = Record<string, never>>(
  path: string,
  body?: TBody,
  timeoutMs = 8000,
): Promise<TResponse> {
  return getJson<TResponse>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  }, timeoutMs);
}

const inflightRequests = new Set<string>();

export async function singleFlight<T>(
  key: string,
  work: () => T | Promise<T>,
): Promise<T | undefined> {
  if (inflightRequests.has(key)) {
    return undefined;
  }
  inflightRequests.add(key);
  try {
    return await work();
  } finally {
    inflightRequests.delete(key);
  }
}

/** Dashboard poll rates from the [Ui] section of the rig's config. */
export interface UiConfig {
  status_poll_ms: number;
  sensors_poll_ms: number;
  sensors_poll_capturing_ms: number;
  background_poll_ms: number;
  uplink_poll_ms: number;
  netbird_poll_ms: number;
  backup_poll_ms: number;
  verify_poll_ms: number;
  heartbeat_ms: number;
}

// Mirrors default.cfg; used for any key the page did not supply.
const UI_CONFIG_DEFAULTS: UiConfig = {
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

function readUiConfig(): UiConfig {
  const config: UiConfig = { ...UI_CONFIG_DEFAULTS };
  const block = document.getElementById("ui-config");
  if (!block?.textContent) {
    return config;
  }
  let supplied: unknown;
  try {
    supplied = JSON.parse(block.textContent);
  } catch {
    return config;
  }
  if (typeof supplied !== "object" || supplied === null) {
    return config;
  }
  for (const key of Object.keys(UI_CONFIG_DEFAULTS) as (keyof UiConfig)[]) {
    const value = (supplied as Record<string, unknown>)[key];
    if (typeof value === "number" && Number.isFinite(value) && value > 0) {
      config[key] = value;
    }
  }
  return config;
}

export const uiConfig: UiConfig = readUiConfig();

type PeriodicWork = () => unknown | Promise<unknown>;

export function runPeriodic(
  work: PeriodicWork,
  delay: number | (() => number),
): void {
  const run = async (): Promise<void> => {
    try {
      await work();
    } finally {
      window.setTimeout(run, typeof delay === "function" ? delay() : delay);
    }
  };
  void run();
}

interface PhoneClockRequest {
  epochMs: number;
  timezoneOffsetMinutes: number;
}

export async function syncPhoneClock(): Promise<void> {
  const now = new Date();
  await postJson<unknown, PhoneClockRequest>("/api/sync_phone_time", {
    epochMs: now.getTime(),
    timezoneOffsetMinutes: now.getTimezoneOffset(),
  });
}

export function downloadBlob(blob: Blob, name: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 4000);
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Request failed";
}

function restoreTheme(): void {
  try {
    const theme = localStorage.getItem("ss-theme");
    if (theme === "light" || theme === "dark" || theme === "default") {
      document.documentElement.setAttribute("data-theme", theme);
    }
  } catch {
    // Browser storage is optional.
  }
}

let heartbeatBusy = false;
let heartbeatFailures = 0;

function showConnectionWarning(show: boolean): void {
  byId("connectionWarning").classList.toggle("show", show);
}

async function connectionHeartbeat(): Promise<void> {
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
  } catch {
    heartbeatFailures += 1;
    if (heartbeatFailures >= 2) {
      showConnectionWarning(true);
    }
  } finally {
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

document.querySelectorAll<HTMLElement>(".acc-head").forEach((header) => {
  header.addEventListener("click", () => {
    header.closest(".acc")?.classList.toggle("open");
  });
});

import {
  ApiError,
  beginAction,
  byId,
  downloadBlob,
  errorMessage,
  formatValue,
  getJson,
  loadingToast,
  postJson,
  runPeriodic,
  singleFlight,
  toast,
} from "./common.js";

interface GpsStatus {
  avg?: number;
  lastUpdate?: number;
  max?: number;
  min?: number;
  pdop?: number;
  satellites?: number;
}

interface CaptureStatus {
  cams: string[];
  gps?: GpsStatus;
  mode: string;
  wifiSignal?: number;
}

interface StorageUsage {
  capacityGB?: number;
}

interface Statistics {
  captureInterval?: number;
  externalStorage?: StorageUsage;
}

interface LensResponse {
  lens?: string;
}

type ImageFormat = "Default" | "RAW" | "JPEG";

interface ImageFormatResponse {
  value: ImageFormat;
}

interface ActionResponse {
  msg?: string;
  success?: boolean;
}

interface BackupStatus {
  elapsed_seconds?: number;
  eta_seconds?: number;
  files_done?: number;
  files_total?: number;
  message?: string;
  percent?: number;
  phase?: string;
  running: boolean;
  throughput_mib_s?: number;
}

interface VerifyStatus {
  completed?: number;
  message?: string;
  phase: string;
  running: boolean;
  success?: boolean;
  total?: number;
}

interface NetbirdStatus {
  connected: boolean;
}

interface UplinkStatus {
  available: boolean;
  connected?: boolean;
  connection?: string;
  connectivity?: string;
  ip?: string;
  msg?: string;
  signal?: number;
  ssid?: string;
}

interface UplinkRequest {
  psk?: string;
  ssid?: string;
}

type DeleteMode = "force" | "verify";
type AltitudeUnit = "ft" | "m";
type Theme = "default" | "light" | "dark";

const button = (id: string): HTMLButtonElement => byId<HTMLButtonElement>(id);
const input = (id: string): HTMLInputElement => byId<HTMLInputElement>(id);

let currentInterval: number | undefined;
let currentImageFormat: ImageFormat | undefined;
let capturing = false;
let backupRunning = false;
let backupTimer: number | undefined;
let cameraCount = -1;
let externalConnected = false;
let verifyRunning = false;
let verifyTimer: number | undefined;
let verifyAnnounce = false;
let deleteMode: DeleteMode = "verify";

function setControlsEnabled(): void {
  const locked = capturing || backupRunning || verifyRunning;
  document.querySelectorAll<HTMLButtonElement>("[data-locks]").forEach((control) => {
    control.disabled = locked || control.dataset.actionBusy === "true";
  });
  byId("lockNote").textContent = locked
    ? "Some controls are disabled while capture or copy is running."
    : "";
}

function renderImageButtons(count: number): void {
  if (count === cameraCount) return;
  cameraCount = count;
  const container = byId("imageButtons");
  container.replaceChildren();
  if (count === 0) {
    byId("imageNote").textContent = "No cameras detected. Connect cameras and run a copy, then sample images appear here.";
    return;
  }
  byId("imageNote").textContent = "Downloads a representative image from the most recent copy session.";
  for (let index = 0; index < count; index += 1) {
    const control = document.createElement("button");
    control.className = "pill-btn";
    control.type = "button";
    control.textContent = `Camera ${index + 1}`;
    control.addEventListener("click", () => void downloadImage(index, control));
    container.appendChild(control);
  }
}

async function loadSensors(): Promise<void> {
  await singleFlight("setup-status", async () => {
    try {
      const status = await getJson<CaptureStatus>("/api/status");
      const gps = status.gps ?? {};
      capturing = status.mode === "STARTED" || status.mode === "COPYING";
      byId("setupMode").textContent = status.mode || "--";
      byId("wifi").textContent = `${formatValue(status.wifiSignal)} dBm`;
      byId("sats").textContent = formatValue(gps.satellites);
      byId("pdop").textContent = formatValue(gps.pdop);
      const age = Number(gps.lastUpdate);
      byId("age").textContent = Number.isFinite(age) && age >= 0 ? `${age.toFixed(0)}s` : "--";
      byId("snrMin").textContent = formatValue(gps.min);
      byId("snrAvg").textContent = formatValue(gps.avg);
      byId("snrMax").textContent = formatValue(gps.max);
      renderImageButtons(status.cams.length);
      setControlsEnabled();
    } catch {
      byId("setupMode").textContent = "Offline";
    }
  });
}

async function loadStats(): Promise<void> {
  await singleFlight("setup-stats", async () => {
    try {
      const [stats, lens] = await Promise.all([
        getJson<Statistics>("/api/statistics"),
        getJson<LensResponse>("/api/lensNumber").catch((): LensResponse => ({})),
      ]);
      byId("lens").textContent = formatValue(lens.lens);
      externalConnected = Number(stats.externalStorage?.capacityGB) > 0;
      if (stats.captureInterval !== undefined) {
        currentInterval = Number(stats.captureInterval);
        byId("interval").textContent = `${currentInterval.toFixed(1)} s`;
      }
    } catch {
      // Statistics may be unavailable while camera capture is active.
    }
  });
}

function renderImageFormat(value: ImageFormat): void {
  currentImageFormat = value;
  const choices: ReadonlyArray<readonly [string, ImageFormat]> = [
    ["imageFormatDefault", "Default"],
    ["imageFormatRaw", "RAW"],
    ["imageFormatJpeg", "JPEG"],
  ];
  choices.forEach(([id, choice]) => {
    const control = button(id);
    const active = value === choice;
    control.className = `seg-btn${active ? " active" : ""}`;
    control.setAttribute("aria-pressed", String(active));
  });
  byId("imageFormatValue").textContent = value;
}

async function loadImageFormat(): Promise<void> {
  await singleFlight("setup-image-format", async () => {
    try {
      const result = await getJson<ImageFormatResponse>("/api/sony_image_format");
      renderImageFormat(result.value);
    } catch {
      byId("imageFormatValue").textContent = "--";
    }
  });
}

async function setImageFormat(value: ImageFormat, control: HTMLButtonElement): Promise<void> {
  if (value === currentImageFormat) return;
  const finish = beginAction(control, "Saving image format...");
  if (!finish) return;
  try {
    const result = await postJson<ImageFormatResponse, { value: ImageFormat }>(
      "/api/sony_image_format",
      { value },
    );
    renderImageFormat(result.value);
    toast(`Image format set to ${result.value}`);
  } catch (error) {
    toast(errorMessage(error));
  } finally {
    finish();
    setControlsEnabled();
  }
}

async function setIntervalValue(delta: number, control: HTMLButtonElement): Promise<void> {
  if (currentInterval === undefined || Number.isNaN(currentInterval)) {
    toast("Current interval is not available");
    return;
  }
  const next = Math.max(0.1, Math.round((currentInterval + delta) * 10) / 10);
  const finish = beginAction(control, "Saving capture interval...");
  if (!finish) return;
  try {
    await postJson<unknown, { interval: number }>("/api/capture_interval", { interval: next });
    currentInterval = next;
    byId("interval").textContent = `${currentInterval.toFixed(1)} s`;
    toast(`Capture interval set to ${next.toFixed(1)}s`);
  } catch (error) {
    toast(errorMessage(error));
  } finally {
    finish();
    setControlsEnabled();
  }
}

function formatDuration(seconds: number): string {
  const total = Math.max(0, Math.round(seconds));
  if (total < 60) return `${total}s`;
  if (total < 3600) {
    const minutes = Math.floor(total / 60);
    const remainder = total % 60;
    return remainder ? `${minutes}m ${remainder}s` : `${minutes}m`;
  }
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  return minutes ? `${hours}h ${minutes}m` : `${hours}h`;
}

function renderBackup(status: BackupStatus): void {
  const wasRunning = backupRunning;
  backupRunning = status.running;
  setControlsEnabled();
  if (verifyRunning) return;

  const percent = Number(status.percent || 0);
  byId("backupFill").style.width = `${Math.max(0, Math.min(100, percent))}%`;
  let line = status.phase || "Idle";
  if (status.running) {
    line = `${status.phase || "copying"} - ${percent.toFixed(1)}%`;
    if (status.files_total) line += ` (${status.files_done}/${status.files_total} files)`;
    if (Number(status.eta_seconds) > 0) line += ` - ETA ${formatDuration(Number(status.eta_seconds))}`;
    loadingToast(`Copying to SSD... ${percent.toFixed(0)}%`);
  } else if (status.message) {
    line = status.message;
  }
  byId("backupState").textContent = line;

  if (!status.running && Number(status.elapsed_seconds) > 0) {
    const rate = Number(status.throughput_mib_s || 0);
    let benchmark = `Plain copy · ${Number(status.elapsed_seconds).toFixed(1)}s`;
    if (rate > 0) benchmark += ` · ${rate.toFixed(1)} MiB/s`;
    byId("backupBenchmark").textContent = benchmark;
  }
  if (status.running && backupTimer === undefined) {
    backupTimer = window.setInterval(() => void pollBackup(), 2000);
  }
  if (!status.running && backupTimer !== undefined) {
    window.clearInterval(backupTimer);
    backupTimer = undefined;
  }
  if (wasRunning && !status.running) toast(status.message || "Backup complete");
}

async function pollBackup(): Promise<void> {
  await singleFlight("backup-status", async () => {
    try {
      renderBackup(await getJson<BackupStatus>("/api/backup_status"));
    } catch {
      if (backupTimer !== undefined) {
        window.clearInterval(backupTimer);
        backupTimer = undefined;
      }
    }
  });
}

function renderVerify(status: VerifyStatus): void {
  verifyRunning = status.running;
  setControlsEnabled();
  const total = Number(status.total || 0);
  const completed = Number(status.completed || 0);
  const percent = total > 0 ? completed / total * 100 : status.running ? 0 : 100;
  byId("backupFill").style.width = `${Math.max(0, Math.min(100, percent))}%`;

  if (status.running) {
    verifyAnnounce = true;
    const action = status.phase === "deleting" ? "Deleting" : "Verifying";
    byId("backupState").textContent = total
      ? `${action} ${completed}/${total} files...`
      : status.message || `${action}...`;
    loadingToast(total ? `${action} files... ${completed}/${total}` : `${action} files...`);
    if (verifyTimer === undefined) verifyTimer = window.setInterval(() => void pollVerify(), 1000);
    return;
  }

  if (status.phase !== "idle" && status.message) byId("backupState").textContent = status.message;
  if (verifyTimer !== undefined) {
    window.clearInterval(verifyTimer);
    verifyTimer = undefined;
  }
  if (verifyAnnounce && status.phase !== "idle") {
    toast(status.success ? status.message || "Verification complete" : status.message || "Verification failed; files were retained");
    verifyAnnounce = false;
  }
}

async function pollVerify(): Promise<void> {
  await singleFlight("verify-status", async () => {
    const path = deleteMode === "force" ? "/api/force_delete_status" : "/api/verify_and_delete_status";
    try {
      renderVerify(await getJson<VerifyStatus>(path));
    } catch {
      if (verifyTimer !== undefined) {
        window.clearInterval(verifyTimer);
        verifyTimer = undefined;
      }
      verifyRunning = false;
      setControlsEnabled();
    }
  });
}

async function startBackup(control: HTMLButtonElement): Promise<void> {
  const finish = beginAction(control, "Starting backup...");
  if (!finish) return;
  try {
    const result = await getJson<ActionResponse>("/api/backup_start");
    if (result.success === false) toast(result.msg || "Backup failed to start");
    else {
      backupRunning = true;
      loadingToast("Copying to SSD...");
    }
    void pollBackup();
  } catch (error) {
    toast(errorMessage(error));
  } finally {
    finish(backupRunning);
    setControlsEnabled();
  }
}

async function moveBackup(control: HTMLButtonElement): Promise<void> {
  const finish = beginAction(control, "Starting copy & delete...");
  if (!finish) return;
  byId("moveConfirmModal").classList.remove("open");
  try {
    const result = await getJson<ActionResponse>("/api/backup_move");
    if (result.success === false) toast(result.msg || "Copy & delete failed to start");
    else {
      backupRunning = true;
      loadingToast("Moving to SSD...");
    }
    void pollBackup();
  } catch (error) {
    toast(errorMessage(error));
  } finally {
    finish(backupRunning);
    setControlsEnabled();
  }
}

function openDeleteDialog(): void {
  byId("deleteDecisionTitle").textContent = externalConnected ? "Clear internal storage?" : "External SSD not connected";
  byId("deleteDecisionText").textContent = externalConnected
    ? "Verify the SSD copy and delete only matched files. If you continue without verification, all images and logs on internal storage will be permanently deleted and may not be backed up."
    : "The internal files cannot be verified and may not be backed up. Continuing permanently deletes all images and logs from internal storage. This cannot be undone.";
  button("deleteDecisionVerify").hidden = !externalConnected;
  byId("deleteDecisionModal").classList.add("open");
}

async function deleteBackup(control: HTMLButtonElement): Promise<void> {
  const finish = beginAction(control, "Checking storage...");
  if (!finish) return;
  try {
    const stats = await getJson<Statistics>("/api/statistics");
    externalConnected = Number(stats.externalStorage?.capacityGB) > 0;
  } catch {
    // The dialog can use the most recent storage state.
  }
  openDeleteDialog();
  finish();
  setControlsEnabled();
}

async function verifyDeleteMatched(control: HTMLButtonElement): Promise<void> {
  const finish = beginAction(control, "Starting verification...");
  if (!finish) return;
  byId("deleteDecisionModal").classList.remove("open");
  try {
    deleteMode = "verify";
    const result = await getJson<ActionResponse>("/api/verify_and_delete");
    if (result.success) {
      verifyRunning = true;
      verifyAnnounce = true;
      setControlsEnabled();
      byId("backupState").textContent = "Preparing verification...";
      void pollVerify();
    } else {
      toast(result.msg || "Verification could not be started");
    }
  } catch (error) {
    if (error instanceof ApiError && error.data.code === "external_not_connected") {
      externalConnected = false;
      openDeleteDialog();
    } else {
      toast(errorMessage(error));
    }
  } finally {
    finish(verifyRunning);
    setControlsEnabled();
  }
}

async function forceDeleteAll(control: HTMLButtonElement): Promise<void> {
  const finish = beginAction(control, "Clearing internal storage...");
  if (!finish) return;
  byId("deleteDecisionModal").classList.remove("open");
  try {
    deleteMode = "force";
    const result = await postJson<ActionResponse, { confirmation: string }>(
      "/api/force_delete",
      { confirmation: "delete-unbacked-internal-data" },
    );
    if (result.success) {
      verifyRunning = true;
      verifyAnnounce = true;
      setControlsEnabled();
      byId("backupState").textContent = "Preparing to clear internal storage...";
      void pollVerify();
    } else {
      toast(result.msg || "Internal storage could not be cleared");
    }
  } catch (error) {
    toast(errorMessage(error));
  } finally {
    finish(verifyRunning);
    setControlsEnabled();
  }
}

async function netbirdStatus(announce: boolean): Promise<void> {
  try {
    const result = await getJson<NetbirdStatus>("/api/netbird_status");
    byId("nbDot").className = `dot ${result.connected ? "good" : "off"}`;
    byId("nbState").textContent = result.connected ? "Available" : "Off";
    if (announce) toast(result.connected ? "Remote support is available" : "Remote support is off");
  } catch (error) {
    byId("nbDot").className = "dot bad";
    byId("nbState").textContent = "Unavailable";
    if (announce) toast(errorMessage(error));
  }
}

async function downloadImage(index: number, control: HTMLButtonElement): Promise<void> {
  const name = `Camera ${index + 1}`;
  const finish = beginAction(control, `Preparing ${name} sample...`);
  if (!finish) return;
  try {
    const response = await fetch(`/api/get_images/${index}`, { cache: "no-store" });
    if (response.status === 404) {
      toast(`No sample image for ${name} yet (run a copy first).`);
      return;
    }
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    const blob = await response.blob();
    const serverName = response.headers.get("X-SkySeeker-Filename");
    downloadBlob(blob, serverName || `camera${index + 1}_sample`);
    toast(`Downloading ${name} sample`);
  } catch (error) {
    toast(errorMessage(error));
  } finally {
    finish();
  }
}

async function restartCaptureService(control: HTMLButtonElement): Promise<void> {
  if (!confirm("Restart the tricap capture service? Capture pauses briefly.")) return;
  const finish = beginAction(control, "Restarting tricap...");
  if (!finish) return;
  try {
    await getJson<unknown>("/api/restart");
    toast("tricap restart requested");
  } catch (error) {
    toast(errorMessage(error));
  } finally {
    finish();
    setControlsEnabled();
  }
}

async function rebootDevice(control: HTMLButtonElement): Promise<void> {
  if (!confirm("Reboot the SkySeeker device? It will be offline for ~30-60s and you may need to rejoin Wi-Fi.")) return;
  const finish = beginAction(control, "Requesting reboot...");
  if (!finish) return;
  try {
    await getJson<unknown>("/api/reboot");
    toast("Reboot requested - rejoin skyseeker when it returns");
  } catch (error) {
    toast(errorMessage(error));
  } finally {
    finish();
    setControlsEnabled();
  }
}

async function uplinkStatus(): Promise<void> {
  try {
    const result = await getJson<UplinkStatus>("/portal/uplink_status");
    if (!result.available) {
      byId("ulDot").className = "dot off";
      byId("ulState").textContent = "--";
      byId("ulDetail").textContent = result.msg || "Uplink control is not available on this build.";
      return;
    }
    const connected = Boolean(result.connected);
    byId("ulDot").className = `dot ${connected ? "good" : "off"}`;
    byId("ulState").textContent = connected ? "Online" : "Offline";
    byId("ulDetail").textContent = connected
      ? `${result.ssid || result.connection} · ${result.ip || "no IP"} · ${result.signal !== undefined ? `${result.signal} dBm` : "--"} · internet: ${result.connectivity || "unknown"}`
      : "Phone recovery hotspot not found. The USB skyseeker network remains available for local control.";
  } catch {
    byId("ulDot").className = "dot bad";
    byId("ulState").textContent = "--";
  }
}

async function connectUplink(custom: boolean): Promise<void> {
  const control = button(custom ? "ulConnectCustom" : "ulConnect");
  const finish = beginAction(control, "Connecting internet...");
  if (!finish) return;
  try {
    const body: UplinkRequest = {};
    if (custom) {
      const ssid = input("ulSsid").value.trim();
      const psk = input("ulPsk").value;
      if (!ssid) throw new Error("Enter a hotspot name");
      body.ssid = ssid;
      if (psk) body.psk = psk;
    }
    const result = await postJson<ActionResponse, UplinkRequest>("/portal/uplink_connect", body);
    toast(result.msg || "Internet connected");
    void uplinkStatus();
  } catch (error) {
    toast(errorMessage(error));
  } finally {
    finish();
  }
}

async function disconnectUplink(control: HTMLButtonElement): Promise<void> {
  if (!confirm("Disconnect SkySeeker from the phone hotspot? The dashboard remains available through the USB skyseeker Wi-Fi network.")) return;
  const finish = beginAction(control, "Disconnecting internet...");
  if (!finish) return;
  try {
    const result = await postJson<ActionResponse>("/portal/uplink_disconnect");
    toast(result.msg || "Internet disconnected");
    void uplinkStatus();
  } catch (error) {
    toast(errorMessage(error));
  } finally {
    finish();
  }
}

function altitudeUnit(): AltitudeUnit {
  try {
    return localStorage.getItem("ss-alt-unit") === "m" ? "m" : "ft";
  } catch {
    return "ft";
  }
}

function renderAltitudeBand(): void {
  const target = Number.parseFloat(input("altTarget").value);
  const deviation = Number.parseFloat(input("altDev").value);
  const unit = altitudeUnit();
  button("unitFt").className = `seg-btn${unit === "ft" ? " active" : ""}`;
  button("unitM").className = `seg-btn${unit === "m" ? " active" : ""}`;
  byId("altBand").textContent = Number.isFinite(target) && target > 0 && Number.isFinite(deviation) && deviation > 0
    ? `±${Math.round(target * deviation / 100).toLocaleString()} ${unit}`
    : "--";
}

function saveAltitudeSettings(): void {
  try {
    localStorage.setItem("ss-alt-target", input("altTarget").value);
    localStorage.setItem("ss-alt-dev", input("altDev").value);
  } catch {
    // Browser storage is optional.
  }
  renderAltitudeBand();
}

function setAltitudeUnit(unit: AltitudeUnit): void {
  try {
    localStorage.setItem("ss-alt-unit", unit);
  } catch {
    // Browser storage is optional.
  }
  renderAltitudeBand();
}

function loadAltitudeSettings(): void {
  let target = "";
  let deviation = "";
  try {
    target = localStorage.getItem("ss-alt-target") || "";
    deviation = localStorage.getItem("ss-alt-dev") || "";
  } catch {
    // Browser storage is optional.
  }
  input("altTarget").value = target;
  input("altDev").value = deviation || "5";
  if (deviation === "") saveAltitudeSettings();
  else renderAltitudeBand();
}

function applyTheme(theme: Theme, persist: boolean): void {
  document.documentElement.setAttribute("data-theme", theme);
  if (persist) {
    try {
      localStorage.setItem("ss-theme", theme);
    } catch {
      // Browser storage is optional.
    }
  }
  byId("themeVal").textContent = theme === "default" ? "Default" : theme === "dark" ? "Dark" : "Light";
  button("themeDefault").className = `seg-btn${theme === "default" ? " active" : ""}`;
  button("themeLight").className = `seg-btn${theme === "light" ? " active" : ""}`;
  button("themeDark").className = `seg-btn${theme === "dark" ? " active" : ""}`;
}

function selectedTheme(): Theme {
  const theme = document.documentElement.getAttribute("data-theme");
  return theme === "light" || theme === "dark" ? theme : "default";
}

document.querySelectorAll<HTMLButtonElement>("[data-delta]").forEach((control) => {
  control.addEventListener("click", () => void setIntervalValue(Number(control.dataset.delta), control));
});
button("imageFormatDefault").addEventListener("click", () => void setImageFormat("Default", button("imageFormatDefault")));
button("imageFormatRaw").addEventListener("click", () => void setImageFormat("RAW", button("imageFormatRaw")));
button("imageFormatJpeg").addEventListener("click", () => void setImageFormat("JPEG", button("imageFormatJpeg")));
button("restartService").addEventListener("click", () => void restartCaptureService(button("restartService")));
button("rebootDevice").addEventListener("click", () => void rebootDevice(button("rebootDevice")));
button("backupStart").addEventListener("click", () => void startBackup(button("backupStart")));
button("backupMove").addEventListener("click", () => byId("moveConfirmModal").classList.add("open"));
button("moveConfirmContinue").addEventListener("click", () => void moveBackup(button("moveConfirmContinue")));
button("moveConfirmCancel").addEventListener("click", () => byId("moveConfirmModal").classList.remove("open"));
button("backupDelete").addEventListener("click", () => void deleteBackup(button("backupDelete")));
button("deleteDecisionCancel").addEventListener("click", () => byId("deleteDecisionModal").classList.remove("open"));
button("deleteDecisionVerify").addEventListener("click", () => void verifyDeleteMatched(button("deleteDecisionVerify")));
button("deleteDecisionContinue").addEventListener("click", () => void forceDeleteAll(button("deleteDecisionContinue")));
button("nbConnect").addEventListener("click", async () => {
  const control = button("nbConnect");
  const finish = beginAction(control, "Connecting remote support...");
  if (!finish) return;
  try {
    await postJson<unknown>("/api/netbird_connect");
    await netbirdStatus(true);
  } catch (error) {
    toast(errorMessage(error));
  } finally {
    finish();
  }
});
button("nbDisconnect").addEventListener("click", async () => {
  if (!confirm("Turn off remote support? Support will not be able to reach this rig until it is reconnected.")) return;
  const control = button("nbDisconnect");
  const finish = beginAction(control, "Turning off remote support...");
  if (!finish) return;
  try {
    await postJson<unknown>("/api/netbird_disconnect");
    await netbirdStatus(true);
  } catch (error) {
    toast(errorMessage(error));
  } finally {
    finish();
  }
});
button("ulConnect").addEventListener("click", () => void connectUplink(false));
button("ulConnectCustom").addEventListener("click", () => void connectUplink(true));
button("ulDisconnect").addEventListener("click", () => void disconnectUplink(button("ulDisconnect")));
input("altTarget").addEventListener("input", saveAltitudeSettings);
input("altDev").addEventListener("input", saveAltitudeSettings);
button("unitFt").addEventListener("click", () => setAltitudeUnit("ft"));
button("unitM").addEventListener("click", () => setAltitudeUnit("m"));
button("themeDefault").addEventListener("click", () => applyTheme("default", true));
button("themeLight").addEventListener("click", () => applyTheme("light", true));
button("themeDark").addEventListener("click", () => applyTheme("dark", true));

loadAltitudeSettings();
applyTheme(selectedTheme(), false);
void pollBackup();
void pollVerify();
runPeriodic(loadSensors, () => capturing ? 5000 : 2000);
runPeriodic(() => capturing ? undefined : loadStats(), 15000);
runPeriodic(() => capturing ? undefined : loadImageFormat(), 15000);
runPeriodic(() => capturing ? undefined : singleFlight("setup-netbird", () => netbirdStatus(false)), 20000);
runPeriodic(() => capturing ? undefined : singleFlight("setup-uplink", uplinkStatus), 10000);

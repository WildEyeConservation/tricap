import { beginAction, byId, errorMessage, formatValue, getJson, numberFormat, runPeriodic, singleFlight, syncPhoneClock, toast, } from "./common.js";
const healthyCameraStates = new Set(["INITIALISED", "CAPTURING", "READY", "STARTED"]);
const errorStates = new Set(["ERROR_CONFIG", "ERROR_CAPTURE", "ERROR"]);
let latest;
let busy = false;
let lastStats = {};
let lastStorageEstimate = {};
function sum(values) {
    return values?.reduce((total, value) => total + Number(value || 0), 0) ?? 0;
}
function altitudeSettings() {
    let target = Number.NaN;
    let devPct = Number.NaN;
    let unit = "ft";
    try {
        target = Number.parseFloat(localStorage.getItem("ss-alt-target") ?? "");
        devPct = Number.parseFloat(localStorage.getItem("ss-alt-dev") ?? "");
        unit = localStorage.getItem("ss-alt-unit") ?? "ft";
    }
    catch {
        // Browser storage can be disabled without affecting flight controls.
    }
    if (!Number.isFinite(devPct) || devPct < 0) {
        devPct = 5;
    }
    return { target, devPct, unit: unit === "m" ? "m" : "ft" };
}
function convertAltitude(value, from, to) {
    if (from === to) {
        return value;
    }
    return from === "m" ? value * 3.28084 : value / 3.28084;
}
function chevronCount(error, band) {
    const ratio = Math.abs(error) / band;
    if (ratio < 1 / 3)
        return 0;
    if (ratio < 2 / 3)
        return 1;
    if (ratio < 1)
        return 2;
    return 3;
}
function cssColor(variable, styles) {
    const hex = styles.getPropertyValue(variable).trim().replace("#", "");
    if (hex.length !== 6) {
        return undefined;
    }
    return [0, 2, 4].map((index) => Number.parseInt(hex.slice(index, index + 2), 16));
}
function chevronTone(nearVariable, farVariable, severity) {
    const styles = getComputedStyle(document.documentElement);
    const near = cssColor(nearVariable, styles);
    const far = cssColor(farVariable, styles);
    if (!near || !far) {
        return `var(${farVariable})`;
    }
    const ratio = Math.max(0, Math.min(1, severity));
    const smooth = ratio * ratio * (3 - 2 * ratio);
    const color = near.map((value, index) => Math.round(value + ((far[index] ?? value) - value) * smooth).toString(16).padStart(2, "0"));
    return `#${color.join("")}`;
}
function openGlance() {
    byId("glanceModal").classList.add("open");
    byId("glanceBody").appendChild(byId("glanceSections"));
}
function closeGlance() {
    byId("glanceModal").classList.remove("open");
    byId("normalHome").appendChild(byId("glanceSections"));
}
function renderFlight(status, capturing) {
    document.body.classList.toggle("flight", capturing);
    if (!capturing) {
        closeGlance();
        byId("stopConfirmModal").classList.remove("open");
        return;
    }
    const settings = altitudeSettings();
    const altimeter = status.altimeter ?? {};
    const raw = altimeter.height ?? altimeter.measurement;
    const numeric = Number(raw);
    const sensorUnit = altimeter.unit?.toLowerCase().startsWith("f") ? "ft" : "m";
    const altitude = raw !== null && raw !== "" && Number.isFinite(numeric)
        ? convertAltitude(numeric, sensorUnit, settings.unit)
        : Number.NaN;
    byId("flightAlt").textContent = Number.isFinite(altitude)
        ? Math.round(altitude).toLocaleString()
        : "--";
    byId("flightUnit").textContent = Number.isFinite(altitude) ? settings.unit : "";
    let up = 0;
    let down = 0;
    let intensity = 0;
    let note = "";
    if (!Number.isFinite(altitude)) {
        note = "Waiting for altimeter";
    }
    else if (!Number.isFinite(settings.target) || settings.target <= 0) {
        note = "Set a target altitude in Setup";
    }
    else {
        const band = settings.target * settings.devPct / 100;
        const error = altitude - settings.target;
        if (band > 0) {
            intensity = Math.max(0, Math.min(1, Math.abs(error) / band));
            const count = chevronCount(error, band);
            if (error < 0)
                up = count;
            else
                down = count;
        }
        note = `Target ${Math.round(settings.target).toLocaleString()} ${settings.unit} · ±${Math.round(band).toLocaleString()} ${settings.unit}`;
    }
    byId("flightTarget").textContent = note;
    byId("chevUp").style.setProperty("--chev-color", chevronTone("--climb-near", "--climb", intensity));
    byId("chevDown").style.setProperty("--chev-color", chevronTone("--descend-near", "--descend", intensity));
    document.querySelectorAll("#chevUp .fchev").forEach((chevron, index) => {
        chevron.classList.toggle("on", index >= 3 - up);
    });
    document.querySelectorAll("#chevDown .fchev").forEach((chevron, index) => {
        chevron.classList.toggle("on", index < down);
    });
}
function renderCameras(status, images) {
    const grid = byId("cameraGrid");
    const counts = images.imageCount ?? [];
    const copies = images.copyCount ?? [];
    byId("camSummary").textContent = `${status.cams.length} connected`;
    grid.replaceChildren();
    if (status.cams.length === 0) {
        const empty = document.createElement("p");
        empty.className = "empty";
        empty.textContent = "No cameras detected.";
        grid.appendChild(empty);
        return;
    }
    status.cams.forEach((state, index) => {
        const indicator = healthyCameraStates.has(state) ? "good" : errorStates.has(state) ? "bad" : "warn";
        const row = document.createElement("div");
        row.className = "cam-row";
        row.innerHTML = `<div class="cam-left"><span class="dot ${indicator}"></span><span class="cam-name">Camera ${index + 1}</span></div><div class="cam-meta mono">${state} · ${formatValue(counts[index], "0")}/${formatValue(copies[index], "0")}</div>`;
        grid.appendChild(row);
    });
}
function renderComponents(status) {
    const panel = byId("componentPanel");
    const list = byId("componentList");
    const order = ["cameras", "gps", "altimeter", "storage"];
    const missing = order
        .map((name) => status.components?.[name])
        .filter((component) => component?.connected === false);
    panel.hidden = missing.length === 0;
    list.replaceChildren();
    missing.forEach((component) => {
        const item = document.createElement("li");
        const dot = document.createElement("span");
        const message = document.createElement("span");
        item.className = "component-item";
        dot.className = "dot warn";
        dot.setAttribute("aria-hidden", "true");
        message.textContent = component.message ?? "Component not connected.";
        item.append(dot, message);
        list.appendChild(item);
    });
}
function storageBar(percent) {
    const bounded = Math.max(0, Math.min(100, percent));
    return `<div class="track"><div class="fill" style="width:${bounded}%"></div></div>`;
}
function formatFlightTime(seconds) {
    const total = Math.max(0, Math.floor(seconds));
    if (total < 60)
        return "< 1 minute";
    const days = Math.floor(total / 86400);
    const hours = Math.floor((total % 86400) / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    if (days)
        return `${days}d ${hours}h`;
    if (hours)
        return `${hours}h ${minutes}m`;
    return `${minutes}m`;
}
function flightTimeEstimate(stats, estimate) {
    const averageBytes = Number(estimate.averageImageBytes);
    const freeBytes = Number(estimate.freeBytes);
    const interval = Number(stats.captureInterval);
    const cameraCount = latest?.cams.length ?? 0;
    if (!(averageBytes > 0))
        return { text: "Record images to estimate flight time", ready: false };
    if (!(cameraCount > 0))
        return { text: "Connect cameras to estimate flight time", ready: false };
    if (!(interval > 0) || !(freeBytes > 0))
        return { text: "Flight-time estimate unavailable", ready: false };
    return {
        text: `${formatFlightTime(freeBytes * interval / (averageBytes * cameraCount))} estimated flight time`,
        ready: true,
    };
}
function renderStorage(stats, estimate) {
    const internal = stats.internalStorage;
    const external = stats.externalStorage;
    const hasInternal = internal?.freeGB !== undefined;
    const hasExternal = external?.freeGB !== undefined;
    const flight = flightTimeEstimate(stats, estimate);
    byId("storageSummary").textContent = flight.ready
        ? flight.text
        : hasInternal ? `${numberFormat(internal.usedGB)} / ${numberFormat(internal.capacityGB)} GB` : "--";
    const internalBar = hasInternal
        ? storageBar(internal.capacityGB ? Number(internal.usedGB) / internal.capacityGB * 100 : 0)
        : '<div class="track dashed"></div>';
    const externalBar = hasExternal
        ? storageBar(external.capacityGB ? Number(external.usedGB) / external.capacityGB * 100 : 0)
        : '<div class="track dashed"></div>';
    byId("storageBody").innerHTML = `
    <div class="stor-item">
      <div class="stor-head"><span class="stor-name">Internal SSD</span><span class="mono stor-val">${hasInternal ? `${numberFormat(internal.usedGB)} / ${numberFormat(internal.capacityGB)} GB` : "--"}</span></div>
      ${internalBar}<p class="stor-estimate${flight.ready ? "" : " muted"}">${flight.text}</p>
    </div>
    <div class="stor-item">
      <div class="stor-head"><span class="stor-name off">External</span><span class="mono stor-val off">${hasExternal ? `${numberFormat(external.usedGB)} / ${numberFormat(external.capacityGB)} GB` : "not connected"}</span></div>
      ${externalBar}
    </div>`;
}
function render(status, images) {
    latest = status;
    const capturing = status.mode === "STARTED";
    const copying = status.mode === "COPYING";
    const recordDot = byId("recDot");
    const recordText = byId("recText");
    if (capturing) {
        recordDot.className = "rec-dot live";
        recordText.textContent = "Recording";
    }
    else if (errorStates.has(status.mode)) {
        recordDot.className = "rec-dot bad";
        recordText.textContent = "Error";
    }
    else {
        recordDot.className = "rec-dot";
        recordText.textContent = copying ? "Copying" : "Standby";
    }
    byId("modeText").textContent = capturing ? "Capturing" : copying ? "Copying" : "Stopped";
    const captured = sum(images.imageCount);
    const copied = sum(images.copyCount);
    const gps = status.gps ?? {};
    const gpsFix = Boolean(gps.fix);
    const altimeter = status.altimeter ?? {};
    const height = altimeter.height ?? altimeter.measurement;
    const numericHeight = Number(height);
    byId("statCaptured").textContent = numberFormat(captured);
    byId("statSignal").textContent = `${formatValue(status.wifiSignal)} dBm`;
    byId("statPdop").textContent = gpsFix ? `${formatValue(gps.pdop)} · Fix` : "No fix";
    byId("statAltitude").textContent = height !== null && height !== "" && Number.isFinite(numericHeight)
        ? `${numericHeight.toFixed(1)} ${altimeter.unit ?? "m"}`
        : "--";
    const gpsConnected = status.components?.gps?.connected ?? Boolean(status.gps);
    byId("deviceGpsSummary").textContent = !gpsConnected
        ? "Not connected"
        : gpsFix ? `3D fix · PDOP ${formatValue(gps.pdop)}` : "Waiting for fix";
    byId("devCams").textContent = String(status.cams.length);
    byId("gpsFix").textContent = gpsFix ? "3D fix" : "No fix";
    byId("gpsFix").className = `badge ${gpsFix ? "live" : "idle"}`;
    byId("sats").textContent = formatValue(gps.satellites);
    byId("pdop").textContent = formatValue(gps.pdop);
    byId("snrAvg").textContent = formatValue(gps.avg);
    const copyPercent = captured > 0 ? copied / captured * 100 : 0;
    byId("copySummary").textContent = captured > 0 ? `${copyPercent.toFixed(0)}%` : "idle";
    byId("copyFill").style.width = `${Math.max(0, Math.min(100, copyPercent))}%`;
    byId("copyText").textContent = captured > 0
        ? `${numberFormat(copied)} of ${numberFormat(captured)} files copied`
        : status.progress ?? "No active copy reported.";
    byId("camError").classList.toggle("show", Boolean(status.camError));
    renderComponents(status);
    renderCameras(status, images);
    const camerasConnected = status.components?.cameras?.connected ?? status.cams.length > 0;
    const captureButton = byId("captureButton");
    captureButton.textContent = capturing ? "Stop capture" : "Start capture";
    captureButton.className = capturing ? "big-btn stop" : "big-btn go";
    captureButton.disabled = busy || copying || (!capturing && !camerasConnected);
    byId("conn").textContent = !capturing && !camerasConnected
        ? "Connect at least one camera to start capture."
        : "";
    byId("flCaptured").textContent = numberFormat(captured);
    byId("flSignal").textContent = `${formatValue(status.wifiSignal)} dBm`;
    byId("flPdop").textContent = gpsFix ? `${formatValue(gps.pdop)} · Fix` : "No fix";
    byId("flightStop").disabled = busy;
    renderFlight(status, capturing);
}
async function pollStatus() {
    await singleFlight("home-status", async () => {
        try {
            const [status, images] = await Promise.all([
                getJson("/api/status"),
                getJson("/api/images_captured").catch(() => ({})),
            ]);
            render(status, images);
        }
        catch {
            byId("recDot").className = "rec-dot bad";
            byId("recText").textContent = "Offline";
            byId("modeText").textContent = "Offline";
            byId("conn").textContent = "tricap is not reachable on the rig.";
            byId("captureButton").disabled = true;
        }
    });
}
async function pollStorage() {
    await singleFlight("home-storage", async () => {
        const [statsResult, estimateResult] = await Promise.allSettled([
            getJson("/api/statistics"),
            getJson("/portal/storage_estimate"),
        ]);
        if (statsResult.status === "fulfilled")
            lastStats = statsResult.value;
        if (estimateResult.status === "fulfilled")
            lastStorageEstimate = estimateResult.value;
        renderStorage(lastStats, lastStorageEstimate);
        byId("storageNote").textContent = statsResult.status === "fulfilled"
            ? ""
            : "Storage usage refreshes while capture is stopped.";
    });
}
async function toggleCapture(control) {
    if (!latest || busy)
        return;
    const capturing = latest.mode === "STARTED";
    const finish = beginAction(control, capturing ? "Stopping capture..." : "Starting capture...");
    if (!finish)
        return;
    busy = true;
    byId("captureButton").disabled = true;
    byId("flightStop").disabled = true;
    try {
        if (!capturing)
            await syncPhoneClock();
        await getJson(capturing ? "/api/stop_capture" : "/api/start_capture");
        toast(capturing ? "Capture stopped" : "Capture started");
    }
    catch (error) {
        toast(errorMessage(error));
    }
    finally {
        busy = false;
        finish();
        void pollStatus();
        void pollStorage();
    }
}
function requestToggle(control) {
    if (!latest || busy)
        return;
    if (latest.mode === "STARTED") {
        const finish = beginAction(control, "Opening confirmation...");
        if (!finish)
            return;
        byId("stopConfirmModal").classList.add("open");
        requestAnimationFrame(() => finish());
        return;
    }
    void toggleCapture(control);
}
const captureButton = byId("captureButton");
const flightStop = byId("flightStop");
byId("host2").textContent = location.host || "control.skyseeker";
byId("stopConfirmYes").addEventListener("click", () => {
    byId("stopConfirmModal").classList.remove("open");
    void toggleCapture(captureButton);
});
byId("stopConfirmNo").addEventListener("click", () => byId("stopConfirmModal").classList.remove("open"));
captureButton.addEventListener("click", () => requestToggle(captureButton));
flightStop.addEventListener("click", () => requestToggle(flightStop));
byId("glanceOpen").addEventListener("click", openGlance);
byId("glanceClose").addEventListener("click", closeGlance);
runPeriodic(pollStatus, 1000);
runPeriodic(() => latest?.mode === "STARTED" ? undefined : pollStorage(), 15000);

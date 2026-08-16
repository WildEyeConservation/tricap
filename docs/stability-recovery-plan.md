# Rig stability recovery plan

**Date:** 2026-08-16
**Branch:** `skyseeker-production`
**Commits under review:** `9bdeeb3` (harden rig connectivity recovery), `b41ad1b` (recover stalled Wi-Fi access point), `4097216` (sync rig network identity)
**"Somewhat safe" baseline:** `2f8436b` (sync rig clock from dashboard device) — the commit one rig has been reverted to.

---

## 1. What we experienced and how it ties to the changes

### The original problem (before the three commits)

The rig would drop the connected user but keep the access point up: the user could still *see* the AP (hostapd kept beaconing) but could not connect or reach the dashboard. The three commits were an attempt to fix this, but they bundled several unrelated interventions — client polling changes, a server accept-queue change, a hostapd liveness watchdog with reboot escalation, a systemd hardware watchdog, and boot-time rewriting of `/etc/hosts` and the hostapd config — into one deployment, so no single fix could be validated on its own.

### The new problems (after the three commits)

1. **The system locks up completely and nothing happens.**
2. **Large numbers of PCIe errors that did not exist before.**

### How the symptoms tie to the changes

**The hardware watchdog (`RuntimeWatchdogSec=30s`, commit `9bdeeb3`) plausibly explains both new symptoms at once.** The rig is a Rock Pi (Rockchip SoC) with its imagery storage on an NVMe drive attached over PCIe. The Rockchip SoC watchdog performs a *warm* reset: it resets the CPU cores but does **not** power-cycle the PCIe PHY or the NVMe drive. This is a known failure mode on these boards — after a watchdog-initiated reset, the PCIe link can come back untrained or in an undefined state. The kernel then logs streams of PCIe/AER link errors, or the boot hangs entirely because the root/data filesystem on NVMe cannot be found. A rig in that state looks exactly like ours: frozen, unresponsive, recoverable only by a full power cycle. In addition, 30 seconds is an aggressive timeout for a small ARM board doing sustained heavy I/O (backups, verify-and-delete); if PID 1 misses its watchdog deadline under load, the board hard-resets mid-write with no clean shutdown.

**The AP watchdog (commit `b41ad1b`) can enter a permanent restart/reboot loop, which multiplies exposure to the above.** Its escalation is: 3 failed 15-second checks → restart hostapd → if the next check still fails → reboot, with **no rate limit** on the reboot path. Its health check depends on `hostapd_cli ping` over a control socket that `ensure_hostapd_control` only just appended to the config file — the *running* hostapd doesn't have that socket until it is restarted, so on first deployment the ping is guaranteed to fail, and the watchdog restarts hostapd (dropping every connected user — the very symptom we were trying to fix). If anything about the socket is wrong long-term (hostapd actually loading a different conf file, an interface-name mismatch, `hostapd_cli` at a different path), the check *never* passes and the rig reboots roughly every two minutes forever. Every one of those reboots is another roll of the dice on the PCIe warm-reset problem.

**The identity sync (commit `4097216`) adds a corruption hazard on top.** It runs non-atomic `sed -i` edits of `/etc/hosts` and the hostapd config on every boot. On a machine that two watchdogs can now hard-reset at any moment, an interrupted in-place edit can truncate the hostapd config → hostapd fails to start → the AP watchdog reboots → loop. The SSID rewrite is also a silent behavior change: the next time hostapd restarts (which the AP watchdog now does on its own), the SSID changes to the hostname mid-session and clients with the old SSID saved won't rejoin.

**A diagnostic gap:** none of the three commits actually identifies the root cause of the original "AP visible but can't connect" symptom. That pattern is very often DHCP failure (dnsmasq dead or wedged) rather than hostapd — hostapd keeps beaconing while clients fail to get a lease — and the new watchdog does not check DHCP at all.

### Immediate recovery for stuck rigs

On any rig still running the three commits: remove `/etc/systemd/system.conf.d/skyseeker-watchdog.conf`, run `systemctl daemon-reload` and `systemctl daemon-reexec`, disable `skyseeker-ap-watchdog.timer`, then **full power cycle** (pull power — a `reboot` will not clear a bad PCIe link state). If the PCIe errors disappear on the reverted rig after a power cycle, that confirms the watchdog-reset attribution.

---

## 2. The plan: one controlled fix at a time

Rules for every step: one change per commit, deployed to **one** test rig, soaked for several days under real load (backup and verify-and-delete running) before the next step lands. If a step regresses anything, only one variable changed.

Step 1 is pulled forward as the **pre-flight package**: the basic polling and connection-cap changes needed for the next flight. Steps 2 onward continue afterwards at the normal one-at-a-time pace.

---

### Step 1 — Pre-flight: polling and connection-cap changes

Two small commits, both confined to the portal, landed together before the next flight. Neither grants any restart/reboot authority, so this is the lowest-risk slice of the whole plan.

#### Step 1a — Polling changes (one commit, agreed values)

**Issue:** The baseline dashboard polls aggressively (heartbeat every 1.5 s, home status every 1 s, sensors every 2 s, plus five slower pollers) with plain `setInterval`, which does not wait for the previous request to finish. On a slow link, requests stack up, saturate the tiny portal server, and make the "connected but nothing loads" state worse. Worse, the setup page keeps all five of its pollers running during capture even though the page is locked out then — pure load for zero benefit, at exactly the moment the rig is busiest.

**Proposed solution:** One commit with the agreed values. During capture, the dashboard's polling footprint reduces to the home status poll, the heartbeat, and a slow unlock check — everything else pauses.

| Poller | Interval | Behavior while capturing |
|---|---|---|
| `connection_heartbeat` (portal-local `/healthz`) | 1500 ms → **5000 ms** | runs |
| `home_status_poll` (`/api/status` + `/api/images_captured`; carries the altimeter reading) | **1000 ms (unchanged)** — altimeter must update every second | runs |
| `home_storage_poll` (storage bars + remaining-capture-time estimate) | **15000 ms (unchanged)** | **paused** |
| `sensors_poll` (`/api/status`) | 2000 ms (unchanged) | **slowed to 5000 ms** — keeps running only so the page notices capture ended and re-enables (this *is* the unlock check; one poller, not two, so duplicate `/api/status` requests are impossible) |
| `stats_poll` | 15000 ms (unchanged) | **paused** |
| `image_format_poll` | 15000 ms (unchanged) | **paused** |
| `netbird_poll` | 20000 ms (unchanged) | **paused** |
| `uplink_poll` | 10000 ms (unchanged) | **paused** |
| `backup_status_poll` / `verify_status_poll` | 2000/1000 ms (unchanged) | n/a — backup/verify can't run during capture |

All pollers additionally get a single-flight guard: a tick that finds the previous request still in flight is **skipped, not queued**, so at most one request per poller is ever outstanding and no catch-up burst fires when a stall clears. (At baseline, a wedged tricap plus the 20 s proxy timeout lets the 1 s status poll stack ~20 concurrent requests; only the heartbeat has a guard today.) Implementation notes: out-of-band refreshes — the immediate `poll()`/`pollStorage()` calls after a user action — must share the timer's single-flight key so they are skipped rather than duplicated when the timer's request is in flight; and pollers reschedule from the `finally` after completion (as `9bdeeb3`'s `runPeriodic` did) rather than via `setInterval`, so the spacing is guaranteed even when requests run long. No retry logic exists anywhere in the stack (JS or proxy) and none is added — a failed request's only "retry" is the next scheduled tick.

The pause-while-capturing rationale: the setup page is locked out during capture anyway, and the storage estimate's NVMe directory walk is the one poller that competes with the cameras for disk I/O — pausing it removes that contention exactly when it matters. The trade-off (no remaining-capture-time updates mid-flight) is accepted.

**Differs from the latest commits:** `9bdeeb3` slowed three intervals (heartbeat to 3000 ms, home status to 2000 ms, sensors to 3000 ms) and added single-flight guards, but kept every poller running during capture. This version instead keeps the home status poll at 1 s (the altimeter readout requires it), slows only the heartbeat, and gets its load reduction from pausing the setup-page and storage pollers during capture — a bigger reduction during flight than `9bdeeb3` achieved, with faster altimeter data.

**Differs from the safe baseline:** The baseline polls everything, always, with unbounded overlapping requests — roughly 2.5 requests/s per page even mid-flight. This drops the during-capture footprint to the status poll plus two slow checks, and caps every poller at one in-flight request.

#### Step 1b — Portal server accept queue

**Issue:** The portal's `ThreadingHTTPServer` uses Python's default accept backlog (5). A dashboard reconnect burst — exactly what happens when a phone rejoins after a Wi-Fi drop and every poller fires at once — can overflow the queue, so connections are refused and the user experiences "AP up but portal unreachable."

**Proposed solution:** Set `request_queue_size = 50` and `block_on_close = False` on `PortalServer`. No client-side changes in this commit.

The 50 is sized from the worst-case burst, not picked arbitrarily. The portal speaks HTTP/1.0 (no keep-alive), so every request is a short-lived connection and the backlog only has to absorb simultaneous *arrivals* — already-accepted requests, even ones stalled 20 s in the tricap proxy, live on handler threads and occupy no backlog slot. The worst burst per device is the reconnect moment: ~4 OS captive-portal probes (Android `generate_204`, iOS `hotspot-detect`, fired immediately on association) plus up to 6 parallel browser sockets as the dashboard reloads — ~10 simultaneous connections. Worst-case simultaneous devices is taken as 4 (two phones, a tablet, a laptop — more than a rig realistically sees at once). 4 × 10 = 40, plus a buffer of 10 = **50**. This burst profile is exactly what follows a hostapd restart, when every client rejoins at the same instant. Steady-state load is negligible by comparison: with step 1a's single-flight guards, a home page holds at most 3 in-flight requests and a setup page at most ~9 even with tricap fully stalled.

**Differs from the latest commits:** `9bdeeb3` used 128 — a number with no derivation, bundled with all the client polling changes and the hardware watchdog (its test even asserts `>= 128` and would need updating). Here the queue is sized from the measured burst profile with a stated buffer, and lands alone.

**Differs from the safe baseline:** The baseline keeps the default backlog of 5 — small enough that one single reconnecting phone (~10 simultaneous connections) can overflow it — and waits on open threads at shutdown. This covers a four-device simultaneous rejoin with headroom and lets service restarts complete promptly.

#### Interim fixes landed during the step-1 soak

**`f6cdb50` — AP dongle power management pinned off.** Field evidence (2026-08-16: two hard freezes in one day, both with a deliberately weak ~-70 dBm client parked on the AP; journal shows healthy-then-silence with no kernel warning) points at the AP dongle's out-of-tree `rtl8192eu` driver, whose power-state transitions are a known kernel-lockup trigger. The dongle is a TP-Link (USB `2357:0108`, RTL8192EU) on kernel 5.10, where the in-kernel `rtl8xxxu` driver has no AP mode — so no driver swap is possible. Mitigation: disable the driver's inactive power save (`rtw_ips_mode=0` — the only power feature that was enabled) and pin `rtw_power_mgnt=0`/`rtw_enusbss=0` via `modprobe.d`; pin USB autosuspend off via udev; assert `power_save off` each boot in the autodetect script. **The structural fix is replacing the dongle with a mainline-supported chipset (MT7612U-class, `mt76x2u` works on 5.10) once out of the field** — bench-soak it with a weak client before flying it.

**`ca20072` — stuck "Opening confirmation..." spinner.** Pre-existing baseline bug found while field-testing step 1 on skyseeker-2: pressing "Stop capture" and then choosing to keep capturing left the loading spinner on screen until capture was actually stopped. Cause: the confirmation flow cleared its loading state via `requestAnimationFrame(finish)`, and rAF passes a timestamp to its callback, which `finish(keepLoading)` interpreted as "keep the loading toast up". Fixed by wrapping the callback (`requestAnimationFrame(()=>finish())`). UI-only, no polling or server behavior touched, so it doesn't disturb the step-1 soak.

---

### Step 2 — Instrumentation (before any recovery automation)

**Issue:** We cannot attribute failures. The original AP drop was never root-caused, journald logs don't survive reboots by default, and watchdog resets leave no trace, so every incident is a guess.

**Proposed solution:** On the reverted rig, enable persistent journald (`Storage=persistent` in `journald.conf`) and deploy the AP health check in **log-only** mode: every 15 seconds, record hostapd service state, `iw` link/interface state, associated station count, dnsmasq (DHCP) status, and any `pcieport`/AER lines from dmesg — but take **no action**. When the next "AP visible / can't connect" event happens, this data tells us whether hostapd, the driver, or DHCP failed, which determines what a watchdog should even check.

**Differs from the latest commits:** `b41ad1b` shipped the health check with restart-and-reboot authority on day one, and doesn't observe DHCP at all. This step reuses the same check logic but strips all authority to act, and widens observation to DHCP and PCIe.

**Differs from the safe baseline:** `2f8436b` has no health monitoring and volatile logs — after a failure in the field there is nothing to analyze. This step adds eyes without adding risk.

---

### Step 3 — `udp_ip.sh` fix

**Issue:** The baseline script runs an infinite loop that, when the rig has no default gateway (the normal AP-only field state), invokes `nc -u` every 5 seconds with an *empty* destination and backgrounds it with `&`, never reaping it — spawning junk processes forever. It also announces whatever address `hostname -I` happens to list first, which may be the wrong interface.

**Proposed solution:** Re-land the `udp_ip.sh` rewrite from `4097216` exactly as written, but as its own commit: skip cleanly when there is no default route, resolve the source address from the actual route to the gateway, and bound `nc` with `timeout 2 ... -w 1` instead of backgrounding it.

**Differs from the latest commits:** Same code — the difference is purely that it lands alone, so its effect (or any regression in rig discovery on the office network) is attributable.

**Differs from the safe baseline:** The baseline leaks background `nc` processes and calls `nc` with an empty gateway argument every 5 seconds in the field. This is a strict cleanup of that behavior.

---

> **Status 2026-08-16:** steps 4 and 5 landed together as the "soft recovery"
> package after the field freezes: the control socket enabler in the autodetect
> script plus the restart-only watchdog (no reboot path in the code, 10-minute
> restart cooldown, dnsmasq check added for the "AP visible but no DHCP" case).
> The step-5 precondition (long false-positive soak of the health check) was
> consciously shortened under field pressure — the restart-only worst case is
> a client rejoin, and the cooldown bounds even that. Reboot escalation
> (step 6) remains unbuilt.

### Step 4 — hostapd control socket, enabled and verified manually

**Issue:** hostapd on the rig runs without a control socket, so nothing — human or watchdog — can ask it "are you actually alive?" as opposed to "is the systemd unit active?". Any future liveness check needs this, and it must be *proven* working before anything is allowed to act on it.

**Proposed solution:** Land `ensure_hostapd_control` (append `ctrl_interface=/run/hostapd` to the hostapd config) on its own, perform **one planned hostapd restart during maintenance** so the running instance picks it up, then manually verify `hostapd_cli -p /run/hostapd -i <iface> ping` returns `PONG` and `status` reports `state=ENABLED`.

**Differs from the latest commits:** `b41ad1b` appended the socket config and enabled a watchdog that depends on it *in the same deploy*, before the running hostapd had restarted — guaranteeing the watchdog's first checks failed and it kicked users off by restarting hostapd. Here the config change and its verification are complete, human-confirmed steps before any automation depends on the socket.

**Differs from the safe baseline:** The baseline has no control socket at all; this adds the capability with zero behavioral change to the running AP (until the one planned restart).

---

### Step 5 — AP watchdog, restart-only (no reboot)

**Issue:** When the AP path genuinely wedges (hostapd dead, driver dropped out of AP mode), nothing recovers it today — the rig needs a field visit. But a recovery agent with false positives is worse than none: it kicks users off a healthy AP.

**Proposed solution:** Enable the AP watchdog from `b41ad1b` with its escalation capped at **restarting hostapd** — the reboot path removed entirely, not just disabled. Precondition: step 2's log-only data shows a near-zero false-positive rate for the health check, and step 4 confirmed the control socket works. Keep the `/run/skyseeker-ap-watchdog.disabled` maintenance marker. Soak, and measure two things: how often it fires, and whether a hostapd restart actually recovers the failure it fires on.

**Differs from the latest commits:** `b41ad1b` granted restart *and* reboot authority simultaneously, on an unproven health check, with no false-positive data. This grants the mildest authority only, only after the check has earned trust.

**Differs from the safe baseline:** The baseline has no recovery at all — a dead hostapd stays dead until someone drives to the rig. This adds bounded self-healing whose worst case is a hostapd restart.

---

### Step 6 — Reboot escalation, only if the data demands it

**Issue:** Some failures (Wi-Fi driver or USB dongle wedged at the kernel level) may not be recoverable by restarting hostapd. But an ungated reboot path turns any persistent false negative into an infinite ~2-minute reboot loop.

**Proposed solution:** Only if step 5's data shows real failures that hostapd restarts do not recover, add reboot escalation with structural guards: never reboot within ~10 minutes of boot, at most one watchdog-initiated reboot per several hours (counter persisted on disk, not in `/run`), and a logged reason before every reboot. These guards make a reboot loop impossible by construction.

**Differs from the latest commits:** `b41ad1b`'s reboot path fires 15 seconds after a failed restart, unconditionally, forever, with its state in `/run` (wiped by the very reboot it triggers, so the loop never terminates). This version is opt-in based on evidence and rate-limited on persistent storage.

**Differs from the safe baseline:** The baseline never reboots on its own; this adds a last-resort recovery that cannot run away.

---

### Step 7 — Hardware watchdog, bench-proven or dropped

**Issue:** A true kernel/SoC lockup is unrecoverable by any userspace watchdog, so a hardware watchdog is attractive. But on this Rockchip board the watchdog's warm reset is the prime suspect for our PCIe errors and boot hangs — a "recovery" mechanism that converts a rare lockup into a bricked rig needing a field power-cycle is strictly worse than the lockup.

**Proposed solution:** On a **bench rig only**, arm the watchdog and deliberately hang the kernel (`echo c > /proc/sysrq-trigger`) at least five times. Ship it only if the board comes back cleanly *with NVMe detected and no PCIe/AER errors* every single time — and even then with a much longer timeout (120 s+) so heavy-I/O stalls can't trigger it spuriously. If the PCIe link does not reliably survive the warm reset (the expected outcome on this SoC), **drop this change permanently** and document why.

**Differs from the latest commits:** `9bdeeb3` shipped `RuntimeWatchdogSec=30s` straight to a production rig with no reset-survival testing and a tight timeout. Here the failure mode we've now experienced becomes an explicit pre-ship test with a documented kill criterion.

**Differs from the safe baseline:** The baseline has no hardware watchdog and hangs stay hung until a manual power cycle. If the bench test fails, we consciously keep the baseline behavior — a rare manual power cycle beats an automated brick.

---

### Step 8 — Identity sync, split and made safe

**Issue:** Rigs cloned from a common image can have a stale `/etc/hosts` entry (breaking sudo/name resolution warnings) and an SSID that doesn't match the rig's hostname, so two rigs in the field can broadcast the same network name. But the shipped fix rewrites system config files in place on every boot, on a machine watchdogs can reset mid-write.

**Proposed solution:** Two separate changes:

- **8a — `/etc/hosts` sync:** keep the boot-time `127.0.1.1` correction, but write atomically (write a temp file, then `mv` over the original) instead of `sed -i`.
- **8b — SSID rename:** remove it from the boot path entirely. Make it an explicit one-time provisioning command run by an operator when setting up a rig, which edits the config atomically and restarts hostapd deliberately, at a chosen moment. An SSID must never change underneath connected users because a watchdog happened to restart hostapd.

**Differs from the latest commits:** `4097216` did both edits with `sed -i` on every boot, and let the SSID change take effect at whatever unplanned moment hostapd next restarted. This keeps the intent (identity matches hostname) but removes the boot-time config-corruption window and the silent mid-session SSID switch.

**Differs from the safe baseline:** The baseline never fixes identity drift — stale hosts entries and duplicate SSIDs persist until someone edits files by hand. This automates the safe part and makes the disruptive part a deliberate operator action.

---

## 3. Sequencing logic

Step 1 is the pre-flight package: the polling and connection-cap changes, pure portal software with no authority to restart or reboot anything — the lowest-risk slice, pulled forward so the next flight benefits from it. Steps 2–4 (instrumentation, the `udp_ip.sh` cleanup, the hostapd control socket) build the evidence and plumbing that recovery automation depends on. Steps 5–7 grant recovery *authority* incrementally — restart, then rate-limited reboot, then hardware reset — and each grant must be justified by data from the previous step, not by the assumption that more recovery is better. Step 8 is independent cleanup, last because it touches system config files and is safest once no untested watchdog can reset the board mid-write.

At every point exactly one variable has changed on the test rig, so when something regresses we know what did it — which is the discipline the last three commits skipped.

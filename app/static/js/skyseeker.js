(function () {
  function qs(sel) { return document.querySelector(sel); }
  function qsa(sel) { return Array.prototype.slice.call(document.querySelectorAll(sel)); }
  function setText(sel, value) { var el = qs(sel); if (el) { el.textContent = value; } }
  function fmtGB(value) { return value === undefined || value === null || value === '' ? '--' : Number(value).toFixed(2).replace(/\.00$/, '') + 'GB'; }
  function fetchJson(url, options) { return fetch(url, options || {}).then(function (res) { if (!res.ok) { return res.json().catch(function () { return {}; }).then(function (body) { throw new Error(body.msg || res.statusText); }); } return res.json(); }); }
  function postJson(url, body) { return fetchJson(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) }); }
  function setUpdated(sel) { setText(sel, 'Updated ' + new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })); }

  function refreshHome() {
    Promise.all([
      fetchJson('/api/status').catch(function () { return {}; }),
      fetchJson('/api/images_captured').catch(function () { return {}; }),
      fetchJson('/api/statistics').catch(function () { return {}; }),
      fetchJson('/api/backup_status').catch(function () { return {}; }),
      fetch('/api/copy_eta').then(function (r) { return r.ok ? r.text() : ''; }).catch(function () { return ''; })
    ]).then(function (parts) {
      var status = parts[0], counts = parts[1], stats = parts[2], backup = parts[3], copy = parts[4];
      var mode = status.mode || 'STOPPED';
      setText('#sky-capture-state', mode.charAt(0) + mode.slice(1).toLowerCase());
      setText('#sky-wifi', (status.wifiSignal || 0) + ' dBm');
      setText('#sky-device-cameras', (status.cams || []).length);
      setText('#sky-camera-count', ((status.cams || []).length) + ' cameras');
      setText('#sky-device-gps', status.gps && status.gps.fix ? 'Yes' : 'No');
      setText('#sky-satellites', status.gps ? status.gps.satellites : 0);
      setText('#sky-snr-avg', status.gps ? status.gps.avg : 0);
      setText('#sky-gps-age', status.gps && status.gps.lastUpdate >= 0 ? Math.round(status.gps.lastUpdate) + 's ago' : 'no update');
      var dot = qs('#sky-capture-dot');
      if (dot) { dot.className = 'dot ' + (mode === 'STARTED' ? 'green' : (status.camError ? 'red' : '')); }
      var captured = (counts.imageCount || []).reduce(function (sum, n) { return sum + Number(n || 0); }, 0);
      var copied = (counts.copyCount || []).reduce(function (sum, n) { return sum + Number(n || 0); }, 0);
      setText('#sky-captured', captured);
      setText('#sky-copied', copied);
      var internal = stats.internalStorage || {}, external = stats.externalStorage || {};
      setText('#sky-int-free', fmtGB(internal.freeGB));
      setText('#sky-int-used', fmtGB(internal.usedGB));
      setText('#sky-int-capacity', fmtGB(internal.capacityGB));
      setText('#sky-ext-free', fmtGB(external.freeGB));
      setText('#sky-ext-used', fmtGB(external.usedGB));
      setText('#sky-ext-capacity', fmtGB(external.capacityGB));
      if (copy) { setText('#sky-copy-progress', copy); }
      else if (backup.running) { setText('#sky-copy-progress', 'Backup ' + backup.phase + ' ' + backup.percent + '%'); }
      else { setText('#sky-copy-progress', 'No active copy reported.'); }
      setUpdated('#sky-updated');
    });
  }

  function refreshSetup() {
    Promise.all([
      fetchJson('/api/status').catch(function () { return {}; }),
      fetchJson('/api/statistics').catch(function () { return {}; }),
      fetchJson('/api/backup_status').catch(function () { return {}; }),
      fetchJson('/api/netbird_status').catch(function () { return {}; }),
      fetchJson('/api/lensNumber').catch(function () { return {}; })
    ]).then(function (parts) {
      var status = parts[0], stats = parts[1], backup = parts[2], netbird = parts[3], lens = parts[4];
      if (stats.captureInterval !== undefined) { setText('#capture-interval-value', Number(stats.captureInterval).toFixed(1)); }
      setText('#setup-wifi', (status.wifiSignal || 0) + ' dBm');
      setText('#setup-satellites', status.gps ? status.gps.satellites : '--');
      setText('#setup-pdop', status.gps ? status.gps.pdop : '--');
      setText('#setup-gps-age', status.gps && status.gps.lastUpdate >= 0 ? Math.round(status.gps.lastUpdate) + 's' : '--');
      setText('#setup-snr-min', status.gps ? status.gps.min : '--');
      setText('#setup-snr-avg', status.gps ? status.gps.avg : '--');
      setText('#setup-snr-max', status.gps ? status.gps.max : '--');
      setText('#setup-lens', lens.lens || '--');
      setText('#sensor-pill', status.mode || '--');
      var pct = Number(backup.percent || 0), fill = qs('#backup-progress');
      if (fill) { fill.style.width = pct + '%'; }
      setText('#backup-status', backup.running ? (backup.phase + ' ' + pct + '% (' + backup.files_done + '/' + backup.files_total + ' files)') : (backup.phase || 'idle'));
      setText('#netbird-pill', netbird.connected ? 'connected' : 'offline');
      setText('#netbird-status', netbird.connected ? 'Connected' : 'Disconnected');
      setUpdated('#setup-updated');
    });
  }

  function initHome() { refreshHome(); setInterval(refreshHome, 3000); }
  function initSetup() {
    function updateInterval(delta) {
      var displayed = Number((qs('#capture-interval-value') || {}).textContent || 0);
      var next = Math.max(0.1, Math.round((displayed + delta) * 10) / 10);
      setText('#interval-status', 'Saving...');
      postJson('/api/capture_interval', { interval: String(next) }).then(function () { setText('#capture-interval-value', next.toFixed(1)); setText('#interval-status', 'Saved'); }).catch(function (err) { setText('#interval-status', err.message); });
    }
    qsa('[data-interval-delta]').forEach(function (button) { button.addEventListener('click', function () { updateInterval(Number(button.getAttribute('data-interval-delta'))); }); });
    var backupStart = qs('#backup-start'); if (backupStart) { backupStart.addEventListener('click', function () { setText('#backup-status', 'Starting backup...'); fetchJson('/api/backup_start').then(refreshSetup).catch(function (err) { setText('#backup-status', err.message); }); }); }
    var verify = qs('#backup-verify-delete'); if (verify) { verify.addEventListener('click', function () { if (!confirm('Verify backup and delete matched source files?')) { return; } setText('#backup-status', 'Verifying...'); fetchJson('/api/verify_and_delete').then(refreshSetup).catch(function (err) { setText('#backup-status', err.message); }); }); }
    qsa('[data-download-url]').forEach(function (button) { button.addEventListener('click', function () { window.location.href = button.getAttribute('data-download-url'); }); });
    var restart = qs('#restart-tricap'); if (restart) { restart.addEventListener('click', function () { setText('#restart-status', 'Restarting service...'); fetchJson('/api/restart').catch(function () {}).finally(function () { setText('#restart-status', 'Restart requested. Refresh after a few seconds.'); }); }); }
    var reboot = qs('#reboot-device'); if (reboot) { reboot.addEventListener('click', function () { if (!confirm('Reboot the device now?')) { return; } setText('#restart-status', 'Reboot requested...'); fetchJson('/api/reboot').catch(function (err) { setText('#restart-status', err.message); }); }); }
    var setKey = qs('#netbird-set-key'); if (setKey) { setKey.addEventListener('click', function () { var key = (qs('#netbird-key') || {}).value || ''; setText('#netbird-status', 'Setting key...'); postJson('/api/netbird_key', { key: key }).then(refreshSetup).catch(function (err) { setText('#netbird-status', err.message); }); }); }
    var connect = qs('#netbird-connect'); if (connect) { connect.addEventListener('click', function () { setText('#netbird-status', 'Connecting...'); postJson('/api/netbird_connect').then(refreshSetup).catch(function (err) { setText('#netbird-status', err.message); }); }); }
    var disconnect = qs('#netbird-disconnect'); if (disconnect) { disconnect.addEventListener('click', function () { setText('#netbird-status', 'Disconnecting...'); postJson('/api/netbird_disconnect').then(refreshSetup).catch(function (err) { setText('#netbird-status', err.message); }); }); }
    refreshSetup(); setInterval(refreshSetup, 3000);
  }
  document.addEventListener('DOMContentLoaded', function () { var page = document.body.getAttribute('data-page'); if (page === 'home') { initHome(); } if (page === 'setup') { initSetup(); } });
})();
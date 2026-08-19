(function () {
  function qs(sel) { return document.querySelector(sel); }
  function qsa(sel) { return Array.prototype.slice.call(document.querySelectorAll(sel)); }
  function setText(sel, value) { var el = qs(sel); if (el) { el.textContent = value; } }
  function fmtGB(value) { return value === undefined || value === null || value === '' ? '--' : Number(value).toFixed(2).replace(/\.00$/, '') + 'GB'; }
  function fetchJson(url, options) { return fetch(url, options || {}).then(function (res) { if (!res.ok) { return res.json().catch(function () { return {}; }).then(function (body) { throw new Error(body.msg || res.statusText); }); } return res.json(); }); }
  function postJson(url, body) { return fetchJson(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) }); }
  function syncPhoneClock() {
    var now = new Date();
    return postJson('/api/sync_phone_time', {
      epochMs: now.getTime(),
      timezoneOffsetMinutes: now.getTimezoneOffset()
    });
  }
  function setUpdated(sel) { setText(sel, 'Updated ' + new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })); }
  function toast(message) {
    var target = qs('#sky-action-toast');
    if (!target) { return; }
    target.textContent = message;
    target.classList.remove('loading');
    target.classList.add('show');
    clearTimeout(target._hideTimer);
    target._hideTimer = setTimeout(function () { target.classList.remove('show'); }, 2800);
  }
  function loadingToast(message) {
    var target = qs('#sky-action-toast'), spinner, label;
    if (!target) { return; }
    spinner = document.createElement('span');
    spinner.className = 'sky-toast-spinner';
    spinner.setAttribute('aria-hidden', 'true');
    label = document.createElement('span');
    label.textContent = message;
    target.textContent = '';
    target.appendChild(spinner);
    target.appendChild(label);
    target.classList.add('show', 'loading');
    clearTimeout(target._hideTimer);
  }
  function hideLoadingToast() {
    var target = qs('#sky-action-toast');
    if (target && target.classList.contains('loading')) { target.classList.remove('show', 'loading'); }
  }
  function beginAction(control, message, softDisable) {
    var finished = false;
    if (!control || control.disabled || control.getAttribute('data-action-busy') === 'true') { return null; }
    control.setAttribute('data-action-busy', 'true');
    control.setAttribute('aria-busy', 'true');
    control.classList.add('sky-action-busy');
    if (!softDisable && 'disabled' in control) { control.disabled = true; }
    else { control.setAttribute('aria-disabled', 'true'); }
    loadingToast(message);
    return function (keepLoading) {
      if (finished) { return; }
      finished = true;
      control.removeAttribute('data-action-busy');
      control.removeAttribute('aria-busy');
      control.removeAttribute('aria-disabled');
      control.classList.remove('sky-action-busy');
      if ('disabled' in control) { control.disabled = false; }
      if (!keepLoading) { hideLoadingToast(); }
    };
  }
  window.SkySeekerActions = { begin: beginAction, toast: toast, loading: loadingToast };
  window.SkySeekerClock = { sync: syncPhoneClock };

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

  var setupBackupRunning = false;
  function refreshSetup() {
    Promise.all([
      fetchJson('/api/status').catch(function () { return {}; }),
      fetchJson('/api/statistics').catch(function () { return {}; }),
      fetchJson('/api/backup_status').catch(function () { return {}; }),
      fetchJson('/api/netbird_status').catch(function () { return {}; }),
      fetchJson('/api/lensNumber').catch(function () { return {}; }),
      fetchJson('/api/sony_image_format').catch(function () { return {}; })
    ]).then(function (parts) {
      var status = parts[0], stats = parts[1], backup = parts[2], netbird = parts[3], lens = parts[4], imageFormat = parts[5];
      var backupWasRunning = setupBackupRunning;
      setupBackupRunning = Boolean(backup.running);
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
      ['#backup-start', '#backup-move', '#backup-verify-delete'].forEach(function (selector) {
        var button = qs(selector);
        if (button) { button.disabled = setupBackupRunning || button.getAttribute('data-action-busy') === 'true'; }
      });
      if (setupBackupRunning) { loadingToast('Copying to SSD... ' + Math.round(pct) + '%'); }
      else if (backupWasRunning) { toast(backup.message || 'Backup complete'); }
      if (imageFormat.value) {
        setText('#camera-format-value', imageFormat.value);
        qsa('[data-image-format]').forEach(function (button) {
          var active = button.getAttribute('data-image-format') === imageFormat.value;
          button.classList.toggle('active', active);
          button.setAttribute('aria-pressed', active ? 'true' : 'false');
          button.disabled = status.mode === 'STARTED' || status.mode === 'COPYING' ||
            button.getAttribute('data-action-busy') === 'true';
        });
      }
      setText('#netbird-pill', netbird.connected ? 'connected' : 'offline');
      setText('#netbird-status', netbird.connected ? 'Connected' : 'Disconnected');
      setUpdated('#setup-updated');
    });
  }

  function initHome() { refreshHome(); setInterval(refreshHome, 3000); }
  function initSetup() {
    function updateInterval(delta, button) {
      var displayed = Number((qs('#capture-interval-value') || {}).textContent || 0);
      var next = Math.max(0.1, Math.round((displayed + delta) * 10) / 10);
      var finish = beginAction(button, 'Saving capture interval...');
      if (!finish) { return; }
      setText('#interval-status', 'Saving...');
      postJson('/api/capture_interval', { interval: String(next) })
        .then(function () { setText('#capture-interval-value', next.toFixed(1)); setText('#interval-status', 'Saved'); toast('Capture interval saved'); })
        .catch(function (err) { setText('#interval-status', err.message); toast(err.message); })
        .then(function () { finish(); });
    }
    function requestAction(button, message, request, success, failure) {
      var finish = beginAction(button, message);
      if (!finish) { return; }
      request().then(function (result) {
        if (success) { success(result); }
      }).catch(function (err) {
        if (failure) { failure(err); }
        toast(err.message);
      }).then(function () { finish(setupBackupRunning); });
    }
    qsa('[data-interval-delta]').forEach(function (button) { button.addEventListener('click', function () { updateInterval(Number(button.getAttribute('data-interval-delta')), button); }); });
    qsa('[data-image-format]').forEach(function (button) { button.addEventListener('click', function () {
      if (button.classList.contains('active')) { return; }
      requestAction(
        button,
        'Saving image format...',
        function () { return postJson('/api/sony_image_format', { value: button.getAttribute('data-image-format') }); },
        function (result) { setText('#camera-format-value', result.value); toast('Image format set to ' + result.value); refreshSetup(); }
      );
    }); });
    var backupStart = qs('#backup-start'); if (backupStart) { backupStart.addEventListener('click', function () {
      setText('#backup-status', 'Starting backup...');
      requestAction(backupStart, 'Starting backup...', function () { return fetchJson('/api/backup_start'); }, function (result) {
        if (result && result.success === false) { throw new Error(result.msg || 'Backup failed to start'); }
        setupBackupRunning = true;
        loadingToast('Copying to SSD...');
        refreshSetup();
      }, function (err) { setText('#backup-status', err.message); });
    }); }
    var move = qs('#backup-move'); if (move) { move.addEventListener('click', function () {
      if (!confirm('Copy files to the SSD and delete them from internal storage as they are verified?')) { return; }
      setText('#backup-status', 'Starting copy & delete...');
      requestAction(move, 'Starting copy & delete...', function () { return fetchJson('/api/backup_move'); }, function (result) {
        if (result && result.success === false) { throw new Error(result.msg || 'Copy & delete failed to start'); }
        setupBackupRunning = true;
        loadingToast('Moving to SSD...');
        refreshSetup();
      }, function (err) { setText('#backup-status', err.message); });
    }); }
    var verify = qs('#backup-verify-delete'); if (verify) { verify.addEventListener('click', function () {
      if (!confirm('Verify backup and delete matched source files?')) { return; }
      setText('#backup-status', 'Verifying...');
      requestAction(verify, 'Starting verification...', function () { return fetchJson('/api/verify_and_delete'); }, refreshSetup, function (err) { setText('#backup-status', err.message); });
    }); }
    qsa('[data-download-url]').forEach(function (button) { button.addEventListener('click', function () {
      var finish = beginAction(button, 'Preparing download...');
      if (!finish) { return; }
      setTimeout(function () { window.location.href = button.getAttribute('data-download-url'); }, 0);
      setTimeout(finish, 1500);
    }); });
    var restart = qs('#restart-tricap'); if (restart) { restart.addEventListener('click', function () {
      requestAction(restart, 'Restarting tricap...', function () { return fetchJson('/api/restart'); }, function () { setText('#restart-status', 'Restart requested. Refresh after a few seconds.'); toast('Restart requested'); });
    }); }
    var reboot = qs('#reboot-device'); if (reboot) { reboot.addEventListener('click', function () {
      if (!confirm('Reboot the device now?')) { return; }
      requestAction(reboot, 'Requesting reboot...', function () { return fetchJson('/api/reboot'); }, function () { setText('#restart-status', 'Reboot requested...'); toast('Reboot requested'); }, function (err) { setText('#restart-status', err.message); });
    }); }
    var setKey = qs('#netbird-set-key'); if (setKey) { setKey.addEventListener('click', function () {
      var key = (qs('#netbird-key') || {}).value || '';
      setText('#netbird-status', 'Setting key...');
      requestAction(setKey, 'Setting remote-access key...', function () { return postJson('/api/netbird_key', { key: key }); }, refreshSetup, function (err) { setText('#netbird-status', err.message); });
    }); }
    var connect = qs('#netbird-connect'); if (connect) { connect.addEventListener('click', function () {
      setText('#netbird-status', 'Connecting...');
      requestAction(connect, 'Connecting remote access...', function () { return postJson('/api/netbird_connect'); }, refreshSetup, function (err) { setText('#netbird-status', err.message); });
    }); }
    var disconnect = qs('#netbird-disconnect'); if (disconnect) { disconnect.addEventListener('click', function () {
      setText('#netbird-status', 'Disconnecting...');
      requestAction(disconnect, 'Disconnecting remote access...', function () { return postJson('/api/netbird_disconnect'); }, refreshSetup, function (err) { setText('#netbird-status', err.message); });
    }); }
    var settingsForm = qs('#form'); if (settingsForm) { settingsForm.addEventListener('submit', function (event) {
      var button = event.submitter || document.activeElement;
      if (!beginAction(button, button && button.id === 'btn_revert' ? 'Restoring defaults...' : 'Saving settings...', true)) { event.preventDefault(); }
    }); }
    refreshSetup(); setInterval(refreshSetup, 3000);
  }
  document.addEventListener('DOMContentLoaded', function () {
    syncPhoneClock().catch(function () {});
    var page = document.body.getAttribute('data-page');
    if (page === 'home') { initHome(); }
    if (page === 'setup') { initSetup(); }
  });
})();

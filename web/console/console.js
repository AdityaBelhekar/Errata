/* ═══════════════════════════════════════════════════════════════════════════
   ERRATA CONSOLE — FE-7

   Renders Evidence Bundles and records decisions in the real ledger.

   It has no extractor, no PDF library and no knowledge of what a PDF is. That
   is not an omission — it is FR-7.8 made structural: "evidence shown is
   reconstructible from stored state, not regenerated at view time". There is
   no code path here that could regenerate evidence, so the console cannot show
   a reviewer something the ledger cannot reproduce.

   Every geometry it draws was projected once, at bundle time, by
   errata_bundle.geometry, and stored as a fraction of the rendered page. The
   console multiplies by the page's on-screen size. That is the whole of its
   coordinate maths.

   NO FRAMEWORK, AND THAT IS A DECISION
   ------------------------------------
   The advanced stack here is the platform, not a dependency tree: native
   <dialog> for the focus trap, the View Transitions API for record switching,
   container queries for the text layer, WebCrypto for verification. Each
   replaces a library that would otherwise need auditing, bundling and shipping
   inside a product whose README hook is that it runs from a clean clone with
   no signup (FR-7.9).

   Where a framework WOULD earn its place is FE-7b: the 1.2M-row virtual queue
   and the as-of time model. That is a real argument to have then, with the
   problem in front of us, rather than now, in advance of it.
   ═══════════════════════════════════════════════════════════════════════════ */

(function () {
  'use strict';

  var API = '/api';

  var state = {
    queue: [],          // index entries, joined to decisions
    filter: 'undecided',
    sku: null,
    manifest: null,
    redlines: null,
    words: null,
    finding: null,
    page: null,
    zoom: 'fit',
    manifestDigest: null,
    identity: null,
    presentedUtc: null,
    busy: false
  };

  /* ── small helpers ─────────────────────────────────────────────────── */

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }
  function svgEl(tag, attrs) {
    var n = document.createElementNS('http://www.w3.org/2000/svg', tag);
    for (var k in attrs) n.setAttribute(k, attrs[k]);
    return n;
  }
  function $(id) { return document.getElementById(id); }

  function getJSON(url) {
    return fetch(url, { cache: 'no-store' }).then(function (r) {
      if (!r.ok) throw new Error(r.status + ' ' + url);
      return r.json();
    });
  }
  function postJSON(url, body) {
    return fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    }).then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); });
  }

  function say(message) { $('say').textContent = message; }

  function toast(title, detail, kind) {
    var region = $('toasts');
    var node = el('div', 'toast');
    node.setAttribute('role', kind === 'error' ? 'alert' : 'status');
    if (kind) node.dataset.state = kind;
    var body = el('div');
    body.appendChild(el('div', 'toast-title t-h4', title));
    if (detail) body.appendChild(el('div', 't-body-s u-dim', detail));
    node.appendChild(body);
    var close = el('button', 'icon-btn', '×');
    close.setAttribute('aria-label', 'Dismiss');
    close.addEventListener('click', function () { node.remove(); });
    node.appendChild(close);
    region.appendChild(node);
    // 6s auto-dismiss per §13.1, but errors stay: a message that explains why a
    // decision was refused must not vanish before it has been read.
    if (kind !== 'error') setTimeout(function () { node.remove(); }, 6000);
  }

  /* Render inside a view transition where the platform supports one. The
     fallback is simply doing the work — never a hand-rolled animation, because
     a bespoke crossfade that only fires on some browsers is worse than a plain
     repaint everywhere. */
  var activeTransition = null;

  function transition(fn) {
    if (!document.startViewTransition || matchMedia('(prefers-reduced-motion: reduce)').matches) {
      fn();
      return;
    }
    // Starting a transition while one is running SKIPS the old one and rejects
    // its promises. Holding j to move down the queue does exactly that, several
    // times a second, and every rejection surfaces as an unhandled
    // InvalidStateError in the console. So: catch them, and never let a failed
    // decoration stop the render from happening.
    try {
      var t = document.startViewTransition(fn);
      activeTransition = t;
      var swallow = function () {};
      if (t.finished && t.finished.catch) t.finished.catch(swallow);
      if (t.ready && t.ready.catch) t.ready.catch(swallow);
      if (t.updateCallbackDone && t.updateCallbackDone.catch) t.updateCallbackDone.catch(swallow);
    } catch (e) {
      fn();
    }
  }

  /* ── identity (FR-7.6 actor · FR-9.3 role) ─────────────────────────── */

  var identity = {
    load: function () {
      try { state.identity = JSON.parse(localStorage.getItem('errata-reviewer') || 'null'); }
      catch (e) { state.identity = null; }
      identity.render();
    },
    save: function (name, role) {
      state.identity = { name: name, role: role };
      try { localStorage.setItem('errata-reviewer', JSON.stringify(state.identity)); } catch (e) {}
      identity.render();
    },
    render: function () {
      var chip = $('identity-btn');
      var label = $('identity-label');
      if (state.identity && state.identity.name) {
        label.textContent = state.identity.name;
        chip.dataset.set = 'true';
        chip.dataset.role = state.identity.role;
        chip.title = state.identity.role === 'implementer'
          ? 'Implementer. Decisions are recorded but excluded from the FR-9.3 reviewer-seconds rate.'
          : 'Domain reviewer. Decisions count toward FR-9.3.';
      } else {
        label.textContent = 'Set reviewer';
        chip.dataset.set = 'false';
        chip.removeAttribute('data-role');
      }
      renderDecisionBar();
    },
    prompt: function () {
      var dialog = $('identity-dialog');
      $('identity-name').value = (state.identity && state.identity.name) || '';
      var role = (state.identity && state.identity.role) || 'domain_reviewer';
      var radio = document.querySelector('input[name="role"][value="' + role + '"]');
      if (radio) radio.checked = true;
      dialog.showModal();
    }
  };

  /* ── FR-9.3 · the reviewer-seconds timer ───────────────────────────────
     Pauses on blur and counts the pauses. A figure that keeps running while
     somebody answers Slack is not a measurement of review, and this is the
     metric the PRD calls the one a buyer actually pays for. Both endpoints are
     also recorded, so the duration can be checked rather than trusted. */

  var timer = {
    ms: 0, last: null, paused: false, pauses: 0, node: null,
    start: function () {
      this.ms = 0; this.pauses = 0; this.paused = false;
      this.last = performance.now();
      state.presentedUtc = new Date().toISOString();
      this.render();
    },
    tick: function () {
      var now = performance.now();
      if (!this.paused && this.last != null) this.ms += now - this.last;
      this.last = now;
      this.render();
    },
    pause: function () { if (!this.paused) { this.tick(); this.paused = true; this.pauses += 1; this.render(); } },
    resume: function () { if (this.paused) { this.paused = false; this.last = performance.now(); this.render(); } },
    seconds: function () { this.tick(); return +(this.ms / 1000).toFixed(2); },
    render: function () {
      if (!this.node) return;
      this.node.textContent = (this.ms / 1000).toFixed(1) + ' s';
      this.node.dataset.paused = String(this.paused);
      this.node.title = 'FR-9.3 reviewer-seconds on this record. Paused ' + this.pauses +
        ' time(s) — pauses are counted, not hidden.';
    }
  };

  /* ── queue ─────────────────────────────────────────────────────────── */

  function visibleQueue() {
    return state.queue.filter(function (e) {
      if (state.filter === 'all') return true;
      var decided = e.decisions && Object.keys(e.decisions).length;
      return state.filter === 'decided' ? decided : !decided;
    });
  }

  function decisionOf(entry) {
    var d = entry.decisions || {};
    var keys = Object.keys(d);
    return keys.length ? d[keys[0]] : null;
  }

  function queueSentence(entry, finding) {
    var s = el('span', 'queue-sentence t-body');
    s.appendChild(el('span', 'sku', entry.sku));
    s.appendChild(document.createTextNode(' says ' + (finding.label || finding.attribute).toLowerCase() + ' is '));
    s.appendChild(el('span', 'val was', finding.catalog_value || '—'));
    var ev = (finding.evidence || [])[0];
    s.appendChild(document.createTextNode(
      ev && ev.page
        ? '. Page ' + ev.page + (ev.column_header ? ', column “' + ev.column_header + '”' : '') + ' says '
        : '. The document says '
    ));
    s.appendChild(el('span', 'val', finding.derived_value || '—'));
    s.appendChild(document.createTextNode('.'));
    return s;
  }

  function blastLine(finding) {
    var b = finding.blast || {};
    var wrap = el('span', 'blast t-micro');
    function add(name, value, safety) {
      var x = el('span');
      if (safety) x.dataset.safety = 'true';
      x.appendChild(document.createTextNode(name));
      x.appendChild(el('span', 'f', value));
      wrap.appendChild(x);
    }
    // Each factor separately (FR-8.4). Absent factors are omitted, never
    // defaulted: a rendered 1.0 is indistinguishable from a measured 1.0.
    if (b.safety_class_multiplier != null) add('Safety class', '×' + b.safety_class_multiplier, b.safety_class_multiplier > 1);
    if (b.revenue_weight != null) add('Revenue', b.revenue_weight);
    if (b.propagation_count != null) add('Propagates to', b.propagation_count);
    if (b.record_multiplicity != null) add('Shared by', b.record_multiplicity + ' SKU(s)');
    return wrap;
  }

  var findingCache = {};

  function loadFinding(sku) {
    if (findingCache[sku]) return Promise.resolve(findingCache[sku]);
    return getJSON(API + '/bundle/' + sku + '/redlines.json').then(function (r) {
      findingCache[sku] = (r.findings || [])[0] || null;
      return findingCache[sku];
    });
  }

  function renderQueue() {
    var list = $('queue-list');
    var rows = visibleQueue();
    list.innerHTML = '';

    // The container is only a listbox while it holds options. An empty one fails
    // aria-required-children, and with tabindex=0 it is also a focus stop containing nothing --
    // a keyboard user tabs into a box that announces itself and has no contents.
    if (rows.length) {
      list.setAttribute('role', 'listbox');
      list.setAttribute('tabindex', '0');
    } else {
      list.removeAttribute('role');
      list.removeAttribute('tabindex');
    }

    if (!rows.length) {
      var e = el('div', 'queue-empty');
      if (state.filter === 'undecided' && state.queue.length) {
        e.appendChild(el('span', 't-h4', 'Everything here is decided'));
        e.appendChild(el('span', 't-body-s u-dimmer', 'Switch to All to review what you did, or run another audit.'));
      } else if (!state.queue.length) {
        e.appendChild(el('span', 't-h4', 'Nothing disagrees with its evidence'));
        e.appendChild(el('span', 't-body-s u-dimmer', 'Either no findings, or no bundles have been built yet.'));
      } else {
        e.appendChild(el('span', 't-h4', 'Nothing decided yet'));
      }
      list.appendChild(e);
      return;
    }

    rows.forEach(function (entry) {
      var row = el('div', 'queue-row');
      row.setAttribute('role', 'option');
      row.setAttribute('aria-selected', String(entry.sku === state.sku));
      row.tabIndex = -1;
      row.dataset.sku = entry.sku;
      row.dataset.state = 'disputed';

      var decision = decisionOf(entry);
      if (decision) {
        row.dataset.decided = decision.decision;
        row.dataset.state = decision.decision === 'accept_redline' ? 'settled' : 'declined';
      }

      var skeleton = el('span', 'queue-sentence t-body skel skel--pulse');
      skeleton.textContent = ' ';
      row.appendChild(skeleton);
      row.addEventListener('click', function () { select(entry.sku); });
      list.appendChild(row);

      loadFinding(entry.sku).then(function (f) {
        if (!f) return;
        row.innerHTML = '';
        row.appendChild(queueSentence(entry, f));
        row.appendChild(blastLine(f));
        if (decision) {
          var mark = el('span', 'decided-mark t-micro');
          mark.dataset.decision = decision.decision;
          mark.textContent = decisionLabel(decision.decision) +
            (decision.decided_by ? ' · ' + decision.decided_by : '') +
            (decision.seconds != null ? ' · ' + decision.seconds + ' s' : '');
          row.appendChild(mark);
        }
      });
    });
  }

  function decisionLabel(value) {
    return { accept_redline: 'Accepted', keep_catalog: 'Kept catalog', escalate: 'Escalated' }[value] || value;
  }

  function renderProgress() {
    var total = state.queue.length;
    var done = state.queue.filter(function (e) { return decisionOf(e); }).length;
    $('progress-fill').style.width = total ? (100 * done / total) + '%' : '0';
    $('progress-label').textContent = done + ' of ' + total + ' decided';
    $('progress').setAttribute('title', done + ' of ' + total + ' findings have a recorded decision');
  }

  /* ── the evidence page ─────────────────────────────────────────────── */

  function renderPage(pageNumber) {
    var base = API + '/bundle/' + state.sku;
    var projection = state.manifest.projections[String(pageNumber)];
    var sheet = $('sheet');
    var img = $('page-img');
    var overlay = $('overlay');
    var textlayer = $('textlayer');

    state.page = pageNumber;
    sheet.style.aspectRatio = projection.pixel_width + ' / ' + projection.pixel_height;
    // alt stays empty: the raster is presentational, the text layer carries the
    // content. See the comment beside the sheet in index.html.
    img.alt = '';
    img.src = base + '/pages/p' + pageNumber + '.png';

    overlay.setAttribute('viewBox', '0 0 1 1');
    overlay.innerHTML = '';
    textlayer.innerHTML = '';

    var words = (state.words && state.words[String(pageNumber)]) || [];
    var frag = document.createDocumentFragment();
    var made = [];
    words.forEach(function (w) {
      var b = w.b;
      var span = document.createElement('span');
      span.textContent = w.t;
      span.style.left = (b[0] * 100) + '%';
      span.style.top = (b[1] * 100) + '%';
      // `cqh` — 1% of the CONTAINER's height — not `%`. A percentage font-size
      // resolves against the PARENT'S font size, which once produced 0.147px
      // text: invisible and unselectable, quietly defeating L-6 while the
      // layer still looked present in the DOM.
      span.style.fontSize = ((b[3] - b[1]) * 100) + 'cqh';
      frag.appendChild(span);
      made.push({ node: span, target: b[2] - b[0] });
    });
    textlayer.appendChild(frag);

    // Squeeze each word to its true width: the raster used the document's font
    // and this uses the reader's. Measured in one batch and applied in a
    // second, so it costs one layout rather than one per word.
    var sheetWidth = sheet.getBoundingClientRect().width || 1;
    var widths = made.map(function (m) { return m.node.getBoundingClientRect().width; });
    made.forEach(function (m, i) {
      var want = m.target * sheetWidth;
      if (widths[i] > 0.5 && want > 0.5) m.node.style.transform = 'scaleX(' + (want / widths[i]).toFixed(4) + ')';
    });

    drawMarks(overlay, pageNumber);
  }

  function drawMarks(overlay, pageNumber) {
    var finding = state.finding;
    if (!finding) return;

    var evidence = (finding.evidence || []).filter(function (e) { return e.page === pageNumber && e.box; });
    var counter = (finding.counter_evidence || []).filter(function (e) { return e.page === pageNumber && e.box; });

    // Which span is THE VALUE and which are its HEADERS? The bundle says so: an
    // evidence item whose table_cell equals a header string IS the header. A
    // property of the data, not a guess about ordering.
    var value = null, headers = [];
    evidence.forEach(function (e) {
      var isHeader = e.table_cell && (e.table_cell === e.column_header || e.table_cell === e.row_header);
      if (!isHeader && !value) value = e; else headers.push(e);
    });
    if (!value && evidence.length) { value = evidence[0]; headers = evidence.slice(1); }

    headers.forEach(function (h) {
      var b = h.box, pad = 0.002;
      var arm = Math.min(0.012, (b[2] - b[0]) / 3);
      overlay.appendChild(svgEl('path', { 'class': 'mark-header',
        d: 'M' + (b[0] - pad + arm) + ' ' + (b[1] - pad) + ' H' + (b[0] - pad) + ' V' + (b[3] + pad) + ' H' + (b[0] - pad + arm) }));
      overlay.appendChild(svgEl('path', { 'class': 'mark-header',
        d: 'M' + (b[2] + pad - arm) + ' ' + (b[1] - pad) + ' H' + (b[2] + pad) + ' V' + (b[3] + pad) + ' H' + (b[2] + pad - arm) }));
      if (value) {
        overlay.appendChild(svgEl('line', { 'class': 'mark-leader',
          x1: (b[0] + b[2]) / 2, y1: (b[1] + b[3]) / 2,
          x2: (value.box[0] + value.box[2]) / 2, y2: (value.box[1] + value.box[3]) / 2 }));
      }
    });

    if (value) {
      var b = value.box, pad = 0.002;
      overlay.appendChild(svgEl('rect', { 'class': 'mark-value',
        x: b[0] - pad, y: b[1] - pad, width: (b[2] - b[0]) + 2 * pad, height: (b[3] - b[1]) + 2 * pad }));
      overlay.appendChild(svgEl('line', { 'class': 'mark-reveal',
        x1: b[0] - pad, y1: b[1] - pad, x2: b[0] - pad, y2: b[3] + pad }));
      state.valueBox = b;
    }

    counter.forEach(function (c) {
      var cb = c.box, cpad = 0.003;
      overlay.appendChild(svgEl('rect', { 'class': 'mark-counter',
        x: cb[0] - cpad, y: cb[1] - cpad, width: (cb[2] - cb[0]) + 2 * cpad, height: (cb[3] - cb[1]) + 2 * cpad }));
    });
  }

  /* Scroll the evidence so the value is in view. The single highest-value UX
     decision in this pane: an A4 page at readable zoom is four screens tall,
     and a reviewer who has to hunt for the box pays for the hunt in the metric
     the product is sold on. */
  /* The height, in CSS pixels, we want the disputed value's own box to occupy.
     A datasheet table cell is ~8pt; at "fit" width on a 830px pane that lands
     around 10px on screen, which is a value a reviewer has to lean in to read.
     18px is ordinary body size — the point at which they can just read it. */
  var TARGET_VALUE_PX = 18;

  /* Land the reviewer ON the evidence, already legible. This is the single
     highest-value interaction in the pane: an A4 page at readable zoom is four
     screens tall, and a reviewer who has to find and then enlarge the box pays
     for both in the metric the product is sold on. */
  function focusEvidence(refit) {
    var wrap = $('sheet-wrap');
    var sheet = $('sheet');
    if (!state.valueBox || !wrap || !sheet) return;

    if (refit && state.zoom === 'fit') {
      var boxFraction = state.valueBox[3] - state.valueBox[1];
      var fitHeight = sheet.getBoundingClientRect().height;
      if (boxFraction > 0 && fitHeight > 0) {
        var wanted = TARGET_VALUE_PX / (boxFraction * fitHeight);
        // Never zoom OUT to hit the target: a page that shrinks on load reads
        // as a bug, and a value already legible does not need help.
        if (wanted > 1.05) setZoom(Math.min(3, wanted));
      }
    }

    requestAnimationFrame(function () {
      var rect = sheet.getBoundingClientRect();
      var top = sheet.offsetTop + state.valueBox[1] * rect.height;
      var left = sheet.offsetLeft + state.valueBox[0] * rect.width;
      wrap.scrollTo({
        // 0.38 rather than centre: the eye settles above the middle of a
        // viewport, and a box parked dead-centre reads as lower than it is.
        top: Math.max(0, top - wrap.clientHeight * 0.38),
        left: Math.max(0, left - wrap.clientWidth * 0.42),
        behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'
      });
    });
  }

  function centreOnEvidence() { focusEvidence(false); }

  function setZoom(next) {
    var sheet = $('sheet');
    if (next === 'fit') {
      state.zoom = 'fit';
      sheet.style.width = '100%';
      $('zoom-label').textContent = 'Fit';
    } else {
      state.zoom = Math.min(4, Math.max(0.5, next));
      sheet.style.width = (state.zoom * 100) + '%';
      $('zoom-label').textContent = Math.round(state.zoom * 100) + '%';
    }
  }
  function zoomStep(delta) {
    var current = state.zoom === 'fit' ? 1 : state.zoom;
    setZoom(current + delta);
  }

  /* ── verification ──────────────────────────────────────────────────────
     Hash BYTES, never a re-serialised structure. An earlier format stored a
     digest over canonical JSON and recomputed it here; it failed on the first
     real bundle, because Python writes 2.0 where JavaScript writes 2 and every
     projection carries floats. The format now keeps the manifest's own digest
     in bundle.sha256, so this needs no notion of canonical form at all. */

  function sha256Hex(buffer) {
    return crypto.subtle.digest('SHA-256', buffer).then(function (d) {
      return Array.prototype.map.call(new Uint8Array(d), function (b) {
        return b.toString(16).padStart(2, '0');
      }).join('');
    });
  }

  function verifyBundle(base, manifest) {
    var badge = $('verify'), text = $('verify-text');
    badge.dataset.state = 'checking';
    text.textContent = 'verifying…';

    function digestOf(name) {
      return fetch(base + '/' + name, { cache: 'no-store' })
        .then(function (r) { return r.arrayBuffer(); }).then(sha256Hex);
    }

    var jobs = [
      Promise.all([
        fetch(base + '/bundle.sha256', { cache: 'no-store' }).then(function (r) { return r.text(); }),
        digestOf('manifest.json')
      ]).then(function (pair) {
        state.manifestDigest = pair[1];
        return pair[0].trim() === pair[1] ? null : 'manifest digest mismatch';
      }).catch(function () { return 'bundle.sha256 unreadable'; })
    ];
    Object.keys(manifest.files).forEach(function (name) {
      jobs.push(digestOf(name)
        .then(function (d) { return d === manifest.files[name] ? null : name + ' digest mismatch'; })
        .catch(function () { return name + ' unreadable'; }));
    });

    return Promise.all(jobs).then(function (results) {
      var problems = results.filter(Boolean);
      var count = Object.keys(manifest.files).length + 1;
      if (problems.length) {
        badge.dataset.state = 'bad';
        text.textContent = problems.length + ' verification failure(s)';
        badge.title = problems.join('; ');
        say('Bundle verification failed.');
      } else {
        badge.dataset.state = 'ok';
        text.textContent = 'verified';
        badge.title = 'All ' + count + ' files match their recorded SHA-256, recomputed in this ' +
          'browser from the bytes on disk. No canonicalisation, and no trust in the writer.';
      }
    });
  }

  /* ── the claim pane ────────────────────────────────────────────────── */

  function renderDetail() {
    var host = $('detail');
    host.innerHTML = '';
    var f = state.finding;
    if (!f) {
      var e = el('div', 'empty-state');
      e.appendChild(el('span', 't-h4', 'Nothing selected'));
      e.appendChild(el('span', 't-body-s u-dimmer', 'Choose a finding from the queue, or press ⌘K.'));
      host.appendChild(e);
      $('claim-attr').textContent = '—';
      return;
    }

    $('claim-attr').textContent = f.attribute;

    var b1 = el('div', 'block');
    b1.appendChild(el('span', 'block-title t-col', f.label || f.attribute));
    var diff = el('div', 'diff-pair');
    diff.appendChild(el('span', 'diff-claim', f.catalog_value || '—'));
    diff.appendChild(el('span', 'diff-evidence', f.derived_value || '—'));
    if (f.detail) diff.appendChild(el('span', 'diff-note t-micro', f.detail));
    b1.appendChild(diff);
    host.appendChild(b1);

    var bl = f.blast || {};
    if (Object.keys(bl).length) {
      var b2 = el('div', 'block');
      b2.appendChild(el('span', 'block-title t-col', 'Why this is ranked here'));
      var factors = el('div', 'factors t-body-s');
      function factor(name, value, safety) {
        var row = el('div', 'factor');
        if (safety) row.dataset.safety = 'true';
        row.appendChild(el('span', 'f-name', name));
        row.appendChild(el('span', 'f-value', value));
        factors.appendChild(row);
      }
      if (bl.revenue_weight != null) factor('Revenue weight', bl.revenue_weight);
      if (bl.safety_class_multiplier != null) factor('Safety-class multiplier', '×' + bl.safety_class_multiplier, bl.safety_class_multiplier > 1);
      if (bl.propagation_count != null) factor('Downstream surfaces', bl.propagation_count);
      if (bl.record_multiplicity != null) factor('SKUs sharing this signature', bl.record_multiplicity);
      if (bl.score != null) {
        var total = el('div', 'factor factor-total');
        total.appendChild(el('span', 'f-name', 'Blast radius'));
        total.appendChild(el('span', 'f-value', bl.score));
        factors.appendChild(total);
      }
      if (f.expected_review_value != null) {
        var erv = el('div', 'factor');
        erv.appendChild(el('span', 'f-name', 'Expected review value'));
        erv.appendChild(el('span', 'f-value', f.expected_review_value));
        factors.appendChild(erv);
      }
      b2.appendChild(factors);
      b2.appendChild(el('p', 't-micro u-dimmer', 'Each factor separately, because a reviewer given one score has a number, not a reason (FR-8.4).'));
      host.appendChild(b2);
    }

    // FR-7.4 — never empty, never absent.
    var b3 = el('div', 'block');
    b3.appendChild(el('span', 'block-title t-col', 'The case for the catalog'));
    var panel = el('div', 'counter-panel t-body-s');
    if ((f.counter_evidence || []).length) {
      f.counter_evidence.forEach(function (c) {
        panel.appendChild(el('p', 't-body-s', '“' + (c.snippet || '').trim() + '”'));
        panel.appendChild(el('p', 't-micro u-dimmer', 'Page ' + c.page + (c.table_cell ? ' · cell ' + c.table_cell : '')));
      });
    } else {
      panel.appendChild(el('p', 't-body-s', f.counter_summary));
      panel.appendChild(el('p', 't-micro u-dimmer', 'Never omitted. “We looked and found nothing” and “nobody looked” are different claims, and a reviewer must be able to tell them apart.'));
    }
    b3.appendChild(panel);
    host.appendChild(b3);

    var b4 = el('div', 'block');
    b4.appendChild(el('span', 'block-title t-col', 'Evidence'));
    (f.evidence || []).forEach(function (ev) {
      var item = el('div', 'evidence-item');
      if (ev.column_header || ev.row_header) {
        item.appendChild(el('div', 't-micro u-dimmer',
          [ev.row_header && ('row “' + ev.row_header + '”'), ev.column_header && ('column “' + ev.column_header + '”')]
            .filter(Boolean).join(' · ')));
      }
      if (ev.table_cell) item.appendChild(el('div', 't-data', 'cell ' + ev.table_cell));
      item.appendChild(el('div', 't-micro u-dimmer',
        'page ' + ev.page + ' · chars ' + (ev.char_span || []).join('–') + ' · ' + (ev.layer_version || '')));
      b4.appendChild(item);
    });
    host.appendChild(b4);

    var declined = (state.redlines && state.redlines.declined) || [];
    if (declined.length) {
      var b5 = el('div', 'block');
      b5.appendChild(el('span', 'block-title t-col', 'Not checked on this record'));
      declined.forEach(function (d) {
        var row = el('div', 'evidence-item');
        row.appendChild(el('span', 't-body-s', (d.label || d.attribute) + ' — ' + (d.declined_reason || '').replace(/_/g, ' ')));
        b5.appendChild(row);
      });
      b5.appendChild(el('p', 't-micro u-dimmer', 'An abstention is a distinct type in the schema, not a null. Shown, because what was not checked is part of what the audit says.'));
      host.appendChild(b5);
    }
  }

  /* ── the decision bar (FR-7.6 · 8.9 · 9.4) ─────────────────────────── */

  function currentEntry() {
    return state.queue.filter(function (e) { return e.sku === state.sku; })[0] || null;
  }

  function renderDecisionBar() {
    var bar = $('decision-bar');
    var f = state.finding;
    if (!f) { bar.hidden = true; return; }
    bar.hidden = false;
    bar.innerHTML = '';

    var entry = currentEntry();
    var decided = entry && decisionOf(entry);

    if (decided) {
      var done = el('div', 'decided-state');
      done.appendChild(el('span', 't-h4', decisionLabel(decided.decision)));
      done.appendChild(el('span', 't-body-s u-dim',
        'by ' + (decided.decided_by || 'unknown') +
        (decided.second_adjudicator ? ' and ' + decided.second_adjudicator : '') +
        (decided.seconds != null ? ' · ' + decided.seconds + ' s' : '')));
      // The ledger is append-only, so there is no undo. Changing your mind is a
      // NEW claim that supersedes the old one, and calling the control "change"
      // rather than "undo" is the difference between describing the system and
      // misdescribing it.
      done.appendChild(el('span', 't-micro u-dimmer',
        'The ledger is append-only. Deciding again records a new claim that supersedes this one; nothing is erased.'));
      var change = el('button', 'btn btn--quiet', 'Decide again');
      change.addEventListener('click', function () {
        entry.decisions = {};
        renderQueue(); renderDecisionBar(); timer.start();
      });
      done.appendChild(change);
      bar.appendChild(done);
      return;
    }

    if (!state.identity || !state.identity.name) {
      var need = el('div', 'two-sig');
      need.appendChild(el('span', 't-body-s', 'A decision needs an actor. Every adjudication records who made it, immutably.'));
      var set = el('button', 'btn', 'Set reviewer');
      set.addEventListener('click', identity.prompt);
      need.appendChild(set);
      bar.appendChild(need);
      return;
    }

    // FR-9.4 — asked separately from the decision, because "the value is wrong"
    // and "the box is on the right words" are different judgements and pooling
    // them loses both.
    var box = el('label', 'check');
    var boxInput = document.createElement('input');
    boxInput.type = 'checkbox'; boxInput.id = 'box-accepted';
    box.appendChild(boxInput);
    box.appendChild(el('span', 'box'));
    box.appendChild(el('span', 't-body-s', 'The highlighted span supports the claim'));
    box.appendChild(el('kbd', null, 'b'));
    bar.appendChild(box);

    // FR-8.9 — dual control, surfaced BEFORE the click. The domain model
    // refuses a single signature on a safety-class attribute; letting the
    // reviewer discover that as a server error after deciding would be a wall
    // they could have been shown.
    if (f.requires_two_signatures) {
      var sig = el('div', 'two-sig');
      sig.appendChild(el('span', 't-body-s',
        (f.label || f.attribute) + ' is a safety-class attribute. Every decision on it needs a second named adjudicator — single-signature is impossible by construction (FR-8.9).'));
      var field = el('label', 'field');
      field.appendChild(el('span', 'field-label t-col', 'Second adjudicator'));
      var input = el('input', 'input');
      input.id = 'second-adjudicator';
      input.placeholder = 'Their name';
      input.autocomplete = 'off';
      field.appendChild(input);
      sig.appendChild(field);
      sig.appendChild(el('span', 't-micro u-dimmer',
        'Two names typed at one keyboard are one signature wearing two hats. This is honest for a local operator tool and not sufficient for a real deployment — see FE-SYSTEM-REVIEW §5.5.'));
      bar.appendChild(sig);
    }

    var row = el('div', 'decision-row');
    [['accept_redline', 'Accept', 'a', ''],
     ['keep_catalog', 'Keep catalog', 'c', 'btn--quiet'],
     ['escalate', 'Escalate', 'x', 'btn--quiet']].forEach(function (spec) {
      var b = el('button', 'btn ' + spec[3]);
      b.appendChild(document.createTextNode(spec[1]));
      b.appendChild(el('span', 'k', spec[2]));
      b.addEventListener('click', function () { adjudicate(spec[0]); });
      row.appendChild(b);
    });
    bar.appendChild(row);

    bar.appendChild(el('p', 't-micro u-dimmer',
      'Keep catalog is the highest-signal event in the system when nothing supports the catalog value: the reviewer knows something the corpus does not (§5.4).'));
  }

  function adjudicate(decision) {
    var f = state.finding;
    if (!f || state.busy) return;
    if (!state.identity || !state.identity.name) { identity.prompt(); return; }

    var second = $('second-adjudicator');
    if (f.requires_two_signatures && (!second || !second.value.trim())) {
      if (second) { second.focus(); second.setAttribute('aria-invalid', 'true'); }
      toast('Second adjudicator required',
        (f.label || f.attribute) + ' is safety-class. FR-8.9 makes single-signature impossible by construction — name the second adjudicator.',
        'error');
      say('Second adjudicator required.');
      return;
    }

    var boxAccepted = $('box-accepted');
    state.busy = true;

    postJSON(API + '/adjudicate', {
      sku: state.sku,
      attribute: f.attribute,
      decision: decision,
      decided_by: state.identity.name,
      decided_by_role: state.identity.role,
      second_adjudicator: second ? second.value.trim() : '',
      seconds_to_decision: timer.seconds(),
      evidence_accepted: boxAccepted ? boxAccepted.checked : null,
      presented_utc: state.presentedUtc,
      decided_utc: new Date().toISOString(),
      raw_score: f.confidence != null ? f.confidence : null
    }).then(function (res) {
      state.busy = false;
      if (!res.ok || !res.body.ok) {
        // The server's reason is shown verbatim. A generic "something went
        // wrong" would hide the one message that tells the reviewer what to do.
        toast('Not recorded', (res.body && res.body.error) || 'The ledger refused this decision.', 'error');
        say('Decision refused.');
        return;
      }
      toast(decisionLabel(decision),
        'Recorded in the ledger' + (res.body.supersedes ? ', superseding an earlier claim' : '') + '.');
      say(decisionLabel(decision) + ' recorded.');
      return refreshQueue().then(function () {
        var next = nextUndecided();
        if (next) select(next); else { renderQueue(); renderDecisionBar(); }
      });
    }).catch(function (err) {
      state.busy = false;
      toast('Not recorded', String(err), 'error');
    });
  }

  function nextUndecided() {
    var rows = visibleQueue();
    var here = rows.findIndex(function (e) { return e.sku === state.sku; });
    for (var i = here + 1; i < rows.length; i++) if (!decisionOf(rows[i])) return rows[i].sku;
    for (var j = 0; j < rows.length; j++) if (!decisionOf(rows[j])) return rows[j].sku;
    return null;
  }

  /* ── selection ─────────────────────────────────────────────────────── */

  function select(sku) {
    if (!sku) return;
    var base = API + '/bundle/' + sku;
    state.sku = sku;
    $('sheet-wrap').dataset.loading = 'true';
    $('sheet').dataset.loading = 'true';

    Promise.all([
      getJSON(base + '/manifest.json'),
      getJSON(base + '/redlines.json'),
      getJSON(base + '/words.json')
    ]).then(function (parts) {
      state.manifest = parts[0];
      state.redlines = parts[1];
      state.words = parts[2];
      state.finding = (parts[1].findings || [])[0] || null;

      var page = (state.finding && (state.finding.evidence || [])[0])
        ? state.finding.evidence[0].page
        : (state.manifest.document.pages || [])[0];

      transition(function () {
        renderPage(page);
        renderDetail();
        renderQueue();
        renderDecisionBar();
      });

      $('ev-source').textContent = state.manifest.document.name + ' · page ' + page;
      $('provenance').textContent =
        'Document SHA-256 ' + state.manifest.document.sha256.slice(0, 16) + '… · layout ' +
        state.manifest.versions.layout + ' · derive ' + state.manifest.versions.derive +
        ' · geometry ' + state.manifest.geometry_version;

      $('sheet-wrap').dataset.loading = 'false';
      $('sheet').dataset.loading = 'false';
      timer.start();
      // Each record starts at fit and is then zoomed to legibility, so the reviewer
      // never inherits the previous record's zoom on a differently-sized page.
      setZoom('fit');
      requestAnimationFrame(function () { focusEvidence(true); });
      say(sku + ' selected. ' + (state.finding ? state.finding.label : ''));
      return verifyBundle(base, parts[0]);
    }).catch(function (err) {
      $('sheet-wrap').dataset.loading = 'false';
      $('sheet').dataset.loading = 'false';
      $('detail').innerHTML = '';
      var e = el('div', 'empty-state');
      e.appendChild(el('span', 't-h4', 'Bundle unreadable'));
      e.appendChild(el('span', 't-body-s', String(err)));
      $('detail').appendChild(e);
    });
  }

  function move(delta) {
    var rows = visibleQueue();
    if (!rows.length) return;
    var here = rows.findIndex(function (e) { return e.sku === state.sku; });
    var next = rows[Math.min(rows.length - 1, Math.max(0, (here < 0 ? 0 : here + delta)))];
    if (next) {
      select(next.sku);
      var node = document.querySelector('.queue-row[data-sku="' + next.sku + '"]');
      if (node) node.scrollIntoView({ block: 'nearest' });
    }
  }

  function refreshQueue() {
    return getJSON(API + '/queue').then(function (index) {
      state.queue = index.bundles || [];
      renderProgress();
      if (index.error) {
        $('queue-note').textContent = index.error;
      } else {
        $('queue-note').textContent =
          'Ranked by expected review value — P(catalog wrong) × blast radius (FR-8.4), not by confidence. ' +
          'No confidence percentage appears in this pane, by requirement (FR-7.5).';
      }
      return index;
    });
  }

  /* ── command palette ───────────────────────────────────────────────── */

  var palette = {
    items: [], active: 0,
    open: function () {
      var dialog = $('palette');
      var input = $('palette-input');
      input.value = '';
      palette.build('');
      dialog.showModal();
      input.focus();
    },
    build: function (query) {
      var q = query.trim().toLowerCase();
      var items = [];

      state.queue.forEach(function (entry) {
        var f = findingCache[entry.sku];
        var label = entry.sku + (f ? ' — ' + (f.label || f.attribute) + ' ' + (f.catalog_value || '') + ' → ' + (f.derived_value || '') : '');
        items.push({ label: label, hint: decisionOf(entry) ? 'decided' : 'to do', run: function () { select(entry.sku); } });
      });

      [['Set reviewer identity', identity.prompt],
       ['Keyboard shortcuts', function () { $('help-dialog').showModal(); }],
       ['Centre on the evidence', centreOnEvidence],
       ['Fit page', function () { setZoom('fit'); }],
       ['Open the design system', function () { location.href = '/web/datum/'; }],
       ['Open the site', function () { location.href = '/web/site/'; }]
      ].forEach(function (c) { items.push({ label: c[0], hint: 'command', run: c[1] }); });

      palette.items = items.filter(function (i) { return !q || i.label.toLowerCase().indexOf(q) >= 0; });
      palette.active = 0;
      palette.render();
    },
    render: function () {
      var list = $('palette-list');
      list.innerHTML = '';
      if (!palette.items.length) {
        list.appendChild(el('div', 'queue-empty t-body-s', 'No commands match'));
        return;
      }
      palette.items.forEach(function (item, i) {
        var b = el('button', 'menu-item');
        b.setAttribute('role', 'option');
        b.dataset.active = String(i === palette.active);
        b.setAttribute('aria-selected', String(i === palette.active));
        b.appendChild(el('span', null, item.label));
        b.appendChild(el('kbd', null, item.hint));
        b.addEventListener('click', function () { palette.run(i); });
        list.appendChild(b);
      });
    },
    step: function (delta) {
      if (!palette.items.length) return;
      palette.active = (palette.active + delta + palette.items.length) % palette.items.length;
      palette.render();
      var node = $('palette-list').children[palette.active];
      if (node) node.scrollIntoView({ block: 'nearest' });
    },
    run: function (i) {
      var item = palette.items[i];
      $('palette').close();
      if (item) item.run();
    }
  };

  /* ── keyboard ──────────────────────────────────────────────────────── */

  var SHORTCUTS = [
    [['j', '↓'], 'Next finding'],
    [['k', '↑'], 'Previous finding'],
    [['a'], 'Accept redline'],
    [['c'], 'Keep catalog'],
    [['x'], 'Escalate'],
    [['b'], 'Toggle “the span supports the claim” (FR-9.4)'],
    [['f'], 'Centre the page on the evidence'],
    [['+', '−'], 'Zoom in / out'],
    [['0'], 'Fit the page'],
    [['⌘K', 'Ctrl K'], 'Command palette'],
    [['i'], 'Set reviewer identity'],
    [['?'], 'This list'],
    [['Esc'], 'Close whatever is open']
  ];

  function renderShortcuts() {
    var list = $('keys-list');
    list.innerHTML = '';
    SHORTCUTS.forEach(function (row) {
      var dt = el('dt');
      row[0].forEach(function (k) { dt.appendChild(el('kbd', null, k)); });
      list.appendChild(dt);
      list.appendChild(el('dd', 't-body-s', row[1]));
    });
  }

  function isTyping(target) {
    return target && (/^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName) || target.isContentEditable);
  }

  function onKey(e) {
    var open = document.querySelector('dialog[open]');

    if (open && open.id === 'palette') {
      if (e.key === 'ArrowDown') { e.preventDefault(); palette.step(1); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); palette.step(-1); }
      else if (e.key === 'Enter') { e.preventDefault(); palette.run(palette.active); }
      return;
    }

    if ((e.key === 'k' || e.key === 'K') && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      if (!open) palette.open();
      return;
    }
    if (open || isTyping(e.target)) return;
    if (e.metaKey || e.ctrlKey || e.altKey) return;

    switch (e.key) {
      case 'j': case 'ArrowDown': e.preventDefault(); move(1); break;
      case 'k': case 'ArrowUp': e.preventDefault(); move(-1); break;
      case 'a': adjudicate('accept_redline'); break;
      case 'c': adjudicate('keep_catalog'); break;
      case 'x': adjudicate('escalate'); break;
      case 'b': {
        var box = $('box-accepted');
        if (box) { box.checked = !box.checked; say(box.checked ? 'Span accepted.' : 'Span not accepted.'); }
        break;
      }
      case 'f': setZoom('fit'); focusEvidence(true); break;
      case '+': case '=': zoomStep(0.25); break;
      case '-': case '_': zoomStep(-0.25); break;
      case '0': setZoom('fit'); break;
      case 'i': identity.prompt(); break;
      case '?': $('help-dialog').showModal(); break;
      default: break;
    }
  }

  /* ── boot ──────────────────────────────────────────────────────────── */

  function boot() {
    timer.node = $('timer');
    setInterval(function () { timer.tick(); }, 100);
    addEventListener('blur', function () { timer.pause(); });
    addEventListener('focus', function () { timer.resume(); });
    document.addEventListener('visibilitychange', function () {
      if (document.hidden) timer.pause(); else timer.resume();
    });

    renderShortcuts();
    identity.load();

    $('identity-btn').addEventListener('click', identity.prompt);
    $('help-btn').addEventListener('click', function () { $('help-dialog').showModal(); });
    $('help-close').addEventListener('click', function () { $('help-dialog').close(); });
    $('identity-form').addEventListener('submit', function (e) {
      if (e.submitter && e.submitter.value === 'cancel') return;
      var name = $('identity-name').value.trim();
      if (!name) { e.preventDefault(); return; }
      var role = (document.querySelector('input[name="role"]:checked') || {}).value || 'domain_reviewer';
      identity.save(name, role);
      say('Reviewer set to ' + name + '.');
    });

    $('palette-input').addEventListener('input', function (e) { palette.build(e.target.value); });

    $('zoom-in').addEventListener('click', function () { zoomStep(0.25); });
    $('zoom-out').addEventListener('click', function () { zoomStep(-0.25); });
    $('zoom-fit').addEventListener('click', function () { setZoom('fit'); focusEvidence(true); });

    document.querySelectorAll('[data-filter]').forEach(function (tab) {
      tab.addEventListener('click', function () {
        state.filter = tab.dataset.filter;
        document.querySelectorAll('[data-filter]').forEach(function (t) {
          t.setAttribute('aria-selected', String(t === tab));
        });
        renderQueue();
        say(visibleQueue().length + ' findings shown.');
      });
    });

    addEventListener('keydown', onKey);
    setZoom('fit');

    refreshQueue().then(function () {
      renderQueue();
      var first = visibleQueue()[0] || state.queue[0];
      if (first) select(first.sku); else { renderDetail(); renderDecisionBar(); }
      if (!state.identity || !state.identity.name) identity.prompt();
    }).catch(function (err) {
      $('queue-list').innerHTML = '';
      var e = el('div', 'queue-empty');
      e.appendChild(el('span', 't-h4', 'No queue'));
      e.appendChild(el('span', 't-body-s u-dimmer',
        'The console needs its server: python -m errata_bundle serve'));
      e.appendChild(el('span', 't-micro u-dimmer', String(err)));
      $('queue-list').appendChild(e);
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();

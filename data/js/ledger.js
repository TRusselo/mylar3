(function () {
  var MK = ['--lg-gap', '--lg-unrec', '--lg-after', '--lg-before', '--lg-cut'];
  var ML = ['Gap', 'Files not recognised', 'After last owned', 'Before first owned', 'After collection ended'];
  var MH = ['Owned issues on both sides', 'Series has files Mylar can\'t match', 'Past your last owned issue', 'Before your first owned issue', 'Released after your cutoff date'];
  var CK = ['fills_gaps', 'covered', 'partly', 'not_in_library', 'unknown'];
  var CC = ['--lg-gap', '--lg-done', '--lg-after', '--lg-before', '--lg-cut'];
  var CL = ['Fills gaps', 'Duplicates singles', 'Partly covered', 'Not in library', 'No contents info'];
  var CH = ['Collects issues you don\'t have as singles', 'You own every issue it collects', 'Some collected issues aren\'t in Mylar', 'Collects series you don\'t track', 'ComicVine doesn\'t list what it collects'];

  var st = {
    tab: 'missing', by: 'issue', kinds: { missing: [0], collected: [0, 1] }, q: '', pub: '', dec: '',
    sort: null, limit: 300, sel: {}, open: {}, owned: true
  };
  try { var saved = JSON.parse(localStorage.getItem('mylar-ledger') || 'null'); if (saved) { st.tab = saved.tab || st.tab; st.kinds = saved.kinds || st.kinds; st.by = saved.by || st.by; } } catch (e) {}
  function save() { try { localStorage.setItem('mylar-ledger', JSON.stringify({ tab: st.tab, kinds: st.kinds, by: st.by })); } catch (e) {} }

  var M = null, C = null, $id = function (i) { return document.getElementById(i); };
  var fmt = function (n) { return Number(n).toLocaleString(); };
  var esc = function (s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); };
  var isOwned = function (t) { return t.tstatus === 'Downloaded' || t.tstatus === 'Archived'; };
  var cmp = function (a, b) { return a < b ? -1 : a > b ? 1 : 0; };

  function load(view, cb) {
    $id('lg-count').textContent = 'Loading…';
    $.getJSON('ledger_data', { view: view }, cb);
  }

  function tiles() {
    var counts, L, H, K, keys = st.kinds[st.tab];
    if (st.tab === 'missing') {
      counts = [0, 0, 0, 0, 0]; M.rows.forEach(function (r) { counts[r[0]]++; }); L = ML; H = MH; K = MK;
    } else {
      counts = [0, 0, 0, 0, 0]; C.trades.forEach(function (t) { if (!st.owned || isOwned(t)) counts[CK.indexOf(t.coverage)]++; }); L = CL; H = CH; K = CC;
    }
    $id('lg-tiles').innerHTML = L.map(function (l, i) {
      if (st.tab === 'missing' && i === 4 && !M.cutoff) return '';
      return '<button class="lg-tile" style="--c:var(' + K[i] + ')" data-k="' + i + '" aria-pressed="' + (keys.indexOf(i) >= 0) + '"><b>' + fmt(counts[i]) + '</b><span>' + l + '</span><small>' + H[i] + '</small></button>';
    }).join('');
  }

  $('#lg-tiles').on('click', '.lg-tile', function () {
    var k = +this.getAttribute('data-k'), a = st.kinds[st.tab], p = a.indexOf(k);
    if (p >= 0) a.splice(p, 1); else a.push(k);
    this.setAttribute('aria-pressed', p < 0); st.limit = 300; save(); render();
  });

  function filters() {
    var pubs = {}, decs = {};
    if (st.tab === 'missing') {
      M.rows.forEach(function (r) { var p = M.pubs[M.series[r[1]][4]]; pubs[p] = (pubs[p] || 0) + 1; if (r[5]) decs[r[5].slice(0, 3) + '0'] = 1; });
    } else {
      C.trades.forEach(function (t) { pubs[t.pub || '?'] = (pubs[t.pub || '?'] || 0) + 1; });
    }
    var list = Object.keys(pubs).sort(function (a, b) { return pubs[b] - pubs[a]; });
    $id('lg-pub').innerHTML = '<option value="">All publishers</option>' + list.map(function (p) { return '<option value="' + esc(p) + '">' + esc(p) + ' (' + fmt(pubs[p]) + ')</option>'; }).join('');
    $id('lg-pub').value = st.pub;
    var dl = Object.keys(decs).sort();
    $id('lg-dec').innerHTML = '<option value="">All decades</option>' + dl.map(function (d) { return '<option value="' + d + '">' + d + 's</option>'; }).join('');
    $id('lg-dec').value = st.dec;
    $id('lg-dec').hidden = st.tab !== 'missing';
    $id('lg-cutoff-wrap').hidden = st.tab !== 'missing';
    $id('lg-owned-wrap').hidden = st.tab !== 'collected';
    $id('lg-owned').checked = st.owned;
    $id('lg-cutoff').value = (M && M.cutoff) || '';
    $('.lg-seg').toggle(st.tab === 'missing');
  }

  $('#lg-q').on('input', function () { st.q = this.value.trim().toLowerCase(); st.limit = 300; render(); });
  $('#lg-pub').on('change', function () { st.pub = this.value; st.limit = 300; render(); });
  $('#lg-dec').on('change', function () { st.dec = this.value; st.limit = 300; render(); });
  $('#lg-more').on('click', function () { st.limit += 300; render(); });
  $('#lg-owned').on('change', function () { st.owned = this.checked; st.limit = 300; tiles(); render(); });
  $('#lg-cutoff').on('change', function () {
    $.getJSON('ledger_cutoff', { cutoff: this.value }, function (r) {
      if (!r.ok) { alert(r.error); return; }
      load('missing', function (d) { M = d; st.sel = {}; tiles(); filters(); render(); });
    });
  });

  function setTab(t) {
    st.tab = t; st.sel = {}; st.limit = 300; st.sort = null; save();
    $id('lg-tab-missing').setAttribute('aria-selected', t === 'missing');
    $id('lg-tab-collected').setAttribute('aria-selected', t === 'collected');
    var go = function () { tiles(); filters(); render(); buildBar(); };
    if (t === 'missing') { if (M) go(); else load('missing', function (d) { M = d; go(); }); }
    else { if (C) go(); else load('collected', function (d) { C = d; go(); }); }
  }
  $('#lg-tab-missing').on('click', function () { setTab('missing'); });
  $('#lg-tab-collected').on('click', function () { setTab('collected'); });
  function setBy(b) { st.by = b; st.sort = null; st.limit = 300; save(); $id('lg-by-issue').setAttribute('aria-pressed', b === 'issue'); $id('lg-by-series').setAttribute('aria-pressed', b === 'series'); render(); }
  $('#lg-by-issue').on('click', function () { setBy('issue'); });
  $('#lg-by-series').on('click', function () { setBy('series'); });

  function head(cols, check) {
    var s = st.sort || {};
    $('#lg-table thead').html('<tr>' + (check ? '<th class="lg-chk"><input type="checkbox" id="lg-all" aria-label="Select all shown"></th>' : '') + cols.map(function (c) {
      return '<th data-key="' + c[0] + '" class="' + (c[2] || '') + '" aria-sort="' + (s.key === c[0] ? (s.dir > 0 ? 'ascending' : 'descending') : 'none') + '" tabindex="0">' + c[1] + '</th>';
    }).join('') + '</tr>');
  }
  $('#lg-table').on('click', 'th[data-key]', function () {
    var k = this.getAttribute('data-key'); if (k === 'mix' || k === 'lack') return;
    st.sort = st.sort && st.sort.key === k ? { key: k, dir: -st.sort.dir } : { key: k, dir: ['gap', 'other', 'own', 'found', 'lacking'].indexOf(k) >= 0 ? -1 : 1 };
    render();
  });
  $('#lg-table').on('keydown', 'th[data-key]', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); $(this).click(); } });

  function missingRows() {
    var keys = st.kinds.missing;
    return M.rows.filter(function (r) {
      if (keys.indexOf(r[0]) < 0) return false;
      var S = M.series[r[1]];
      if (st.pub && M.pubs[S[4]] !== st.pub) return false;
      if (st.dec && (!r[5] || r[5].slice(0, 3) + '0' !== st.dec)) return false;
      if (st.q && S[0].toLowerCase().indexOf(st.q) < 0 && r[4].toLowerCase().indexOf(st.q) < 0) return false;
      return true;
    });
  }

  function render() {
    if (st.tab === 'missing') { if (st.by === 'issue') renderIssues(); else renderSeries(); }
    else renderTrades();
    selBar();
  }

  function renderIssues() {
    var f = missingRows(), s = st.sort || { key: 'k', dir: 1 };
    head([['k', 'Kind'], ['series', 'Series'], ['n', '#', 'num'], ['t', 'Title'], ['d', 'Released'], ['st', 'Status'], ['own', 'Series owned', 'num']], true);
    var v = function (r) { var S = M.series[r[1]]; return s.key === 'series' ? S[0].toLowerCase() : s.key === 'own' ? S[2] / (S[3] || 1) : s.key === 'k' ? r[0] : s.key === 'n' ? r[3] : s.key === 't' ? r[4] : s.key === 'd' ? r[5] : r[7]; };
    f.sort(function (a, b) { return s.dir * cmp(v(a), v(b)) || cmp(M.series[a[1]][0], M.series[b[1]][0]) || cmp(a[3], b[3]); });
    var page = f.slice(0, st.limit);
    $('#lg-table tbody').html(page.length ? page.map(function (r) {
      var S = M.series[r[1]];
      return '<tr class="' + (st.sel[r[6]] ? 'lg-on' : '') + '"><td class="lg-chk"><input type="checkbox" data-id="' + r[6] + '"' + (st.sel[r[6]] ? ' checked' : '') + ' aria-label="Select issue"></td>' +
        '<td><span class="lg-pill" style="--c:var(' + MK[r[0]] + ')">' + ML[r[0]] + '</span></td>' +
        '<td><a href="comicDetails?ComicID=' + S[5] + '">' + esc(S[0]) + '</a> <span class="lg-dim">(' + esc(S[1]) + ')</span><br><small class="lg-dim">' + esc(M.pubs[S[4]]) + '</small></td>' +
        '<td class="num lg-mono"><a href="https://comicvine.gamespot.com/issue/4000-' + r[6] + '/" target="_blank" rel="noopener">' + esc(r[2]) + '</a></td>' +
        '<td class="lg-dim lg-title-cell">' + (esc(r[4]) || '—') + '</td><td class="lg-mono">' + (r[5] || '—') + '</td>' +
        '<td><span class="lg-status lg-st-' + esc(r[7]) + '">' + esc(r[7]) + '</span></td><td class="num lg-mono">' + S[2] + ' / ' + S[3] + '</td></tr>';
    }).join('') : '<tr><td class="lg-empty" colspan="8">No issues match. Turn on more kinds above or clear the search.</td></tr>');
    $id('lg-count').textContent = fmt(Math.min(st.limit, f.length)) + ' of ' + fmt(f.length) + ' issues';
    $id('lg-more').hidden = f.length <= st.limit;
    $id('lg-note').textContent = 'Wanted starts a search for those issues. Ignored stops Mylar from ever searching for them. Series lost completely aren\'t in Mylar, so they can\'t show here.';
  }

  function renderSeries() {
    var f = missingRows(), g = {};
    f.forEach(function (r) { var x = g[r[1]] || (g[r[1]] = { s: r[1], c: [0, 0, 0, 0, 0], ids: [] }); x.c[r[0]]++; x.ids.push(r[6]); });
    var s = st.sort || { key: 'gap', dir: -1 };
    var list = Object.keys(g).map(function (k) { var x = g[k], S = M.series[x.s]; x.series = S[0].toLowerCase(); x.pub = M.pubs[S[4]]; x.own = S[2] / (S[3] || 1); x.gap = x.c[0]; x.other = x.c[1] + x.c[2] + x.c[3] + x.c[4]; return x; });
    list.sort(function (a, b) { return s.dir * cmp(a[s.key], b[s.key]) || cmp(a.series, b.series); });
    head([['series', 'Series'], ['pub', 'Publisher'], ['own', 'Owned', 'num'], ['gap', 'Gaps', 'num'], ['other', 'Other missing', 'num'], ['mix', 'Breakdown']], true);
    var page = list.slice(0, st.limit);
    $('#lg-table tbody').html(page.length ? page.map(function (x) {
      var S = M.series[x.s], tot = S[3] || 1, all = x.ids.every(function (i) { return st.sel[i]; });
      var seg = function (n, c) { return n ? '<i style="width:' + (100 * n / tot) + '%;background:var(' + c + ')" title="' + n + '"></i>' : ''; };
      return '<tr class="' + (all ? 'lg-on' : '') + '"><td class="lg-chk"><input type="checkbox" data-ids="' + x.ids.join(',') + '"' + (all ? ' checked' : '') + ' aria-label="Select all missing issues in this series"></td>' +
        '<td><a href="comicDetails?ComicID=' + S[5] + '">' + esc(S[0]) + '</a> <span class="lg-dim">(' + esc(S[1]) + ')</span></td><td>' + esc(M.pubs[S[4]]) + '</td>' +
        '<td class="num lg-mono">' + S[2] + ' / ' + S[3] + '</td><td class="num lg-mono lg-strong">' + (x.gap || '') + '</td><td class="num lg-mono">' + (x.other || '') + '</td>' +
        '<td><div class="lg-bar">' + seg(S[2], '--lg-done') + x.c.map(function (n, i) { return seg(n, MK[i]); }).join('') + '</div></td></tr>';
    }).join('') : '<tr><td class="lg-empty" colspan="7">No series match these filters.</td></tr>');
    $id('lg-count').textContent = fmt(Math.min(st.limit, list.length)) + ' of ' + fmt(list.length) + ' series';
    $id('lg-more').hidden = list.length <= st.limit;
    $id('lg-note').textContent = 'Selecting a series selects all of its missing issues that match the filters.';
  }

  function renderTrades() {
    var keys = st.kinds.collected, s = st.sort || { key: 'cov', dir: 1 };
    var f = C.trades.filter(function (t) {
      if (keys.indexOf(CK.indexOf(t.coverage)) < 0) return false;
      if (st.owned && !isOwned(t)) return false;
      if (st.pub && (t.pub || '?') !== st.pub) return false;
      if (st.q && (t.name + ' ' + t.collects).toLowerCase().indexOf(st.q) < 0) return false;
      return true;
    });
    var v = function (t) { return s.key === 'cov' ? CK.indexOf(t.coverage) : s.key === 'name' ? t.name.toLowerCase() : s.key === 'lacking' ? t.lacking.length : s.key === 'found' ? t.own / (t.found || 1) : s.key === 'tstatus' ? t.tstatus : t.collects; };
    f.sort(function (a, b) { return s.dir * cmp(v(a), v(b)) || cmp(a.name, b.name); });
    head([['cov', 'Coverage'], ['name', 'Collected edition'], ['collects', 'Collects'], ['found', 'Singles owned', 'num'], ['lacking', 'Covers missing', 'num'], ['tstatus', 'Edition status']], true);
    var page = f.slice(0, st.limit);
    $('#lg-table tbody').html(page.length ? page.map(function (t) {
      var i = CK.indexOf(t.coverage), open = st.open[t.iid];
      var row = '<tr class="' + (st.sel[t.iid] ? 'lg-on' : '') + '"><td class="lg-chk"><input type="checkbox" data-id="' + t.iid + '"' + (st.sel[t.iid] ? ' checked' : '') + ' aria-label="Select edition"></td>' +
        '<td><span class="lg-pill" style="--c:var(' + CC[i] + ')">' + CL[i] + '</span></td>' +
        '<td><a href="comicDetails?ComicID=' + t.cid + '">' + esc(t.name) + '</a> <span class="lg-dim">(' + esc(t.year) + ') #' + esc(t.num) + '</span><br><small class="lg-dim">' + esc(t.type) + ' · ' + esc(t.pub) + '</small></td>' +
        '<td class="lg-dim lg-title-cell">' + (esc(t.collects) || '—') + '</td>' +
        '<td class="num lg-mono">' + (t.found ? t.own + ' / ' + t.found : '—') + (t.unresolved ? '<br><small class="lg-dim">+' + t.unresolved + ' not tracked</small>' : '') + '</td>' +
        '<td class="num lg-mono">' + (t.lacking.length ? '<button class="lg-link" data-open="' + t.iid + '" aria-expanded="' + !!open + '">' + t.lacking.length + '</button>' : '') + '</td>' +
        '<td><span class="lg-status lg-st-' + esc(t.tstatus) + '">' + esc(t.tstatus) + '</span></td></tr>';
      if (open) row += '<tr class="lg-sub-row"><td></td><td colspan="6">' + t.lacking.map(function (l) { return '<span class="lg-chip">' + esc(l[1]) + ' (' + esc(l[2]) + ') #' + esc(l[3]) + ' <em>' + esc(l[4]) + '</em></span>'; }).join('') + '</td></tr>';
      return row;
    }).join('') : '<tr><td class="lg-empty" colspan="7">' + (C.trades.length ? 'No editions match these filters.' : 'Trade contents haven\'t been read yet. Use the button above.') + '</td></tr>');
    $id('lg-count').textContent = fmt(Math.min(st.limit, f.length)) + ' of ' + fmt(f.length) + ' editions';
    $id('lg-more').hidden = f.length <= st.limit;
    $id('lg-note').textContent = 'Contents come from ComicVine\'s description of each edition, so editions without a "Collects …" line can\'t be checked. "Ignore issues it covers" marks the singles you don\'t have as Ignored, since you own them in this edition.';
  }

  $('#lg-table').on('click', '[data-open]', function () { var k = this.getAttribute('data-open'); st.open[k] = !st.open[k]; render(); });
  $('#lg-table').on('change', 'input[type=checkbox]', function () {
    if (this.id === 'lg-all') {
      var on = this.checked;
      $('#lg-table tbody input[type=checkbox]').each(function () { ids(this).forEach(function (i) { if (on) st.sel[i] = 1; else delete st.sel[i]; }); });
      render(); return;
    }
    var on2 = this.checked; ids(this).forEach(function (i) { if (on2) st.sel[i] = 1; else delete st.sel[i]; });
    $(this).closest('tr').toggleClass('lg-on', on2); selBar();
  });
  function ids(el) { var a = el.getAttribute('data-ids'); return a ? a.split(',') : [el.getAttribute('data-id')]; }

  function selBar() {
    var n = Object.keys(st.sel).length;
    $id('lg-actions').hidden = n === 0;
    $id('lg-selcount').textContent = fmt(n) + (st.tab === 'missing' ? ' issues selected' : ' editions selected');
    var ig = $id('lg-ignore-covered');
    if (st.tab === 'collected' && !ig) $('#lg-clear').before('<button class="lg-btn" id="lg-ignore-covered">Ignore issues it covers</button>');
    if (st.tab !== 'collected' && ig) $(ig).remove();
  }
  $('#lg-clear').on('click', function () { st.sel = {}; render(); });

  function mark(action, list, done) {
    if (!list.length) return;
    $('.lg-actions button').prop('disabled', true);
    $.ajax({ url: 'markissues', type: 'POST', traditional: true, data: { action: action, 'issueids[]': list } })
      .always(function () { $('.lg-actions button').prop('disabled', false); })
      .done(function () { done(); })
      .fail(function () { $id('lg-selcount').textContent = 'Mylar didn\'t accept the change. Check the log.'; });
  }
  function reload() {
    st.sel = {};
    if (st.tab === 'missing') load('missing', function (d) { M = d; tiles(); render(); });
    else load('collected', function (d) { C = d; tiles(); render(); });
  }
  $('#lg-actions').on('click', '[data-action]', function () { mark(this.getAttribute('data-action'), Object.keys(st.sel), reload); });
  $('#lg-actions').on('click', '#lg-ignore-covered', function () {
    var list = [];
    C.trades.forEach(function (t) { if (st.sel[t.iid]) t.lacking.forEach(function (l) { if (list.indexOf(l[0]) < 0) list.push(l[0]); }); });
    mark('Ignored', list, function () { M = null; reload(); });
  });

  var poll = null;
  function buildBar(s) {
    if (st.tab !== 'collected') { $id('lg-build').hidden = true; return; }
    s = s || (C && C.build) || {};
    $id('lg-build').hidden = false;
    var t;
    if (s.running) t = (s.phase || 'Working') + ': ' + fmt(s.done) + ' of ' + fmt(s.total) + ' editions';
    else if (s.error) t = 'Last read failed: ' + s.error;
    else if (s.stored) t = fmt(s.stored) + ' editions read, last on ' + s.updated + '.';
    else t = 'Trade contents haven\'t been read yet.';
    $id('lg-build-text').textContent = t;
    $('#lg-build-btn, #lg-rebuild-btn').prop('disabled', !!s.running);
    $id('lg-build-btn').textContent = s.stored ? 'Read new editions' : 'Read trade contents from ComicVine';
    if (s.running && !poll) poll = setInterval(function () {
      $.getJSON('ledger_status', function (x) {
        buildBar(x);
        if (!x.running) { clearInterval(poll); poll = null; load('collected', function (d) { C = d; tiles(); filters(); render(); buildBar(); }); }
      });
    }, 4000);
  }
  $('#lg-build-btn').on('click', function () { $.getJSON('ledger_build', { force: 0 }, function (r) { buildBar(r.status); }); });
  $('#lg-rebuild-btn').on('click', function () { $.getJSON('ledger_build', { force: 1 }, function (r) { buildBar(r.status); }); });

  $id('lg-by-issue').setAttribute('aria-pressed', st.by === 'issue');
  $id('lg-by-series').setAttribute('aria-pressed', st.by === 'series');
  setTab(st.tab);
})();

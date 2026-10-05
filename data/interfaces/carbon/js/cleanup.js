(function () {
  var nav = document.getElementById('nav');
  var logo = document.querySelector('#logo a');
  if (logo) { logo.setAttribute('aria-label', 'Library'); logo.setAttribute('title', 'Library'); }
  if (nav && !nav.querySelector('a[href="home"]')) {
    var li = document.createElement('li');
    li.innerHTML = '<a href="home">Library</a>';
    nav.insertBefore(li, nav.firstChild);
  }

  var cfg = nav && nav.querySelector('a.config');
  if (cfg) {
    cfg.setAttribute('aria-label', 'Settings');
    cfg.setAttribute('title', 'Settings');
    cfg.innerHTML = '<svg class="nav-gear" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="3.2"/><path d="M19.4 13.5a7.6 7.6 0 0 0 0-3l2-1.6-2-3.4-2.4 1a7.4 7.4 0 0 0-2.6-1.5L14 2.5h-4l-.4 2.5A7.4 7.4 0 0 0 7 6.5l-2.4-1-2 3.4 2 1.6a7.6 7.6 0 0 0 0 3l-2 1.6 2 3.4 2.4-1a7.4 7.4 0 0 0 2.6 1.5l.4 2.5h4l.4-2.5a7.4 7.4 0 0 0 2.6-1.5l2.4 1 2-3.4z"/></svg>';
  }

  var hdr = document.querySelector('header');
  function headHeight() { if (hdr) document.documentElement.style.setProperty('--carbon-head', hdr.offsetHeight + 'px'); }
  headHeight();
  window.addEventListener('resize', headHeight);

  var page = (location.pathname.split('/').pop() || 'home').toLowerCase();
  var groups = {
    home: ['home', 'comicdetails', 'issuedetails', 'searchit', 'addcomic'],
    upcoming: ['upcoming', 'wanted'],
    pullist: ['pullist', 'futurepulllist', 'weeklypull'],
    manage: ['manage', 'managecomics', 'manageissues', 'managefailed', 'queue_management', 'importresults', 'webpconvert'],
    storyarc_main: ['storyarc_main', 'detailstoryarc', 'readlist'],
    ledger: ['ledger'],
    history: ['history'],
    config: ['config']
  };
  if (nav) {
    nav.querySelectorAll('a').forEach(function (a) {
      var target = (a.getAttribute('href') || '').split('?')[0].split('#')[0].toLowerCase();
      if ((groups[target] || [target]).indexOf(page) >= 0) a.classList.add('is-current');
    });
  }

  var mainEl = document.getElementById('main');
  if (page === 'home' && mainEl && !mainEl.querySelector('h1')) {
    var h = document.createElement('h1');
    h.className = 'page-title';
    h.textContent = 'Library';
    var sub1 = document.getElementById('subhead');
    mainEl.insertBefore(h, sub1 ? sub1.nextSibling : mainEl.firstChild);
  }

  var menu = document.getElementById('subhead_menu');
  var main = document.getElementById('main');
  if (menu && main && menu.querySelector('a')) {
    var title = main.querySelector('h1');
    if (title && title.closest('.lg-head')) {
      menu.classList.add('page-actions');
      title.parentNode.appendChild(menu);
      var sub0 = document.getElementById('subhead');
      if (sub0 && !sub0.textContent.trim()) sub0.style.display = 'none';
    } else if (title && !title.closest('.page-head')) {
      var head = document.createElement('div');
      head.className = 'page-head';
      title.parentNode.insertBefore(head, title);
      head.appendChild(title);
      head.appendChild(menu);
      var sub = document.getElementById('subhead');
      if (sub && !sub.textContent.trim() && !sub.querySelector('img, input, a')) sub.style.display = 'none';
    }
  }
})();

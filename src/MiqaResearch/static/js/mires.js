function setActiveMenuItem() {
  urlPath = window.location.pathname.split('/').filter(i => i);

  const topNav = document.getElementById('top-nav');
  const mainContainer = document.getElementById('mires-main');

  topNav.childNodes.forEach((menuItem) =>  {
    if (menuItem.nodeType !== 1) return;
    menuItem.classList.remove('active');
  });
  mainContainer.classList.remove('fw');

  if (urlPath.length === 0) return;

  switch (urlPath[0]) {
    case "dashboard":
      document.getElementById('nav-dashboard').classList.add('active');
      break;
    case "administration":
      document.getElementById('nav-administration').classList.add('active');
      break;
    case "monitor":
      document.getElementById('nav-monitor').classList.add('active');
      mainContainer.classList.add('fw');
      break;
    case "upload":
      document.getElementById('nav-upload-data').classList.add('active');
      break;
    case "about":
      document.getElementById('nav-about').classList.add('active');
      break;
  }
}

function toggleTheme() {
  const body = document.body;
  body.classList.toggle('dark');
  localStorage.setItem('darkMode', body.classList.contains('dark') ? 'dark' : 'light');
  setDarkLightModeIcon();
}

function setDarkLightModeIcon() {
  const btn = document.getElementById('theme-toggle-btn');
  if (!btn) return;

  let darkModeStatus = document.body.classList.contains('dark');

  let darkMode = localStorage.getItem('darkMode');
  if (darkMode === null) {
    localStorage.setItem('darkMode', darkModeStatus ? 'dark' : 'light');
    darkMode = darkModeStatus ? 'dark' : 'light';
  }

  if (darkMode === 'dark' && !darkModeStatus || darkMode === 'light' && darkModeStatus) {
    document.body.classList.toggle('dark', darkMode === 'dark');
  }

  const iconName = darkMode === 'dark' ? btn.dataset.iconLight : btn.dataset.iconDark;
  fetch(`/static/icons/${iconName}.svg`)
    .then(response => response.text())
    .then(svg => { btn.innerHTML = svg; });
}

function initAppModal() {
  const modal = document.getElementById('app-modal');
  if (!modal) return;

  let trigger = null;

  document.body.addEventListener('htmx:afterSwap', function(evt) {
    if (evt.detail.target.id !== 'app-modal-content') return;

    trigger = evt.detail.elt;

    const heading = modal.querySelector('#app-modal-title');
    const description = modal.querySelector('#app-modal-description');
    if (heading) {
      modal.setAttribute('aria-labelledby', heading.id);
    } else {
      modal.removeAttribute('aria-labelledby');
    }
    if (description) {
      modal.setAttribute('aria-describedby', description.id);
    } else {
      modal.removeAttribute('aria-describedby');
    }

    modal.showModal();
  });

  modal.addEventListener('click', function(evt) {
    if (evt.target === modal || evt.target.closest('[data-modal-close]')) {
      modal.close();
    }
  });

  document.body.addEventListener('close-app-modal', function() {
    modal.close();
  });

  modal.addEventListener('close', function() {
    if (trigger) {
      trigger.focus();
      trigger = null;
    }
  });
}

// A <data-table> button column reports a click as `row-action`; a table that declares `data-row-action-url` gets the
// modal content for that row loaded from the URL, in which the nil UUID stands in for the row's value.
const NIL_UUID = '00000000-0000-0000-0000-000000000000';

document.addEventListener('row-action', function(evt) {
  const table = evt.target.closest('[data-row-action-url]');
  if (!table || !window.htmx) return;
  const url = table.dataset.rowActionUrl.replace(NIL_UUID, encodeURIComponent(evt.detail.value));
  htmx.ajax('GET', url, { target: '#app-modal-content', swap: 'innerHTML', source: table });
});

// Location Grant form (#394): "Browse storage" loads the chosen storage's buckets/folders into the form;
// "Use this folder" copies the bucket and prefix being browsed into the form's own inputs.
document.addEventListener('click', function(evt) {
  const browse = evt.target.closest('[data-etl-browse]');
  if (browse && window.htmx) {
    const select = document.getElementById(browse.dataset.select);
    const url = browse.dataset.url.replace(NIL_UUID, encodeURIComponent(select.value));
    htmx.ajax('GET', url, { target: '#etl-storage-browser', swap: 'outerHTML', source: browse });
    return;
  }
  const toggle = evt.target.closest('[data-etl-tree-toggle]');
  if (toggle) {
    // The first click's htmx request fills the children list; every click expands or collapses it.
    const children = toggle.closest('.etl-tree-node').querySelector('.etl-tree-children');
    const expand = children.hidden;
    children.hidden = !expand;
    toggle.setAttribute('aria-expanded', String(expand));
    return;
  }
  const pick = evt.target.closest('[data-etl-pick]');
  if (pick) {
    const form = pick.closest('form');
    form.querySelector('[name=bucket]').value = pick.dataset.bucket;
    form.querySelector('[name=prefix]').value = pick.dataset.prefix;
    form.querySelectorAll('.etl-tree-label.selected').forEach(function(el) { el.classList.remove('selected'); });
    pick.classList.add('selected');
  }
});

// Source Location form: choosing a location grant shows the storage, bucket and prefix it fixes; only an
// additional prefix can be typed after them.
document.addEventListener('change', function(evt) {
  const select = evt.target.closest('[data-etl-grant-select]');
  if (!select) return;
  const base = select.closest('form').querySelector('[data-etl-grant-base]');
  const option = select.selectedOptions[0];
  base.textContent = option ? option.dataset.base || '' : '';
});

document.addEventListener('DOMContentLoaded', function() {
  setActiveMenuItem();
  setDarkLightModeIcon();
  initAppModal();
});

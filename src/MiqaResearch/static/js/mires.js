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

document.addEventListener('DOMContentLoaded', function() {
  setActiveMenuItem();
  setDarkLightModeIcon();
});

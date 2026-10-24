// Aplica o tema antes da renderização para evitar "piscar" (preferência local, não sensível).
try {
  var t = localStorage.getItem('cw-theme') || 'system';
  var dark = t === 'dark' || (t === 'system' && matchMedia('(prefers-color-scheme: dark)').matches);
  if (dark) document.documentElement.classList.add('dark');
} catch (e) {}

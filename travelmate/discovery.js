// Keep DOM/keyboard order while allowing full-size photos to form two columns.
for (const grid of document.querySelectorAll('.discovery-grid')) {
  const cards = [...grid.children];
  const layout = () => {
    if (!grid.clientWidth) return;
    const gap = parseFloat(getComputedStyle(grid).columnGap) || 24;
    for (const card of cards) {
      card.style.gridRowEnd = 'span ' + Math.ceil((card.firstElementChild.getBoundingClientRect().height + gap) / 4);
    }
    grid.classList.add('is-masonry');
  };
  const observer = new ResizeObserver(layout);
  for (const card of cards) observer.observe(card.firstElementChild);
  window.addEventListener('hashchange', layout);
  window.addEventListener('resize', layout);
  document.addEventListener('visibilitychange', layout);
  layout();
}

for (const feed of document.querySelectorAll('.overview-feed')) {
  const cards = [...feed.querySelectorAll('.overview-card')];
  if (!cards.length) continue;
  const carousel = feed.querySelector('.overview-carousel');
  const indicators = [...feed.querySelectorAll('[data-overview-index]')];
  const count = feed.querySelector('.overview-count');
  let current = 0;
  const select = index => {
    if (feed.classList.contains('is-ready')) feed.classList.add('is-animated');
    current = (index + cards.length) % cards.length;
    cards.forEach((card, i) => {
      let offset = (i - current + cards.length) % cards.length;
      if (offset > cards.length / 2) offset -= cards.length;
      const distance = Math.abs(offset);
      card.style.setProperty('--offset', offset);
      card.style.setProperty('--scale', distance === 0 ? 1 : distance === 1 ? .76 : .64);
      card.style.setProperty('--opacity', distance < 2 ? 1 : distance === 2 ? .25 : 0);
      card.style.setProperty('--layer', 5 - Math.min(distance, 5));
      card.classList.toggle('is-active', i === current);
      card.inert = distance > 1;
      card.setAttribute('aria-roledescription', '幻灯片');
      card.setAttribute('aria-label', `${i + 1} / ${cards.length} · ${card.querySelector('h3').textContent}`);
      indicators[i].setAttribute('aria-current', String(i === current));
    });
    count.textContent = `${String(current + 1).padStart(2, '0')} / ${String(cards.length).padStart(2, '0')}`;
  };
  feed.querySelector('.overview-prev').addEventListener('click', () => select(current - 1));
  feed.querySelector('.overview-next').addEventListener('click', () => select(current + 1));
  indicators.forEach((button, i) => button.addEventListener('click', () => select(i)));
  cards.forEach((card, i) => card.addEventListener('click', event => {
    if (i !== current) {
      event.preventDefault();
      select(i);
      (card.querySelector('a') || card).focus({preventScroll: true});
    }
  }));
  feed.addEventListener('keydown', event => {
    if (!event.target.closest('.overview-carousel, .overview-pagination')) return;
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    select(event.key === 'Home' ? 0 : event.key === 'End' ? cards.length - 1 : current + (event.key === 'ArrowRight' ? 1 : -1));
    (cards[current].querySelector('a') || cards[current]).focus({preventScroll: true});
  });
  let touchStart;
  let suppressClickUntil = 0;
  carousel.addEventListener('touchstart', event => {
    touchStart = event.touches.length === 1 ? {x: event.touches[0].clientX, y: event.touches[0].clientY} : null;
    suppressClickUntil = 0;
  }, {passive: true});
  carousel.addEventListener('touchend', event => {
    if (!touchStart) return;
    const dx = event.changedTouches[0].clientX - touchStart.x;
    const dy = event.changedTouches[0].clientY - touchStart.y;
    if (Math.abs(dx) > 45 && Math.abs(dx) > Math.abs(dy)) {
      suppressClickUntil = Date.now() + 400;
      select(current + (dx < 0 ? 1 : -1));
    }
    touchStart = null;
  }, {passive: true});
  carousel.addEventListener('touchcancel', () => { touchStart = null; }, {passive: true});
  carousel.addEventListener('click', event => {
    if (Date.now() < suppressClickUntil) {
      event.preventDefault();
      event.stopPropagation();
      suppressClickUntil = 0;
    }
  }, true);
  select(0);
  feed.classList.add('is-ready');
  feed.classList.toggle('is-single', cards.length === 1);
}

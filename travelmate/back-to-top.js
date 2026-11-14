window.addEventListener('DOMContentLoaded', () => {
  if (document.querySelector('.back-to-top')) return;

  const style = document.createElement('style');
  style.textContent = `
    .back-to-top {
      position: fixed; right: max(28px, env(safe-area-inset-right)); bottom: 28px;
      z-index: 6; display: grid; place-items: center; width: 48px; height: 48px;
      min-height: 48px; padding: 0; border: 1px solid #dedfd5; border-radius: 50%;
      background: #fffefa; color: #087f7a; cursor: pointer;
      box-shadow: 0 4px 14px #193c3814; transition: background .18s, box-shadow .18s;
    }
    .back-to-top[hidden] { display: none; }
    .back-to-top:hover { background: #eaf3ee; box-shadow: 0 6px 18px #193c3820; }
    .back-to-top:focus-visible { outline: 3px solid #087f7a; outline-offset: 4px; }
    .back-to-top svg { width: 24px; height: 24px; }
    .back-to-top span {
      position: absolute; right: calc(100% + 12px); padding: 5px 10px;
      border-radius: 8px; background: #193c38; color: #fff; white-space: nowrap;
      font: 13px/1.6 'Segoe UI', 'Microsoft YaHei', sans-serif;
      opacity: 0; pointer-events: none;
    }
    .back-to-top:hover span, .back-to-top:focus-visible span { opacity: 1; }
    body:has(.conversation #messages:not(:empty)) .back-to-top {
      bottom: calc(100dvh - var(--back-to-top-edge) + 16px);
    }
    @media (max-width: 850px) {
      .back-to-top { right: max(18px, env(safe-area-inset-right)); bottom: max(20px, env(safe-area-inset-bottom)); }
      .library-page:not(.guide-detail-page) .back-to-top { bottom: calc(92px + env(safe-area-inset-bottom)); }
    }
    @media (prefers-reduced-motion: reduce) { .back-to-top { transition: none; } }
    @media print { .back-to-top { display: none; } }
  `;
  document.head.append(style);
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'back-to-top';
  button.setAttribute('aria-label', '返回顶部');
  button.hidden = true;
  button.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 4h14M12 20V8m-6 6 6-6 6 6"/></svg><span aria-hidden="true">返回顶部</span>';
  document.body.append(button);

  const messages = document.querySelector('#messages');
  const conversation = document.querySelector('.conversation');
  const main = document.querySelector('main');
  const scroller = () => conversation ? (messages.children.length ? conversation : main) : document.scrollingElement;
  const update = () => {
    button.hidden = scroller().scrollTop < 240;
    if (conversation) button.style.setProperty('--back-to-top-edge', `${conversation.getBoundingClientRect().bottom}px`);
  };
  button.addEventListener('click', () => {
    scroller().scrollTo({top: 0, behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth'});
  });
  document.addEventListener('scroll', update, {capture: true, passive: true});
  window.addEventListener('resize', update);
  window.addEventListener('pageshow', update);
  if (messages) new MutationObserver(update).observe(messages, {childList: true});
  if (conversation) new ResizeObserver(update).observe(conversation);
  update();
});

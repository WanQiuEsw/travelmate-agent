// Authentication stays in an HttpOnly cookie; JavaScript only reads public account data.
export async function apiFetch(url, options = {}) {
  const headers = new Headers(options.headers);
  if (!['GET', 'HEAD'].includes((options.method || 'GET').toUpperCase())) {
    headers.set('X-TravelMate-Request', '1');
  }
  const response = await window.fetch(url, {...options, headers, credentials: 'same-origin'});
  if (response.status === 401) window.location.replace('/login');
  return response;
}

export async function refreshAccount() {
  const response = await apiFetch('/auth/me');
  if (!response.ok) throw new Error('登录状态无法确认，请刷新重试');
  const account = await response.json();
  document.querySelector('#account-name').textContent = account.user.display_name;
  document.querySelector('#account-quota').textContent = `今日剩余 ${account.quota.remaining} / ${account.quota.limit} 次生成`;
  return account;
}

export async function logout() {
  const response = await apiFetch('/auth/logout', {method: 'POST'});
  if (!response.ok) throw new Error('退出失败，请重试');
  window.location.replace('/login');
}

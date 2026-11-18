async function req(path, opts = {}) {
  const r = await fetch('/api' + path, {
    headers: { 'Content-Type': 'application/json', ...(opts.headers || {}) },
    ...opts,
  })
  const text = await r.text()
  let data = null
  try { data = text ? JSON.parse(text) : null } catch { data = text }
  if (!r.ok) {
    const detail = (data && data.detail) || text || r.statusText
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  return data
}

export const api = {
  dashboard: () => req('/dashboard'),
  campaigns: () => req('/campaigns'),
  events: (day) => req('/events' + (day ? `?business_day=${encodeURIComponent(day)}` : '')),
  addEvent: (body) => req('/events', { method: 'POST', body: JSON.stringify(body) }),
  facts: (day) => req('/facts' + (day ? `?business_day=${encodeURIComponent(day)}` : '')),
  preview: (day, campaign) => {
    const q = []
    if (day) q.push(`business_day=${encodeURIComponent(day)}`)
    if (campaign) q.push(`campaign_code=${encodeURIComponent(campaign)}`)
    return req('/redeem/preview' + (q.length ? `?${q.join('&')}` : ''))
  },
  seal: (body) => req('/redeem/seal', { method: 'POST', body: JSON.stringify(body) }),
  batches: () => req('/batches'),
  getDay: () => req('/settings/day'),
  setDay: (business_day) => req('/settings/day', { method: 'PUT', body: JSON.stringify({ business_day }) }),
}

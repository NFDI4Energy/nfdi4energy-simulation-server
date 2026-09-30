// HTTP transport is independent of the demo generator.
async function request(path, signal) {
  const response = await fetch(path, { signal });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `Monitor request failed (${response.status})`);
  return payload;
}

export async function getMonitorSnapshot(taskId, cursor = 0, pinnedMetrics = [], historyIndex = null, options = {}) {
  const params = new URLSearchParams({ cursor: String(cursor) });
  if (historyIndex !== null) params.set('history_index', String(historyIndex));
  if (options.generation) params.set('generation', options.generation);
  return request(`/monitor/${encodeURIComponent(taskId)}/snapshot?${params}`, options.signal);
}

export async function getMonitorDebug(taskId, signal) {
  let cursor = 0;
  let failedEvents = [];
  let page;
  let generation;
  do {
    const params = new URLSearchParams({ cursor: String(cursor) });
    if (generation) params.set('generation', generation);
    page = await request(`/monitor/${encodeURIComponent(taskId)}/debug/failed-events?${params}`, signal);
    if (page.reset) { cursor = 0; failedEvents = []; }
    generation = page.generation;
    failedEvents = [...failedEvents, ...(page.failedEvents || [])].slice(-1000);
    if (page.hasMore && page.cursor <= cursor) throw new Error('Debug pagination did not advance');
    cursor = page.cursor;
  } while (page.hasMore);
  return { failedEvents, count: page.count };
}

export class MosaikError extends Error {
  constructor(message, status = 0, code = '', taskId = null) {
    super(message);
    Object.assign(this, { status, code, taskId });
  }
}

async function request(path, options = {}) {
  const controller = new AbortController();
  const cancel = () => controller.abort();
  options.signal?.addEventListener('abort', cancel, { once: true });
  if (options.signal?.aborted) cancel();
  const timer = setTimeout(cancel, 20000);
  try {
    const response = await fetch(path, { ...options, credentials: 'same-origin', signal: controller.signal });
    let body;
    try { body = await response.json(); }
    catch (error) {
      if (response.ok) throw new MosaikError('Server returned an incomplete response');
      body = {};
    }
    if (!response.ok) {
      throw new MosaikError(body.error || (typeof body.detail === 'string' ? body.detail : 'Request failed'),
        response.status, body.code, body.task_id);
    }
    return body;
  } finally {
    clearTimeout(timer);
    options.signal?.removeEventListener('abort', cancel);
  }
}

export async function submitMosaik(file, signal) {
  const body = new FormData();
  body.append('scenario_file', file);
  const result = await request('/api/mosaik/submit', { method: 'POST', body, signal });
  if (typeof result.task_id !== 'string' || !result.task_id) throw new MosaikError('Submission response omitted the task ID');
  return result;
}

export function listMosaikTasks(cursor = 0, signal) {
  return request(`/api/mosaik/tasks?cursor=${cursor}&limit=100`, { signal });
}

export async function getMosaikTask(taskId, signal) {
  const task = await request(`/check/${encodeURIComponent(taskId)}`, { signal });
  if (task.framework !== 'mosaik') throw new MosaikError('Task is not a Mosaik run', 404);
  return task;
}

export function resultUrl(taskId, filename) {
  return `/download/${encodeURIComponent(taskId)}/${filename.split('/').map(encodeURIComponent).join('/')}`;
}

// One request at a time; each selection owns its timer and cancellation signal.
export function pollMosaikTask(taskId, onTask, onError, {
  read = getMosaikTask, interval = 2000, schedule = setTimeout, unschedule = clearTimeout,
} = {}) {
  const controller = new AbortController();
  let timer;
  let failures = 0;
  async function advance() {
    try {
      const task = await read(taskId, controller.signal);
      if (controller.signal.aborted) return;
      failures = 0;
      onTask(task);
      if (task.status !== 'PENDING' && task.status !== 'RUNNING') return;
    } catch (error) {
      if (controller.signal.aborted) return;
      failures += 1;
      const retry = failures < 3 && (!error.status || error.status >= 500);
      onError(error, retry);
      if (!retry) return;
    }
    if (!controller.signal.aborted) timer = schedule(advance, interval * (2 ** failures));
  }
  advance();
  return () => { controller.abort(); unschedule(timer); };
}

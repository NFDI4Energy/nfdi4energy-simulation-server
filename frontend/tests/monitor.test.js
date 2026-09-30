import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { test } from 'node:test';
import { parse } from 'svelte/compiler';
import { getMonitorDebug, getMonitorSnapshot } from '../src/lib/monitorClient.js';

// Execute the component's request/playback logic without a DOM. Browser layout
// and real EventSource reconnection remain separate integration checks.
function harness(client) {
  const source = readFileSync(new URL('../src/lib/RunMonitor.svelte', import.meta.url), 'utf8');
  const program = parse(source).instance.content;
  let script = source.slice(program.start, program.end);
  for (const node of [...program.body].reverse()) {
    if (['ImportDeclaration', 'LabeledStatement'].includes(node.type)) {
      script = script.slice(0, node.start - program.start) + script.slice(node.end - program.start);
    } else if (node.type === 'ExportNamedDeclaration') {
      script = script.slice(0, node.start - program.start) + script.slice(node.declaration.start - program.start);
    }
  }
  const timers = new Map();
  let timerId = 0;
  const context = vm.createContext({
    AbortController, isRealTask: true, onMount() {}, onDestroy() {},
    getMonitorSnapshot: client, getMonitorDebug: async () => ({}),
    getDefaultPinnedMetrics: () => ['vehicles.active'],
    setTimeout(fn) { timers.set(++timerId, fn); return timerId; },
    clearTimeout(id) { timers.delete(id); }, clearInterval(id) { timers.delete(id); },
  });
  vm.runInContext(script + `
    mounted = true; taskId = 'task';
    globalThis.api = { loadNext, loadPlaybackIndex, startPlayback, stopPlayback, appendStreamEvent,
      read: () => ({ monitor, cursor, playbackIndex, followLatest, loadError, isPlaying }),
      history: index => { followLatest = false; playbackIndex = index; }
    };`, context);
  return { ...context.api, timers };
}

function frame(index, historical = false) {
  return { cursor: index + 1, generation: 'gen', snapshot: { domain: 'traffic', status: 'RUNNING' },
    playback: { index, count: 4 }, entities: [], events: [{ id: String(index) }],
    observables: [{ key: 'vehicles.active' }], frame: { historical } };
}

test('rapid scrubbing aborts superseded request and rejects its late response', async () => {
  const pending = [];
  const view = harness((...args) => new Promise(resolve => pending.push({ args, resolve })));
  const first = view.loadNext(0, 0);
  const second = view.loadNext(0, 2);
  assert.equal(pending[0].args[4].signal.aborted, true);
  pending[1].resolve(frame(2, true));
  await second;
  pending[0].resolve(frame(0, true));
  await first;
  assert.equal(view.read().playbackIndex, 2);
});

test('live arrivals never change a selected historical frame or its logs', async () => {
  const view = harness(async () => frame(0, true));
  view.history(0);
  await view.loadNext(0, 0);
  view.appendStreamEvent({ cursor: 10, generation: 'gen', event: { id: 'live' } });
  assert.equal(view.read().monitor.events.length, 1);
  assert.equal(view.read().monitor.events[0].id, '0');
  assert.equal(view.read().cursor, 10);
});

test('historical seeks replace logs instead of merging later events', async () => {
  const view = harness(async (_task, _cursor, _pins, index) => frame(index, true));
  await view.loadNext(0, 3);
  await view.loadNext(0, 0);
  assert.equal(view.read().monitor.events.length, 1);
  assert.equal(view.read().monitor.events[0].id, '0');
});

test('playback schedules its next advance only after the pending frame completes', async () => {
  let resolveFrame;
  let calls = 0;
  const view = harness(() => ++calls === 1 ? Promise.resolve(frame(0)) : new Promise(resolve => { resolveFrame = resolve; }));
  await view.loadNext();
  await view.startPlayback();
  assert.equal(view.timers.size, 1);
  const [id, advance] = [...view.timers][0];
  view.timers.delete(id);
  const pending = advance();
  assert.equal(view.timers.size, 0);
  assert.equal(calls, 2);
  resolveFrame(frame(1, true));
  await pending;
  assert.equal(view.timers.size, 1);
  view.stopPlayback();
  assert.equal(view.timers.size, 0);
});

test('snapshot transport forwards cancellation, cursor, frame and generation', async () => {
  const previous = globalThis.fetch;
  const controller = new AbortController();
  globalThis.fetch = async (path, options) => {
    const url = new URL(path, 'http://test');
    assert.equal(url.searchParams.get('history_index'), '2');
    assert.equal(url.searchParams.get('generation'), 'gen');
    assert.equal(options.signal, controller.signal);
    return { ok: true, json: async () => frame(2, true) };
  };
  try {
    await getMonitorSnapshot('task', 1, [], 2, { signal: controller.signal, generation: 'gen' });
  } finally { globalThis.fetch = previous; }
});

test('debug transport follows subsequent pages', async () => {
  const previous = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = async () => ({ ok: true, json: async () => ({
    failedEvents: [{ id: String(++calls) }], cursor: calls, count: 2, hasMore: calls < 2,
  }) });
  try {
    const result = await getMonitorDebug('task');
    assert.equal(result.failedEvents.length, 2);
    assert.equal(calls, 2);
  } finally { globalThis.fetch = previous; }
});

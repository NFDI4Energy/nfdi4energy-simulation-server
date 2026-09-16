import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { parse } from 'svelte/compiler';
import { pollMosaikTask, resultUrl, MosaikError, getMosaikTask, submitMosaik } from '../src/lib/mosaikClient.js';

const settle = () => new Promise(resolve => setImmediate(resolve));

test('scenario authoring opens the external GUI in a separate protected tab', () => {
  const source = readFileSync(new URL('../src/lib/MosaikWorkspace.svelte', import.meta.url), 'utf8');
  const ast = parse(source);
  let anchor;
  function visit(node) {
    if (!node || typeof node !== 'object') return;
    if (node.type === 'Element' && node.name === 'a' && node.attributes.some(
      attr => attr.name === 'class' && attr.value?.some(value => value.data?.includes('create-scenario')))) anchor = node;
    for (const value of Object.values(node)) {
      if (Array.isArray(value)) value.forEach(visit);
      else if (value && typeof value === 'object') visit(value);
    }
  }
  visit(ast.html);
  assert.ok(anchor);
  const attr = name => anchor.attributes.find(item => item.name === name).value[0];
  assert.equal(attr('target').data, '_blank');
  assert.equal(attr('rel').data, 'noopener noreferrer');
  assert.equal(attr('href').expression.name, 'guiUrl');
  const declaration = ast.instance.content.body.flatMap(node => node.declarations || []).find(node => node.id.name === 'guiUrl');
  assert.equal(declaration.init.value, 'http://localhost:8002');
});

test('polling serializes reads and stops on terminal state', async () => {
  const timers = [], states = [];
  let release;
  let reads = 0;
  const read = () => { reads++; return new Promise(resolve => { release = resolve; }); };
  const stop = pollMosaikTask('task', row => states.push(row.status), assert.fail,
    { read, schedule: callback => timers.push(callback), unschedule: () => {} });
  assert.equal(reads, 1);
  assert.equal(timers.length, 0);
  release({ status: 'RUNNING' });
  await settle();
  assert.equal(timers.length, 1);
  timers.shift()();
  release({ status: 'DONE' });
  await settle();
  assert.deepEqual(states, ['RUNNING', 'DONE']);
  assert.equal(timers.length, 0);
  stop();
});

test('leaving a task aborts and ignores a late response', async () => {
  let release, signal;
  const states = [];
  const stop = pollMosaikTask('old', row => states.push(row), assert.fail, {
    read: (id, value) => { signal = value; return new Promise(resolve => { release = resolve; }); },
    schedule: assert.fail, unschedule: () => {},
  });
  stop();
  release({ status: 'RUNNING' });
  await settle();
  assert.equal(signal.aborted, true);
  assert.equal(states.length, 0);
});

test('UNKNOWN does not schedule endless polling', async () => {
  pollMosaikTask('task', () => {}, assert.fail, { read: async () => ({ status: 'UNKNOWN' }), schedule: assert.fail });
  await settle();
});

test('transient reads retry at most three times, authentication does not retry', async () => {
  const timers = [], retrying = [];
  pollMosaikTask('task', assert.fail, (error, retry) => retrying.push(retry), {
    read: async () => { throw new MosaikError('Offline', 503); }, schedule: fn => timers.push(fn),
  });
  await settle();
  while (timers.length) { timers.shift()(); await settle(); }
  assert.deepEqual(retrying, [true, true, false]);
  pollMosaikTask('task', assert.fail, (error, retry) => assert.equal(retry, false), {
    read: async () => { throw new MosaikError('Sign in', 401); }, schedule: assert.fail,
  });
  await settle();
});

test('wrong framework rejected and ambiguous submission returns task id without retry', async () => {
  const original = globalThis.fetch;
  try {
    globalThis.fetch = async () => new Response(JSON.stringify({ framework: 'dacedsx' }));
    await assert.rejects(getMosaikTask('task'), error => error.status === 404);
    let calls = 0;
    globalThis.fetch = async () => { calls++; return new Response(JSON.stringify({
      error: 'Unknown', code: 'submission_outcome_unknown', task_id: 'retained',
    }), { status: 503 }); };
    await assert.rejects(submitMosaik(new Blob(['{}'])), error => error.taskId === 'retained');
    assert.equal(calls, 1);
  } finally { globalThis.fetch = original; }
});

test('download path encodes each filename segment', () => {
  assert.equal(resultUrl('task', 'a folder/x#1.json'), '/download/task/a%20folder/x%231.json');
});

test('incomplete successful submission response is not treated as a task', async () => {
  const original = globalThis.fetch;
  try {
    for (const body of ['{', '{}']) {
      let calls = 0;
      globalThis.fetch = async () => { calls++; return new Response(body); };
      await assert.rejects(submitMosaik(new Blob(['{}'])), error => error.status === 0 && !error.taskId);
      assert.equal(calls, 1);
    }
  } finally { globalThis.fetch = original; }
});

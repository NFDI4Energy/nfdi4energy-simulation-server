const energyNodes = [
  { id: "bus-1", label: "Bus 1", x: 18, y: 24, voltage: 1.01 },
  { id: "bus-2", label: "Bus 2", x: 44, y: 18, voltage: 0.99 },
  { id: "bus-3", label: "Bus 3", x: 70, y: 31, voltage: 1.04 },
  { id: "bus-4", label: "Bus 4", x: 34, y: 66, voltage: 0.97 },
  { id: "bus-5", label: "Bus 5", x: 67, y: 72, voltage: 1.02 },
];

const energyEdges = [
  { id: "line-1", from: "bus-1", to: "bus-2", loading: 48 },
  { id: "line-2", from: "bus-2", to: "bus-3", loading: 72 },
  { id: "line-3", from: "bus-2", to: "bus-4", loading: 58 },
  { id: "line-4", from: "bus-4", to: "bus-5", loading: 84 },
  { id: "line-5", from: "bus-3", to: "bus-5", loading: 66 },
];

const trafficRoads = [
  { id: "edge-a", points: [[8, 50], [28, 50], [46, 42], [66, 42], [92, 46]] },
  { id: "edge-b", points: [[34, 12], [42, 35], [46, 62], [58, 88]] },
  { id: "edge-c", points: [[18, 78], [38, 64], [61, 61], [82, 74]] },
  { id: "edge-d", points: [[22, 24], [40, 36], [64, 48], [78, 30]] },
];

const observablePresets = {
  energy: [
    { key: "bus.vm_pu.min", label: "Min voltage", unit: "p.u.", default: true, visualization: "card" },
    { key: "bus.vm_pu.max", label: "Max voltage", unit: "p.u.", default: true, visualization: "card" },
    { key: "line.loading_percent.max", label: "Max line loading", unit: "%", default: true, visualization: "card" },
    { key: "load.p_mw.total", label: "Total load", unit: "MW", default: true, visualization: "line" },
    { key: "grid.losses_mw", label: "Grid losses", unit: "MW", default: false, visualization: "line" },
    { key: "converged", label: "Converged", unit: "", default: false, visualization: "event" },
  ],
  traffic: [
    { key: "vehicles.active", label: "Active vehicles", unit: "", default: true, visualization: "card" },
    { key: "speed.avg_mps", label: "Average speed", unit: "m/s", default: true, visualization: "card" },
    { key: "vehicles.arrived", label: "Arrived", unit: "", default: true, visualization: "line" },
  ],
};

function wave(step, amplitude, offset, speed = 1) {
  return offset + Math.sin(step / speed) * amplitude;
}

function round(value, digits = 2) {
  return Number(value.toFixed(digits));
}

function buildHistory(step, keys, domain) {
  const start = Math.max(0, step - 22);
  return Array.from({ length: step - start + 1 }, (_, index) => {
    const t = start + index;
    return {
      time: t * 10,
      values: buildMetrics(t, domain, keys),
    };
  });
}

function buildMetrics(step, domain, keys = []) {
  const metrics =
    domain === "energy"
      ? {
          "bus.vm_pu.min": round(0.965 + wave(step, 0.018, 0, 4), 3),
          "bus.vm_pu.max": round(1.035 + wave(step + 3, 0.015, 0, 5), 3),
          "line.loading_percent.max": round(68 + wave(step, 14, 0, 3), 1),
          "load.p_mw.total": round(18.5 + wave(step, 3.4, 0, 4), 1),
          "grid.losses_mw": round(0.72 + wave(step + 2, 0.15, 0, 6), 2),
          converged: step % 13 !== 0,
        }
      : {
          "vehicles.active": Math.round(165 + wave(step, 42, 0, 4)),
          "speed.avg_mps": round(9.8 + wave(step + 1, 2.2, 0, 5), 1),
          "vehicles.arrived": Math.max(0, Math.round(step * 5 + wave(step, 7, 0, 2))),
        };

  if (keys.length === 0) return metrics;
  return keys.reduce((picked, key) => {
    picked[key] = metrics[key];
    return picked;
  }, {});
}

function buildEnergyNetwork(step) {
  return {
    nodes: energyNodes.map((node, index) => ({
      ...node,
      voltage: round(node.voltage + wave(step + index, 0.018, 0, 4), 3),
    })),
    edges: energyEdges.map((edge, index) => ({
      ...edge,
      loading: round(edge.loading + wave(step + index, 9, 0, 3), 1),
    })),
  };
}

function buildTrafficEntities(step) {
  return Array.from({ length: 22 }, (_, index) => {
    const lane = index % trafficRoads.length;
    const progress = (step * (1.8 + (index % 5) * 0.18) + index * 9) % 100;
    const baseY = 22 + lane * 16;
    return {
      id: `veh-${String(index + 1).padStart(2, "0")}`,
      kind: "vehicle",
      x: round((progress + wave(step + index, 2.4, 0, 3)) % 100, 1),
      y: round(baseY + wave(step + index, 5.5, 0, 5), 1),
      speed: round(7.5 + ((index * 0.6) % 5) + wave(step + index, 1.8, 0, 4), 1),
      edge: trafficRoads[lane].id,
      status: index % 9 === step % 9 ? "slow" : "moving",
    };
  });
}

function buildEvents(step, domain) {
  const base = [
    { time: step * 10, level: "info", source: "orchestrator", message: "Timestep committed" },
    { time: Math.max(0, step * 10 - 10), level: "info", source: domain === "energy" ? "pandapower_0" : "sumo_0", message: "Telemetry snapshot received" },
  ];

  if (domain === "energy" && step % 7 === 0) {
    base.unshift({
      time: step * 10,
      level: "warning",
      source: "pandapower_0",
      message: "Line loading approaching configured threshold",
    });
  }

  if (domain === "traffic" && step % 6 === 0) {
    base.unshift({
      time: step * 10,
      level: "info",
      source: "sumo_0",
      message: "Vehicle projection updated for monitored edges",
    });
  }

  return base;
}

const runPresets = {
  energy: {
    taskId: "mock-energy-run",
    scenarioId: "pandapower_profile_demo",
    domain: "energy",
    title: "Power-flow profile run",
    simulationStart: 0,
    simulationEnd: 240,
  },
  traffic: {
    taskId: "mock-traffic-run",
    scenarioId: "sumo_projection_demo",
    domain: "traffic",
    title: "SUMO vehicle projection",
    simulationStart: 0,
    simulationEnd: 240,
  },
};

export function getDefaultPinnedMetrics(domain) {
  const preset = observablePresets[domain] || observablePresets.energy;
  return preset.filter((metric) => metric.default).map((metric) => metric.key);
}

export async function getMockMonitorSnapshot(runKey = "energy", cursor = 0, pinnedMetrics = []) {
  const preset = runPresets[runKey] || runPresets.energy;
  const step = cursor % 25;
  const simulationTime = step * 10;
  const status = step > 21 ? "DONE" : step < 2 ? "PENDING" : "RUNNING";
  const metricKeys = pinnedMetrics.length ? pinnedMetrics : getDefaultPinnedMetrics(preset.domain);

  return {
    cursor: cursor + 1,
    snapshot: {
      ...preset,
      status,
      simulationTime,
      progress: simulationTime / preset.simulationEnd,
      updatedAt: new Date().toISOString(),
    },
    metrics: buildMetrics(step, preset.domain),
    metricHistory: buildHistory(step, metricKeys, preset.domain),
    entities: preset.domain === "traffic" ? buildTrafficEntities(step) : [],
    network: preset.domain === "energy" ? buildEnergyNetwork(step) : { roads: trafficRoads },
    events: buildEvents(step, preset.domain),
    observables: observablePresets[preset.domain],
  };
}

export async function getMonitorSnapshot(taskId, cursor = 0, pinnedMetrics = [], historyIndex = null) {
  if (!taskId) {
    return getMockMonitorSnapshot("energy", cursor, pinnedMetrics);
  }

  const params = new URLSearchParams({ cursor: String(cursor) });
  if (historyIndex !== null && historyIndex !== undefined) {
    params.set("history_index", String(historyIndex));
  }

  const response = await fetch(`/monitor/${taskId}/snapshot?${params.toString()}`);
  if (!response.ok) {
    let detail = "";
    try {
      const payload = await response.json();
      detail = payload.error ? `: ${payload.error}` : "";
    } catch (error) {
      detail = "";
    }
    throw new Error(`Failed to load monitor snapshot (${response.status})${detail}`);
  }
  const snapshot = await response.json();
  return {
    ...snapshot,
    observables: snapshot.observables || observablePresets.energy,
    entities: snapshot.entities || [],
    network: snapshot.network || { nodes: [], edges: [], roads: [] },
    events: snapshot.events || [],
    metrics: snapshot.metrics || {},
    metricHistory: snapshot.metricHistory || [],
    playback: snapshot.playback || { index: 0, count: 0, isLatest: true },
  };
}

export async function getMonitorDebug(taskId) {
  if (!taskId) {
    return { failedEvents: [], count: 0 };
  }

  const response = await fetch(`/monitor/${taskId}/debug/failed-events`);
  if (!response.ok) {
    let detail = "";
    try {
      const payload = await response.json();
      detail = payload.error ? `: ${payload.error}` : "";
    } catch (error) {
      detail = "";
    }
    throw new Error(`Failed to load monitor debug data (${response.status})${detail}`);
  }
  const payload = await response.json();
  return {
    failedEvents: payload.failedEvents || [],
    count: payload.count || 0,
  };
}

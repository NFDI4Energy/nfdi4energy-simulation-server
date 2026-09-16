"""Assemble consistent monitor frames from task storage and simulator adapters."""
import xml.etree.ElementTree as ET
from fastapi_app.frameworks.dacedsx.monitoring.adapters.energy import build_pandapower_network, network_object
from fastapi_app.frameworks.dacedsx.monitoring.adapters.traffic import load_roads, projection
from fastapi_app.frameworks.dacedsx.monitoring.scenario_resources import scenario_stream, network_resource, load_json
from fastapi_app.frameworks.dacedsx.monitoring.csv_store import CsvStore
from fastapi_app.frameworks.dacedsx.events.normalization import event_metadata, event_domain, event_time_seconds, safe_float, safe_int, TIME_SCALES
from fastapi_app.frameworks.dacedsx.monitoring.formatting import frontend_event

ENERGY_OBSERVABLES = [
    {"key": "bus.vm_pu.min", "label": "Min voltage", "unit": "p.u.", "default": True, "visualization": "card"},
    {"key": "bus.vm_pu.max", "label": "Max voltage", "unit": "p.u.", "default": True, "visualization": "card"},
    {"key": "line.loading_percent.max", "label": "Max line loading", "unit": "%", "default": True, "visualization": "card"},
    {"key": "load.p_mw.total", "label": "Total load", "unit": "MW", "default": True, "visualization": "line"},
]

TRAFFIC_OBSERVABLES = [
    {"key": "vehicles.active", "label": "Active vehicles", "unit": "", "default": True, "visualization": "card"},
    {"key": "speed.avg_mps", "label": "Average speed", "unit": "m/s", "default": True, "visualization": "card"},
    {"key": "vehicles.arrived", "label": "Arrived", "unit": "", "default": True, "visualization": "line"},
]


class MonitorService:
    def __init__(self, storage, events, status):
        self.storage, self.events, self.status = storage, events, status
        self.csv = CsvStore(events)

    def payload(self, task_id, cursor=0, history_index=None, stored_status=None,
                stored_error=None, resource_files=None, generation=None):
        event_path = self.storage.result_file(task_id, "events/structured_events.jsonl")
        metric_path = self.storage.result_file(task_id, "events/metrics.jsonl")
        scenario, block, warnings = scenario_stream(self.storage, task_id, resource_files)
        domain = block.get("domain")
        if not domain:
            first = self.events.rows(metric_path, limit=1, summaries=True)
            domain = event_domain(first[0][1]) if first else None
            domain = domain or "energy"
            warnings.append("Monitor domain inferred from legacy telemetry")
        instance = block.get("instanceID")
        instance = instance if isinstance(instance, str) else None
        supported = [b for b in scenario.get("buildingBlocks", []) if isinstance(b, dict) and b.get("domain") in ("energy", "traffic")]
        same_domain = sum(b.get("domain") == domain for b in supported)
        where = "(domain=? OR domain IS NULL)" if len(supported) <= 1 else "domain=?"
        params = [domain]
        if instance:
            if same_domain > 1:
                where += " AND instance=?"
                warnings.append("Unidentified wrapper telemetry is excluded from this multi-wrapper run")
            else:
                where += " AND (instance=? OR instance IS NULL)"
            params.append(instance)
        bus_path = self.storage.result_file(task_id, "bus_vm_pu.csv")
        metric_count = self.events.count(metric_path, where, params)
        csv_count = self.csv.info(bus_path)[0] if domain == "energy" and not metric_count else 0
        count = metric_count or csv_count
        selected_index = min(max(0, history_index), count - 1) if count and history_index is not None else max(0, count - 1)
        selected_rows = self.events.rows(metric_path, selected_index, 1, where, params) if metric_count else []
        selected = selected_rows[0][1] if selected_rows else {}
        metadata = event_metadata(selected)
        step = safe_int(metadata.get("step"))
        if csv_count:
            csv_row, inferred = self.csv.row(bus_path, selected_index)
            step = safe_int(csv_row.get("step")) if not inferred else selected_index
            if inferred:
                warnings.append("Legacy CSV frames use positional step matching")
        raw_metrics = metadata.get("metrics")
        metrics = {key: safe_float(value) for key, value in raw_metrics.items()} if isinstance(raw_metrics, dict) else {}
        unit = metadata.get("simulation_time_unit")
        scenario_unit = scenario.get("simulationTimeUnit") or ("ms" if domain == "traffic" else "scenario-unit")
        scale = TIME_SCALES.get(scenario_unit, 1.0) if isinstance(scenario_unit, str) else 1.0
        start, end = safe_float(scenario.get("simulationStart")), safe_float(scenario.get("simulationEnd"))
        start = start * scale if start is not None else None
        end = end * scale if end is not None else None
        time = event_time_seconds(selected, domain)
        if time is not None and ((start is not None and time < start) or (end is not None and time > end)):
            warnings.append("Reported frame time lies outside scenario bounds")
        if time is None and csv_count and step is not None and start is not None:
            length = safe_float(block.get("stepLength"))
            time = start + step * length * scale if length is not None else None
        if unit is None:
            warnings.append("Legacy traffic time assumes milliseconds" if domain == "traffic" else "Legacy energy time uses scenario units")
        if unit is not None and (not isinstance(unit, str) or unit not in TIME_SCALES):
            warnings.append("Unsupported event time unit; frame time is unavailable")
        time_unit = "s" if isinstance(unit, str) and unit in TIME_SCALES or domain == "traffic" else "scenario-unit"
        total_steps = safe_int(metadata.get("total_steps"))
        progress = None
        if step is not None and total_steps and total_steps > 0:
            progress = (step + (1 if domain == "energy" else 0)) / total_steps
        elif time is not None and start is not None and end is not None and end > start:
            progress = (time - start) / (end - start)
        progress = max(0, min(1, progress)) if progress is not None else None
        runtime = self.status.resolve(task_id, stored_status, stored_error)
        if history_index is None and runtime["status"] == "DONE":
            progress = 1.0
        window_start = max(0, selected_index - 79)
        history = self.events.rows(metric_path, window_start, selected_index - window_start + 1,
                                   where, params, summaries=True) if metric_count else []
        metric_history = [{"time": event_time_seconds(e, domain),
                           "values": {k: safe_float(v) for k, v in (event_metadata(e).get("metrics") or {}).items()}}
                          for _, e in history]
        network = {"nodes": [], "edges": [], "roads": []}
        entities = []
        element_values = False
        try:
            resource, resource_warnings = network_resource(self.storage, task_id, block, domain)
            warnings.extend(resource_warnings)
            if domain == "traffic":
                roads = load_roads(resource)
                if not roads:
                    warnings.append("Vehicle projection unavailable without stable network bounds")
                network, entities = projection(roads, metadata.get("entities", []))
                element_values = isinstance(metadata.get("entities"), list)
            elif resource:
                data = network_object(load_json(resource))
                result_index = selected_index if count and (not metric_count or step is not None) else None
                bus_values, inferred = self.csv.row(bus_path, result_index, step)
                line_values, _ = self.csv.row(self.storage.result_file(task_id, "line_loading_percent.csv"),
                                               result_index, step)
                if inferred:
                    warnings.append("Legacy CSV frame association is positional")
                network = build_pandapower_network(data, bus_values, line_values)
                element_values = any(node.get("voltage") is not None for node in network["nodes"])
                if not bus_values:
                    warnings.append("Per-bus values unavailable for this frame")
                if not line_values:
                    warnings.append("Per-line loading unavailable for this frame")
        except (OSError, ValueError, TypeError, ET.ParseError) as exc:
            warnings.append("Network data unavailable: " + type(exc).__name__)
        if history_index is None:
            info = self.events.info(event_path)
            # Initial snapshot is a tail. Subsequent pages advance without skipping.
            initial = cursor == 0 and generation is None
            page = self.events.page(event_path, max(0, info["count"] - 80) if initial else cursor, 80, generation)
            visible = page.pop("rows")
        else:
            page = self.events.info(event_path)
            page.update(cursor=page["count"], hasMore=False, reset=False)
            if time is None:
                visible = []
            else:
                # SQL time is normalized per event; legacy energy uses scenario units.
                historical = self.events.rows(event_path, limit=80,
                    where=where + " AND time IS NOT NULL AND "
                          "(CASE WHEN domain IS NULL AND time_unit IS NULL AND ?='traffic' "
                          "THEN time*0.001 ELSE time END)<=?",
                    params=params + [domain, time], reverse=True)
                visible = [event for _, event in reversed(historical)]
        run_events = self.events.rows(event_path, limit=80, where="time IS NULL", reverse=True)
        observables = TRAFFIC_OBSERVABLES if domain == "traffic" else ENERGY_OBSERVABLES
        return {
            **page,
            "snapshot": {
                "taskId": task_id, "domain": domain,
                "title": "SUMO traffic run" if domain == "traffic" else "Simulation run",
                **runtime, "simulationTime": time, "simulationStart": start,
                "simulationEnd": end, "timeUnit": time_unit, "progress": progress,
                "updatedAt": selected.get("timestamp"),
            },
            "metrics": metrics, "metricHistory": metric_history,
            "network": network, "entities": entities,
            "events": [frontend_event(e, domain) for e in visible if history_index is None or event_time_seconds(e, domain) is not None],
            "runEvents": [frontend_event(e) for _, e in reversed(run_events)],
            "observables": observables,
            "availability": {"metrics": bool(selected_rows), "elementValues": element_values,
                             "topology": bool(network["nodes"] or network["roads"]),
                             "limitations": list(dict.fromkeys(warnings))},
            "frame": {"step": step, "time": time, "instanceId": instance, "historical": history_index is not None},
            "playback": {"index": selected_index, "count": count, "isLatest": not count or selected_index == count - 1},
        }

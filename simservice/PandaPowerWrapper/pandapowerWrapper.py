import sys
import os
import time

this_directory = os.path.dirname(os.path.abspath(__file__))

for subdir in ['PythonBaseWrapper/src/logic', 'PythonBaseWrapper/src/communication',
               '../PythonBaseWrapper/src/logic', '../PythonBaseWrapper/src/communication',
               '/app/PythonBaseWrapper/src/logic', '/app/PythonBaseWrapper/src/communication']:
    path = os.path.join(this_directory, subdir) if not subdir.startswith('/') else subdir
    if os.path.exists(path):
        sys.path.append(path)

try:
    from TimeSync import TimeSync
    from KafkaConsumer import KafkaConsumer
    from KafkaProducer import KafkaProducer
except ImportError:
    print("Warning: PythonBaseWrapper modules not found.")
    TimeSync = KafkaConsumer = KafkaProducer = None

from pandapowerApi import pandapowerAPI
from simulation_event_emitter import SimulationEventEmitter


def read_properties(path):
    props = {}
    if not os.path.exists(path):
        return props

    with open(path, 'r') as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' not in line:
                continue
            key, value = line.split('=', 1)
            props[key.strip()] = value.strip()
    return props


def parse_float(value, fallback=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


class PandapowerWrapper:
    def __init__(self, scenarioID, instanceID, task_id=None, config_path='/data/config.properties'):
        self.scenarioID = scenarioID
        self.instanceID = instanceID
        self.task_id = task_id

        config = read_properties(config_path)
        
        def get_config(key, fallback):
            return os.getenv(key, os.getenv(key.upper(), config.get(key, fallback)))
        
        self.broker = get_config('kafkaBroker', 'localhost:9092')
        self.registry = get_config('schemaRegistry', 'http://localhost:8081')
        if task_id:
            resource_base = get_config('resourceDir', '/data/resources')
            results_base = get_config('resultsDir', '/data/results')
            self.resource_dir = os.getenv('RESOURCES_DIR', os.path.join(resource_base, task_id))
            self.results_dir = os.getenv('RESULTS_DIR', os.path.join(results_base, task_id))
        else:
            self.resource_dir = get_config('resourceDir', '/data/resources')
            base_results_dir = get_config('resultsDir', '/data/results')
            self.results_dir = os.path.join(base_results_dir, scenarioID)
        
        self.kid = f"{scenarioID}.{instanceID}"
        self.topic_scenario = [f"provision.simulation.{scenarioID}.scenario"]
        self.topic_time = f"orchestration.simulation.{scenarioID}.sync"
        self.topic_status = f"orchestration.simulation.{scenarioID}.status"
        
        self.status_producer = KafkaProducer(self.broker, self.registry, self.kid, useAvro=False) if KafkaProducer else None
        self.event_emitter = SimulationEventEmitter(
            task_id,
            "wrapper",
            "PandapowerWrapper",
            producer=self.status_producer,
            results_dir=self.results_dir,
        )
        self.sim_config = None
        self.scenario_data = None
        self.network_file = None
        self.api = None
        self.timeSync = None

    def log(self, msg):
        print(f"[{self.instanceID}] {msg}", flush=True)
        if self.status_producer:
            try:
                self.status_producer.produce(self.topic_status, f"{self.instanceID}: {msg}")
            except:
                pass

    def wait_for_scenario(self):
        self.log("Waiting for scenario...")
        self.event_emitter.emit("WRAPPER", "CONFIG_WAIT_STARTED", "Waiting for scenario configuration")
        consumer = KafkaConsumer(self.broker, self.registry, self.topic_scenario, self.kid + ".sce")
        
        while True:
            msg = consumer.poll(1.0)
            if msg is None or msg.error():
                continue
            scenario = msg.value()
            for block in scenario.get('buildingBlocks', []):
                if block['instanceID'] == self.instanceID:
                    self.sim_config = block
                    self.scenario_data = scenario
                    self.log(f"Found config for {self.instanceID}")
                    self.event_emitter.emit("WRAPPER", "CONFIG_RECEIVED", "Scenario configuration received")
                    break
            if self.sim_config:
                break
        consumer.stop()
        
        for res_id, res_type in self.sim_config.get('resources', {}).items():
            if res_type == 'Network':
                self.network_file = res_id
                break
        
        if not self.network_file:
            self.log("ERROR: No Network resource found")
            self.event_emitter.emit("ERROR", "NETWORK_RESOURCE_MISSING", "No Network resource found", metadata={"fatal": True})
            sys.exit(1)

    def run(self):
        failed = False
        self.event_emitter.emit("WRAPPER", "WRAPPER_STARTED", "PandaPower wrapper started", progress=0.20)
        if self.task_id:
            self.log(f"Task data directory: {os.getenv('TASK_DIR', os.path.dirname(self.results_dir))}")
        self.log(f"Resource directory: {self.resource_dir}")
        self.log(f"Results directory: {self.results_dir}")

        self.wait_for_scenario()
        
        net_path = os.path.join(self.resource_dir, self.network_file)
        self.log(f"Loading network: {net_path}")
        self.event_emitter.emit("SIMULATION", "NETWORK_LOADING_STARTED", "Loading PandaPower network")
        
        step_size = self.sim_config.get('stepLength', 1000)
        sim_end = self.scenario_data.get('simulationEnd', 1000)
        n_steps = max(1, sim_end // step_size)
        parameters = self.sim_config.get('parameters', {}) or {}
        step_delay_seconds = parse_float(
            parameters.get('stepDelaySeconds'),
            parse_float(os.getenv('PANDAPOWER_STEP_DELAY_SECONDS'), 0.0),
        )
        if 'stepDelayMs' in parameters:
            step_delay_seconds = parse_float(parameters.get('stepDelayMs'), 0.0) / 1000.0
        step_delay_seconds = max(0.0, step_delay_seconds)
        
        self.api = pandapowerAPI(net_path, step_size, n_steps, self.results_dir)
        try:
            self.api.init()
            self.event_emitter.emit("SIMULATION", "NETWORK_LOADED", "PandaPower network loaded")
            
            synced = self.scenario_data.get('execution', {}).get('syncedParticipants', 1)
            self.timeSync = TimeSync(self.broker, self.registry, self.topic_time, self.kid + ".ts", synced, logging=False)
            self.timeSync.joinTiming()
            self.log("TimeSync joined. Running simulation...")
            self.event_emitter.emit("PROGRESS", "SIMULATION_STARTED", "PandaPower simulation started", progress=0.20, simulation_time=0)

            for step in range(n_steps):
                self.timeSync.timeAdvance(step_size)
                self.log(f"Step {step}")
                self.api.prepareStep(step)
                converged = self.api.step(step)
                simulation_time = step * step_size
                progress = 0.20 + (0.70 * ((step + 1) / n_steps))
                metrics = self.api.get_metric_snapshot()
                self.event_emitter.metric_snapshot(
                    simulation_time,
                    metrics,
                    progress=progress,
                    metadata={"step": step, "total_steps": n_steps, "converged": converged},
                )
                if not converged:
                    self.event_emitter.emit(
                        "WARNING",
                        "POWER_FLOW_NOT_CONVERGED",
                        f"Power flow did not converge at step {step}",
                        progress=progress,
                        simulation_time=simulation_time,
                        metadata={"step": step},
                    )
                self.event_emitter.emit(
                    "PROGRESS",
                    "STEP_COMPLETED",
                    f"Completed step {step + 1}/{n_steps}",
                    progress=progress,
                    simulation_time=simulation_time,
                    metadata={"step": step, "total_steps": n_steps},
                )
                if step_delay_seconds:
                    time.sleep(step_delay_seconds)
        except Exception as e:
            failed = True
            self.log(f"Error: {e}")
            self.event_emitter.emit("ERROR", "WRAPPER_FAILED", f"PandaPower wrapper failed: {e}", metadata={"fatal": True})
        finally:
            self.log("Exporting results...")
            self.event_emitter.emit("RESULT", "RESULT_EXPORT_STARTED", "Exporting PandaPower results", progress=0.92)
            try:
                if self.api and self.api.bus_vm is not None:
                    self.api.export_results()
                    self.event_emitter.emit("RESULT", "RESULT_EXPORT_COMPLETED", "PandaPower results exported", progress=0.98)
            except Exception as e:
                failed = True
                self.event_emitter.emit("ERROR", "RESULT_EXPORT_FAILED", f"Failed to export PandaPower results: {e}", metadata={"fatal": True})
            if self.timeSync:
                self.timeSync.leaveTiming()
            if failed:
                sys.exit(1)
            self.event_emitter.emit("WRAPPER", "WRAPPER_COMPLETED", "PandaPower wrapper completed", progress=1.0)
            self.log("Done.")


def main():
    if len(sys.argv) > 2:
        scenarioID, instanceID = sys.argv[1], sys.argv[2]
        task_id = sys.argv[3] if len(sys.argv) > 3 else os.getenv('TASK_ID')
    else:
        print("Usage: python pandapowerWrapper.py <scenarioID> <instanceID> [task_id]")
        sys.exit(1)

    wrapper = PandapowerWrapper(scenarioID, instanceID, task_id)
    wrapper.run()


if __name__ == '__main__':
    main()

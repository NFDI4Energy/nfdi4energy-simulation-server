import sys
import os
import csv
import json
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

CHARGING_SETPOINT_SCHEMA = os.path.join(this_directory, "AvroSchemas", "ChargingSetpoint.avsc")


def read_properties(path):
    props = {}
    if not os.path.exists(path):
        return props
    with open(path, 'r') as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            props[key.strip()] = value.strip()
    return props


def parse_float(value, fallback=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


# ---------------------------------------------------------------------------
# Batterie-/SOC-Modell pro Station (siehe fruehere Absprache: Ladedauer
# und Netzverletzungen sind die eigentliche Payoff-Metrik des Workshops)
# ---------------------------------------------------------------------------
class StationState:
    def __init__(self, label, battery_capacity_kWh=50.0, target_soc=0.8,
                 start_soc=0.2, efficiency=0.9):
        self.label = label
        self.battery_capacity_kWh = battery_capacity_kWh
        self.target_soc = target_soc
        self.efficiency = efficiency

        self.present = False
        self.vehicle_id = None
        self.soc = start_soc
        self.arrival_time = None
        self.departure_time = None
        self.charge_complete_time = None
        self.grid_violation_seen = False

    def arrive(self, vehicle_id, sim_time):
        if not self.present:
            self.present = True
            self.vehicle_id = vehicle_id
            self.arrival_time = sim_time
            self.soc = 0.2  # TODO: ggf. randomisieren/aus Szenario-Parametern lesen
            self.charge_complete_time = None

    def depart(self, sim_time):
        if self.present:
            self.present = False
            self.departure_time = sim_time
            self.vehicle_id = None

    def apply_charging(self, allowed_power_kW, dt_hours, sim_time):
        if not self.present:
            return
        energy_kWh = allowed_power_kW * dt_hours * self.efficiency
        self.soc = min(1.0, self.soc + energy_kWh / self.battery_capacity_kWh)
        if self.soc >= self.target_soc and self.charge_complete_time is None:
            self.charge_complete_time = sim_time

    def requested_power_kW(self, max_power_kW):
        if not self.present or self.soc >= self.target_soc:
            return 0.0
        return max_power_kW


# ---------------------------------------------------------------------------
# Controller-Entscheidungslogik: drei austauschbare Modi mit identischer
# Signatur. Genau dieser Austausch ist die Kernaussage des Workshops.
# ---------------------------------------------------------------------------
def decide_uncontrolled(requests, capacity_kW):
    """Jede Station bekommt exakt das, was sie anfordert - keine Ruecksicht
    auf die gemeinsame Trafokapazitaet."""
    return dict(requests)


def decide_safe_mode(requests, capacity_kW):
    """Reaktiv: wird die Kapazitaet ueberschritten, kuerzen wir ALLE
    aktiven Stationen gleichmaessig (proportional), bis die Summe passt."""
    total_requested = sum(requests.values())
    if total_requested <= capacity_kW or total_requested == 0:
        return dict(requests)
    scale = capacity_kW / total_requested
    return {label: p * scale for label, p in requests.items()}


def decide_heuristic(requests, capacity_kW):
    """Vorausschauender: Stationen, die kurz vor dem Ladeziel stehen (wenig
    angefordert), werden zuerst bedient, der Rest wird von der verbleibenden
    Kapazitaet proportional versorgt. Einfache Prioritaets-Heuristik, kein
    echtes Optimierungsproblem - bewusst simpel fuer den Workshop."""
    remaining = capacity_kW
    allocation = {}
    # kleine Anforderungen zuerst -> die "fast fertigen" Stationen werden
    # bevorzugt komplett bedient, bevor grosse Anforderungen Kapazitaet fressen
    for label, req in sorted(requests.items(), key=lambda kv: kv[1]):
        granted = min(req, remaining)
        allocation[label] = granted
        remaining -= granted
    return allocation


CONTROLLER_MODES = {
    "uncontrolled": decide_uncontrolled,
    "safe_mode": decide_safe_mode,
    "heuristic": decide_heuristic,
}


class ControllerWrapper:
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
            self.results_dir = os.path.join(get_config('resultsDir', '/data/results'), scenarioID)

        self.kid = f"{scenarioID}.{instanceID}"
        self.topic_scenario = [f"provision.simulation.{scenarioID}.scenario"]
        self.topic_time = f"orchestration.simulation.{scenarioID}.sync"
        self.topic_setpoints = f"interaction.simulation.{scenarioID}.charging.setpoints"

        self.sim_config = None
        self.scenario_data = None
        self.station_mapping = None
        self.mode_name = "uncontrolled"
        self.capacity_kW = 160.0  # Trafo-Kapazitaet, siehe build_workshop_network.py
        self.timeSync = None
        self.vehicle_consumers = {}  # label -> KafkaConsumer
        self.setpoint_producer = None
        self.stations = {}  # label -> StationState
        self.current_sim_time = 0

    def log(self, msg):
        print(f"[{self.instanceID}] {msg}", flush=True)

    def wait_for_scenario(self):
        self.log("Waiting for scenario...")
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
                    break
            if self.sim_config:
                break
        consumer.stop()

        # Controller-Modus kommt als Parameter aus der Szenario-Definition -
        # so laeuft dasselbe Image dreimal, nur mit anderem instanceID +
        # anderem Parameter, statt 3 separate Images bauen zu muessen.
        parameters = self.sim_config.get('parameters', {}) or {}
        self.mode_name = parameters.get('controllerMode', 'uncontrolled')
        self.capacity_kW = parse_float(parameters.get('transformerCapacity_kW'), 160.0)
        if self.mode_name not in CONTROLLER_MODES:
            self.log(f"WARNING: unknown controllerMode '{self.mode_name}', falling back to uncontrolled")
            self.mode_name = 'uncontrolled'
        self.log(f"Controller mode: {self.mode_name}, capacity: {self.capacity_kW} kW")

        # station_mapping.json muss als Resource vom Typ 'Config' an dieses
        # Szenario angehaengt sein (Schritt 4). 'Config' ist einer der im
        # Dashboard fest vorgegebenen Ressourcentypen (siehe
        # ScenarioBBCard.svelte resourceTypeOptions) - ein eigener Typ
        # 'StationMapping' steht dort nicht zur Auswahl.
        mapping_file = None
        for res_id, res_type in self.sim_config.get('resources', {}).items():
            if res_type == 'Config':
                mapping_file = res_id
                break
        if not mapping_file:
            self.log("ERROR: No StationMapping resource found")
            sys.exit(1)

        with open(os.path.join(self.resource_dir, mapping_file)) as f:
            self.station_mapping = json.load(f)['stations']

        for entry in self.station_mapping:
            self.stations[entry['label']] = StationState(entry['label'])

    def setup_kafka(self):
        self.vehicle_topics = {}
        for entry in self.station_mapping:
            edge = entry['sumo_edge']
            topic = f"provision.simulation.{self.scenarioID}.traffic.micro.edge.{edge}.vehicles"
            self.vehicle_topics[entry['label']] = topic
            self.vehicle_consumers[entry['label']] = KafkaConsumer(
                self.broker, self.registry, [topic], f"{self.kid}.{entry['label']}"
            )

        self.setpoint_producer = KafkaProducer(
            self.broker, self.registry, self.kid,
            useAvro=True, schemaPath=CHARGING_SETPOINT_SCHEMA,
        )

    def poll_vehicle_presence(self, sim_time):
        """Fuer jede Station den KOMPLETTEN seit dem letzten Schritt
        aufgelaufenen Nachrichten-Rueckstand leeren (nicht nur eine
        Nachricht), sonst haengt der Controller bei hoher Observer-Frequenz
        und/oder Hintergrundverkehr auf derselben Edge hoffnungslos hinterher.

        WICHTIG: Der 'edge.vehicles'-Observer sendet PRO FAHRZEUG eine
        eigene Nachricht (ein einzelnes Micro-Record-Dict), KEINE Liste -
        anders als der Name des Topics (".vehicles") vermuten laesst.
        msg.value() ist also direkt {"vehicleID": ..., "edge": ..., ...},
        nicht [{"vehicleID": ...}, ...].

        Zusaetzlich: nur eigene EV-Fahrzeuge (Prefix 'ev_') beruecksichtigen,
        falls Hintergrundverkehr dieselbe Edge durchquert."""
        for label, consumer in self.vehicle_consumers.items():
            station = self.stations[label]
            topic = self.vehicle_topics[label]
            saw_ev_this_step = False
            # Ein leerer poll() heisst NICHT, dass der Rueckstand leer ist -
            # Kafka liefert in Batches, zwischen denen leicht mehr als der
            # Poll-Timeout vergeht. Beim ersten None abzubrechen laesst
            # Nachrichten liegen; TimeSync wartet dann in msgCountOK()
            # volle 10 s (100 x 0.1 s) auf den timeoutHandler. Darum:
            # mehrere Leerlaeufe hintereinander tolerieren und laenger warten.
            empty_polls = 0
            for _ in range(2000):
                msg = consumer.poll(0.1)
                if msg is None or msg.error():
                    empty_polls += 1
                    if empty_polls >= 3:
                        break
                    continue
                empty_polls = 0
                vehicle = msg.value()
                if not isinstance(vehicle, dict):
                    continue
                vehicle_id = vehicle.get('vehicleID')
                if vehicle_id and vehicle_id.startswith('ev_'):
                    station.arrive(vehicle_id, sim_time)
                    saw_ev_this_step = True
            if not saw_ev_this_step and station.present:
                # kein eigenes EV mehr in diesem Rueckstand gesehen ->
                # vermutlich abgereist (siehe Timeout-Hinweis unten)
                pass  # TODO: echte Timeout-Logik statt sofortigem depart()

    def run(self):
        self.wait_for_scenario()
        self.setup_kafka()

        # EINHEITEN: Die C++-Seite (SumoWrapper) rechnet TimeSync in
        # MILLISEKUNDEN - sie liest stepLength direkt als ms und rechnet
        # simulationEnd * 1000. Die Python-Wrapper haben stepLength bisher
        # als reine Zahl uebernommen, wodurch ihre Zeitachse (bis 3400)
        # um Faktor 1000 unter SUMOs Achse (bis 3.400.000) lag. Da
        # lbts = min(alle angeforderten Zeiten), war timeOK() fuer den
        # Controller praktisch sofort immer erfuellt -> er rannte in 13s
        # durch, waehrend SUMO noch lief.
        step_size_ms = self.sim_config.get('stepLength', 60000)
        sim_end_ms = self.scenario_data.get('simulationEnd', 3200) * 1000
        n_steps = max(1, sim_end_ms // step_size_ms)
        dt_hours = step_size_ms / 3600000.0

        synced = self.scenario_data.get('execution', {}).get('syncedParticipants', 3)
        # NUR zeitbasierte Synchronisation (LBTS). Bewusst KEIN
        # addExpectedTopic(): TimeSync.msgCountOK() ruft seinen
        # timeoutHandler nur im Zweig "Topic noch nie empfangen" - sobald
        # ein Topic mindestens eine Nachricht hat, wartet es im zweiten
        # Zweig endlos, ohne je wieder zu pollen (Deadlock bei
        # "msgCount OK? NO! ... 102 / 185"). Seit der ms-Korrektur haelt
        # die Zeitsynchronisation den Controller ohnehin zuverlaessig auf
        # SUMOs Fortschritt zurueck; die Nachrichtenzaehlung ist eine
        # zweite, fragile Sicherung, die wir hier nicht brauchen. Ein
        # Fahrzeug-Update kann dadurch hoechstens einen Schritt spaeter
        # ankommen - fuer die Demo ohne Bedeutung.
        self.timeSync = TimeSync(self.broker, self.registry, self.topic_time, self.kid + ".ts", synced, logging=False)
        self.timeSync.joinTiming()
        self.log("TimeSync joined. Running simulation...")

        decision_fn = CONTROLLER_MODES[self.mode_name]
        max_power_by_label = {e['label']: e['max_power_kw'] for e in self.station_mapping}
        bus_by_label = {e['label']: e['pandapower_bus'] for e in self.station_mapping}
        load_by_label = {e['label']: e['pandapower_load'] for e in self.station_mapping}

        for step in range(n_steps):
            # sim_time bleibt in SEKUNDEN - das ist die Einheit, in der
            # Ankunftszeiten, charging_log.csv und die ChargingSetpoint-
            # Nachrichten gelesen werden. Nur TimeSync rechnet in ms.
            sim_time = step * step_size_ms // 1000
            self.current_sim_time = sim_time

            # WICHTIG: Polling MUSS vor timeAdvance() laufen. timeAdvance()
            # blockiert, bis alle von SUMO angekuendigten Nachrichten als
            # empfangen gemeldet wurden - gemeldet werden sie aber genau
            # hier. Stuende der Poll danach, warteten beide aufeinander
            # (Deadlock: "never received a message on ... supposed to have N").
            self.poll_vehicle_presence(sim_time)
            self.timeSync.timeAdvance(step_size_ms)

            requests = {
                label: station.requested_power_kW(max_power_by_label[label])
                for label, station in self.stations.items()
            }
            allocation = decision_fn(requests, self.capacity_kW)

            for label, station in self.stations.items():
                allowed = allocation.get(label, 0.0)
                station.apply_charging(allowed, dt_hours, sim_time)
                if sum(allocation.values()) > self.capacity_kW + 1e-6:
                    station.grid_violation_seen = True

                setpoint = {
                    "stationID": label,
                    "busID": bus_by_label[label],
                    "loadID": load_by_label[label],
                    "vehicleID": station.vehicle_id,
                    "requestedPower_kW": requests[label],
                    "allowedPower_kW": allowed,
                    "controllerMode": self.mode_name,
                    "simTime": sim_time,
                }
                self.setpoint_producer.produce(topic=self.topic_setpoints, value=setpoint)

            if step % 10 == 0:
                self.log(f"Step {step}/{n_steps} - requests={requests} allocation={allocation}")

        self.timeSync.leaveTiming()
        self.export_results()
        self.log("Done.")

    def export_results(self):
        os.makedirs(self.results_dir, exist_ok=True)
        path = os.path.join(self.results_dir, "charging_log.csv")
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["station", "controller_mode", "arrival_time", "departure_time",
                              "charge_complete_time", "final_soc", "grid_violation"])
            for label, s in self.stations.items():
                writer.writerow([
                    label, self.mode_name, s.arrival_time, s.departure_time,
                    s.charge_complete_time, round(s.soc, 3), s.grid_violation_seen,
                ])
        self.log(f"Wrote {path}")


def main():
    if len(sys.argv) > 2:
        scenarioID, instanceID = sys.argv[1], sys.argv[2]
        task_id = sys.argv[3] if len(sys.argv) > 3 else os.getenv('TASK_ID')
    else:
        print("Usage: python controllerWrapper.py <scenarioID> <instanceID> [task_id]")
        sys.exit(1)

    wrapper = ControllerWrapper(scenarioID, instanceID, task_id)
    wrapper.run()


if __name__ == '__main__':
    main()

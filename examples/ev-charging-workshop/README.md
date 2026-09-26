# Grid-Aware EV Charging Control — Workshop Scenario

A small, deliberately synthetic co-simulation scenario built for the hands-on workshop **Easy Ways to Simulate at the DACH+ Energy Informatics 2026**.
It demonstrates how swapping a single controller — nothing else — changes whether a local distribution grid gets overloaded by EV charging.

## The idea

Five EV charging stations share one small transformer.
If every vehicle charges at full power the moment it arrives, the transformer gets overloaded.
Two lightweight control strategies are provided to fix that, without touching the grid, the traffic network, or any other part of the scenario — only the `controllerMode` parameter changes.

This mirrors the more detailed use case studied in [Mohamed-lbrahim/Grid-Aware-EV-Charging-Control](https://github.com/Mohamed-lbrahim/Grid-Aware-EV-Charging-Control), simplified into a network small and controllable enough to run live in a workshop.

## The network

A synthetic **star topology** (not real map data, on purpose — it makes the outcome reproducible instead of dependent on traffic randomness):

- **1 transformer**, 160 kVA
- **5 charging stations** (A–E), 44 kW each, one per arm of the star
- Vehicles arrive staggered (300 s apart) so the number of simultaneously charging stations ramps 1 → 5 → 1 over the run, instead of everyone charging at once

With all 5 charging at once: 5 × 44 kW = 220 kW against a 160 kW transformer — a guaranteed, reproducible overload for the `uncontrolled` baseline to show.

## The three controller modes

Set via the `controllerMode` parameter on the `ControllerWrapper` building block — everything else in the scenario stays identical:

| Mode | Behaviour |
|---|---|
| `uncontrolled` | Every station charges at full power immediately, regardless of grid state. |
| `safe_mode` | If the transformer limit would be exceeded, all active stations are throttled proportionally. |
| `heuristic` | Stations closest to their charging target are served first; remaining capacity is distributed to the rest. |

## Files in this folder

| File | Role |
|---|---|
| `workshop_network.net.xml` | SUMO road network (5-arm star, generated with `netgenerate`) |
| `workshop_routes_.rou.xml` | Fixed, staggered routes for the 5 EVs — deliberately not `randomTrips.py`, so arrivals are reproducible |
| `background_traffic_30.trips.xml` | Optional light background traffic on the ring roads |
| `workshop_ev_charging_network.json` | PandaPower grid model (transformer + 5 station buses), built by `build_workshop_network.py` |
| `station_mapping.json` | Maps SUMO edges to PandaPower buses/loads, so the controller knows which vehicle belongs to which station |
| `python-scripts/build_workshop_network.py` | Regenerates `workshop_ev_charging_network.json` from scratch, with a runnable sanity-check power flow |
| `python-scripts/plot_results.py` | Turns `trafo_p_mw.csv` + `charging_log.csv` from one or more runs into comparison charts |
| `scenario-files/scenario_{controllerMode}.json` | Ready-to-upload scenario definition to run the use case in DaceDSX with the given `controllerMode` |
| `DaceDSX_workshop.pdf` | Tutorial with step-by-step instructions on how to run the use case |

## Running it

1. Upload one of the `scenario-files/scenario_{controllerMode}.json` files together with the resource files (everything in the folder root) to a new DaceDSX scenario — pick the file matching the controller mode you want to test.
2. Launch it, then download `trafo_p_mw.csv` / `charging_log.csv` from the run's results once it completes.
3. Repeat for the other two `controllerMode` values, then compare all three runs:

   ```bash
   pip install matplotlib
   python python-scripts/plot_results.py \
     --run uncontrolled/ \
     --run safe_mode/ \
     --run heuristic/
   ```

   Each `--run` folder should contain that run's `trafo_p_mw.csv` and
   `charging_log.csv`.

## Regenerating the grid model

If you want to change transformer capacity, station count, or line lengths:

```bash
python python-scripts/build_workshop_network.py
```

This rebuilds `workshop_ev_charging_network.json` and prints a sanity check (bus voltages, transformer/line loading) for all 5 stations at full power, so you can confirm the overload threshold before running the full co-simulation.

## Known limitations

- **Charging vs. physical departure are not yet fully decoupled.** Each vehicle stays parked in SUMO for 1800 s before it disappears from the traffic simulation, but fully charging from 20 % to 80 % takes longer than that under most controller modes. The controller keeps tracking a station's charging progress even after the vehicle has visually left SUMO, so the final state-of-charge numbers are correct, but `departure_time` in `charging_log.csv` is currently always empty. Safe to ignore for the workshop demo; worth fixing before using this as a basis for anything beyond a live demonstration.
- `simulationEnd` is set to 3600 s in all three scenario files. Not every station necessarily reaches its charging target within that window.

---

AI-assisted development: Parts of this scenario's code and documentation were developed with assistance from Claude (Anthropic). All design decisions, testing, and validation were performed by the authors.

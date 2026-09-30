"""
Erzeugt ein kleines, bewusst dimensioniertes Testnetz fuer den SimaaS-Workshop.

Ziel: NICHT realistisch, sondern ein garantierter, sauberer Kontrast zwischen
den drei EV-Charging-Controllern:
  - Uncontrolled : alle 5 Stationen laden gleichzeitig mit voller Leistung
                   -> deutliche Trafo-Ueberlastung + Unterspannung
  - Safe Mode    : reaktive Drosselung bei Grenzverletzung
  - Heuristic    : vorausschauende Verteilung der verfuegbaren Kapazitaet

Dimensionierung:
  5 Ladestationen x 44 kW = 220 kW maximale Gesamtlast
  Trafo: 160 kVA  ->  2 Stationen = 55% Auslastung (unproblematisch)
                      3 Stationen = 82% Auslastung (knapp, aber ok)
                      4 Stationen = 110% Auslastung (Ueberlastung)
                      5 Stationen = 138% Auslastung (deutliche Ueberlastung)

Die Ladestationen sind mit zunehmender elektrischer Entfernung vom Trafo
angeordnet (Reihenschaltung), damit auch der Spannungsabfall je nach
Position sichtbar unterschiedlich ausfaellt (Station E am staerksten
betroffen, Station A am wenigsten).
"""

import pandapower as pp

net = pp.create_empty_network(name="simaas_workshop_ev_charging")

# --- Busse ---------------------------------------------------------------
hv_bus = pp.create_bus(net, vn_kv=20.0, name="MV_Slack")
lv_trafo_bus = pp.create_bus(net, vn_kv=0.4, name="LV_Trafo")

station_buses = {}
for label in ["A", "B", "C", "D", "E"]:
    station_buses[label] = pp.create_bus(
        net, vn_kv=0.4, name=f"LV_Station_{label}"
    )

# --- Einspeisung + Transformator -----------------------------------------
pp.create_ext_grid(net, bus=hv_bus, vm_pu=1.0, name="MV_Grid_Connection")

# 160 kVA Verteilnetztrafo, ueber Parameter statt std_type definiert,
# damit die Werte unabhaengig von der pandapower-Version stimmen.
pp.create_transformer_from_parameters(
    net,
    hv_bus=hv_bus,
    lv_bus=lv_trafo_bus,
    sn_mva=0.160,
    vn_hv_kv=20.0,
    vn_lv_kv=0.4,
    vkr_percent=1.2,
    vk_percent=4.0,
    pfe_kw=0.46,
    i0_percent=0.3,
    shift_degree=150,
    name="Trafo_160kVA_20-0.4kV",
)

# --- Sternfoermige Leitungen: jede Station direkt vom Trafo aus ----------
# Spiegelt die SUMO-Spider-Topologie (ein Zentrum, 5 unabhaengige Arme).
# NAYY 4x150 SE ist ein pandapower-Standardkabeltyp fuer NS-Netze.
#
# Wichtiger Unterschied zur vorherigen Reihenschaltung: Jede Station
# haengt jetzt an ihrer EIGENEN Leitung direkt am Trafo-Bus. Das
# bedeutet, der Spannungsabfall einer Station wird nicht mehr durch
# die Last anderer Stationen "vorbelastet" (kein Kettenreaktions-
# Effekt mehr). Der gemeinsame Engpass bleibt trotzdem bestehen: der
# 160-kVA-Trafo, durch den alle 5 Arme gemeinsam gespeist werden -
# der Ueberlast-Kontrast zwischen den Controllern bleibt also erhalten,
# nur die Ursache ist jetzt ausschliesslich die Trafo-Kapazitaet statt
# Trafo + kumulierter Leitungsimpedanz.
order = ["A", "B", "C", "D", "E"]
lengths_km = [0.10, 0.12, 0.14, 0.16, 0.18]  # unterschiedliche Armlaengen

for label, length in zip(order, lengths_km):
    pp.create_line(
        net,
        from_bus=lv_trafo_bus,
        to_bus=station_buses[label],
        length_km=length,
        std_type="NAYY 4x150 SE",
        name=f"Line_to_Station_{label}",
    )

# --- Ladestationen als steuerbare Lasten ----------------------------------
# p_mw startet bei 0 - die Controller (uncontrolled/safe/heuristic) setzen
# den tatsaechlichen Wert pro Zeitschritt ueber Kafka. max_p_mw = 0.044
# (44 kW) ist die physikalische Ladeleistungsgrenze der Station.
for label in order:
    pp.create_load(
        net,
        bus=station_buses[label],
        p_mw=0.0,
        max_p_mw=0.044,
        controllable=True,
        name=f"EV_Charging_Station_{label}",
    )

# --- Sanity-Check: Lastfluss fuer den unkontrollierten Extremfall --------
print("=== Sanity-Check: alle 5 Stationen bei Volllast (44 kW) ===")
for label in order:
    net.load.at[net.load[net.load.name == f"EV_Charging_Station_{label}"].index[0], "p_mw"] = 0.044

pp.runpp(net)
print(net.res_bus[["vm_pu"]])
print(net.res_trafo[["loading_percent"]])
print(net.res_line[["loading_percent"]])

# --- Export ----------------------------------------------------------------
# Lasten fuer den Export wieder auf 0 zuruecksetzen - die Controller
# setzen die tatsaechlichen Werte zur Laufzeit.
net.load["p_mw"] = 0.0

pp.to_json(net, "workshop_ev_charging_network.json")
print("\nNetz gespeichert als workshop_ev_charging_network.json")

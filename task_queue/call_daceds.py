import os
import subprocess
import json
import traceback
from operator import truediv

import sys
import time
from datetime import datetime
import logging
import threading

# import jpype
# from jpype.types import *
#
#
# jpype.startJVM(classpath=["/home/cori/Desktop/DaceDSX/JavaBaseWrapper/target/JavaBaseWrapper-0.0.1-SNAPSHOT-jar-with-dependencies.jar"])
#
# from eu.fau.cs7.daceDS.Kafka import ProducerImplKafka, ConsumerImplKafka

sys.path.append('./PythonBaseWrapper/src/logic')
sys.path.append('./PythonBaseWrapper/src/communication')
from TimeSync import TimeSync
from KafkaConsumer import KafkaConsumer
from KafkaProducer import KafkaProducer
from confluent_kafka.avro import CachedSchemaRegistryClient
orchestration_topic = "orchestration.simulation"
# resource_topic= "orchestration.simulation.resource"
broker = "broker:29092"
registry = "http://schema-registry:8081"
log_dir = "."
resource_path = "."
fileReference = False
sce_id = ""
running = True
timeout_for_polling = 1000
receiveCounter = 0
simStartInMS = 0.0

# declare producer?

class SendScenario(object):
    """ Class representing the surrounding environment """

    def __init__(self, consumer, producer):
        # print("\n\n_____init_____\n\n", flush=True)
        self.consumer = consumer
        self.producer = producer


def init_kafka():


    producer = KafkaProducer(
        broker=broker,
        registry=registry,
        producerID="scenario-producer",
        useAvro=False
    )

    consumer_ack = KafkaConsumer(
        broker=broker,
        registry=registry,
        topics=["ack_topic"],
        consumerID="ack-listener",
        avro=False
    )

    return producer, consumer_ack


def send_to_kafka():
    # produce to topic maybe translate to a message
    pass

def run_scenario(sce):
    send_to_kafka(orchestration_topic, sce)

    for bb in sce["buildingBlocks"]:
        resource_topic= f"provision.simulation.{sce['scenarioID']}.resource"
        for resource in bb["resource"]:
            resource_msg={
                "ID": sce['scenarioID'],
                "Type": resource.key(),
                "File": None,
                "FileRefrence": resource.item()
            }
            send_to_kafka(resource_topic, resource_msg)

def test_smth(simulation_input):
    os.chdir("/home/cori/Desktop/DaceDSX/SimService")
    # with open("scenario.json", "w", encoding="utf-8") as f:
    #     json.dump(simulation_input, f)
    command = ["java", "-jar", "./target/SendScenarioObject.jar", "./scenario.json"]
    try:
        result=subprocess.run(command, check=True, capture_output=True, text=True)
        print(result.stdout)
        data= {
            "simulation_run" : "no error"
        }
        return data
    except:
        print("ERROR")
        return {"simulation_run" : "FAILED"}


def wait_for_ack(ack_id, sceid):
    provision_topic = "provision.simulation." + sceid + ".scenario"
    consumer = KafkaConsumer(
        broker=broker,
        registry=registry,
        topics=[provision_topic],
        consumerID=ack_id,
        avro=False
    )
    print("starts listening")
    listening = True
    while listening:
        try:
            #print("polling")
            msg = consumer.poll(1)
            print(msg, "Message")
            if msg is None:
                continue

            if msg.value() is not None:
                # scenario_id = msg.value()[""]
                consumer.stop()
                listening = False
                return True
            else:
                consumer.stop()
                return False
        except Exception as e:
            logging.error("Fehler aufgetreten:\n%s", traceback.format_exc())
            print("Error")
    print("out of looop")
    consumer.stop()
    return False

def status_listener(sce_id):
    logging.info("String-Listener is triggered for status")
    topic = "orchestration.simulation."+sce_id+".status"
    listen_for_string_observers(topic)

def listen_for_string_observers(topic):
    consumer_string_observer = KafkaConsumer(
        broker=broker,
        registry=registry,
        topics=[topic],
        consumerID="string_observer",
        avro=False
    )
    sce_finished_counter = 5
    sce_about_to_be_finished = False
    receiveCounter =0
    ## While running
    running= True
    while running:
        try:
            msg = consumer_string_observer.poll(timeout_for_polling)
            if msg is None:
                logging.info("recieved null msg")

            receiveCounter = receiveCounter+1
            if not msg:
                continue
            if "finished" in str(msg.value()):
                sce_about_to_be_finished = True
                simDurationInMS = msg.timestamp()[1] - simStartInMS
            if "simulating" in str(msg.value()):
                simStartInMS = msg.timestamp()[1]
            if sce_about_to_be_finished:
                sce_finished_counter = sce_finished_counter-1
                if sce_finished_counter < 1:
                    running = False
                    print("Found 'finished' status: assuming sce to be done and exiting.")
                    print("The scenario took roughly "+ simDurationInMS/1000 + " seconds. Bye bye :-) ")
                    print(sce_id + " "+ simDurationInMS + "ms\n\n\n")
                time.sleep(1000)
        except Exception as e:
            logging.error("Fehler aufgetreten:\n%s", traceback.format_exc())


def main(sce):
    # if (args.length < 1) {
    # System.out.println("Usage: .jar ScenarioFile [-a|--AvroListener] [-j|--JSONListener] [-r|--resultsListener] [-f|--fileReference] ");
    # return;
    # }
    #
    # for (String arg: args){
    #     if (arg.equals("-a") | | arg.equals("--AvroListener")){
    #     avroListener = true;
    #     }
    #     if (arg.equals("-j") | | arg.equals("--JSONListener")){
    #     jsonListener = true;
    #     }
    #     if (arg.equals("-r") | | arg.equals("--resultsListener")){
    #     resultsListener = true;
    #     }
    #     if (arg.equals("-f") | | arg.equals("--fileReference")){
    #     fileReference = true;
    #     }
    # }
    print("in main")
    r = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # Registry-Client
    schema_registry = CachedSchemaRegistryClient({'url': registry})

    # Das letzte Schema vom Subject holen
    subject = f"{orchestration_topic}-value"
    # schema_id, schema, version = schema_registry.get_latest_schema(subject)
    log_file_path = log_dir + "/tmp/call_dace_ds_"+r+".txt"
    logging.basicConfig(filename="call_dace_ds_"+r, level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S")
    sce_id = sce['scenarioID']
    # print("schema", schema)
    kafka_writer = KafkaProducer(
        broker=broker,
        registry=registry,
        producerID="sendScenarioObject",
        useAvro=True,
        # schema=schema
        schemaPath="./AvroSchemas/Scenario.avsc"
    )
    # kafka_writer.create_topic([orchestration_topic])
    kafka_writer.produce(orchestration_topic, sce)
    print("published sce to topic: "+orchestration_topic)
    logging.info("published sce to topic: "+orchestration_topic)
    wait_for_ack('sendScenarioObject_ack', sce['scenarioID'])
    print("not longer waiting_for_ack")
    kafka_resource_file_wirter = KafkaProducer(
        broker=broker,
        registry=registry,
        producerID="kafkaResourceFileWriter",
        useAvro=True,
        schemaPath="./AvroSchemas/ResourceFile.avsc"
    )

    try:
        print("working on resources")
        for bb in sce["buildingBlocks"]:
            resource_topic = f"provision.simulation.{sce_id}.resource"
            for key, value in bb["resources"].items():
                type = value
                id = key
                resourceFileInput = None
                if id.startswith('s3://'):
                    pass
                elif id.startswith("file://"):
                    refpath= id
                    resourceFileInput = {
                    "ID": id,
                    "Type": type,
                    "File": None,
                    "FileReference": refpath
                }
                else:
                    f_path = os.path.join(resource_path, id)
                    # Datei öffnen und Inhalt lesen
                    with open(f_path, "r", encoding="utf-8") as f:
                        inhalt = f.read()

                    resourceFileInput = {
                        "ID": id,
                        "Type": type,
                        "File": inhalt,
                        "FileReference": None
                    }

                kafka_resource_file_wirter.produce(resource_topic, resourceFileInput)
                logging.info("published resource with id: "+id+" and type: "+type+"to topic: "+resource_topic)
                for translators in sce["translators"]:
                    for key, value in translators.items():
                        type = value
                        id = key
                        resourceFileInput = None

                        if not fileReference:
                            f_path = os.path.join(resource_path, id)
                            # Datei öffnen und Inhalt lesen
                            with open(f_path, "r", encoding="utf-8") as f:
                                inhalt = f.read()

                            resourceFileInput = {
                                "ID": id,
                                "Type": type,
                                "File": inhalt,
                                "FileReference": None
                            }

                        kafka_resource_file_wirter.produce(resource_topic, resourceFileInput)
                        logging.info("published resource: "+id+" as "+type)
    except Exception as e:
        logging.error("Fehler aufgetreten:\n%s", traceback.format_exc())
    ##################################
    # Listen for feedback
    ##################################
    listener_thread = threading.Thread(target=status_listener(sce_id), daemon=True)
    listener_thread.start()
    # all the other listerners are missing, since weh have not implemented the flags for that ...





if __name__ == "__main__":
    # if len(sys.argv) < 2:
    #     print("Usage: python call_daceDS.py <your_text>")
    #     sys.exit(1)
    #
    # input_text = sys.argv[1]
    # test_smth(input_text)
    sce = {
        "scenarioID": "m_n",
        "domainReferences": {},
        "simulationStart": 0,
        "simulationEnd": 2,
        "execution": {
            "randomSeed": 23,
            "constraints": "",
            "priority": 0,
            "syncedParticipants": 1
        },
        "buildingBlocks": [{
            "instanceID": "PyPSAWrapper0",
            "type": "PyPSAWrapper",
            "layer": "network",
            "domain": "energy",
            "stepLength": 1,
            "parameters": {},
            "resources": {"file:///../_data/resources/minimal_network.hdf5": "Network"},
            "results": {},
            "synchronized": True,
            "isExternal": False,
            "responsibilities": [],
            "observers": []
        }],
        "translators": [],
        "projectors": []
    }
    main(sce)

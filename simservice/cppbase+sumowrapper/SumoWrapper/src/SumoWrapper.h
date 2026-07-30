/*
MIT License

Copyright 2021 Moritz Gütlein

This code was originally published under the Apache 2.0 License (http://www.apache.org/licenses/LICENSE-2.0) in 2021.
In 2025, it has been relicensed under the MIT License (https://choosealicense.com/licenses/mit/) with the explicit permission of all copyright holders.
*/
#pragma once

#include <stdlib.h>
#include <sys/stat.h>
#include <unistd.h>
// #include <utils/traci/TraCIAPI.h>
//#include <libsumo/Simulation.h>

#include <chrono>
#include <cstdio>
#include <cwchar>
#include <exception>
#include <fstream>
#include <iostream>
#include <locale>
#include <memory>
#include <regex>
#include <string>
#include <utility>

#include "PrepareRun.h"
#include "SimulationEventEmitter.h"
#include "api/InteractionImpl.h"
#include "api/OrchestrationImpl.h"
#include "api/ProvisionImpl.h"
#include "api/Traffic/Micro/ProvisionHandlerTrafficMicro.h"
#ifdef USING_TRACI
    #include "api/SumoConnectionTraCI.h"
#else
    #include "api/SumoConnectionLibSUMO.h"
#endif
#include "communication/InteractionHandler.h"
#include "communication/OrchestrationHandler.h"
#include "communication/ProvisionHandler.h"
#include "communication/kafka/KafkaConsumer.h"
#include "communication/kafka/KafkaProducer.h"
#include "logic/SumoSimulationControl.h"
#include "main/SimulationWrapper.h"
#include "util/Defines.h"
#include "util/log.h"
#include "util/Config.h"



namespace daceDS {

class SumoSimulationControl;
class ProvisionImpl;

class SumoWrapper : public SimulationWrapper {
   protected:
    std::shared_ptr<ProvisionImpl> provision;
    std::shared_ptr<SumoSimulationControl> ctrl;
    std::shared_ptr<KafkaProducer> producer;
    std::shared_ptr<KafkaProducer> statusProducer;
    std::shared_ptr<SimulationEventEmitter> eventEmitter;
    std::string taskId;
    int sumoPID = 0;
    
   public:
    SumoWrapper(std::string s, std::string t, std::string taskId = "")
        : SimulationWrapper(s, t), taskId(std::move(taskId)){};
    ~SumoWrapper(){};

    std::shared_ptr<ProvisionImpl> getProvision() { return provision; };

    void runWrapper();
    void waitForScenario();
    void killWrapper();
    void terminateWrapper();

    void statusMsg(std::string msg);
    void emitEvent(
        const std::string& category,
        const std::string& eventCode,
        const std::string& message,
        double progress = -1.0,
        int64_t simulationTime = -1,
        bool fatal = false);
    void emitMetricSnapshot(
        int64_t simulationTime,
        double progress,
        int step,
        int totalSteps,
        int activeVehicles,
        int arrivedVehicles,
        double averageSpeed,
        const std::vector<SumoVehicleSnapshot>& vehicles);

};

}  // namespace daceDS

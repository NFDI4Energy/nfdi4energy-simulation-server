#pragma once

#include <cstdint>
#include <memory>
#include <string>
#include <vector>

#include "communication/kafka/KafkaProducer.h"

typedef struct json_t json_t;

namespace daceDS {

struct SumoVehicleSnapshot {
    std::string id;
    double x = 0.0;
    double y = 0.0;
    double speed = 0.0;
    std::string edge;
    std::string status;
};

class SimulationEventEmitter {
   public:
    SimulationEventEmitter(
        std::string taskId,
        std::shared_ptr<KafkaProducer> producer,
        std::string resultsDir);

    void emit(
        const std::string& category,
        const std::string& eventCode,
        const std::string& message,
        double progress = -1.0,
        int64_t simulationTime = -1,
        bool fatal = false);

    void metricSnapshot(
        int64_t simulationTime,
        double progress,
        int step,
        int totalSteps,
        int activeVehicles,
        int arrivedVehicles,
        double averageSpeed,
        const std::vector<SumoVehicleSnapshot>& vehicles);

   private:
    std::string taskId;
    std::shared_ptr<KafkaProducer> producer;
    std::string resultsDir;

    void persistAndPublish(json_t* event, bool metric);
};

}  // namespace daceDS

#include "SimulationEventEmitter.h"

#include <jansson.h>

#include <atomic>
#include <chrono>
#include <cstdlib>
#include <ctime>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <sstream>

namespace daceDS {
namespace {

constexpr const char* EVENT_TOPIC = "simservice.logs.events";
std::atomic<uint64_t> eventSequence{0};

std::string eventId() {
    auto now = std::chrono::system_clock::now().time_since_epoch();
    auto micros = std::chrono::duration_cast<std::chrono::microseconds>(now).count();
    return "evt_" + std::to_string(micros) + "_" + std::to_string(eventSequence++);
}

std::string utcTimestamp() {
    auto now = std::chrono::system_clock::now();
    auto seconds = std::chrono::system_clock::to_time_t(now);
    auto millis = std::chrono::duration_cast<std::chrono::milliseconds>(now.time_since_epoch()).count() % 1000;
    std::tm utc{};
    gmtime_r(&seconds, &utc);

    std::ostringstream output;
    output << std::put_time(&utc, "%Y-%m-%dT%H:%M:%S")
           << '.' << std::setw(3) << std::setfill('0') << millis << 'Z';
    return output.str();
}

json_t* baseEvent(
    const std::string& taskId,
    const std::string& category,
    const std::string& eventCode,
    const std::string& message,
    double progress,
    int64_t simulationTime) {
    json_t* event = json_object();
    json_object_set_new(event, "id", json_string(eventId().c_str()));
    json_object_set_new(event, "schema_version", json_string("1.0"));
    json_object_set_new(event, "task_id", json_string(taskId.c_str()));
    json_object_set_new(event, "timestamp", json_string(utcTimestamp().c_str()));
    json_object_set_new(event, "source", json_string("wrapper"));
    json_object_set_new(event, "category", json_string(category.c_str()));
    json_object_set_new(event, "component", json_string("SumoWrapper"));
    json_object_set_new(event, "event_code", json_string(eventCode.c_str()));
    json_object_set_new(event, "message", json_string(message.c_str()));
    if (progress >= 0.0) {
        json_object_set_new(event, "progress", json_real(progress));
    }
    if (simulationTime >= 0) {
        json_object_set_new(event, "simulation_time", json_integer(simulationTime));
    }
    return event;
}

void appendJsonLine(const std::filesystem::path& path, const std::string& payload) {
    std::filesystem::create_directories(path.parent_path());
    std::ofstream output(path, std::ios::app);
    output << payload << '\n';
}

}  // namespace

SimulationEventEmitter::SimulationEventEmitter(
    std::string taskId,
    std::shared_ptr<KafkaProducer> producer,
    std::string resultsDir)
    : taskId(std::move(taskId)), producer(std::move(producer)), resultsDir(std::move(resultsDir)) {}

void SimulationEventEmitter::emit(
    const std::string& category,
    const std::string& eventCode,
    const std::string& message,
    double progress,
    int64_t simulationTime,
    bool fatal) {
    if (taskId.empty()) {
        return;
    }

    json_t* event = baseEvent(taskId, category, eventCode, message, progress, simulationTime);
    if (fatal) {
        json_t* metadata = json_object();
        json_object_set_new(metadata, "fatal", json_true());
        json_object_set_new(event, "metadata", metadata);
    }
    persistAndPublish(event, false);
}

void SimulationEventEmitter::metricSnapshot(
    int64_t simulationTime,
    double progress,
    int step,
    int totalSteps,
    int activeVehicles,
    int arrivedVehicles,
    double averageSpeed,
    const std::vector<SumoVehicleSnapshot>& vehicles) {
    if (taskId.empty()) {
        return;
    }

    json_t* event = baseEvent(
        taskId,
        "METRIC",
        "METRIC_SNAPSHOT",
        "SUMO traffic metric snapshot",
        progress,
        simulationTime);
    json_t* metadata = json_object();
    json_t* metrics = json_object();
    json_object_set_new(metrics, "vehicles.active", json_integer(activeVehicles));
    json_object_set_new(metrics, "vehicles.arrived", json_integer(arrivedVehicles));
    json_object_set_new(metrics, "speed.avg_mps", json_real(averageSpeed));
    json_object_set_new(metadata, "metrics", metrics);
    json_object_set_new(metadata, "domain", json_string("traffic"));
    json_object_set_new(metadata, "simulation_time_unit", json_string("ms"));
    json_object_set_new(metadata, "step", json_integer(step));
    json_object_set_new(metadata, "total_steps", json_integer(totalSteps));

    json_t* entities = json_array();
    for (const auto& vehicle : vehicles) {
        json_t* entity = json_object();
        json_object_set_new(entity, "id", json_string(vehicle.id.c_str()));
        json_object_set_new(entity, "kind", json_string("vehicle"));
        json_object_set_new(entity, "x", json_real(vehicle.x));
        json_object_set_new(entity, "y", json_real(vehicle.y));
        json_object_set_new(entity, "speed", json_real(vehicle.speed));
        json_object_set_new(entity, "edge", json_string(vehicle.edge.c_str()));
        json_object_set_new(entity, "status", json_string(vehicle.status.c_str()));
        json_array_append_new(entities, entity);
    }
    json_object_set_new(metadata, "entities", entities);
    json_object_set_new(event, "metadata", metadata);
    persistAndPublish(event, true);
}

void SimulationEventEmitter::persistAndPublish(json_t* event, bool metric) {
    char* serialized = json_dumps(event, JSON_COMPACT | JSON_ENSURE_ASCII);
    if (serialized == nullptr) {
        json_decref(event);
        return;
    }

    std::string payload(serialized);
    free(serialized);

    if (!resultsDir.empty()) {
        try {
            std::filesystem::path eventsDir = std::filesystem::path(resultsDir) / "events";
            appendJsonLine(eventsDir / "structured_events.jsonl", payload);
            if (metric) {
                appendJsonLine(eventsDir / "metrics.jsonl", payload);
            }
        } catch (...) {
            // Kafka publishing remains available if the local fallback cannot be written.
        }
    }
    try {
        if (producer) {
            producer->publish(EVENT_TOPIC, taskId, payload, -1, false);
        }
    } catch (...) {
        // Monitoring must not terminate the simulation.
    }
    json_decref(event);
}

}  // namespace daceDS

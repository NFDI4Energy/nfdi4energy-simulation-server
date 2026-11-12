#pragma once
#include <cstdlib>
#include <stdexcept>
#include <string>
#include <utility>
#include <initializer_list>

inline void configureKafkaSecurity(RdKafka::Conf* conf) {
    const char* user = std::getenv("KAFKA_USERNAME");
    const char* password = std::getenv("KAFKA_PASSWORD");
    if (!user && !password) return;
    if (!user || !password) throw std::runtime_error("Both Kafka credentials must be configured");
    std::string error;
    for (auto setting : {std::make_pair("security.protocol", "SASL_SSL"),
                         std::make_pair("ssl.ca.location", "/run/kafka/ca.crt"),
                         std::make_pair("sasl.mechanisms", "PLAIN"),
                         std::make_pair("sasl.username", user), std::make_pair("sasl.password", password)}) {
        if (conf->set(setting.first, setting.second, error) != RdKafka::Conf::CONF_OK)
            throw std::runtime_error("Kafka authentication configuration failed");
    }
}

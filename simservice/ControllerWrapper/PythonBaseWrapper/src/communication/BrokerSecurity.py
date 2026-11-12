import os


def kafka_security():
    username, password = os.getenv("KAFKA_USERNAME"), os.getenv("KAFKA_PASSWORD")
    if not username and not password:
        return {}
    if not username or not password:
        raise RuntimeError("Both Kafka credentials must be configured")
    return {"security.protocol": "SASL_SSL", "sasl.mechanism": "PLAIN",
            "ssl.ca.location": os.getenv("KAFKA_CA_FILE", "/run/kafka/ca.crt"),
            "sasl.username": username, "sasl.password": password}

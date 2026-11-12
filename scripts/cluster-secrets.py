"""Render Secret manifests from deployment-only environment variables."""
import base64
import hashlib
import json
import os
import re
from pathlib import Path


def secret(name, namespace, values):
    return {"apiVersion": "v1", "kind": "Secret", "metadata": {"name": name, "namespace": namespace},
            "type": "Opaque", "data": {k: base64.b64encode(v.encode()).decode() for k, v in values.items()}}


def render():
    passwords = {name: os.environ[name] for name in (
        "RABBITMQ_PASSWORD", "REDIS_PASSWORD", "KAFKA_APP_PASSWORD", "KAFKA_ADMIN_PASSWORD",
        "KAFKA_OBSERVER_PASSWORD", "KAFKA_REGISTRY_PASSWORD")}
    if any(not re.fullmatch(r"[a-fA-F0-9]{64}", value) for value in passwords.values()):
        raise ValueError("Broker passwords must each be 64 hexadecimal characters")
    if len(set(passwords.values())) != len(passwords):
        raise ValueError("Each broker role needs a distinct password")
    def kafka(role):
        return {"KAFKA_USERNAME": role, "KAFKA_PASSWORD": passwords["KAFKA_" + {
            "simaas": "APP", "observer": "OBSERVER", "registry": "REGISTRY", "admin": "ADMIN"}[role] + "_PASSWORD"]}
    def jaas(role):
        creds = kafka(role)
        return ('org.apache.kafka.common.security.plain.PlainLoginModule required username="' + role +
                '" password="' + creds['KAFKA_PASSWORD'] + '";')
    broker_jaas = jaas('admin')[:-1] + ''.join(
        ' user_' + role + '="' + kafka(role)['KAFKA_PASSWORD'] + '"'
        for role in ('admin', 'simaas', 'observer', 'registry')) + ';'
    certificate = Path(os.environ['KAFKA_TLS_CERT_FILE']).read_text()
    key = Path(os.environ['KAFKA_TLS_KEY_FILE']).read_text()
    broker_properties = '\n'.join([
        'broker.id=1', 'zookeeper.connect=zookeeper.kafka.svc.cluster.local:2181',
        'listeners=INTERNAL://0.0.0.0:29092,CLIENT://0.0.0.0:9092',
        'advertised.listeners=INTERNAL://broker.kafka.svc.cluster.local:29092,CLIENT://broker.kafka.svc.cluster.local:9092',
        'listener.security.protocol.map=INTERNAL:SASL_SSL,CLIENT:SASL_SSL',
        'inter.broker.listener.name=INTERNAL', 'sasl.enabled.mechanisms=PLAIN',
        'sasl.mechanism.inter.broker.protocol=PLAIN',
        'listener.name.internal.plain.sasl.jaas.config=' + broker_jaas,
        'listener.name.client.plain.sasl.jaas.config=' + broker_jaas,
        'ssl.keystore.type=PEM', 'ssl.keystore.location=/run/kafka/broker.pem',
        'ssl.truststore.type=PEM', 'ssl.truststore.location=/run/kafka/ca.crt',
        'ssl.client.auth=none', 'authorizer.class.name=kafka.security.authorizer.AclAuthorizer',
        'super.users=User:admin', 'allow.everyone.if.no.acl.found=false',
        'offsets.topic.replication.factor=1', 'transaction.state.log.replication.factor=1',
        'transaction.state.log.min.isr=1', 'group.initial.rebalance.delay.ms=0',
        'auto.create.topics.enable=true', 'log.dirs=/var/lib/kafka/data']) + '\n'
    objects = [
        secret('broker-client-secret', 'simservice', {
            'RABBITMQ_USERNAME': 'simaas', 'RABBITMQ_PASSWORD': passwords['RABBITMQ_PASSWORD'],
            'REDIS_USERNAME': 'simaas', 'REDIS_PASSWORD': passwords['REDIS_PASSWORD']}),
        secret('rabbitmq-server-secret', 'simservice', {
            'RABBITMQ_DEFAULT_USER': 'simaas', 'RABBITMQ_DEFAULT_PASS': passwords['RABBITMQ_PASSWORD']}),
        secret('redis-acl', 'simservice', {'users.acl': 'user default off\nuser simaas on #' +
            hashlib.sha256(passwords['REDIS_PASSWORD'].encode()).hexdigest() +
            ' ~task:* +@read +@write +ping +select\n'}),
        secret('kafka-client-secret', 'simservice', kafka('simaas')),
        secret('kafka-observer-secret', 'simservice', kafka('observer')),
        secret('kafka-broker-secret', 'kafka', {
            'server.properties': broker_properties, 'broker.pem': key + '\n' + certificate, 'ca.crt': certificate}),
        secret('kafka-ca', 'simservice', {'ca.crt': certificate}),
        secret('kafka-ca', 'kafka', {'ca.crt': certificate}),
        secret('kafka-registry-secret', 'kafka', {'SCHEMA_REGISTRY_KAFKASTORE_SASL_JAAS_CONFIG': jaas('registry')}),
        secret('kafka-admin-secret', 'kafka', {'admin.properties':
            'security.protocol=SASL_SSL\nssl.truststore.type=PEM\nssl.truststore.location=/ca/ca.crt\n'
            'sasl.mechanism=PLAIN\nsasl.jaas.config=' + jaas('admin') + '\n'})]
    return {'apiVersion': 'v1', 'kind': 'List', 'items': objects}


if __name__ == '__main__':
    print(json.dumps(render()))

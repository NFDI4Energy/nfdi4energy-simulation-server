FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN pip install --no-cache-dir confluent-kafka fastavro avro requests

COPY PythonBaseWrapper /app/PythonBaseWrapper
COPY AvroSchemas /app/AvroSchemas

COPY controllerWrapper.py /app/

ENV PYTHONPATH="/app/PythonBaseWrapper/src/logic:/app/PythonBaseWrapper/src/communication:${PYTHONPATH}"

# Gleiche Absicherung wie bei PandaPowerWrapper: Falls der Orchestrator den
# componentType nicht exakt als "ControllerWrapper" normalisiert und daher
# auf den generischen Java-Startbefehl zurueckfaellt (siehe der PandaPower-
# Bug von eben), faengt dieser "java"-Shim den Aufruf ab und leitet ihn auf
# das Python-Skript um, statt fehlzuschlagen.
RUN echo '#!/bin/sh\n\
shift 2\n\
exec python /app/controllerWrapper.py "$@"' > /usr/local/bin/java && \
    chmod +x /usr/local/bin/java

RUN python -c "import sys; sys.path.insert(0, '/app/PythonBaseWrapper/src/logic'); sys.path.insert(0, '/app/PythonBaseWrapper/src/communication'); from TimeSync import TimeSync; from KafkaConsumer import KafkaConsumer; print('Modules verified OK')"

VOLUME /data

CMD ["python", "controllerWrapper.py"]

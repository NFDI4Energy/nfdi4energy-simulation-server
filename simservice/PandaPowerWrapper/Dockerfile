FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends gcc g++ && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --no-cache-dir pandapower pandas avro numpy openpyxl confluent-kafka fastavro scipy urllib3 requests

COPY PythonBaseWrapper /app/PythonBaseWrapper
COPY AvroSchemas /app/AvroSchemas

COPY pandapowerApi.py /app/
COPY pandapowerWrapper.py /app/
COPY simulation_event_emitter.py /app/

ENV PYTHONPATH="/app/PythonBaseWrapper/src/logic:/app/PythonBaseWrapper/src/communication:${PYTHONPATH}"


RUN echo '#!/bin/sh\n\
shift 2\n\
exec python /app/pandapowerWrapper.py "$@"' > /usr/local/bin/java && \
    chmod +x /usr/local/bin/java

RUN python -c "import sys; sys.path.insert(0, '/app/PythonBaseWrapper/src/logic'); sys.path.insert(0, '/app/PythonBaseWrapper/src/communication'); from TimeSync import TimeSync; from KafkaConsumer import KafkaConsumer; print('Modules verified OK')"

VOLUME /data

CMD ["python", "pandapowerWrapper.py"]

package eu.fau.cs7.daceDS.SimService;

import java.io.File;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.charset.StandardCharsets;
import java.nio.file.StandardOpenOption;
import java.time.Instant;
import java.util.Map;
import java.util.UUID;

import org.apache.log4j.Logger;
import org.json.JSONObject;

import eu.fau.cs7.daceDS.Component.Config;
import eu.fau.cs7.daceDS.Kafka.ProducerImplKafka;

public class SimulationEventEmitter {
    private static final Logger logger = Logger.getLogger(SimulationEventEmitter.class.getName());
    private static final String EVENT_TOPIC = "simservice.logs.events";
    private static final Object FILE_WRITE_LOCK = new Object();
    private static ProducerImplKafka<String> producer;

    private final String taskId;
    private final String source;
    private final String component;

    public SimulationEventEmitter(String taskId, String source, String component) {
        this.taskId = taskId;
        this.source = source;
        this.component = component;
    }

    public void emit(String category, String eventCode, String message) {
        emit(category, eventCode, message, null, null, null);
    }

    public void emit(String category, String eventCode, String message, Double progress, Long simulationTime, Map<String, Object> metadata) {
        if (taskId == null || taskId.isEmpty()) {
            return;
        }

        JSONObject event = new JSONObject();
        event.put("id", "evt_" + UUID.randomUUID().toString());
        event.put("schema_version", "1.0");
        event.put("task_id", taskId);
        event.put("timestamp", Instant.now().toString());
        event.put("source", source);
        event.put("category", category);
        event.put("component", component);
        event.put("event_code", eventCode);
        event.put("message", message);
        if (progress != null) event.put("progress", progress);
        if (simulationTime != null) event.put("simulation_time", simulationTime);
        if (metadata != null) event.put("metadata", new JSONObject(metadata));

        String payload = event.toString();
        appendEvent(payload);
        publishEvent(payload);
    }

    private void appendEvent(String payload) {
        try {
            File eventDir = new File(getResultsDir(), taskId + "/events");
            eventDir.mkdirs();
            eventDir.setWritable(true, false);
            File eventFile = new File(eventDir, "structured_events.jsonl");
            File lockFile = new File(eventDir, ".writer.lock");
            synchronized (FILE_WRITE_LOCK) {
                try (FileChannel lockChannel = FileChannel.open(lockFile.toPath(),
                        StandardOpenOption.CREATE, StandardOpenOption.WRITE)) {
                    lockFile.setWritable(true, false);
                    try (FileLock lock = lockChannel.lock();
                         FileChannel writer = FileChannel.open(eventFile.toPath(),
                             StandardOpenOption.CREATE, StandardOpenOption.WRITE, StandardOpenOption.APPEND)) {
                        ByteBuffer bytes = StandardCharsets.UTF_8.encode(payload + "\n");
                        while (bytes.hasRemaining()) writer.write(bytes);
                        writer.force(true);
                    }
                }
            }
            eventFile.setWritable(true, false);
        } catch (Exception e) {
            logger.warn("Failed to append structured event for task " + taskId + ": " + e.getMessage());
        }
    }

    private void publishEvent(String payload) {
        try {
            ProducerImplKafka<String> p = getProducer();
            if (p != null) {
                p.publish(EVENT_TOPIC, taskId, payload, 0, 0, component);
            }
        } catch (Exception e) {
            logger.warn("Failed to publish structured event for task " + taskId + ": " + e.getMessage());
        }
    }

    private static synchronized ProducerImplKafka<String> getProducer() {
        if (producer == null) {
            producer = new ProducerImplKafka<String>("SimulationEventEmitter");
            producer.initPlainString();
        }
        return producer;
    }

    private String getResultsDir() {
        String resultsDir = Config.get("resultsDir");
        if (resultsDir == null || resultsDir.isEmpty()) {
            resultsDir = "/data/results";
        }
        return resultsDir;
    }
}

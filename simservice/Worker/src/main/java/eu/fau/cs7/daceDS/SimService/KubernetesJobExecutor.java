/*
MIT License

Copyright 2021 Moritz Gütlein

This code was originally published under the Apache 2.0 License (http://www.apache.org/licenses/LICENSE-2.0) in 2021.
In 2025, it has been relicensed under the MIT License (https://choosealicense.com/licenses/mit/) with the explicit permission of all copyright holders.
*/
package eu.fau.cs7.daceDS.SimService;

import io.fabric8.kubernetes.api.model.*;
import io.fabric8.kubernetes.api.model.batch.v1.Job;
import io.fabric8.kubernetes.api.model.batch.v1.JobBuilder;
import io.fabric8.kubernetes.api.model.batch.v1.JobStatus;
import io.fabric8.kubernetes.client.KubernetesClient;
import io.fabric8.kubernetes.client.KubernetesClientBuilder;
import org.apache.log4j.Logger;

import eu.fau.cs7.daceDS.Component.Config;
import eu.fau.cs7.daceDS.datamodel.Scenario;

import java.util.HashMap;
import java.util.Map;

/**
 * Executor that creates and manages Kubernetes Jobs instead of spawning local processes.
 * Replaces the ExecutorThread class for containerized execution.
 * 
 * @author guetlein
 */
public class KubernetesJobExecutor extends Thread {

    private Scenario scenario;
    private String type;
    private String instanceID;
    private String scenarioID;
    private String jobName;
    private String namespace;
    private KubernetesClient kubernetesClient;
    private Job job;
    private boolean running = false;
    private boolean completed = false;
    private boolean failed = false;
    private int exitCode = -1;
    private String failureMessage = "";
    private long startTime = -1;
    private String taskId;
    
    Logger logger = Logger.getLogger(KubernetesJobExecutor.class.getName());

    /**
     * Constructor for Kubernetes Job Executor
     * 
     * @param type The type of component (e.g., "TrafficSim", "Projectors/DataAggregator")
     * @param instanceID Unique instance identifier
     * @param scenario The scenario object containing configuration
     */
    public KubernetesJobExecutor(String type, String instanceID, Scenario scenario) {
        this(type, instanceID, scenario, null);
    }

    public KubernetesJobExecutor(String type, String instanceID, Scenario scenario, String taskId) {
        this.scenario = scenario;
        this.taskId = taskId;
        this.type = type;
        this.instanceID = instanceID;
        this.scenarioID = scenario.getScenarioID().toString();
        this.namespace = getNamespaceFromConfig();
        
        // Generate unique job name (K8s naming: lowercase, max 63 chars, alphanumeric + hyphens)
        this.jobName = generateJobName(scenarioID, instanceID);
        
        logger = Logger.getLogger(KubernetesJobExecutor.class.getName() + "." + type + "." + instanceID);
        
        // Initialize Kubernetes client
        try {
            this.kubernetesClient = new KubernetesClientBuilder().build();
            logger.info("Kubernetes client initialized for job: " + jobName);
        } catch (Exception e) {
            logger.error("Failed to initialize Kubernetes client: " + e.getMessage());
            failureMessage = "Failed to initialize Kubernetes client for " + jobName + ": " + e.getMessage();
            throw new RuntimeException("Cannot create Kubernetes client", e);
        }
    }

    /**
     * Generate Kubernetes-compliant job name
     */
    private String generateJobName(String scenarioID, String instanceID) {
        // K8s names must be lowercase alphanumeric + hyphens, max 63 chars
        String name = (scenarioID + "-" + instanceID)
            .toLowerCase()
            .replaceAll("[^a-z0-9-]", "-")
            .replaceAll("-+", "-")
            .replaceAll("^-|-$", "");
        
        if (name.length() > 63) {
            name = name.substring(0, 63);
        }
        
        return name;
    }

    /**
     * Get namespace from config or environment variable
     */
    private String getNamespaceFromConfig() {
        String ns = Config.get("kubernetesNamespace");
        if (ns == null || ns.isEmpty()) {
            ns = System.getenv("K8S_NAMESPACE");
        }
        if (ns == null || ns.isEmpty()) {
            ns = "default";
            logger.warn("No namespace configured, using: default");
        }
        return ns;
    }

    /**
     * Get container image name for the component type
     */
    private String getContainerImage() {
        // Read from config or environment variable
        String imageRegistry = Config.get("containerRegistry");
        if (imageRegistry == null || imageRegistry.isEmpty()) {
            imageRegistry = System.getenv("CONTAINER_REGISTRY");
        }
        if (imageRegistry == null || imageRegistry.isEmpty()) {
            imageRegistry = "localhost:5000"; // Minikube default registry
        }
        
        // Map type to container image name
        // Format: registry/wrapper-type:tag
        String imageType = type.toLowerCase().replaceAll("[^a-z0-9-]", "-");
        String imageTag = Config.get("containerImageTag");
        if (imageTag == null || imageTag.isEmpty()) {
            imageTag = "latest";
        }
        
        return imageRegistry + "/" + imageType + "-wrapper:" + imageTag;
    }

    /**
     * Build environment variables for the container
     */
    private Map<String, String> buildEnvironmentVariables() {
        Map<String, String> env = new HashMap<>();
        
        // Pass scenario and instance identifiers
        env.put("SCENARIO_ID", scenarioID);
        env.put("INSTANCE_ID", instanceID);
        env.put("COMPONENT_TYPE", type);
        if (taskId != null && !taskId.isEmpty()) {
            String resourceDir = Config.get("resourceDir");
            if (resourceDir == null || resourceDir.isEmpty()) {
                resourceDir = "/data/resources";
            }
            String resultsDir = Config.get("resultsDir");
            if (resultsDir == null || resultsDir.isEmpty()) {
                resultsDir = "/data/results";
            }
            env.put("TASK_ID", taskId);
            env.put("TASK_DIR", resourceDir + "/" + taskId);
            env.put("RESOURCES_DIR", resourceDir + "/" + taskId);
            env.put("RESULTS_DIR", resultsDir + "/" + taskId);
        }
        
        // Kafka configuration
        env.put("KAFKA_BROKER", Config.get(Config.KAFKA_BROKER));
        env.put("SCHEMA_REGISTRY", Config.get(Config.SCHEMA_REGISTRY));
        
        // Topic configuration
        env.put("CHANNEL_ORCHESTRATION", Config.get(Config.CHANNEL_ORCHESTRATION));
        env.put("CHANNEL_INTERACTION", Config.get(Config.CHANNEL_INTERACTION));
        env.put("CHANNEL_PROVISION", Config.get(Config.CHANNEL_PROVISION));
        
        return env;
    }

    /**
     * Create the Kubernetes Job specification
     */
    private Job createJobSpec() {
        Map<String, String> labels = new HashMap<>();
        labels.put("app", "simservice");
        labels.put("scenarioID", scenarioID.substring(0, Math.min(63, scenarioID.length())));
        labels.put("instanceID", instanceID.substring(0, Math.min(63, instanceID.length())));
        labels.put("componentType", type.replaceAll("[^a-zA-Z0-9-_.]", "-").substring(0, Math.min(63, type.length())));
        
        // Build environment variables as EnvVar list
        Map<String, String> envMap = buildEnvironmentVariables();
        
        Job job = new JobBuilder()
            .withNewMetadata()
                .withName(jobName)
                .withNamespace(namespace)
                .withLabels(labels)
            .endMetadata()
            .withNewSpec()
                .withBackoffLimit(2) // Retry up to 2 times on failure
                .withActiveDeadlineSeconds(3600L) // 1 hour timeout
                .withTtlSecondsAfterFinished(600) // Clean up after 10 minutes
                .withNewTemplate()
                    .withNewMetadata()
                        .withLabels(labels)
                    .endMetadata()
                    .withNewSpec()
                        .withRestartPolicy("Never")
                        .addNewVolume()
                            .withName("simservice-data")
                            .withNewPersistentVolumeClaim()
                                .withClaimName("simservice-data-pvc")
                            .endPersistentVolumeClaim()
                        .endVolume()
                        .addNewContainer()
                            .withName("wrapper")
                            .withImage(getContainerImage())
                            .withImagePullPolicy("Never")
                            .withCommand("sh", "-c", "ln -sf /data/config.properties /app/config.properties && " + (taskId != null && !taskId.isEmpty() ? "mkdir -p \"$RESULTS_DIR\" && " : "") + "java -jar /app/wrapper.jar " + scenarioID + " " + instanceID + (taskId != null && !taskId.isEmpty() ? " " + taskId : ""))
                            .addAllToEnv(envMap.entrySet().stream()
                                .map(e -> new EnvVarBuilder()
                                    .withName(e.getKey())
                                    .withValue(e.getValue())
                                    .build())
                                .collect(java.util.stream.Collectors.toList()))
                            .addNewVolumeMount()
                                .withName("simservice-data")
                                .withMountPath("/data")
                            .endVolumeMount()
                        .endContainer()
                    .endSpec()
                .endTemplate()
            .endSpec()
            .build();
        
        return job;
    }

    /**
     * Create and submit the Kubernetes Job
     */
    public boolean createJob() {
        try {
            logger.info("Creating Kubernetes Job: " + jobName + " for type: " + type);
            new SimulationEventEmitter(taskId, "simservice", type).emit("WRAPPER", "WRAPPER_JOB_CREATING", "Creating Kubernetes job: " + jobName);
            
            Job jobSpec = createJobSpec();
            job = kubernetesClient.batch().v1().jobs()
                .inNamespace(namespace)
                .resource(jobSpec)
                .create();
            
            startTime = System.currentTimeMillis();
            running = true;
            
            logger.info("Job created successfully: " + jobName);
            new SimulationEventEmitter(taskId, "simservice", type).emit("WRAPPER", "WRAPPER_JOB_CREATED", "Kubernetes job created: " + jobName);
            return true;
            
        } catch (Exception e) {
            logger.error("Failed to create Kubernetes Job: " + jobName + " - " + e.getMessage());
            failureMessage = "Failed to create Kubernetes job " + jobName + ": " + e.getMessage();
            new SimulationEventEmitter(taskId, "simservice", type).emit("ERROR", "WRAPPER_JOB_CREATE_FAILED", failureMessage);
            e.printStackTrace();
            return false;
        }
    }

    /**
     * Monitor job status and wait for completion
     */
    @Override
    public void run() {
        if (!createJob()) {
            failed = true;
            running = false;
            return;
        }
        
        logger.info("Monitoring Job: " + jobName);
        new SimulationEventEmitter(taskId, "simservice", type).emit("WRAPPER", "WRAPPER_JOB_RUNNING", "Wrapper job is running: " + jobName);
        
        // Poll job status until completion or failure
        while (running && !completed && !failed) {
            try {
                Thread.sleep(10000); // Poll every 10 seconds
                
                Job currentJob = kubernetesClient.batch().v1().jobs()
                    .inNamespace(namespace)
                    .withName(jobName)
                    .get();
                
                if (currentJob == null) {
                    logger.error("Job disappeared: " + jobName);
                    failureMessage = "Kubernetes job disappeared: " + jobName;
                    failed = true;
                    running = false;
                    break;
                }
                
                JobStatus status = currentJob.getStatus();
                if (status != null) {
                    Integer succeeded = status.getSucceeded();
                    Integer failed = status.getFailed();
                    
                    if (succeeded != null && succeeded > 0) {
                        logger.info("Job completed successfully: " + jobName);
                        completed = true;
                        running = false;
                        exitCode = 0;
                        new SimulationEventEmitter(taskId, "simservice", type).emit("WRAPPER", "WRAPPER_JOB_COMPLETED", "Wrapper job completed: " + jobName);
                    } else if (failed != null && failed > 0) {
                        logger.error("Job failed: " + jobName);
                        this.failed = true;
                        running = false;
                        exitCode = 1;
                        failureMessage = "Kubernetes job failed: " + jobName;
                        new SimulationEventEmitter(taskId, "simservice", type).emit("ERROR", "WRAPPER_JOB_FAILED", failureMessage);
                    }
                }
                
                // Check for timeout
                if (System.currentTimeMillis() - startTime > 3600000) { // 1 hour
                    logger.error("Job timeout: " + jobName);
                    deleteJob();
                    this.failed = true;
                    running = false;
                    exitCode = 124; // Timeout exit code
                    failureMessage = "Kubernetes job timed out: " + jobName;
                    new SimulationEventEmitter(taskId, "simservice", type).emit("ERROR", "WRAPPER_JOB_TIMEOUT", failureMessage);
                }
                
            } catch (InterruptedException e) {
                logger.warn("Job monitoring interrupted: " + jobName);
                failureMessage = "Kubernetes job monitoring interrupted: " + jobName;
                running = false;
                break;
            } catch (Exception e) {
                logger.error("Error monitoring job: " + jobName + " - " + e.getMessage());
                failureMessage = "Error monitoring Kubernetes job " + jobName + ": " + e.getMessage();
            }
        }
        
        logger.info("Job monitoring finished: " + jobName + " (success=" + completed + ", failed=" + this.failed + ")");
    }

    /**
     * Delete the Kubernetes Job
     */
    public boolean deleteJob() {
        try {
            if (job != null && kubernetesClient != null) {
                logger.info("Deleting Job: " + jobName);
                
                kubernetesClient.batch().v1().jobs()
                    .inNamespace(namespace)
                    .withName(jobName)
                    .delete();
                
                logger.info("Job deleted: " + jobName);
                return true;
            }
        } catch (Exception e) {
            logger.error("Failed to delete Job: " + jobName + " - " + e.getMessage());
        }
        return false;
    }

    /**
     * Terminate the job forcefully
     */
    public void terminate() {
        logger.info("Terminating Job: " + jobName);
        deleteJob();
        running = false;
        failed = true;
    }

    /**
     * Check if job is still running
     */
    public boolean isJobRunning() {
        return running;
    }

    /**
     * Check if job completed successfully
     */
    public boolean isJobCompleted() {
        return completed;
    }

    /**
     * Check if job failed
     */
    public boolean isJobFailed() {
        return failed;
    }

    /**
     * Get job exit code (0 = success, non-zero = failure)
     */
    public int getExitCode() {
        return exitCode;
    }

    public String getFailureMessage() {
        if (failureMessage != null && !failureMessage.isEmpty()) {
            return failureMessage;
        }
        return "Kubernetes job failed: " + jobName;
    }

    /**
     * Get job name
     */
    public String getJobName() {
        return jobName;
    }

    /**
     * Get job age in milliseconds
     */
    public long getAge() {
        if (startTime < 0) {
            return 0;
        }
        return System.currentTimeMillis() - startTime;
    }

    /**
     * Close the Kubernetes client
     */
    public void close() {
        if (kubernetesClient != null) {
            kubernetesClient.close();
        }
    }
}

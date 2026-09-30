/*
MIT License

Copyright 2021 Moritz Gütlein

This code was originally published under the Apache 2.0 License (http://www.apache.org/licenses/LICENSE-2.0) in 2021.
In 2025, it has been relicensed under the MIT License (https://choosealicense.com/licenses/mit/) with the explicit permission of all copyright holders.
*/
package eu.fau.cs7.daceDS.SimService;
import java.io.File;
import java.io.IOException;
import java.util.HashMap;
import java.util.Map.Entry;

import org.apache.kafka.common.errors.TimeoutException;
import org.apache.log4j.Logger;

import eu.fau.cs7.daceDS.Component.Config;
import eu.fau.cs7.daceDS.Kafka.ProducerImplKafka;
import eu.fau.cs7.daceDS.datamodel.BB;
import eu.fau.cs7.daceDS.datamodel.Projector;
import eu.fau.cs7.daceDS.datamodel.ResourceFile;
import eu.fau.cs7.daceDS.datamodel.Scenario;
import eu.fau.cs7.daceDS.datamodel.Translator;


/**
 * A ScenarioRunner thread spawns several other related threads that are used
 * for the execution of further processes and waits for them to finish.
 * 
 * @author guetlein
 */
public class ScenarioInstanceExecutor extends Thread{


	private Scenario scenario;
	private boolean debug;
	private String scenarioID;
	private String kafkaID;
	private String taskId;
	private boolean done = false;
	private boolean failed = false;
	private String failureMessage = "";
	private long startTime = -1;
	
	//Each Job executor manages one Kubernetes Job
	HashMap<String, KubernetesJobExecutor> jobExecutors;

	static Logger logger  = Logger.getLogger(ScenarioInstanceExecutor.class.getName());

	public ScenarioInstanceExecutor(Scenario scenario, boolean debug) {
		this(scenario, debug, null);
	}

	public ScenarioInstanceExecutor(Scenario scenario, boolean debug, String taskId) {
		this.scenario = scenario;
		this.scenarioID = scenario.getScenarioID().toString();
		this.taskId = taskId;
		this.debug = debug;
		this.kafkaID = scenario.getScenarioID()+ScenarioInstanceExecutor.class.getName();
		if (taskId != null && !taskId.isEmpty()) {
			logger.info("Kubernetes mode: ENABLED, task data directory: " + getTaskDirectory());
		} else {
			logger.info("Kubernetes mode: ENABLED");
		}
	}

	public void run() {
		
		logger.info("ScenarioRunnerThread is started for " + scenarioID);
		SimulationEventEmitter events = new SimulationEventEmitter(taskId, "simservice", "SimService");
		events.emit("PROGRESS", "SIMULATION_STARTED", "Simulation started", 0.20, scenario.getSimulationStart(), null);
		
		// Wait for all Kubernetes Jobs to complete
		for(KubernetesJobExecutor executor : jobExecutors.values()) {
			try {
				executor.join();
			} catch (InterruptedException e) {
				logger.error(e.getLocalizedMessage());
			}
		}

		for(KubernetesJobExecutor executor : jobExecutors.values()) {
			if (executor.isJobFailed()) {
				failed = true;
				failureMessage = executor.getFailureMessage();
				events.emit("ERROR", "WRAPPER_JOB_FAILED", failureMessage);
			}
		}
		
		// Close all Kubernetes clients
		for(KubernetesJobExecutor executor : jobExecutors.values()) {
			executor.close();
		}
		jobExecutors.clear();

		logger.info("ScenarioRunnerThread is exiting for " + scenarioID);
	}
	
	public boolean hasCorruptedParts() {
		if (failed) return true;
		for(KubernetesJobExecutor executor : jobExecutors.values()) {
			if (executor.isJobFailed()) return true;
		}
		return false;
	}

	public String getFailureMessage() {
		if (failureMessage != null && !failureMessage.isEmpty()) {
			return failureMessage;
		}
		return "One or more wrapper jobs failed for task " + taskId;
	}
	
	//run tools, provide resources and so on
	public boolean instantiateScenario() {
		
		startTime = System.currentTimeMillis();

		/* Start requested simulators and translators */
		jobExecutors = executeInstancesKubernetes(scenario);
		try {
			Thread.sleep(Config.DEFAULT_WAIT_MS);
		} catch (InterruptedException e) {
			logger.info(e.getLocalizedMessage());
		}
		
		/* Publish resource files for this scenario */
		boolean resourcesPublished = publishScenarioResources(scenario);
		if (!resourcesPublished) {
			logger.error("Failed to publish resources for scenario: " + scenarioID);
			new SimulationEventEmitter(taskId, "simservice", "SimService").emit("ERROR", "RESOURCE_PUBLISH_FAILED", "Failed to publish resources for task");
			return false;
		}

		/* Repost ScenarioFile --> acts as ACK and can be used by the tools to read parameters */
		logger.info("Acking SCE to "+Config.getProvisionTopic(scenarioID, Config.get(Config.TOPIC_SCENARIO)));
		boolean succPub = true;
		try {
			ProducerImplKafka<Scenario> kafkaWriter = new ProducerImplKafka<Scenario>(kafkaID);	
			kafkaWriter.init();
			succPub = kafkaWriter.publish(Config.getProvisionTopic(scenarioID, Config.get(Config.TOPIC_SCENARIO)), scenario, 0);
			kafkaWriter.close();
		} catch (TimeoutException e) {
			logger.error(e.getLocalizedMessage());
			return false;
		}
		if(!succPub) return false;

		return true;
	}

	/**
	 * Execute instances using Kubernetes Jobs
	 */
	public HashMap<String, KubernetesJobExecutor> executeInstancesKubernetes(Scenario scenario) {
		logger.info("Running scenario " + scenario.getScenarioID() + " (KUBERNETES MODE)");
		logger.info("No. of building blocks: " + scenario.getBuildingBlocks().size());
		logger.info("No. of projectors: " + scenario.getProjectors().size());
		logger.info("No. of translators: " + scenario.getTranslators().size());
		SimulationEventEmitter events = new SimulationEventEmitter(taskId, "simservice", "SimService");
		events.emit("PROGRESS", "SCENARIO_ACCEPTED", "Scenario accepted for execution", 0.10, scenario.getSimulationStart(), null);
		
		HashMap<String, KubernetesJobExecutor> executors = new HashMap<String, KubernetesJobExecutor>();

		// Create Jobs for BuildingBlocks
		for(BB sim : scenario.getBuildingBlocks()) {
			KubernetesJobExecutor executor = new KubernetesJobExecutor(
				sim.getType().toString(), 
				sim.getInstanceID().toString(), 
				scenario,
				taskId
			);
			executors.put(sim.getInstanceID().toString(), executor);
			logger.info("Added Kubernetes Job executor for BuildingBlock: " + sim.getInstanceID().toString());
			executor.start();
		}
		
		// Create Jobs for Projectors
		for(Projector proj : scenario.getProjectors()) {
			KubernetesJobExecutor executor = new KubernetesJobExecutor(
				"projectors-" + proj.getType().toString(), 
				proj.getProjectorID().toString(), 
				scenario,
				taskId
				);
				executors.put(proj.getProjectorID().toString(), executor);
				logger.info("Added Kubernetes Job executor for Projector: " + proj.getProjectorID().toString());
				executor.start();
			}
		
		// Create Jobs for Translators
		for(Translator trans : scenario.getTranslators()) {
			KubernetesJobExecutor executor = new KubernetesJobExecutor(
				"translators-" + trans.getType().toString(), 
				trans.getTranslatorID().toString(), 
				scenario,
				taskId
				);
				executors.put(trans.getTranslatorID().toString(), executor);
				logger.info("Added Kubernetes Job executor for Translator: " + trans.getTranslatorID().toString());
				executor.start();
			}
		
		return executors;
	}
	
	/**
	 * Publish resource files for each building block in the scenario
	 */
	private boolean publishScenarioResources(Scenario scenario) {
		logger.info("Publishing resources for scenario: " + scenarioID);
		SimulationEventEmitter events = new SimulationEventEmitter(taskId, "simservice", "SimService");
		events.emit("PROGRESS", "RESOURCE_DISCOVERY_STARTED", "Discovering task resources");
		
		ProducerImplKafka<ResourceFile> resourceWriter = null;
		try {
			resourceWriter = new ProducerImplKafka<ResourceFile>("resourceWriter-" + scenarioID);
			resourceWriter.init();
			
				// RabbitMQ-submitted runs store scenario and resources under resourceDir/{task_id}.
			String resourceDir = getTaskDirectory();
			File resourceDirFile = new File(resourceDir);
			
			if (!resourceDirFile.exists() || !resourceDirFile.isDirectory()) {
				logger.warn("Resource directory does not exist: " + resourceDir);
				return true; // Not an error if no resources needed
			}
			
			// Collect all unique resource files needed by all building blocks
			HashMap<String, String> allResources = new HashMap<String, String>();
			
			for(BB bb : scenario.getBuildingBlocks()) {
				java.util.Map<CharSequence, CharSequence> resources = bb.getResources();
				if (resources == null || resources.isEmpty()) {
					continue;
				}
				
				for(java.util.Map.Entry<CharSequence, CharSequence> entry : resources.entrySet()) {
					String fileName = entry.getKey().toString();
					String fileType = entry.getValue().toString();
					allResources.put(fileName, fileType);
				}
			}
			
			if (allResources.isEmpty()) {
				logger.info("No resources to publish for scenario: " + scenarioID);
				return true;
			}
			
			logger.info("Found " + allResources.size() + " unique resource files to publish");
			
			// Publish each resource file to scenario-specific topic
			String resourceTopic = Config.getProvisionTopic(scenarioID, "resource");
			
			for(java.util.Map.Entry<String, String> entry : allResources.entrySet()) {
				String fileName = entry.getKey();
				String fileType = entry.getValue();
				
				File file = new File(resourceDir, fileName);
				if (!file.exists()) {
					logger.error("Resource file not found: " + file.getAbsolutePath());
					events.emit("ERROR", "RESOURCE_FILE_MISSING", "Resource file not found: " + fileName);
					continue; // Skip missing files but don't fail completely
				}
				
				try {
					ResourceFile rf = new ResourceFile();
					rf.setID(fileName);
					rf.setType(fileType);
					
					// Read file content
					byte[] fileContent = java.nio.file.Files.readAllBytes(file.toPath());
					java.nio.ByteBuffer buffer = java.nio.ByteBuffer.wrap(fileContent);
					rf.setFile(buffer);
					rf.setFileReference(null);
					
					// Publish to Kafka
					boolean success = resourceWriter.publish(resourceTopic, rf, 0);
					if (success) {
						logger.info("Published resource: " + fileName + " (" + fileType + ") to " + resourceTopic + " (" + fileContent.length + " bytes)");
						events.emit("PROGRESS", "RESOURCE_FILE_PUBLISHED", "Published resource: " + fileName);
					} else {
						logger.error("Failed to publish resource: " + fileName);
						events.emit("ERROR", "RESOURCE_FILE_PUBLISH_FAILED", "Failed to publish resource: " + fileName);
					}
					
				} catch (IOException e) {
					logger.error("Error reading resource file: " + file.getAbsolutePath() + " - " + e.getMessage());
					events.emit("ERROR", "RESOURCE_FILE_READ_FAILED", "Error reading resource file: " + fileName);
				}
			}
			
			return true;
			
		} catch (Exception e) {
			logger.error("Failed to publish scenario resources: " + e.getMessage());
			e.printStackTrace();
			return false;
		} finally {
			if (resourceWriter != null) {
				resourceWriter.close();
			}
		}
	}

	private String getTaskDirectory() {
		if (taskId != null && !taskId.isEmpty()) {
			String resourceDir = Config.get("resourceDir");
			if (resourceDir == null || resourceDir.isEmpty()) {
				resourceDir = Config.get(Config.DIR_ROOT) + "/resources";
			}
			return resourceDir + "/" + taskId;
		}
		return Config.get(Config.DIR_DEFINITION) + "/resources";
	}

	public void printStatus() {
		logger.info("\nScenarioInstanceExecutor "+scenarioID+", done="+done+", there are "+jobExecutors.size()+" Kubernetes Jobs:");
		for(Entry<String, KubernetesJobExecutor> entry : jobExecutors.entrySet()) {
			KubernetesJobExecutor executor = entry.getValue();
			logger.info(entry.getKey()+": jobName="+executor.getJobName()+", running="+executor.isJobRunning()+", completed="+executor.isJobCompleted()+", failed="+executor.isJobFailed()+", exitCode="+executor.getExitCode());
		}
	}
	
	public long getAge() {
		return System.currentTimeMillis() - startTime;
	}
	
	public void kill() {
		// Delete all Kubernetes Jobs
		for(Entry<String, KubernetesJobExecutor> entry : jobExecutors.entrySet()) {
			KubernetesJobExecutor executor = entry.getValue();
			if (executor == null) continue;
			executor.terminate();
		}
		done = true;
	}
}

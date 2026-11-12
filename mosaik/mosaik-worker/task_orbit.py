"""One disposable Orbit pod with only the current task's input and output mounts."""
from contextlib import contextmanager
import os
import time
import uuid


@contextmanager
def task_orbit(task_id):
    from kubernetes import client, config
    if str(uuid.UUID(task_id)) != task_id:
        raise ValueError("Expected a canonical task UUID")
    config.load_incluster_config()
    api = client.CoreV1Api()
    namespace = os.environ.get("K8S_NAMESPACE", "simservice")
    # Unique execution name prevents a delayed cleanup from deleting a later pod.
    name = "mosaik-run-" + uuid.uuid4().hex
    image = os.environ.get("MOSAIK_ORBIT_IMAGE",
        "registry.gitlab.com/mosaik/mosaik-gui/mosaik-orbit:nfdi4energy-simaas")
    pod = {"apiVersion": "v1", "kind": "Pod", "metadata": {
        "name": name, "labels": {"app": "mosaik-execution", "task-id": task_id}}, "spec": {
        "automountServiceAccountToken": False, "restartPolicy": "Never",
        "activeDeadlineSeconds": int(float(os.environ.get("MOSAIK_RUN_TIMEOUT", "3600")) +
                                     float(os.environ.get("MOSAIK_BAKE_TIMEOUT", "120"))) + 180,
        "containers": [{"name": "orbit", "image": image, "imagePullPolicy": "IfNotPresent",
            "workingDir": "/data/resources/" + task_id,
            "env": [{"name": "MOSAIK_ORBIT_HOST", "value": "0.0.0.0"},
                    {"name": "MOSAIK_ORBIT_PORT", "value": "8442"},
                    {"name": "PYTHONDONTWRITEBYTECODE", "value": "1"}],
            "securityContext": {"allowPrivilegeEscalation": False, "capabilities": {"drop": ["ALL"]}},
            "readinessProbe": {"tcpSocket": {"port": 8442}, "periodSeconds": 1},
            "resources": {"requests": {"cpu": "100m", "memory": "256Mi"},
                          "limits": {"cpu": "2", "memory": "2Gi"}},
            "volumeMounts": [
                {"name": "task-data", "mountPath": "/data/resources/" + task_id,
                 "subPath": "resources/" + task_id, "readOnly": True},
                {"name": "task-data", "mountPath": "/data/results/" + task_id,
                 "subPath": "results/" + task_id}]}],
        "volumes": [{"name": "task-data", "persistentVolumeClaim": {
            "claimName": "simservice-data-pvc"}}]}}
    created = False
    try:
        api.create_namespaced_pod(namespace, pod, _request_timeout=15)
        created = True
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            status = api.read_namespaced_pod_status(name, namespace, _request_timeout=15).status
            if status.phase in {"Failed", "Succeeded"}:
                raise RuntimeError("Task Orbit exited before becoming ready")
            if status.pod_ip and any(c.type == "Ready" and c.status == "True" for c in (status.conditions or [])):
                yield "ws://" + status.pod_ip + ":8442/ws"
                return
            time.sleep(1)
        raise TimeoutError("Task Orbit did not become ready within 120 seconds")
    finally:
        if created:
            try:
                api.delete_namespaced_pod(name, namespace, grace_period_seconds=5, _request_timeout=15)
            except client.exceptions.ApiException as exc:
                if exc.status != 404:
                    raise
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                try:
                    api.read_namespaced_pod_status(name, namespace, _request_timeout=10)
                except client.exceptions.ApiException as exc:
                    if exc.status == 404:
                        break
                    raise
                time.sleep(1)
            else:
                raise RuntimeError("Task Orbit termination could not be confirmed")

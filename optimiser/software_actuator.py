"""
All *in-cluster* software actions: pod eviction, right-sizing,
affinity/taint patches, HPA/VPA nudging, node-pool scale hints.
Runs in the same container as the controller (no extra privileges).
"""
from kubernetes import client
import logging, math

class SoftwareActuator:
    def __init__(self, core_v1: client.CoreV1Api):
        self.v1 = core_v1
        self.log = logging.getLogger("software-actuator")

    # ─────────────────────────────────────────────────────────
    def evict_pod(self, name: str, namespace: str):
        if namespace == "kube-system":
            self.log.info("Skip eviction of kube-system pod %s", name); return
        body = client.V1Eviction(metadata=client.V1ObjectMeta(name=name, namespace=namespace))
        try:
            self.v1.create_namespaced_pod_eviction(name, namespace, body)
            self.log.info("Evicted pod %s/%s", namespace, name)
        except client.ApiException as e:
            self.log.warning("Evict failed %s/%s → %s", namespace, name, e.reason)

    # ─────────────────────────────────────────────────────────
    def right_size_requests(self, pod, new_cpu_millicores: int):
        """
        Patch the first container's cpu request; extend for memory if desired.
        """
        patch = {
            "spec": {
                "containers": [{
                    "name": pod.spec.containers[0].name,
                    "resources": {
                        "requests": { "cpu": f"{new_cpu_millicores}m" }
                    }
                }]
            }
        }
        self.v1.patch_namespaced_pod(pod.metadata.name, pod.metadata.namespace, patch)
        self.log.info("Right-sized %s/%s → %dm",
                      pod.metadata.namespace, pod.metadata.name, new_cpu_millicores)

    # ─────────────────────────────────────────────────────────
    def hpa_hint(self, deploy, target_util=0.5):
        """
        Patch the annotation that custom HPA controllers like KEDA can read.
        """
        patch = {"metadata":{
            "annotations": {"optimiser/target-util": str(target_util)}
        }}
        apps = client.AppsV1Api()
        apps.patch_namespaced_deployment(deploy.metadata.name,
        deploy.metadata.namespace, patch)
        self.log.info("Added HPA hint to %s/%s (target %.0f%%)",
                      deploy.metadata.namespace, deploy.metadata.name,
                      target_util*100)

    # ─────────────────────────────────────────────────────────
    def nodepool_scale_hint(self, node, direction: str):
        """
        Attach a label that Cluster-Autoscaler reads (you add an-
        on annotation in CA config).  direction: 'sleep' | 'wake'
        """
        patch = {"metadata": {"labels": {"optimiser/scale": direction}}}
        self.v1.patch_node(node.metadata.name, patch)
        self.log.info("Requested '%s' for node %s", direction, node.metadata.name)

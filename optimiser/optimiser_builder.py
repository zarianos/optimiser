import os, asyncio, aiohttp, time, orjson, numpy as np
from kubernetes import client, config
from typing import Dict, Any

PROM_URL = os.getenv("PROM_URL", "http://localhost:9090")

PROM_QUERIES = {
    # Energy
    "node_cpu_watts":  'kepler_node_cpu_watts',
    "node_cpu_idle_watts": 'kepler_node_cpu_idle_watts',
    "node_mem_bytes": 'node_memory_MemTotal_bytes',
    "pod_cpu_usage": 'sum(rate(container_cpu_usage_seconds_total{image!=""}[5m])) by (pod)',
    # Util
    "node_cpu_util":   'instance:node_cpu_utilisation:ratio5m',
    "node_mem_util":   'instance:node_memory_utilisation:ratio',
    # Kube-system overhead
    "kube_system_cpu": 'sum(rate(container_cpu_usage_seconds_total{namespace="kube-system"}[5m]))',
}

class StateBuilder:
    def __init__(self):
        config.load_incluster_config()
        self.v1 = client.CoreV1Api()
    # ---------------------------------------------------
    async def _prom_query(self, session, query):
        async with session.get(f"{PROM_URL}/api/v1/query",
                               params={"query": query, "time": time.time()}) as r:
            j = await r.json()
            return {tuple(m['metric'].values()): float(m['value'][1])
                    for m in j['data']['result']}
    # ---------------------------------------------------
    async def build_state(self) -> Dict[str, Any]:
        async with aiohttp.ClientSession() as s:
            results = await asyncio.gather(
                *[self._prom_query(s, q) for q in PROM_QUERIES.values()]
            )
        prom_data = dict(zip(PROM_QUERIES.keys(), results))

        # ----- Node info from K8s API --------------
        nodes = {}
        for n in self.v1.list_node().items:
            name = n.metadata.name
            alloc = n.status.allocatable
            nodes[name] = {
                "cpu": int(alloc['cpu'].rstrip('m')) / 1000,
                "mem": int(alloc['memory'].rstrip('Ki')) * 1024,
                "cpu_util":      prom_data["node_cpu_util"].get((name,), 0),
                "mem_util":      prom_data["node_mem_util"].get((name,), 0),
                "cpu_power_w":   prom_data["node_cpu_watts"].get((name,), 0),
                "idle_power_w":  prom_data["node_cpu_idle_watts"].get((name,), 0),
            }

        # ---- Pods (only essential data) ------------
        pods = {}
        for p in self.v1.list_pod_for_all_namespaces().items:
            pods[p.metadata.uid] = {
                "name": p.metadata.name,
                "ns":   p.metadata.namespace,
                "node": p.spec.node_name,
                "cpu_mcores": prom_data["pod_cpu_usage"].get((p.metadata.name,), 0)*1000,
                "qos": p.status.qos_class or "BestEffort"
            }

        return {
            "ts": time.time(),
            "nodes": nodes,
            "pods": pods,
            "cluster_wide": {
                "kube_system_cpu_overhead": prom_data["kube_system_cpu"]
            }
        }

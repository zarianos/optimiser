"""
Turns the huge Prometheus metric space + Kubernetes API objects
into a **compact numeric state vector** that the RL agent consumes,
while also returning the full rich dict so the controller can print
friendly status messages.
"""
import os, time, asyncio, aiohttp
from typing import Dict, Any
from kubernetes import client, config

PROM_URL = os.getenv("PROM_URL", "http://prometheus-k8s.monitoring:9090")

PROM_QUERIES = {
    # adjust / extend freely – every metric you listed is available
    "node_cpu_watts": 'kepler_node_cpu_watts',
    "node_cpu_util":  'instance:node_cpu_utilisation:ratio5m',
    "node_mem_util":  'instance:node_memory_utilisation:ratio',
    "pod_cpu_usage":  'sum by(pod) (rate(container_cpu_usage_seconds_total{image!=""}[5m]))',
    "kube_sys_cpu":   'sum(rate(container_cpu_usage_seconds_total{namespace="kube-system"}[5m]))',
}

class StateBuilder:
    def __init__(self):
        config.load_incluster_config()
        self.v1 = client.CoreV1Api()

    # ─────────────────────────────────────────────────────────
    async def _prom(self, session: aiohttp.ClientSession, q: str):
        async with session.get(f"{PROM_URL}/api/v1/query",
                               params={"query": q, "time": time.time()}) as r:
            js = await r.json()
            return {tuple(m['metric'].values()): float(m['value'][1])
                    for m in js['data']['result']}

    # ─────────────────────────────────────────────────────────
    async def get_cluster_state(self) -> Dict[str, Any]:
        async with aiohttp.ClientSession() as s:
            res = await asyncio.gather(*[self._prom(s, q) for q in PROM_QUERIES.values()])
        prom = dict(zip(PROM_QUERIES.keys(), res))

        nodes = {}
        for n in self.v1.list_node().items:
            name = n.metadata.name
            alloc = n.status.allocatable
            nodes[name] = {
                "alloc_cpu": float(alloc['cpu'].rstrip('m')) / 1000,
                "alloc_mem": int(alloc['memory'].rstrip('Ki')) * 1024,
                "cpu_util":  prom["node_cpu_util"].get((name,), 0),
                "mem_util":  prom["node_mem_util"].get((name,), 0),
                "cpu_power_watts": prom["node_cpu_watts"].get((name,), 0),
            }

        pods = {}
        for p in self.v1.list_pod_for_all_namespaces().items:
            pods[p.metadata.uid] = {
                "name":      p.metadata.name,
                "namespace": p.metadata.namespace,
                "node":      p.spec.node_name,
                "cpu_millicores": prom["pod_cpu_usage"].get((p.metadata.name,), 0)*1000
            }

        return {
            "ts": time.time(),
            "nodes": nodes,
            "pods": pods,
            "cluster_wide": {
                "kube_system_cpu_overhead": prom["kube_sys_cpu"]
            }
        }

    # ─────────────────────────────────────────────────────────
    def to_vector(self, state: Dict[str, Any]):
        nodes = list(state['nodes'].values())
        if not nodes:                       # empty cluster?
            return [0]*12
        cpu_utils  = [n['cpu_util'] for n in nodes]
        power      = [n['cpu_power_watts'] for n in nodes]
        return [
            len(nodes),                        # 0
            len(state['pods']),                # 1
            sum(power)/len(power),             # 2 mean W
            max(power),                        # 3 max  W
            max(cpu_utils),                    # 4 max  CPU util
            sum(cpu_utils)/len(cpu_utils),     # 5 mean CPU util
            max(state['cluster_wide'].get('kube_system_cpu_overhead',0), 1e-6),
                                               # 6 kube-system CPU
            # placeholders for future metrics
            0, 0, 0, 0, 0                      # 7-11
        ]

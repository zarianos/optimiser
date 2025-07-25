# SPDX-License-Identifier: Apache-2.0
# optimiser/energy_optimization_controller.py
#
# Async controller that: pulls cluster state, lets the hierarchical RL agent
# choose an action, executes it, measures Δ power, updates Prometheus gauges.

import os, json, time, asyncio
from pathlib import Path
from typing import Dict, Any, Tuple

import numpy as np
from kubernetes import client

from optimiser.exporter         import Exporter
from optimiser.software_actuator import SoftwareActuator
from optimiser.decision_engine   import HierarchicalAgent, HierMem

# ────────────── constants ─────────────────────────────────────────────
ACTION_DO_NOTHING    = 0
ACTION_CONSOLIDATE   = 1
ACTION_DEFRAGMENT    = 2
ACTION_HARDWARE_TUNE = 3
ACTION_NAMES = (
    "DO_NOTHING", "CONSOLIDATE", "DEFRAGMENT", "HARDWARE_TUNE"
)

SUGGESTION_DIR = Path("/tmp/k8s_optimizer_suggestions")
TRIGGER_FILE   = Path("/tmp/k8s_optimizer_trigger.signal")

# ────────────── helpers ───────────────────────────────────────────────
def _power(state: Dict[str, Any]) -> float:
    return sum(n.get("cpu_power_watts", 0.0) for n in state["nodes"].values())


# ────────────── controller class ──────────────────────────────────────
class OptimizationController:
    def __init__(
        self,
        agent:          HierarchicalAgent,
        data_collector,                     # StateBuilder-like (async)
        memory:         HierMem,
        exporter:       Exporter,
        update_timestep: int = 400,
    ):
        self.agent      = agent
        self.sb         = data_collector
        self.memory     = memory
        self.exp        = exporter
        self.update_ts  = update_timestep
        self.t          = 0
        self.saved_w    = 0.0

        self.v1         = client.CoreV1Api()
        self.sw_act     = SoftwareActuator(self.v1)

        SUGGESTION_DIR.mkdir(parents=True, exist_ok=True)
        TRIGGER_FILE.unlink(missing_ok=True)

    # ──────────────────────────────────────────────────────────────
    def state_vector(self, state):
        nodes = list(state["nodes"].values())
        if not nodes:
            return [0.0] * 12

        power   = [n["cpu_power_watts"] for n in nodes]
        cpu_u   = [n["cpu_util"]        for n in nodes]

        def safe_num(x, default=0.0):
            return x if isinstance(x, (int, float)) else default

        return [
            len(nodes),                        # 0
            len(state["pods"]),                # 1
            float(np.mean(power)),             # 2
            float(np.max(power)),              # 3
            float(np.mean(cpu_u)),             # 4
            float(np.max(cpu_u)),              # 5
            safe_num(state["cluster_wide"].get("kube_system_cpu_overhead")),
            0.0, 0.0, 0.0, 0.0, 0.0            # 7-11
        ]
    # ──────────────────────────────────────────────────────────────
    def _suggest(self, fam: int, tgt_idx: int, state) -> Dict[str, Any]:
        sug = {"action": fam, "target": None}
        if fam == ACTION_DO_NOTHING or not state["nodes"]:
            return sug

        node_names = list(state["nodes"])
        node       = node_names[tgt_idx % len(node_names)]
        sug["target"] = node
        return sug

    # ──────────────────────────────────────────────────────────────
    async def _execute(self, sug: Dict[str, Any], st_before: Dict[str, Any],
                       settle: int) -> float:
        fam  = sug["action"]
        node = sug.get("target")

        if fam == ACTION_DO_NOTHING:
            return 0.0

        if fam == ACTION_HARDWARE_TUNE and node:
            patch = {"metadata": {"labels": {"optimiser/tune":"cpusave"}}}
            self.v1.patch_node(node, patch)

        elif fam in (ACTION_CONSOLIDATE, ACTION_DEFRAGMENT) and node:
            pods = [p for p in st_before["pods"].values() if p["node"] == node]
            if pods:
                getter = lambda p: p.get("cpu_mcores", 0.0)
                pod = max(pods, key=getter) \
                      if fam == ACTION_CONSOLIDATE \
                      else min(pods, key=getter)
                self.sw_act.evict_pod(pod["name"], pod["namespace"])

        # wait for cluster to stabilise
        await asyncio.sleep(settle)

        st_after = await self.sb.get_cluster_state()
        return _power(st_before) - _power(st_after)

    # ──────────────────────────────────────────────────────────────
    async def run_loop_async(self, observation_interval=30, action_settle_time=90):
        while True:
            self.t += 1
            st = await self.sb.get_cluster_state()
            vec = self.state_vector(st)

            fam, tgt = self.agent.select(vec, self.memory)
            sug      = self._suggest(fam, tgt, st)

            # human-readable log
            print(f"\n── cycle {self.t} — {time.ctime()} ──")
            print("Nodes:", ", ".join(st["nodes"].keys()) or "Ø")
            print("Suggested:", ACTION_NAMES[sug['action']], sug.get("target"))

            # save suggestion
            (SUGGESTION_DIR / f"sug_{self.t}.json").write_text(json.dumps(sug))

            # execute immediately (auto-mode)
            delta = await self._execute(sug, st, action_settle_time)
            if delta:
                self.saved_w += delta
                self.exp.record(before=0, after=0, action_id=fam)
                print(f"Δ power realised: {delta:.2f} W  (cum {self.saved_w:.2f} W)")

            # reward bookkeeping
            r = -_power(st)            # simple reward: lower is better
            self.memory.high.rewards.append(r)
            self.memory.low.rewards.append(r)
            self.memory.high.is_terminals.append(False)
            self.memory.low.is_terminals.append(False)

            if self.t % self.update_ts == 0:
                self.agent.update(self.memory)

            await asyncio.sleep(observation_interval)

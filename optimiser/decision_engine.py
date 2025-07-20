import numpy as np
from .advanced_optimization import PPOAgent, Memory

# MEMORY WRAPPER FOR 2-LEVEL POLICY
class HierMem:
    def __init__(self):
        self.high, self.low = Memory(), Memory()
    def clear(self):
        self.high.clear(); self.low.clear()

class HierarchicalAgent:
    """
    High-level   – chooses ACTION_FAMILY  (0..3)
    Low-level    – chooses PARAM (target node / pod / knob)
    """
    def __init__(self, state_dim, max_nodes, max_pods):
        # family: DO_NOTHING, CONSOLIDATE, DEFRAG, HW_TUNE
        self.high = PPOAgent(state_dim, 4)
        # low: binary split of 'index' (node=0-(max_nodes-1) or
        #      pod=0-(max_pods-1) encoded as Gray code bits)
        self.target_bits = int(np.ceil(np.log2(max(max_nodes, max_pods))))
        self.low  = PPOAgent(state_dim + 1, 2 ** self.target_bits)

    # ----------------------------------------------------
    def select(self, state_vec: np.ndarray, memory: HierMem):
        fam = self.high.select_action(state_vec, memory.high)
        # add family id as extra feature for the lower policy
        low_state = np.append(state_vec, fam)
        tgt = self.low.select_action(low_state, memory.low)
        return fam, tgt

    def update(self, memory: HierMem):
        self.high.update(memory.high)
        self.low.update(memory.low)

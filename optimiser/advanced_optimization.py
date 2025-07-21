# SPDX-License-Identifier: Apache-2.0
# optimiser/advanced_optimization.py
#
# Energy-aware PPO implementation
# – AMP, smaller nets, torch.compile().

import os
from typing import List

import torch
import torch.nn as nn
from torch.distributions import Categorical

# ───────── Tunables (env-overridable) ─────────
H1 = int(os.getenv("PPO_HIDDEN_1", 32))
H2 = int(os.getenv("PPO_HIDDEN_2", 32))
LR_ACTOR   = float(os.getenv("PPO_LR_ACTOR", 3e-4))
LR_CRITIC  = float(os.getenv("PPO_LR_CRITIC", 1e-3))
K_EPOCHS   = int(os.getenv("PPO_K_EPOCHS", 40))
EPS_CLIP   = float(os.getenv("PPO_EPS_CLIP", 0.20))
GAMMA      = float(os.getenv("PPO_GAMMA", 0.99))
N_THREADS  = int(os.getenv("PPO_NUM_THREADS", 2))
USE_AMP    = os.getenv("PPO_MIXED_PRECISION", "1") == "1"
DTYPE_AMP  = torch.bfloat16 if torch.cuda.is_available() else torch.bfloat16

torch.set_num_threads(N_THREADS)

# ───────────────────────────────────────────────
class PPOAgent:
    def __init__(self,
                 state_dim: int,
                 action_dim: int,
                 lr_actor: float = LR_ACTOR,
                 lr_critic: float = LR_CRITIC,
                 gamma: float = GAMMA,
                 K_epochs: int = K_EPOCHS,
                 eps_clip: float = EPS_CLIP):

        self.gamma, self.K_epochs, self.eps_clip = gamma, K_epochs, eps_clip
        self.dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        self.policy     = ActorCritic(state_dim, action_dim).to(self.dev)
        self.policy_old = ActorCritic(state_dim, action_dim).to(self.dev)
        self.policy_old.load_state_dict(self.policy.state_dict())

        self.opt = torch.optim.Adam(
            [{"params": self.policy.actor.parameters(),  "lr": lr_actor},
             {"params": self.policy.critic.parameters(), "lr": lr_critic}]
        )
        self.mse = nn.MSELoss()

        if hasattr(torch, "compile"):
            self.policy = torch.compile(self.policy)
            self.policy_old = torch.compile(self.policy_old)

    # ───────────────────────────────────────────
    @torch.no_grad()
    def select_action(self, state, memory):
        st = torch.as_tensor(state, dtype=torch.float32, device=self.dev)
        with torch.autocast(self.dev.type, dtype=DTYPE_AMP, enabled=USE_AMP):
            probs = self.policy_old.actor(st)
            dist  = Categorical(probs)
            act   = dist.sample()
        memory.states.append(st)
        memory.actions.append(act)
        memory.logprobs.append(dist.log_prob(act))
        return int(act.item())

    # ───────────────────────────────────────────
    def update(self, memory):
        # discounted rewards
        R, buf = 0.0, []
        for r, done in zip(reversed(memory.rewards), reversed(memory.is_terminals)):
            R = r + self.gamma * R * (1.0 - done)
            buf.insert(0, R)
        rewards = torch.tensor(buf, dtype=torch.float32, device=self.dev)
        rewards = (rewards - rewards.mean()) / (rewards.std(unbiased=False) + 1e-7)

        s  = torch.stack(memory.states).to(self.dev)
        a  = torch.stack(memory.actions).to(self.dev)
        lp = torch.stack(memory.logprobs).to(self.dev)

        for _ in range(self.K_epochs):
            with torch.autocast(self.dev.type, dtype=DTYPE_AMP, enabled=USE_AMP):
                new_lp, vals, ent = self.policy.evaluate(s, a)
                ratios = torch.exp(new_lp - lp.detach())
                adv = rewards - vals.detach().squeeze(-1)
                surr1 = ratios * adv
                surr2 = torch.clamp(ratios, 1 - self.eps_clip, 1 + self.eps_clip) * adv
                loss  = (-torch.min(surr1, surr2)
                         + 0.5 * self.mse(vals.squeeze(-1), rewards)
                         - 0.01 * ent).mean()

            self.opt.zero_grad(set_to_none=True)
            loss.backward()
            self.opt.step()

        self.policy_old.load_state_dict(self.policy.state_dict())
        memory.clear()

# ───────────────────────────────────────────────
class ActorCritic(nn.Module):
    def __init__(self, state_dim, action_dim):
        super().__init__()
        self.actor = nn.Sequential(
            nn.Linear(state_dim, H1), nn.Tanh(),
            nn.Linear(H1, H2),        nn.Tanh(),
            nn.Linear(H2, action_dim), nn.Softmax(dim=-1))
        self.critic = nn.Sequential(
            nn.Linear(state_dim, H1), nn.Tanh(),
            nn.Linear(H1, H2),        nn.Tanh(),
            nn.Linear(H2, 1))

    def evaluate(self, states, actions):
        probs   = self.actor(states)
        dist    = Categorical(probs)
        logps   = dist.log_prob(actions)
        entropy = dist.entropy()
        values  = self.critic(states)
        return logps, values, entropy

# ───────────────────────────────────────────────
class Memory:
    def __init__(self):
        self.actions, self.states, self.logprobs = [], [], []
        self.rewards, self.is_terminals          = [], []

    def clear(self):
        self.actions.clear(); self.states.clear(); self.logprobs.clear()
        self.rewards.clear(); self.is_terminals.clear()

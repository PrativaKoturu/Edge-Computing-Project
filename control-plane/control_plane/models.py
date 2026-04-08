from __future__ import annotations

import torch
import torch.nn as nn

from ncps.torch import LTC
from ncps.wirings import AutoNCP


class LtCActor(nn.Module):
    """
    Actor: Liquid Time-Constant network using ncps wiring:
      - AutoNCP(units=19, output_size=1)
    Input: 8-D state
    Output: cache score in [0,1]

    Implementation detail to satisfy quantization spec:
      - first layer is Linear(8 -> 19), so its weight matrix is shape [19, 8]
    """

    def __init__(self, state_dim: int = 8):
        super().__init__()
        if state_dim != 8:
            raise ValueError("Actor expects state_dim=8 by spec")
        self.input_proj = nn.Linear(8, 19)
        wiring = AutoNCP(units=19, output_size=1)
        self.ltc = LTC(19, wiring)

    def forward(self, s: torch.Tensor) -> torch.Tensor:
        # s: (B, 8)
        x = torch.tanh(self.input_proj(s))  # (B, 19)
        y, _ = self.ltc(x)  # (B, 1)
        return torch.sigmoid(y)  # (B, 1) in [0,1]


class Td3Critic(nn.Module):
    """
    Critic: twin Q networks (TD3)
    - Each Q is 3-layer MLP with 256 hidden units.
    Input: concat(state[8], action[1]) => 9
    Output: scalar Q
    """

    def __init__(self, state_dim: int = 8, action_dim: int = 1, hidden: int = 256):
        super().__init__()
        in_dim = state_dim + action_dim

        def qnet() -> nn.Module:
            return nn.Sequential(
                nn.Linear(in_dim, hidden),
                nn.ReLU(),
                nn.Linear(hidden, hidden),
                nn.ReLU(),
                nn.Linear(hidden, 1),
            )

        self.q1 = qnet()
        self.q2 = qnet()

    def forward(self, s: torch.Tensor, a: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        x = torch.cat([s, a], dim=-1)
        return self.q1(x), self.q2(x)


class Td3Agent(nn.Module):
    """
    Bundles actor/critic + target networks.
    """

    def __init__(self) -> None:
        super().__init__()
        self.actor = LtCActor()
        self.critic = Td3Critic()
        self.actor_target = LtCActor()
        self.critic_target = Td3Critic()
        self.reset_targets(hard=True)

    @torch.no_grad()
    def reset_targets(self, hard: bool = False, tau: float = 0.005) -> None:
        if hard:
            self.actor_target.load_state_dict(self.actor.state_dict())
            self.critic_target.load_state_dict(self.critic.state_dict())
            return
        for p, pt in zip(self.actor.parameters(), self.actor_target.parameters()):
            pt.data.mul_(1.0 - tau).add_(p.data, alpha=tau)
        for p, pt in zip(self.critic.parameters(), self.critic_target.parameters()):
            pt.data.mul_(1.0 - tau).add_(p.data, alpha=tau)

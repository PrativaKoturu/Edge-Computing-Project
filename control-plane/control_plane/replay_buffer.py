from __future__ import annotations

from dataclasses import dataclass
from collections import deque
import random

import numpy as np


@dataclass(frozen=True)
class Transition:
    node_id: str
    s: np.ndarray  # shape (8,)
    a: float       # scalar action in [0,1]
    r: float
    sp: np.ndarray  # shape (8,)
    done: bool


class GlobalReplayBuffer:
    def __init__(self, capacity: int = 10_000):
        self._buf: deque[Transition] = deque(maxlen=capacity)

    def push(self, t: Transition) -> None:
        self._buf.append(t)

    def __len__(self) -> int:
        return len(self._buf)

    def sample(self, batch_size: int) -> list[Transition]:
        batch_size = min(batch_size, len(self._buf))
        return random.sample(list(self._buf), k=batch_size)

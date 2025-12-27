
import numpy as np
from dataclasses import dataclass
from typing import List, Tuple, Dict, Optional

# --- GLOBAL DEFAULT CONFIG ---
class MirageConfig:
    # Detection (v3.7)
    WINDOW_SIZE: float = 60.0
    ROBUST_A: float = 0.008
    BLOCK_SIZE: int = 512
    REPEATS: int = 16
    GAP_CHIPS: int = 32
    Z_THRESHOLD: float = 4.5
    
    # Countermeasures (v4.1)
    MAX_TARPIT_DELAY_MS: float = 500.0
    SAWTOOTH_PERIOD: float = 20.0
    SAWTOOTH_DROP: float = 0.9
    
    # Simulation
    SIM_DURATION: float = 600.0

@dataclass
class PacketFlow:
    """Represents a sequence of network packets."""
    ts: np.ndarray  # Arrival timestamps
    sizes: Optional[np.ndarray] = None
    
    @property
    def iats(self) -> np.ndarray:
        """Inter-Arrival Times."""
        if len(self.ts) < 2:
            return np.array([])
        return np.diff(self.ts)

def pn_key(n: int, seed: Optional[int] = None) -> np.ndarray:
    """Generates a Pseudo-Noise (+1/-1) key."""
    if seed is not None:
        np.random.seed(seed)
    return np.random.choice([-1, 1], size=n)

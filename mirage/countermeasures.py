
import numpy as np
import struct
from .core import MirageConfig

class SmartPoisonEngine:
    """
    Generates realistic-looking but corrupted data chunks.
    Target: SQLite Database files.
    """
    def generate_chunk(self, size: int) -> bytes:
        # Fake SQLite Header (Leaf Table B-Tree) 
        # This fools file type sniffers (magic bytes)
        # Header: Flag(1) + FreeBlock(2) + NumCells(2) + CellContentStart(2)
        # 0x0D = Leaf Table B-Tree
        header = struct.pack('>BHHH', 0x0D, 0x0000, 0x0005, 0x1000)
        
        # Fill rest with random garbage (Entropy)
        # In a real ops scenario, this would contain beacon tokens.
        body = np.random.bytes(max(0, size - len(header)))
        return header + body

class SawtoothTarpit:
    """
    Psychological Traffic Pacing.
    Implements a 'Sawtooth' latency pattern to manage attacker suspicion.
    """
    def __init__(self, config: MirageConfig):
        self.config = config
        self.latency = 0.0
        self.timer = 0.0
        
        # Derived from config
        # We calculate gradient to reach peak in Period
        # Peak = Max Delay. Period = Sawtooth Period.
        self.gradient = (config.MAX_TARPIT_DELAY_MS / 1000.0) / config.SAWTOOTH_PERIOD
        
    def step(self, dt: float) -> float:
        """
        Updates the Tarpit state by dt seconds.
        Returns the current latency penalty (seconds).
        """
        # Squeeze Phase
        self.latency += self.gradient * dt
        self.timer += dt
        
        # Release Phase (Psychological Reset)
        if self.timer >= self.config.SAWTOOTH_PERIOD:
            self.latency *= (1.0 - self.config.SAWTOOTH_DROP)
            self.timer = 0.0
            
        # Add Jitter for realism (Network isn't perfectly smooth)
        jitter = np.random.normal(0, 0.002) 
        effective = max(0.0, self.latency + jitter)
        
        return effective

class ActiveDefenseController:
    """
    Orchestrates the response to detected threats.
    """
    def __init__(self, config: MirageConfig):
        self.config = config
        self.tarpit = SawtoothTarpit(config)
        self.poisoner = SmartPoisonEngine()
        self.is_engaged = False
        
    def update(self, z_score: float, dt: float) -> dict:
        """
        Main logic loop.
        Inputs: Current Z-Score, Time Delta.
        Returns: Dict of applied effects.
        """
        # Hysteresis Logic
        # Engage if Z > Threshold
        # Disengage if Z < Threshold - 1.0 (Cool down)
        
        if z_score > self.config.Z_THRESHOLD:
            self.is_engaged = True
        elif z_score < (self.config.Z_THRESHOLD - 2.0):
            # Only disengage if we are VERY sure it's gone
            self.is_engaged = False
            
        effects = {
            "engaged": self.is_engaged,
            "latency_penalty": 0.0,
            "poison_active": False
        }
        
        if self.is_engaged:
            # 1. Apply Tarpit
            effects["latency_penalty"] = self.tarpit.step(dt)
            
            # 2. Activate Poisoning
            effects["poison_active"] = True
            
        # Diagnosis Logic
        effects["reason"] = "MONITORING"
        if self.is_engaged:
            if z_score > self.config.Z_THRESHOLD:
                effects["reason"] = "THREAT DETECTED (Z-SCORE)"
            else:
                effects["reason"] = "HYSTERESIS LOCK (COOLDOWN)"

        return effects

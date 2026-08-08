"""
AURA v6.11 Execution Safety Core Module
========================================
Implements System State Machine, Model Integrity SHA-256 Verifier, Demo-Only Account Enforcer,
Idempotency Signal Handler, and Safety Kill Switch Router.
"""

import os
import sys
import json
import hashlib
from enum import Enum, auto
from datetime import datetime, timezone
import pandas as pd

class SystemState(Enum):
    INIT = auto()
    VALIDATING = auto()
    READY = auto()
    MONITORING = auto()
    SIGNAL_APPROVED = auto()
    EXECUTING = auto()
    POSITION_OPEN = auto()
    POSITION_CLOSING = auto()
    POSITION_CLOSED = auto()
    HALTED = auto()
    ERROR = auto()

class SystemStateMachine:
    """Rigid state machine for v6.11 execution safety."""

    VALID_TRANSITIONS = {
        SystemState.INIT: [SystemState.VALIDATING, SystemState.HALTED, SystemState.ERROR],
        SystemState.VALIDATING: [SystemState.READY, SystemState.HALTED, SystemState.ERROR],
        SystemState.READY: [SystemState.MONITORING, SystemState.HALTED, SystemState.ERROR],
        SystemState.MONITORING: [SystemState.SIGNAL_APPROVED, SystemState.HALTED, SystemState.ERROR],
        SystemState.SIGNAL_APPROVED: [SystemState.EXECUTING, SystemState.HALTED, SystemState.ERROR],
        SystemState.EXECUTING: [SystemState.POSITION_OPEN, SystemState.HALTED, SystemState.ERROR],
        SystemState.POSITION_OPEN: [SystemState.POSITION_CLOSING, SystemState.HALTED, SystemState.ERROR],
        SystemState.POSITION_CLOSING: [SystemState.POSITION_CLOSED, SystemState.HALTED, SystemState.ERROR],
        SystemState.POSITION_CLOSED: [SystemState.MONITORING, SystemState.HALTED, SystemState.ERROR],
        SystemState.HALTED: [], # Hard stop: requires manual reset
        SystemState.ERROR: [SystemState.HALTED]
    }

    def __init__(self):
        self.state = SystemState.INIT
        self.halt_reason = None
        self.halt_code = None

    def transition(self, new_state: SystemState, reason: str = None, code: str = None):
        if new_state in self.VALID_TRANSITIONS[self.state]:
            self.state = new_state
            if new_state == SystemState.HALTED:
                self.halt_reason = reason or "UNKNOWN_HALT_REASON"
                self.halt_code = code or "CRITICAL_HALT"
            return True
        else:
            self.state = SystemState.HALTED
            self.halt_reason = f"INVALID_STATE_TRANSITION ({self.state.name} -> {new_state.name})"
            self.halt_code = "STATE_MACHINE_VIOLATION"
            return False

def verify_model_hash(model_path: str, expected_hash: str) -> bool:
    if not os.path.exists(model_path):
        return False
    h = hashlib.sha256()
    with open(model_path, 'rb') as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest() == expected_hash

def verify_demo_account(account_mode: str) -> bool:
    """Enforce MT5 DEMO mode strictly."""
    return account_mode.upper() == "DEMO"

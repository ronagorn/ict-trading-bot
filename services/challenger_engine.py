"""
Production-Grade Champion / Challenger Engine (AURA v5)
========================================================
Manages model versioning, state locking, and registry for Champion and Challenger models.
"""

from __future__ import annotations
import sys
import json
import hashlib
from pathlib import Path
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.logger import logger


@dataclass
class ModelVersionManifest:
    model_id: str
    strategy_version: str = "v5.0"
    model_version: str = "v5.0.0"
    config_version: str = "v5.0_production"
    dataset_version: str = "2026_Q3_OOS"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    is_locked: bool = False
    model_hash: str = ""
    feature_schema_hash: str = ""
    is_champion: bool = False


class ChampionChallengerRegistry:
    """
    Registry managing active Champion and competing Challenger candidates.
    """

    def __init__(self, registry_dir: Optional[Path] = None):
        self.registry_dir = registry_dir or (Path(__file__).resolve().parent.parent / "data" / "model_registry")
        self.registry_dir.mkdir(parents=True, exist_ok=True)
        self.champion_manifest: Optional[ModelVersionManifest] = None
        self.history_manifests: List[ModelVersionManifest] = []

    @staticmethod
    def compute_manifest_hash(features: List[str], params: Dict[str, Any]) -> str:
        """Computes deterministic hash to verify state locking."""
        data_str = json.dumps({"features": sorted(features), "params": params}, sort_keys=True)
        return hashlib.sha256(data_str.encode("utf-8")).hexdigest()[:16]

    def register_model_candidate(
        self,
        model_id: str,
        features: List[str],
        parameters: Dict[str, Any],
        strategy_ver: str = "v5.0",
        is_champion: bool = False
    ) -> ModelVersionManifest:
        """Registers a new model version candidate."""
        h_val = self.compute_manifest_hash(features, parameters)
        manifest = ModelVersionManifest(
            model_id=model_id,
            strategy_version=strategy_ver,
            model_hash=h_val,
            feature_schema_hash=h_val,
            is_champion=is_champion
        )
        if is_champion and self.champion_manifest is not None:
            self.history_manifests.append(self.champion_manifest)
            
        if is_champion:
            self.champion_manifest = manifest

        return manifest

    def lock_model_candidate(self, manifest: ModelVersionManifest) -> ModelVersionManifest:
        """Locks model state prior to Untouched OOS evaluation."""
        manifest.is_locked = True
        logger.info(f"🔒 Model Manifest {manifest.model_id} (Ver: {manifest.model_version}) LOCKED for OOS Evaluation.")
        return manifest

    def rollback_to_previous_champion(self) -> Tuple[bool, Optional[ModelVersionManifest]]:
        """Rolls back active Champion to previous stable version."""
        if not self.history_manifests:
            logger.warning("Rollback Failed: No previous Champion found in history!")
            return False, None

        prev_champ = self.history_manifests.pop()
        prev_champ.is_champion = True
        
        current_champ_id = self.champion_manifest.model_id if self.champion_manifest else "None"
        self.champion_manifest = prev_champ

        logger.warning(f"⏪ ROLLBACK TRIGGERED: Demoted Champion {current_champ_id} -> Promoted Previous Champion {prev_champ.model_id}")
        return True, prev_champ

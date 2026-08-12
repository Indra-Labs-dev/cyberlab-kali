"""Backward-compatible aliases. Phase 13 (Asset Model) generalized `Target`
into `Asset` (app/models/asset.py) -- same table, same rows, same primary
keys. Every pre-Phase-13 import (`from app.models.target import Target,
TargetType, AuthorizationStatus`) keeps resolving to the exact same class,
so `/api/targets` and everything built on it needed zero changes.

New code should import from app.models.asset directly.
"""

from app.models.asset import Asset as Target
from app.models.asset import AssetType as TargetType
from app.models.asset import AuthorizationStatus

__all__ = ["Target", "TargetType", "AuthorizationStatus"]

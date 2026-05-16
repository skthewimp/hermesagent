"""In-memory pending action store for lightweight gateway confirmation flows."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple


DEFAULT_PENDING_TTL_SECONDS = 15 * 60


@dataclass
class PendingAction:
    action_id: str
    user_id: str
    chat_id: str
    payload: Dict[str, Any]
    created_at: float
    expires_at: float
    source_message_id: Optional[str] = None
    confirmation_message_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


_pending_actions: Dict[str, PendingAction] = {}
_awaiting_corrections: Dict[Tuple[str, str], str] = {}


def cleanupExpiredPendingActions(now: Optional[float] = None) -> int:
    """Remove expired pending actions and correction waits."""
    current = time.time() if now is None else now
    expired_ids = [
        action_id
        for action_id, action in _pending_actions.items()
        if action.expires_at <= current
    ]
    for action_id in expired_ids:
        _pending_actions.pop(action_id, None)

    if expired_ids:
        expired_set = set(expired_ids)
        for key, action_id in list(_awaiting_corrections.items()):
            if action_id in expired_set:
                _awaiting_corrections.pop(key, None)
    return len(expired_ids)


def registerPendingAction(
    *,
    user_id: str,
    chat_id: str,
    payload: Dict[str, Any],
    source_message_id: Optional[str] = None,
    confirmation_message_id: Optional[str] = None,
    ttl_seconds: int = DEFAULT_PENDING_TTL_SECONDS,
    metadata: Optional[Dict[str, Any]] = None,
) -> PendingAction:
    """Register a parsed action awaiting user confirmation."""
    cleanupExpiredPendingActions()
    now = time.time()
    action_id = uuid.uuid4().hex[:12]
    action = PendingAction(
        action_id=action_id,
        user_id=str(user_id),
        chat_id=str(chat_id),
        payload=dict(payload),
        created_at=now,
        expires_at=now + ttl_seconds,
        source_message_id=str(source_message_id) if source_message_id is not None else None,
        confirmation_message_id=str(confirmation_message_id) if confirmation_message_id is not None else None,
        metadata=dict(metadata or {}),
    )
    _pending_actions[action_id] = action
    return action


def getPendingAction(action_id: str) -> Optional[PendingAction]:
    """Return a pending action if it exists and has not expired."""
    cleanupExpiredPendingActions()
    return _pending_actions.get(str(action_id))


def updatePendingActionMessage(action_id: str, confirmation_message_id: str) -> None:
    """Associate a confirmation Telegram message with a pending action."""
    action = getPendingAction(action_id)
    if action:
        action.confirmation_message_id = str(confirmation_message_id)


def clearPendingAction(action_id: str) -> Optional[PendingAction]:
    """Remove a pending action and any correction wait for it."""
    action_id = str(action_id)
    action = _pending_actions.pop(action_id, None)
    for key, waiting_action_id in list(_awaiting_corrections.items()):
        if waiting_action_id == action_id:
            _awaiting_corrections.pop(key, None)
    return action


def markAwaitingCorrection(*, user_id: str, chat_id: str, action_id: str) -> None:
    """Mark that the next text message from user/chat edits this pending action."""
    cleanupExpiredPendingActions()
    _awaiting_corrections[(str(user_id), str(chat_id))] = str(action_id)


def popAwaitingCorrection(*, user_id: str, chat_id: str) -> Optional[PendingAction]:
    """Consume and return the pending action waiting for corrected text."""
    cleanupExpiredPendingActions()
    action_id = _awaiting_corrections.pop((str(user_id), str(chat_id)), None)
    if not action_id:
        return None
    return getPendingAction(action_id)


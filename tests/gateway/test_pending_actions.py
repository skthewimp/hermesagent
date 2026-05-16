from gateway.platforms import pending_actions as pa


def setup_function():
    pa._pending_actions.clear()
    pa._awaiting_corrections.clear()


def test_register_get_and_clear_pending_action():
    action = pa.registerPendingAction(
        user_id="u1",
        chat_id="c1",
        source_message_id="m1",
        payload={"parsed": {"type": "reminder"}},
    )

    assert pa.getPendingAction(action.action_id) == action
    assert action.user_id == "u1"
    assert action.chat_id == "c1"
    assert action.source_message_id == "m1"

    assert pa.clearPendingAction(action.action_id) == action
    assert pa.getPendingAction(action.action_id) is None


def test_awaiting_correction_is_scoped_to_user_and_chat():
    action = pa.registerPendingAction(
        user_id="u1",
        chat_id="c1",
        payload={"transcript": "old"},
    )

    pa.markAwaitingCorrection(user_id="u1", chat_id="c1", action_id=action.action_id)

    assert pa.popAwaitingCorrection(user_id="u2", chat_id="c1") is None
    assert pa.popAwaitingCorrection(user_id="u1", chat_id="c2") is None
    assert pa.popAwaitingCorrection(user_id="u1", chat_id="c1") == action
    assert pa.popAwaitingCorrection(user_id="u1", chat_id="c1") is None


def test_cleanup_expired_pending_actions_removes_correction_wait():
    action = pa.registerPendingAction(
        user_id="u1",
        chat_id="c1",
        payload={"transcript": "old"},
        ttl_seconds=1,
    )
    pa.markAwaitingCorrection(user_id="u1", chat_id="c1", action_id=action.action_id)

    assert pa.cleanupExpiredPendingActions(now=action.expires_at + 1) == 1
    assert pa.getPendingAction(action.action_id) is None
    assert pa.popAwaitingCorrection(user_id="u1", chat_id="c1") is None


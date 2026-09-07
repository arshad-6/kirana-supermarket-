import pytest
from domain.preferences import PreferenceService
from agent.agent import kirana_agent

@pytest.mark.asyncio
async def test_persistent_preferences_and_new_chat(test_session):
    # Set preference: "Always assume UPI unless I say cash"
    res = await PreferenceService.set_preference(test_session, "default_payment_mode", "UPI")
    assert res["success"] is True

    # Check preference
    val = await PreferenceService.get_preference(test_session, "default_payment_mode")
    assert val == "UPI"

    # Simulate /new chat via agent
    reply_data = await kirana_agent.process_message(test_session, "/new", session_id="test_sess_1")
    assert "Started a new conversation context" in reply_data["reply"]

    # Verify preference is STILL in database after /new
    val_after = await PreferenceService.get_preference(test_session, "default_payment_mode")
    assert val_after == "UPI"

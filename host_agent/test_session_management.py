import asyncio
import os
import unittest
import uuid
from google.adk.sessions import DatabaseSessionService, Session, State
from google.adk.events.event import Event
from google.adk.events.event_actions import EventActions

APP_NAME = "test_app"
USER_ID = "test_user"
SESSION_ID = "test_session"


class TestSessionManagement(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db_path = "test_session_management.db"
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        self.session_service = DatabaseSessionService(
            db_url=f"sqlite:///{self.db_path}"
        )



    async def test_create_and_get_session(self):
        """Tests that a session can be created and retrieved."""
        await self.session_service.create_session(
            app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID
        )

        retrieved_session = await self.session_service.get_session(
            app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID
        )

        self.assertIsNotNone(retrieved_session)
        self.assertEqual(retrieved_session.app_name, APP_NAME)
        self.assertEqual(retrieved_session.user_id, USER_ID)
        self.assertEqual(retrieved_session.id, SESSION_ID)

    async def test_update_session_state_via_append_event(self):
        """Tests that session state can be updated via append_event."""
        # 1. Create the initial session
        await self.session_service.create_session(
            app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID
        )

        # 2. Retrieve it to get a valid session object
        session = await self.session_service.get_session(
            app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID
        )
        self.assertNotIn("tenant_id", session.state)

        # 3. Create an event with a state delta to add the tenant_id
        event1 = Event(
            id=str(uuid.uuid4()),
            invocation_id=str(uuid.uuid4()),
            author="user",
            actions=EventActions(state_delta={"tenant_id": "tenant-abc"}),
        )
        await self.session_service.append_event(session, event1)

        # 4. Retrieve and verify the updated state
        retrieved_session_1 = await self.session_service.get_session(
            app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID
        )
        self.assertEqual(
            retrieved_session_1.state.get("tenant_id"), "tenant-abc"
        )

        # 5. Create a second event to add an access_token
        event2 = Event(
            id=str(uuid.uuid4()),
            invocation_id=str(uuid.uuid4()),
            author="user",
            actions=EventActions(state_delta={"access_token": "xyz123"}),
        )
        await self.session_service.append_event(retrieved_session_1, event2)

        # 6. Retrieve and verify the final state
        retrieved_session_2 = await self.session_service.get_session(
            app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID
        )
        self.assertEqual(
            retrieved_session_2.state.get("tenant_id"), "tenant-abc"
        )
        self.assertEqual(
            retrieved_session_2.state.get("access_token"), "xyz123"
        )

    async def test_get_nonexistent_session(self):
        """Tests that getting a non-existent session returns None."""
        retrieved_session = await self.session_service.get_session(
            app_name=APP_NAME, user_id=USER_ID, session_id="nonexistent"
        )
        self.assertIsNone(retrieved_session)


if __name__ == "__main__":
    unittest.main()
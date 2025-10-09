import asyncio
import unittest
import os
import uuid
from a2a.types import Message, Part, Task, TaskState, TaskStatus
from host_agent.persistent_task_store import PersistentTaskStore

class TestPersistentTaskStore(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db_path = "test_host_agent.db"
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        self.task_store = PersistentTaskStore(db_path=self.db_path)



    async def test_create_and_get_task(self):
        task_id = "test_task_1"
        context_id = str(uuid.uuid4())
        request = Message(messageId=str(uuid.uuid4()), role="user", parts=[Part(type="text", text="test request")])
        task = Task(id=task_id, contextId=context_id, request=request, status=TaskStatus(state=TaskState.submitted))
        await self.task_store.save(task)
        retrieved_task = await self.task_store.get(task_id)
        self.assertIsNotNone(retrieved_task)
        self.assertEqual(retrieved_task.id, task_id)
        self.assertEqual(retrieved_task.status.state, TaskState.submitted)

    async def test_update_task(self):
        task_id = "test_task_2"
        context_id = str(uuid.uuid4())
        request = Message(messageId=str(uuid.uuid4()), role="user", parts=[Part(type="text", text="test request")])
        task = Task(id=task_id, contextId=context_id, request=request, status=TaskStatus(state=TaskState.submitted))
        await self.task_store.save(task)
        task.status.state = TaskState.working
        await self.task_store.save(task)
        retrieved_task = await self.task_store.get(task_id)
        self.assertEqual(retrieved_task.status.state, TaskState.working)

    async def test_task_done(self):
        task_id = "test_task_3"
        context_id = str(uuid.uuid4())
        request = Message(messageId=str(uuid.uuid4()), role="user", parts=[Part(type="text", text="test request")])
        task = Task(id=task_id, contextId=context_id, request=request, status=TaskStatus(state=TaskState.submitted))
        await self.task_store.save(task)
        response = Message(messageId=str(uuid.uuid4()), role="agent", parts=[Part(type="text", text="test response")])
        await self.task_store.task_done(task_id, response)
        retrieved_task = await self.task_store.get(task_id)
        self.assertEqual(retrieved_task.status.state, TaskState.completed)

    async def test_task_failed(self):
        task_id = "test_task_4"
        context_id = str(uuid.uuid4())
        request = Message(messageId=str(uuid.uuid4()), role="user", parts=[Part(type="text", text="test request")])
        task = Task(id=task_id, contextId=context_id, request=request, status=TaskStatus(state=TaskState.submitted))
        await self.task_store.save(task)
        error = Message(messageId=str(uuid.uuid4()), role="agent", parts=[Part(type="text", text="test error")])
        await self.task_store.task_failed(task_id, error)
        retrieved_task = await self.task_store.get(task_id)
        self.assertEqual(retrieved_task.status.state, TaskState.failed)

if __name__ == "__main__":
    unittest.main()

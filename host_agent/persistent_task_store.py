# Copyright 2024 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS-IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
A persistent, SQLite-backed implementation of the A2A TaskStore.

This module provides a concrete TaskStore that saves A2A Task objects to a
local SQLite database, ensuring that the state of delegated tasks is preserved
across server restarts and asynchronous operations like user authentication.
"""

import json
import logging
import sqlite3
import uuid
from typing import List, Optional

from a2a.server.tasks.task_store import TaskStore
from a2a.types import Artifact, Message, Part, Task, TaskState, TaskStatus

logging.basicConfig(level=logging.INFO)


class PersistentTaskStore(TaskStore):
    """
    Manages the lifecycle of tasks by persisting them to a SQLite database.

    This implementation handles the storage, retrieval, and state management of
    A2A Task objects, including the crucial linking of a local `host_agent` task
    to the corresponding `remote_task_id` from a downstream agent.
    """

    def __init__(self, db_path: str):
        """
        Initializes the task store and creates the necessary database table.

        Args:
            db_path: The file path for the SQLite database (e.g., "host_agent.db").
        """
        self.db_path = db_path
        self._create_table()

    def _get_connection(self) -> sqlite3.Connection:
        """Establishes a connection to the SQLite database."""
        return sqlite3.connect(self.db_path)

    def _create_table(self) -> None:
        """
        Creates the 'tasks' table if it doesn't already exist and ensures the
        schema is up to date.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # The core table stores the task's primary ID and its full data as JSON.
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    task_data TEXT NOT NULL,
                    remote_task_id TEXT
                )
            """)
            # For backward compatibility, add the remote_task_id column if it
            # doesn't exist. This prevents errors if running against an older DB.
            try:
                cursor.execute("ALTER TABLE tasks ADD COLUMN remote_task_id TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists, which is fine.
            conn.commit()

    async def save(self, task: Task) -> None:
        """
        Saves or updates a task in the database (an "upsert" operation).

        If a task with the same ID already exists, its `task_data` is updated.
        If it's a new task, a new record is inserted. This method is critical
        for reflecting changes to a task's status or artifacts.

        Args:
            task: The Task object to save.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Check if the task already exists to decide between INSERT and UPDATE.
            cursor.execute("SELECT id FROM tasks WHERE id = ?", (task.id,))
            exists = cursor.fetchone()

            if exists:
                # Update the existing task's data.
                cursor.execute(
                    "UPDATE tasks SET task_data = ? WHERE id = ?",
                    (task.model_dump_json(), task.id),
                )
            else:
                # Insert a new task record.
                cursor.execute(
                    "INSERT INTO tasks (id, task_data) VALUES (?, ?)",
                    (task.id, task.model_dump_json()),
                )
            conn.commit()
        logging.info(f"Task {task.id} saved.")

    async def get(self, task_id: str) -> Optional[Task]:
        """
        Retrieves a task from the database by its primary ID.

        Args:
            task_id: The unique ID of the local task.

        Returns:
            The deserialized Task object if found, otherwise None.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT task_data FROM tasks WHERE id = ?", (task_id,))
            row = cursor.fetchone()
            if row:
                return Task.model_validate_json(row[0])
            return None

    async def get_by_remote_task_id(self, remote_task_id: str) -> Optional[Task]:
        """
        Retrieves a local task by searching for its linked remote_task_id.

        This is essential for the `/callback` endpoint to find the original
        local task after an asynchronous operation (like OAuth) has completed.

        Args:
            remote_task_id: The unique ID of the task on the downstream agent.

        Returns:
            The corresponding local Task object if a link exists, otherwise None.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT task_data FROM tasks WHERE remote_task_id = ?", (remote_task_id,))
            row = cursor.fetchone()
            if row:
                return Task.model_validate_json(row[0])
            return None

    async def set_remote_task_id(self, task_id: str, remote_task_id: str) -> None:
        """
        Links a local task to its remote counterpart by storing the remote task ID.

        This is a critical step in the A2A task delegation lifecycle.

        Args:
            task_id: The ID of the local task to update.
            remote_task_id: The ID of the task created by the downstream agent.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE tasks SET remote_task_id = ? WHERE id = ?",
                (remote_task_id, task_id),
            )
            conn.commit()
        logging.info(f"Set remote_task_id {remote_task_id} for task {task_id}.")

    async def delete(self, task_id: str) -> None:
        """
        Deletes a task from the database by its ID.

        Args:
            task_id: The ID of the task to delete.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            conn.commit()
        logging.info(f"Task {task_id} deleted.")

    async def get_all_tasks(self) -> List[Task]:
        """
        Retrieves all tasks currently stored in the database.

        Returns:
            A list of all Task objects.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT task_data FROM tasks")
            rows = cursor.fetchall()
            return [Task.model_validate_json(row[0]) for row in rows]

    async def task_done(self, task_id: str, response: Message) -> None:
        """
        Marks a task as completed and saves the final response as an artifact.

        Args:
            task_id: The ID of the task to mark as done.
            response: The final Message object from the agent.
        """
        task = await self.get(task_id)
        if task:
            task.artifacts = [Artifact(artifact_id=str(uuid.uuid4()), parts=[Part(type="text", text=json.dumps(response.model_dump()))])]
            task.status.state = TaskState.completed
            await self.save(task)
            logging.info(f"Task {task_id} marked as done.")

    async def task_failed(self, task_id: str, error: Message) -> None:
        """
        Marks a task as failed and saves the error message as an artifact.

        Args:
            task_id: The ID of the task to mark as failed.
            error: The error Message object from the agent.
        """
        task = await self.get(task_id)
        if task:
            task.artifacts = [Artifact(artifact_id=str(uuid.uuid4()), parts=[Part(type="text", text=json.dumps(error.model_dump()))])]
            task.status.state = TaskState.failed
            await self.save(task)
            logging.info(f"Task {task_id} marked as failed.")

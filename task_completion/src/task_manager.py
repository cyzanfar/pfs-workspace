import json
import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum


class TaskStatus(Enum):
    AVAILABLE = "available"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SUBMITTED = "submitted"


@dataclass
class Task:
    task_id: str
    description: str
    reward: float
    deadline: datetime.datetime
    status: TaskStatus
    priority: int = 0

    def to_dict(self) -> Dict:
        return {
            "task_id": self.task_id,
            "description": self.description,
            "reward": self.reward,
            "deadline": self.deadline.isoformat(),
            "status": self.status.value,
            "priority": self.priority
        }


class TaskManager:
    def __init__(self):
        self.tasks: Dict[str, Task] = {}
        self.completed_tasks: List[str] = []

    def add_task(self, task: Task) -> bool:
        if task.task_id in self.tasks:
            return False
        self.tasks[task.task_id] = task
        return True

    def get_task(self, task_id: str) -> Optional[Task]:
        return self.tasks.get(task_id)

    def list_available_tasks(self) -> List[Task]:
        return [task for task in self.tasks.values()
                if task.status == TaskStatus.AVAILABLE]

    def start_task(self, task_id: str) -> bool:
        task = self.tasks.get(task_id)
        if not task or task.status != TaskStatus.AVAILABLE:
            return False
        task.status = TaskStatus.IN_PROGRESS
        return True

    def complete_task(self, task_id: str) -> bool:
        task = self.tasks.get(task_id)
        if not task or task.status != TaskStatus.IN_PROGRESS:
            return False
        task.status = TaskStatus.COMPLETED
        self.completed_tasks.append(task_id)
        return True

    def submit_task(self, task_id: str) -> bool:
        task = self.tasks.get(task_id)
        if not task or task.status != TaskStatus.COMPLETED:
            return False
        task.status = TaskStatus.SUBMITTED
        return True

    def calculate_earnings(self) -> float:
        return sum(self.tasks[task_id].reward
                   for task_id in self.completed_tasks)


class TaskAnalyzer:
    def __init__(self, manager: TaskManager):
        self.manager = manager

    def prioritize_tasks(self) -> List[Task]:
        available_tasks = self.manager.list_available_tasks()

        for task in available_tasks:
            # Calculate priority based on reward and deadline
            time_until_deadline = (task.deadline - datetime.datetime.now())
            hours_left = time_until_deadline.total_seconds() / 3600

            if hours_left <= 0:
                task.priority = 0
            else:
                # Higher reward and shorter deadline = higher priority
                task.priority = int((task.reward / hours_left) * 100)

        return sorted(available_tasks,
                      key=lambda x: x.priority,
                      reverse=True)


def save_tasks(manager: TaskManager, filename: str):
    with open(filename, 'w') as f:
        tasks_dict = {task_id: task.to_dict()
                      for task_id, task in manager.tasks.items()}
        json.dump(tasks_dict, f, indent=2)


def load_tasks(filename: str) -> TaskManager:
    manager = TaskManager()
    try:
        with open(filename, 'r') as f:
            tasks_dict = json.load(f)
            for task_data in tasks_dict.values():
                task = Task(
                    task_id=task_data["task_id"],
                    description=task_data["description"],
                    reward=task_data["reward"],
                    deadline=datetime.datetime.fromisoformat(task_data["deadline"]),
                    status=TaskStatus(task_data["status"]),
                    priority=task_data["priority"]
                )
                manager.add_task(task)
    except FileNotFoundError:
        pass
    return manager
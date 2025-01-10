# tests/test_core.py
import pytest
import datetime
from src.task_manager import TaskManager, Task, TaskStatus, TaskAnalyzer


@pytest.fixture
def task_manager():
    return TaskManager()


@pytest.fixture
def test_task():
    return Task(
        task_id="TEST001",
        description="Test Task",
        reward=100.0,
        deadline=datetime.datetime.now() + datetime.timedelta(hours=24),
        status=TaskStatus.AVAILABLE
    )


class TestTaskCore:
    """Core functionality tests for task management system"""

    def test_task_creation(self, task_manager, test_task):
        """Test 1: Task Creation and Retrieval"""
        # Add task
        assert task_manager.add_task(test_task) == True

        # Verify retrieval
        stored_task = task_manager.get_task(test_task.task_id)
        assert stored_task is not None
        assert stored_task.task_id == test_task.task_id
        assert stored_task.reward == test_task.reward

        # Test duplicate prevention
        assert task_manager.add_task(test_task) == False

    def test_task_workflow(self, task_manager, test_task):
        """Test 2: Task Workflow States"""
        task_manager.add_task(test_task)

        # Test state transitions
        assert task_manager.start_task(test_task.task_id) == True
        assert task_manager.get_task(test_task.task_id).status == TaskStatus.IN_PROGRESS

        assert task_manager.complete_task(test_task.task_id) == True
        assert task_manager.get_task(test_task.task_id).status == TaskStatus.COMPLETED

        assert task_manager.submit_task(test_task.task_id) == True
        assert task_manager.get_task(test_task.task_id).status == TaskStatus.SUBMITTED

    def test_earnings_calculation(self, task_manager):
        """Test 3: Earnings Calculation"""
        tasks = [
            Task("EARN001", "Task 1", 100.0,
                 datetime.datetime.now() + datetime.timedelta(hours=24),
                 TaskStatus.AVAILABLE),
            Task("EARN002", "Task 2", 150.0,
                 datetime.datetime.now() + datetime.timedelta(hours=24),
                 TaskStatus.AVAILABLE)
        ]

        # Add and complete tasks
        for task in tasks:
            task_manager.add_task(task)
            task_manager.start_task(task.task_id)
            task_manager.complete_task(task.task_id)

        assert task_manager.calculate_earnings() == 250.0

    def test_edge_cases(self, task_manager):
        """Test 4: Edge Cases"""
        # Test expired task
        expired_task = Task(
            "EXPIRED",
            "Expired Task",
            100.0,
            datetime.datetime.now() - datetime.timedelta(hours=1),
            TaskStatus.AVAILABLE
        )
        task_manager.add_task(expired_task)
        assert task_manager.start_task(expired_task.task_id) == False

        # Test invalid state transitions
        future_task = Task(
            "FUTURE",
            "Future Task",
            100.0,
            datetime.datetime.now() + datetime.timedelta(hours=24),
            TaskStatus.AVAILABLE
        )
        task_manager.add_task(future_task)

        # Cannot complete without starting
        assert task_manager.complete_task(future_task.task_id) == False

        # Cannot submit without completing
        task_manager.start_task(future_task.task_id)
        assert task_manager.submit_task(future_task.task_id) == False

    def test_error_handling(self, task_manager):
        """Test 5: Error Handling"""
        # Test non-existent task
        assert task_manager.start_task("NONEXISTENT") == False
        assert task_manager.complete_task("NONEXISTENT") == False
        assert task_manager.submit_task("NONEXISTENT") == False

        # Test invalid task creation
        with pytest.raises(ValueError):
            Task("", "Empty ID", 100.0,
                 datetime.datetime.now() + datetime.timedelta(hours=24),
                 TaskStatus.AVAILABLE)

        with pytest.raises(ValueError):
            Task("INVALID", "Negative Reward", -100.0,
                 datetime.datetime.now() + datetime.timedelta(hours=24),
                 TaskStatus.AVAILABLE)
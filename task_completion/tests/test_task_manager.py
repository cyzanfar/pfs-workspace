import pytest
import datetime
from task_manager import TaskManager, Task, TaskStatus, TaskAnalyzer


@pytest.fixture
def manager():
    return TaskManager()


@pytest.fixture
def analyzer(manager):
    return TaskAnalyzer(manager)


@pytest.fixture
def sample_task():
    return Task(
        task_id="TEST001",
        description="Test task",
        reward=100.0,
        deadline=datetime.datetime.now() + datetime.timedelta(hours=24),
        status=TaskStatus.AVAILABLE
    )


def test_add_task(manager, sample_task):
    assert manager.add_task(sample_task) == True
    assert manager.get_task(sample_task.task_id) == sample_task


def test_duplicate_task(manager, sample_task):
    manager.add_task(sample_task)
    assert manager.add_task(sample_task) == False


def test_list_available_tasks(manager, sample_task):
    manager.add_task(sample_task)
    available = manager.list_available_tasks()
    assert len(available) == 1
    assert available[0] == sample_task


def test_start_task(manager, sample_task):
    manager.add_task(sample_task)
    assert manager.start_task(sample_task.task_id) == True
    assert manager.get_task(sample_task.task_id).status == TaskStatus.IN_PROGRESS


def test_complete_task(manager, sample_task):
    manager.add_task(sample_task)
    manager.start_task(sample_task.task_id)
    assert manager.complete_task(sample_task.task_id) == True
    assert manager.get_task(sample_task.task_id).status == TaskStatus.COMPLETED


def test_submit_task(manager, sample_task):
    manager.add_task(sample_task)
    manager.start_task(sample_task.task_id)
    manager.complete_task(sample_task.task_id)
    assert manager.submit_task(sample_task.task_id) == True
    assert manager.get_task(sample_task.task_id).status == TaskStatus.SUBMITTED


def test_calculate_earnings(manager):
    task1 = Task(
        task_id="TEST001",
        description="Test task 1",
        reward=100.0,
        deadline=datetime.datetime.now() + datetime.timedelta(hours=24),
        status=TaskStatus.AVAILABLE
    )
    task2 = Task(
        task_id="TEST002",
        description="Test task 2",
        reward=150.0,
        deadline=datetime.datetime.now() + datetime.timedelta(hours=24),
        status=TaskStatus.AVAILABLE
    )

    manager.add_task(task1)
    manager.add_task(task2)

    manager.start_task(task1.task_id)
    manager.complete_task(task1.task_id)

    manager.start_task(task2.task_id)
    manager.complete_task(task2.task_id)

    assert manager.calculate_earnings() == 250.0


def test_task_prioritization(analyzer, manager):
    task1 = Task(
        task_id="TEST001",
        description="Low priority task",
        reward=100.0,
        deadline=datetime.datetime.now() + datetime.timedelta(hours=24),
        status=TaskStatus.AVAILABLE
    )
    task2 = Task(
        task_id="TEST002",
        description="High priority task",
        reward=150.0,
        deadline=datetime.datetime.now() + datetime.timedelta(hours=12),
        status=TaskStatus.AVAILABLE
    )

    manager.add_task(task1)
    manager.add_task(task2)

    prioritized = analyzer.prioritize_tasks()
    assert len(prioritized) == 2
    assert prioritized[0].task_id == "TEST002"  # Higher priority task should be first
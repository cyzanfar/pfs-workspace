from typing import Dict, List, Optional, Set, Callable
from datetime import datetime, timedelta
import threading
import time
import logging
import argparse
import queue
import heapq
from dataclasses import dataclass
from enum import Enum
import json


class JobStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Job:
    id: str
    func: Callable
    schedule: str  # Cron-like schedule
    dependencies: Set[str]
    status: JobStatus
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    retry_count: int = 0
    max_retries: int = 3
    timeout: int = 3600  # Default timeout of 1 hour


class Metrics:
    def __init__(self):
        self.successful_jobs = 0
        self.failed_jobs = 0
        self.total_execution_time = 0
        self.job_history: Dict[str, List[Dict]] = {}

    def record_execution(self, job_id: str, status: JobStatus, execution_time: float):
        if status == JobStatus.COMPLETED:
            self.successful_jobs += 1
        elif status == JobStatus.FAILED:
            self.failed_jobs += 1

        self.total_execution_time += execution_time

        if job_id not in self.job_history:
            self.job_history[job_id] = []

        self.job_history[job_id].append({
            'timestamp': datetime.now().isoformat(),
            'status': status.value,
            'execution_time': execution_time
        })


class TaskScheduler:
    def __init__(self):
        self.jobs: Dict[str, Job] = {}
        self.execution_queue = queue.PriorityQueue()
        self.running_jobs: Set[str] = set()
        self.metrics = Metrics()
        self.lock = threading.Lock()
        self.logger = logging.getLogger(__name__)

        # Start worker threads
        self.worker_thread = threading.Thread(target=self._worker_loop)
        self.scheduler_thread = threading.Thread(target=self._scheduler_loop)
        self.running = True

        self._setup_logging()

    def _setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s [%(levelname)s] %(message)s',
            handlers=[
                logging.FileHandler('scheduler.log'),
                logging.StreamHandler()
            ]
        )

    def add_job(self, job_id: str, func: Callable, schedule: str,
                dependencies: Optional[Set[str]] = None) -> None:
        """Add a new job to the scheduler."""
        with self.lock:
            if job_id in self.jobs:
                raise ValueError(f"Job {job_id} already exists")

            self.jobs[job_id] = Job(
                id=job_id,
                func=func,
                schedule=schedule,
                dependencies=dependencies or set(),
                status=JobStatus.PENDING
            )
            self.logger.info(f"Added job {job_id} with schedule {schedule}")

    def remove_job(self, job_id: str) -> None:
        """Remove a job from the scheduler."""
        with self.lock:
            if job_id not in self.jobs:
                raise ValueError(f"Job {job_id} does not exist")

            del self.jobs[job_id]
            self.logger.info(f"Removed job {job_id}")

    def _parse_schedule(self, schedule: str) -> datetime:
        """Parse cron-like schedule and return next run time."""
        # Simplified implementation - extend based on requirements
        if schedule == "@hourly":
            return datetime.now().replace(minute=0, second=0) + timedelta(hours=1)
        elif schedule == "@daily":
            return datetime.now().replace(hour=0, minute=0, second=0) + timedelta(days=1)
        # Add more schedule parsing logic as needed
        return datetime.now() + timedelta(minutes=5)  # Default fallback

    def _can_run_job(self, job: Job) -> bool:
        """Check if a job can run based on its dependencies."""
        return all(
            self.jobs[dep_id].status == JobStatus.COMPLETED
            for dep_id in job.dependencies
            if dep_id in self.jobs
        )

    def _worker_loop(self):
        """Main worker loop for executing jobs."""
        while self.running:
            try:
                priority, job_id = self.execution_queue.get(timeout=1)
                job = self.jobs[job_id]

                if not self._can_run_job(job):
                    # Requeue if dependencies aren't met
                    self.execution_queue.put((priority, job_id))
                    continue

                start_time = time.time()
                job.status = JobStatus.RUNNING

                try:
                    job.func()
                    job.status = JobStatus.COMPLETED
                    self.logger.info(f"Job {job_id} completed successfully")
                except Exception as e:
                    job.status = JobStatus.FAILED
                    job.retry_count += 1
                    self.logger.error(f"Job {job_id} failed: {str(e)}")

                    if job.retry_count < job.max_retries:
                        self.execution_queue.put((priority + 1, job_id))

                execution_time = time.time() - start_time
                self.metrics.record_execution(job_id, job.status, execution_time)

            except queue.Empty:
                continue
            except Exception as e:
                self.logger.error(f"Worker loop error: {str(e)}")

    def _scheduler_loop(self):
        """Main scheduler loop for queuing jobs."""
        while self.running:
            try:
                with self.lock:
                    now = datetime.now()
                    for job in self.jobs.values():
                        if job.next_run and job.next_run <= now:
                            if job.status != JobStatus.RUNNING:
                                self.execution_queue.put((now.timestamp(), job.id))
                                job.next_run = self._parse_schedule(job.schedule)

                time.sleep(1)
            except Exception as e:
                self.logger.error(f"Scheduler loop error: {str(e)}")

    def start(self):
        """Start the scheduler."""
        self.worker_thread.start()
        self.scheduler_thread.start()
        self.logger.info("TaskScheduler started")

    def stop(self):
        """Stop the scheduler."""
        self.running = False
        self.worker_thread.join()
        self.scheduler_thread.join()
        self.logger.info("TaskScheduler stopped")

    def get_job_status(self, job_id: str) -> Dict:
        """Get detailed status of a specific job."""
        if job_id not in self.jobs:
            raise ValueError(f"Job {job_id} does not exist")

        job = self.jobs[job_id]
        return {
            'id': job.id,
            'status': job.status.value,
            'last_run': job.last_run.isoformat() if job.last_run else None,
            'next_run': job.next_run.isoformat() if job.next_run else None,
            'retry_count': job.retry_count,
            'dependencies': list(job.dependencies)
        }

    def get_metrics(self) -> Dict:
        """Get scheduler metrics."""
        return {
            'successful_jobs': self.metrics.successful_jobs,
            'failed_jobs': self.metrics.failed_jobs,
            'total_execution_time': self.metrics.total_execution_time,
            'job_history': self.metrics.job_history
        }


def main():
    """CLI entry point for the TaskScheduler."""
    parser = argparse.ArgumentParser(description='Task Scheduler CLI')
    parser.add_argument('command', choices=['status', 'list', 'metrics'])
    parser.add_argument('--job-id', help='Job ID for status command')
    args = parser.parse_args()

    scheduler = TaskScheduler()

    if args.command == 'status' and args.job_id:
        print(json.dumps(scheduler.get_job_status(args.job_id), indent=2))
    elif args.command == 'list':
        print(json.dumps({job_id: job.status.value for job_id, job in scheduler.jobs.items()}, indent=2))
    elif args.command == 'metrics':
        print(json.dumps(scheduler.get_metrics(), indent=2))


if __name__ == '__main__':
    main()
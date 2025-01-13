import unittest
from unittest.mock import Mock, patch


class TestTaskScheduler(unittest.TestCase):
    def setUp(self):
        self.scheduler = TaskScheduler()

    def tearDown(self):
        self.scheduler.stop()

    def test_add_job(self):
        mock_func = Mock()
        self.scheduler.add_job("test_job", mock_func, "@hourly")
        self.assertIn("test_job", self.scheduler.jobs)

    def test_job_dependencies(self):
        mock_func1 = Mock()
        mock_func2 = Mock()

        self.scheduler.add_job("job1", mock_func1, "@hourly")
        self.scheduler.add_job("job2", mock_func2, "@hourly", dependencies={"job1"})

        job2 = self.scheduler.jobs["job2"]
        self.assertFalse(self.scheduler._can_run_job(job2))

        self.scheduler.jobs["job1"].status = JobStatus.COMPLETED
        self.assertTrue(self.scheduler._can_run_job(job2))

    def test_job_execution(self):
        mock_func = Mock()
        self.scheduler.add_job("test_job", mock_func, "@hourly")

        # Simulate job execution
        self.scheduler.start()
        time.sleep(2)  # Allow time for execution

        mock_func.assert_called()
        self.assertEqual(self.scheduler.jobs["test_job"].status, JobStatus.COMPLETED)

    def test_job_retry(self):
        mock_func = Mock(side_effect=Exception("Test error"))
        self.scheduler.add_job("failing_job", mock_func, "@hourly")

        # Simulate job execution
        self.scheduler.start()
        time.sleep(2)  # Allow time for execution

        self.assertEqual(self.scheduler.jobs["failing_job"].status, JobStatus.FAILED)
        self.assertTrue(self.scheduler.jobs["failing_job"].retry_count > 0)


if __name__ == '__main__':
    unittest.main()
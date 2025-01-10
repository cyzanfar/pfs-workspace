import unittest
import os
import tempfile
import json
from datetime import datetime, timedelta

from system_health_check import SystemHealthCheck


class TestSystemHealthCheck(unittest.TestCase):
    """
    Comprehensive test suite for the SystemHealthCheck class.
    """

    def setUp(self):
        """
        Set up test environment before each test.
        """
        # Create a temporary directory for test data
        self.test_dir = tempfile.mkdtemp()

        # Create health check instance with temp directory
        self.health_check = SystemHealthCheck(
            config_path=os.path.join(self.test_dir, 'test_config.json'),
            log_dir=os.path.join(self.test_dir, 'health_logs')
        )

    def tearDown(self):
        """
        Clean up test environment after each test.
        """
        # Remove temporary directory and its contents
        for root, dirs, files in os.walk(self.test_dir, topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))
        os.rmdir(self.test_dir)

    def test_component_registration(self):
        """
        Test registering system components.
        """

        def mock_health_check():
            return {
                'status': 'operational',
                'health_score': 100.0,
                'details': 'Mock component health'
            }

        # Register components with dependencies
        self.health_check.register_component(
            'database',
            health_check_callback=mock_health_check
        )
        self.health_check.register_component(
            'web_service',
            dependencies=['database'],
            health_check_callback=mock_health_check
        )

        # Verify components are registered
        self.assertIn('database', self.health_check.components)
        self.assertIn('web_service', self.health_check.components)

        # Check dependencies
        web_service_component = self.health_check.components['web_service']
        self.assertEqual(web_service_component.dependencies, ['database'])

    def test_quick_health_check(self):
        """
        Test quick health check functionality.
        """
        # Perform quick health check
        health_report = self.health_check.perform_health_check(depth='quick')

        # Validate basic report structure
        self.assertIn('timestamp', health_report)
        self.assertIn('resources', health_report)

        # Check resource sections
        resources = health_report['resources']
        self.assertIn('cpu', resources)
        self.assertIn('memory', resources)
        self.assertIn('disk', resources)
        self.assertIn('network', resources)

        # Validate resource health metrics
        self.assertIn('usage_percent', resources['cpu'])
        self.assertIn('used_percent', resources['memory'])
        self.assertIn('used_percent', resources['disk'])

    def test_full_health_check(self):
        """
        Test full health check with component registration.
        """

        # Register some mock components
        def mock_health_check_optimal():
            return {
                'status': 'optimal',
                'health_score': 100.0,
                'details': 'Fully operational'
            }

        def mock_health_check_degraded():
            return {
                'status': 'degraded',
                'health_score': 70.0,
                'details': 'Performance slightly impacted'
            }

        # Register components
        self.health_check.register_component(
            'cpu',
            health_check_callback=mock_health_check_optimal
        )
        self.health_check.register_component(
            'memory',
            health_check_callback=mock_health_check_degraded
        )

        # Perform full health check
        health_report = self.health_check.perform_health_check(depth='full')

        # Validate full report structure
        self.assertIn('components', health_report)

        # Check specific component healths
        components = health_report['components']
        self.assertIn('cpu', components)
        self.assertIn('memory', components)

        # Verify component status
        self.assertEqual(components['cpu']['status'], 'optimal')
        self.assertEqual(components['memory']['status'], 'degraded')

    def test_failure_prediction(self):
        """
        Test potential failure prediction mechanism.
        """

        # Register a component
        def mock_fluctuating_health():
            return {
                'status': 'degraded',
                'health_score': 65.0,
                'details': 'Intermittent performance issues'
            }

        self.health_check.register_component(
            'network',
            health_check_callback=mock_fluctuating_health
        )

        # Simulate multiple health checks to generate prediction data
        for _ in range(5):
            self.health_check.perform_health_check(depth='full')

        # Run failure prediction
        predictions = self.health_check.predict_potential_failures()

        # Validate prediction structure
        self.assertIn('timestamp', predictions)
        self.assertIn('potential_failures', predictions)

        # Check network component prediction
        network_prediction = predictions['potential_failures'].get('network')
        self.assertIsNotNone(network_prediction)
        self.assertIn('trend', network_prediction)
        self.assertIn('avg_health_score', network_prediction)

    def test_log_generation(self):
        """
        Test health check log generation.
        """
        # Perform health check
        self.health_check.perform_health_check(depth='full')

        # Check log directory
        log_files = os.listdir(self.health_check.log_dir)
        self.assertTrue(len(log_files) > 0)

        # Verify log file content
        log_file_path = os.path.join(
            self.health_check.log_dir,
            log_files[0]
        )

        with open(log_file_path, 'r') as f:
            log_content = json.load(f)

        # Validate log structure
        self.assertIn('timestamp', log_content)
        self.assertIn('resources', log_content)


def main():
    """
    Run the test suite.
    """
    unittest.main()


if __name__ == '__main__':
    main()
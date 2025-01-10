import unittest
import os
import tempfile
import json
from datetime import datetime, timedelta

from monitoring_dashboard import MonitoringDashboard


class TestMonitoringDashboard(unittest.TestCase):
    """
    Comprehensive test suite for the MonitoringDashboard system.
    """

    def setUp(self):
        """
        Set up test environment before each test.
        """
        # Create a temporary directory for test data
        self.test_dir = tempfile.mkdtemp()

        # Create dashboard instance with temp directory
        self.dashboard = MonitoringDashboard(
            data_dir=self.test_dir,
            config_file='test_dashboard_config.json'
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
            return 'operational'

        # Register components with dependencies
        self.dashboard.register_component(
            'database',
            health_check_callback=mock_health_check
        )
        self.dashboard.register_component(
            'web_service',
            dependencies=['database'],
            health_check_callback=mock_health_check
        )

        # Verify component health retrieval
        db_health = self.dashboard.component_health.get_component_health('database')
        web_service_health = self.dashboard.component_health.get_component_health('web_service')

        self.assertEqual(db_health['name'], 'database')
        self.assertEqual(db_health['status'], 'operational')

        self.assertEqual(web_service_health['name'], 'web_service')
        self.assertEqual(web_service_health['dependencies'], ['database'])

    def test_alert_management(self):
        """
        Test alert recording and retrieval.
        """
        # Record some alerts
        self.dashboard.alert_manager.record_alert(
            'cpu_usage',
            'warning',
            'CPU usage exceeding 70%'
        )
        self.dashboard.alert_manager.record_alert(
            'memory_usage',
            'critical',
            'Memory usage exceeding 90%'
        )

        # Retrieve all alerts
        all_alerts = self.dashboard.alert_manager.get_alerts()
        self.assertEqual(len(all_alerts), 2)

        # Filter by severity
        warning_alerts = self.dashboard.alert_manager.get_alerts(severity='warning')
        self.assertEqual(len(warning_alerts), 1)
        self.assertEqual(warning_alerts[0]['metric_name'], 'cpu_usage')

        # Filter by start time
        recent_time = datetime.now() - timedelta(minutes=1)
        recent_alerts = self.dashboard.alert_manager.get_alerts(start_time=recent_time)
        self.assertEqual(len(recent_alerts), 2)

    def test_dashboard_report_generation(self):
        """
        Test generating a comprehensive dashboard report.
        """

        def mock_health_check_1():
            return 'operational'

        def mock_health_check_2():
            return 'degraded'

        # Register components
        self.dashboard.register_component(
            'component1',
            health_check_callback=mock_health_check_1
        )
        self.dashboard.register_component(
            'component2',
            dependencies=['component1'],
            health_check_callback=mock_health_check_2
        )

        # Record some alerts
        self.dashboard.alert_manager.record_alert(
            'test_metric',
            'warning',
            'Test warning alert'
        )

        # Generate report
        report = self.dashboard.generate_dashboard_report()

        # Validate report structure
        self.assertIn('timestamp', report)
        self.assertIn('components', report)
        self.assertIn('recent_alerts', report)

        # Check component statuses
        self.assertEqual(
            report['components']['component1']['status'],
            'operational'
        )
        self.assertEqual(
            report['components']['component2']['status'],
            'degraded'
        )

    def test_configuration_management(self):
        """
        Test dashboard configuration management.
        """
        # Verify default configuration
        self.assertIn('health_check_interval', self.dashboard._config)
        self.assertIn('metrics_retention_days', self.dashboard._config)

        # Update configuration
        updated_config = {
            'health_check_interval': 30,
            'metrics_retention_days': 60
        }

        # Update and save configuration
        self.dashboard._config.update(updated_config)
        self.dashboard.save_config()

        # Reload configuration
        reloaded_dashboard = MonitoringDashboard(
            data_dir=self.test_dir,
            config_file='test_dashboard_config.json'
        )

        # Verify configuration was saved and loaded correctly
        self.assertEqual(
            reloaded_dashboard._config['health_check_interval'],
            30
        )
        self.assertEqual(
            reloaded_dashboard._config['metrics_retention_days'],
            60
        )

    def test_dashboard_export(self):
        """
        Test exporting dashboard report to a file.
        """

        # Register a component and create an alert
        def mock_health_check():
            return 'operational'

        self.dashboard.register_component(
            'test_component',
            health_check_callback=mock_health_check
        )

        self.dashboard.alert_manager.record_alert(
            'test_metric',
            'warning',
            'Test export alert'
        )

        # Export report to a specific file
        export_path = os.path.join(self.test_dir, 'test_export_report.json')
        exported_file = self.dashboard.export_dashboard_report(export_path)

        # Verify file was created
        self.assertTrue(os.path.exists(exported_file))

        # Verify file contents
        with open(exported_file, 'r') as f:
            exported_data = json.load(f)

        # Validate exported data structure
        self.assertIn('timestamp', exported_data)
        self.assertIn('components', exported_data)
        self.assertIn('recent_alerts', exported_data)


def main():
    """
    Run the test suite.
    """
    unittest.main()


if __name__ == '__main__':
    main()
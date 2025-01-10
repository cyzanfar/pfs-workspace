# tests/test_cli.py
import pytest
from click.testing import CliRunner
from src.cli import cli


@pytest.fixture
def runner():
    return CliRunner()


class TestCLI:
    """Integration tests for CLI interface"""

    def test_add_task_command(self, runner):
        """Test adding tasks via CLI"""
        with runner.isolated_filesystem():
            result = runner.invoke(cli, [
                'add',
                '--id', 'CLI001',
                '--description', 'CLI Test Task',
                '--reward', '100',
                '--hours', '24'
            ])
            assert result.exit_code == 0
            assert 'Added task CLI001' in result.output

    def test_task_workflow_commands(self, runner):
        """Test complete task workflow through CLI"""
        with runner.isolated_filesystem():
            # Add task
            runner.invoke(cli, [
                'add',
                '--id', 'FLOW001',
                '--description', 'Flow Test',
                '--reward', '100',
                '--hours', '24'
            ])

            # Start task
            result = runner.invoke(cli, ['start', '--id', 'FLOW001'])
            assert result.exit_code == 0
            assert 'Started task FLOW001' in result.output

            # Complete task
            result = runner.invoke(cli, ['complete', '--id', 'FLOW001'])
            assert result.exit_code == 0
            assert 'Completed task FLOW001' in result.output

            # Submit task
            result = runner.invoke(cli, ['submit', '--id', 'FLOW001'])
            assert result.exit_code == 0
            assert 'Submitted task FLOW001' in result.output

            # Check earnings
            result = runner.invoke(cli, ['earnings'])
            assert result.exit_code == 0
            assert '100 PFT' in result.output

    def test_list_command(self, runner):
        """Test task listing functionality"""
        with runner.isolated_filesystem():
            # Add tasks
            for i in range(3):
                runner.invoke(cli, [
                    'add',
                    '--id', f'LIST00{i}',
                    '--description', f'List Test {i}',
                    '--reward', '100',
                    '--hours', '24'
                ])

            result = runner.invoke(cli, ['list'])
            assert result.exit_code == 0
            assert 'LIST000' in result.output
            assert 'LIST001' in result.output
            assert 'LIST002' in result.output

    def test_cli_error_handling(self, runner):
        """Test CLI error handling"""
        with runner.isolated_filesystem():
            # Test invalid commands
            result = runner.invoke(cli, ['start', '--id', 'NONEXISTENT'])
            assert result.exit_code != 0
            assert 'Could not start task' in result.output

            # Test invalid parameters
            result = runner.invoke(cli, [
                'add',
                '--id', 'INVALID',
                '--description', 'Invalid Test',
                '--reward', '-100',
                '--hours', '24'
            ])
            assert result.exit_code != 0
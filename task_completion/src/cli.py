import click
import datetime
from task_manager import TaskManager, Task, TaskStatus, TaskAnalyzer, save_tasks, load_tasks


@click.group()
@click.pass_context
def cli(ctx):
    """Task Completion System CLI"""
    ctx.ensure_object(dict)
    ctx.obj['manager'] = load_tasks('tasks.json')
    ctx.obj['analyzer'] = TaskAnalyzer(ctx.obj['manager'])


@cli.command()
@click.option('--id', required=True, help='Task ID')
@click.option('--description', required=True, help='Task description')
@click.option('--reward', required=True, type=float, help='Task reward in PFT')
@click.option('--hours', required=True, type=int, help='Hours until deadline')
@click.pass_context
def add(ctx, id, description, reward, hours):
    """Add a new task"""
    deadline = datetime.datetime.now() + datetime.timedelta(hours=hours)
    task = Task(id, description, reward, deadline, TaskStatus.AVAILABLE)
    manager = ctx.obj['manager']

    if manager.add_task(task):
        click.echo(f"Added task {id}")
        save_tasks(manager, 'tasks.json')
    else:
        click.echo(f"Task {id} already exists")


@cli.command()
@click.pass_context
def list(ctx):
    """List available tasks"""
    analyzer = ctx.obj['analyzer']
    tasks = analyzer.prioritize_tasks()

    if not tasks:
        click.echo("No available tasks")
        return

    click.echo("\nAvailable Tasks:")
    click.echo("-" * 80)
    for task in tasks:
        click.echo(
            f"ID: {task.task_id} | "
            f"Priority: {task.priority} | "
            f"Reward: {task.reward} PFT | "
            f"Deadline: {task.deadline.strftime('%Y-%m-%d %H:%M')}"
        )
        click.echo(f"Description: {task.description}")
        click.echo("-" * 80)


@cli.command()
@click.option('--id', required=True, help='Task ID')
@click.pass_context
def start(ctx, id):
    """Start working on a task"""
    manager = ctx.obj['manager']
    if manager.start_task(id):
        click.echo(f"Started task {id}")
        save_tasks(manager, 'tasks.json')
    else:
        click.echo(f"Could not start task {id}")


@cli.command()
@click.option('--id', required=True, help='Task ID')
@click.pass_context
def complete(ctx, id):
    """Mark a task as completed"""
    manager = ctx.obj['manager']
    if manager.complete_task(id):
        click.echo(f"Completed task {id}")
        save_tasks(manager, 'tasks.json')
    else:
        click.echo(f"Could not complete task {id}")


@cli.command()
@click.option('--id', required=True, help='Task ID')
@click.pass_context
def submit(ctx, id):
    """Submit a completed task"""
    manager = ctx.obj['manager']
    if manager.submit_task(id):
        click.echo(f"Submitted task {id}")
        save_tasks(manager, 'tasks.json')
    else:
        click.echo(f"Could not submit task {id}")


@cli.command()
@click.pass_context
def earnings(ctx):
    """Show total earnings"""
    manager = ctx.obj['manager']
    total = manager.calculate_earnings()
    click.echo(f"Total earnings: {total} PFT")


if __name__ == '__main__':
    cli(obj={})
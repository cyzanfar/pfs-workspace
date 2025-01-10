# Task Completion System Prototype

A functional prototype of the task monitoring and completion system for the Post Fiat System platform.

## Features

- Task management with priority-based scheduling
- Automated task analysis and prioritization
- Progress tracking and status management
- Earnings calculation
- CLI interface for system interaction
- Persistent storage of task data

## Installation

1. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install click pytest
```

## Directory Structure

```
task_completion/
├── src/
│   ├── __init__.py
│   ├── task_manager.py
│   └── cli.py
├── tests/
│   └── test_task_manager.py
├── README.md
└── requirements.txt
```

## Usage

### Running the CLI

```bash
python cli.py [COMMAND] [OPTIONS]
```

Available commands:

- `add`: Add a new task
- `list`: List available tasks
- `start`: Start working on a task
- `complete`: Mark a task as completed
- `submit`: Submit a completed task
- `earnings`: Show total earnings

### Example Usage

1. Add a new task:
```bash
python cli.py add --id "TASK001" --description "Create documentation" --reward 100 --hours 24
```

2. List available tasks:
```bash
python cli.py list
```

3. Start working on a task:
```bash
python cli.py start --id "TASK001"
```

4. Complete a task:
```bash
python cli.py complete --id "TASK001"
```

5. Submit a completed task:
```bash
python cli.py submit --id "TASK001"
```

6. Check earnings:
```bash
python cli.py earnings
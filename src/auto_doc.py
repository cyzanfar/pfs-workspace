import os
import re
import ast
import json
import argparse
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass
from pathlib import Path
import markdown
import logging


@dataclass
class DocItem:
    """Represents a documentation item with its metadata."""
    name: str
    docstring: str
    type: str  # class, function, method
    params: List[Dict[str, str]]
    returns: Optional[str]
    examples: List[str]
    filepath: str
    line_number: int


class AutoDocGenerator:
    """
    Automatically generates API documentation from code annotations across system components.

    Features:
    - Parses Python docstrings and type hints
    - Generates HTML and Markdown documentation
    - Maintains a searchable documentation index
    - Provides CLI interface for doc generation and verification
    - Validates documentation completeness
    """

    def __init__(self, src_dir: str, output_dir: str):
        """
        Initialize the AutoDocGenerator.

        Args:
            src_dir: Root directory containing source code
            output_dir: Directory where documentation will be generated
        """
        self.src_dir = Path(src_dir)
        self.output_dir = Path(output_dir)
        self.doc_items: List[DocItem] = []
        self.index: Dict[str, List[str]] = {}
        self.logger = self._setup_logger()

    def _setup_logger(self) -> logging.Logger:
        """Configure logging for the documentation generator."""
        logger = logging.getLogger("AutoDocGenerator")
        logger.setLevel(logging.INFO)

        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        return logger

    def parse_file(self, filepath: Path) -> List[DocItem]:
        """
        Parse a single Python file for documentation items.

        Args:
            filepath: Path to the Python file

        Returns:
            List of DocItem objects extracted from the file
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

            tree = ast.parse(content)
            items: List[DocItem] = []

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
                    doc_item = self._parse_node(node, filepath)
                    if doc_item:
                        items.append(doc_item)

            return items

        except Exception as e:
            self.logger.error(f"Error parsing file {filepath}: {str(e)}")
            return []

    def _parse_node(self, node: ast.AST, filepath: Path) -> Optional[DocItem]:
        """
        Parse an AST node to extract documentation.

        Args:
            node: AST node to parse
            filepath: Source file path

        Returns:
            DocItem if documentation was found, None otherwise
        """
        if not ast.get_docstring(node):
            return None

        docstring = ast.get_docstring(node)
        params = self._extract_params(docstring)
        returns = self._extract_returns(docstring)
        examples = self._extract_examples(docstring)

        return DocItem(
            name=node.name,
            docstring=docstring,
            type=node.__class__.__name__.lower().replace('def', ''),
            params=params,
            returns=returns,
            examples=examples,
            filepath=str(filepath),
            line_number=node.lineno
        )

    def _extract_params(self, docstring: str) -> List[Dict[str, str]]:
        """Extract parameter documentation from docstring."""
        params = []
        param_pattern = re.compile(r'Args:(.*?)(?:\n\n|$)', re.DOTALL)
        param_match = param_pattern.search(docstring)

        if param_match:
            param_section = param_match.group(1)
            param_lines = param_section.strip().split('\n')

            for line in param_lines:
                line = line.strip()
                if ':' in line:
                    name, desc = line.split(':', 1)
                    params.append({
                        'name': name.strip(),
                        'description': desc.strip()
                    })

        return params

    def _extract_returns(self, docstring: str) -> Optional[str]:
        """Extract return value documentation from docstring."""
        returns_pattern = re.compile(r'Returns:(.*?)(?:\n\n|$)', re.DOTALL)
        returns_match = returns_pattern.search(docstring)

        if returns_match:
            return returns_match.group(1).strip()
        return None

    def _extract_examples(self, docstring: str) -> List[str]:
        """Extract example code from docstring."""
        examples = []
        example_pattern = re.compile(r'Example:(.*?)(?:\n\n|$)', re.DOTALL)

        for match in example_pattern.finditer(docstring):
            examples.append(match.group(1).strip())

        return examples

    def generate_documentation(self) -> None:
        """Generate documentation for all Python files in the source directory."""
        self.logger.info(f"Generating documentation from {self.src_dir}")

        # Clear existing documentation items
        self.doc_items.clear()
        self.index.clear()

        # Create output directory if it doesn't exist
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Parse all Python files
        for filepath in self.src_dir.rglob('*.py'):
            items = self.parse_file(filepath)
            self.doc_items.extend(items)

        # Generate documentation files
        self._generate_markdown()
        self._generate_html()
        self._generate_index()

        self.logger.info(f"Documentation generated in {self.output_dir}")

    def _generate_markdown(self) -> None:
        """Generate Markdown documentation files."""
        md_dir = self.output_dir / 'markdown'
        md_dir.mkdir(exist_ok=True)

        # Group items by file
        items_by_file: Dict[str, List[DocItem]] = {}
        for item in self.doc_items:
            if item.filepath not in items_by_file:
                items_by_file[item.filepath] = []
            items_by_file[item.filepath].append(item)

        # Generate one markdown file per source file
        for filepath, items in items_by_file.items():
            rel_path = Path(filepath).relative_to(self.src_dir)
            output_file = md_dir / f"{rel_path.stem}.md"
            output_file.parent.mkdir(parents=True, exist_ok=True)

            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(f"# {rel_path.stem}\n\n")

                for item in items:
                    f.write(self._item_to_markdown(item))
                    f.write("\n---\n\n")

    def _item_to_markdown(self, item: DocItem) -> str:
        """Convert a DocItem to Markdown format."""
        lines = []
        lines.append(f"## {item.name}\n")
        lines.append(f"**Type:** {item.type}\n")
        lines.append(f"**Source:** {item.filepath}:{item.line_number}\n\n")
        lines.append(f"{item.docstring}\n\n")

        if item.params:
            lines.append("### Parameters\n")
            for param in item.params:
                lines.append(f"- `{param['name']}`: {param['description']}\n")
            lines.append("\n")

        if item.returns:
            lines.append(f"### Returns\n{item.returns}\n\n")

        if item.examples:
            lines.append("### Examples\n")
            for example in item.examples:
                lines.append(f"```python\n{example}\n```\n")

        return ''.join(lines)

    def _generate_html(self) -> None:
        """Generate HTML documentation from Markdown files."""
        html_dir = self.output_dir / 'html'
        html_dir.mkdir(exist_ok=True)

        md_dir = self.output_dir / 'markdown'
        for md_file in md_dir.rglob('*.md'):
            with open(md_file, 'r', encoding='utf-8') as f:
                md_content = f.read()

            html_content = markdown.markdown(
                md_content,
                extensions=['fenced_code', 'tables']
            )

            # Add basic styling
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <title>{md_file.stem}</title>
                <style>
                    body {{ font-family: sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }}
                    code {{ background: #f4f4f4; padding: 2px 5px; }}
                    pre {{ background: #f4f4f4; padding: 10px; }}
                </style>
            </head>
            <body>
                {html_content}
            </body>
            </html>
            """

            output_file = html_dir / f"{md_file.stem}.html"
            output_file.parent.mkdir(parents=True, exist_ok=True)

            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(html_content)

    def _generate_index(self) -> None:
        """Generate searchable documentation index."""
        # Build index
        for item in self.doc_items:
            # Index by name
            self._add_to_index('name', item.name, item.filepath)

            # Index by type
            self._add_to_index('type', item.type, item.filepath)

            # Index words from docstring
            words = set(re.findall(r'\w+', item.docstring.lower()))
            for word in words:
                self._add_to_index('keyword', word, item.filepath)

        # Save index
        index_file = self.output_dir / 'index.json'
        with open(index_file, 'w', encoding='utf-8') as f:
            json.dump(self.index, f, indent=2)

    def _add_to_index(self, index_type: str, key: str, filepath: str) -> None:
        """Add an item to the search index."""
        index_key = f"{index_type}:{key}"
        if index_key not in self.index:
            self.index[index_key] = []
        if filepath not in self.index[index_key]:
            self.index[index_key].append(filepath)

    def verify_documentation(self) -> Tuple[bool, List[str]]:
        """
        Verify documentation completeness and accuracy.

        Returns:
            Tuple of (success: bool, error_messages: List[str])
        """
        errors = []

        for filepath in self.src_dir.rglob('*.py'):
            tree = ast.parse(Path(filepath).read_text(encoding='utf-8'))

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
                    # Check if item has documentation
                    if not ast.get_docstring(node):
                        errors.append(
                            f"Missing documentation for {node.name} in {filepath}:{node.lineno}"
                        )
                        continue

                    # Find corresponding DocItem
                    doc_item = next(
                        (item for item in self.doc_items
                         if item.name == node.name and item.filepath == str(filepath)),
                        None
                    )

                    if not doc_item:
                        errors.append(
                            f"Documentation not generated for {node.name} in {filepath}:{node.lineno}"
                        )
                        continue

                    # Verify parameters match
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        func_params = {arg.arg for arg in node.args.args if arg.arg != 'self'}
                        doc_params = {param['name'] for param in doc_item.params}

                        missing_params = func_params - doc_params
                        if missing_params:
                            errors.append(
                                f"Missing parameter documentation for {', '.join(missing_params)} "
                                f"in {node.name} ({filepath}:{node.lineno})"
                            )

                        extra_params = doc_params - func_params
                        if extra_params:
                            errors.append(
                                f"Documented parameters {', '.join(extra_params)} not found "
                                f"in {node.name} ({filepath}:{node.lineno})"
                            )

        return len(errors) == 0, errors


def main():
    """CLI entry point for the documentation generator."""
    parser = argparse.ArgumentParser(description='Generate API documentation')
    parser.add_argument('src_dir', help='Source code directory')
    parser.add_argument('output_dir', help='Output directory for documentation')
    parser.add_argument(
        '--verify',
        action='store_true',
        help='Verify documentation completeness'
    )

    args = parser.parse_args()

    generator = AutoDocGenerator(args.src_dir, args.output_dir)
    generator.generate_documentation()

    if args.verify:
        success, errors = generator.verify_documentation()
        if not success:
            print("\nDocumentation verification failed:")
            for error in errors:
                print(f"- {error}")
            sys.exit(1)
        else:
            print("\nDocumentation verification successful!")


if __name__ == '__main__':
    main()
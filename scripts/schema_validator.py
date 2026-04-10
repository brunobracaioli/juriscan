#!/usr/bin/env python3
"""
schema_validator.py — Validates analysis outputs against the JSON schema.

Usage:
    python3 schema_validator.py --input analyzed.json
    python3 schema_validator.py --input analyzed.json --schema path/to/output_schema.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys

try:
    from jsonschema import Draft7Validator, ValidationError
except ImportError:
    Draft7Validator = None  # type: ignore[assignment, misc]
    ValidationError = None  # type: ignore[assignment, misc]


SCHEMA_PATH = os.path.join(
    os.path.dirname(__file__), '..', 'references', 'output_schema.json'
)


def load_schema(schema_path: str | None = None) -> dict:
    """Load the JSON schema."""
    path = schema_path or SCHEMA_PATH
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def validate_analysis(data: dict, schema: dict | None = None) -> tuple[bool, list[str]]:
    """Validate a full analysis JSON against the schema.

    Returns (is_valid, list_of_error_messages).
    """
    if Draft7Validator is None:
        return _validate_manual(data)

    if schema is None:
        schema = load_schema()

    validator = Draft7Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))

    if not errors:
        return True, []

    messages = []
    for err in errors:
        path = '.'.join(str(p) for p in err.absolute_path) or '(root)'
        messages.append(f"{path}: {err.message}")

    return False, messages


def validate_chunk(chunk: dict, schema: dict | None = None) -> tuple[bool, list[str]]:
    """Validate a single chunk against the chunk sub-schema."""
    if schema is None:
        schema = load_schema()

    chunk_schema = schema.get('properties', {}).get('chunks', {}).get('items', {})
    if not chunk_schema:
        return True, ['No chunk sub-schema found; skipping validation']

    if Draft7Validator is None:
        return _validate_chunk_manual(chunk)

    validator = Draft7Validator(chunk_schema)
    errors = sorted(validator.iter_errors(chunk), key=lambda e: list(e.path))

    if not errors:
        return True, []

    messages = []
    for err in errors:
        path = '.'.join(str(p) for p in err.absolute_path) or '(root)'
        messages.append(f"{path}: {err.message}")

    return False, messages


def _validate_manual(data: dict) -> tuple[bool, list[str]]:
    """Basic manual validation when jsonschema is not installed."""
    errors = []
    if 'chunks' not in data:
        errors.append("Missing required field: 'chunks'")
    elif not isinstance(data['chunks'], list):
        errors.append("'chunks' must be an array")
    else:
        for i, chunk in enumerate(data['chunks']):
            valid, chunk_errors = _validate_chunk_manual(chunk)
            for err in chunk_errors:
                errors.append(f"chunks[{i}].{err}")
    return len(errors) == 0, errors


def _validate_chunk_manual(chunk: dict) -> tuple[bool, list[str]]:
    """Basic manual validation for a single chunk."""
    errors = []
    if 'index' not in chunk:
        errors.append("Missing required field: 'index'")
    if 'label' not in chunk:
        errors.append("Missing required field: 'label'")
    return len(errors) == 0, errors


def main():
    parser = argparse.ArgumentParser(description='Validate analysis JSON against schema')
    parser.add_argument('--input', '-i', required=True, help='Path to analyzed.json')
    parser.add_argument('--schema', '-s', help='Path to schema (default: references/output_schema.json)')
    args = parser.parse_args()

    with open(args.input, 'r', encoding='utf-8') as f:
        data = json.load(f)

    schema = load_schema(args.schema) if args.schema else None
    valid, errors = validate_analysis(data, schema)

    if valid:
        print(f"OK: {args.input} is valid against schema")
        sys.exit(0)
    else:
        print(f"INVALID: {len(errors)} error(s) in {args.input}")
        for err in errors[:20]:
            print(f"  - {err}")
        if len(errors) > 20:
            print(f"  ... and {len(errors) - 20} more")
        sys.exit(1)


if __name__ == '__main__':
    main()

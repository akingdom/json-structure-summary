#!/usr/bin/env python3
"""
json-structure-summary.py - Infer and summarize the structure of a JSON file.

Can be used as a CLI tool or imported as a module.

CLI Usage:
    python json-structure-summary.py input.json [--schema | --summary] [--pretty]
    cat input.json | python json-structure-summary.py

Module Usage:
    from json_structure_summary import summarize_json_structure
    result = summarize_json_structure("path/to/file.json", output_format='summary', pretty=True)
    # or pass JSON string directly
    result = summarize_json_structure('{"key": "value"}', from_file=False)
"""

import sys
import json
import argparse
import re
from collections import defaultdict, Counter
from typing import Any, Dict, List, Union, Optional, Tuple, Literal

# ----------------------------------------------------------------------
# JSON repair (handles common malformations)
# ----------------------------------------------------------------------

def remove_json_comments(text: str) -> str:
    """Remove C-style comments (// and /* */) from JSON text."""
    # Remove multi-line comments
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
    # Remove single-line comments
    text = re.sub(r'//.*?$', '', text, flags=re.MULTILINE)
    return text

def remove_trailing_commas(text: str) -> str:
    """Remove trailing commas in objects and arrays."""
    # Object: remove comma before }
    text = re.sub(r',\s*}', '}', text)
    # Array: remove comma before ]
    text = re.sub(r',\s*]', ']', text)
    return text

def repair_json(text: str) -> str:
    """Apply a series of repairs to try to make invalid JSON valid."""
    # Remove BOM if present
    if text.startswith('\ufeff'):
        text = text[1:]
    # Remove comments
    text = remove_json_comments(text)
    # Remove trailing commas
    text = remove_trailing_commas(text)
    return text

def parse_json_safe(content: str) -> Any:
    """Attempt to parse JSON, first with strict, then with repairs."""
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # Try with strict=False (allows control characters)
        try:
            return json.loads(content, strict=False)
        except json.JSONDecodeError:
            # Repair and retry
            repaired = repair_json(content)
            try:
                return json.loads(repaired)
            except json.JSONDecodeError as e:
                # Re-raise with original content for better error context
                raise json.JSONDecodeError(
                    f"Unable to parse JSON even after repair: {e.msg}",
                    content,
                    e.pos
                )

# ----------------------------------------------------------------------
# Structure inference
# ----------------------------------------------------------------------

class StructureInferrer:
    """Infer structural schema from JSON data."""

    def __init__(self, max_samples: Optional[int] = None):
        self.max_samples = max_samples

    def infer(self, data: Any) -> Dict:
        """Recursively infer schema from data."""
        return self._infer_value(data, path='$')

    def _infer_value(self, value: Any, path: str) -> Dict:
        """Return a schema dictionary for a single value."""
        if value is None:
            return {'type': 'null'}
        if isinstance(value, bool):
            return {'type': 'boolean'}
        if isinstance(value, int):
            return {'type': 'integer'}
        if isinstance(value, float):
            return {'type': 'number'}
        if isinstance(value, str):
            return {'type': 'string'}
        if isinstance(value, list):
            return self._infer_array(value, path)
        if isinstance(value, dict):
            return self._infer_object(value, path)
        # Should not happen
        return {'type': 'unknown'}

    def _infer_object(self, obj: Dict, path: str) -> Dict:
        """Infer schema for an object (dict)."""
        schema = {'type': 'object', 'properties': {}, 'required': []}
        for key, val in obj.items():
            prop_path = f"{path}.{key}"
            prop_schema = self._infer_value(val, prop_path)
            schema['properties'][key] = prop_schema
            # Mark as required (since we are inferring from a single sample)
            schema['required'].append(key)
        return schema

    def _infer_array(self, arr: List, path: str) -> Dict:
        """Infer schema for an array by inspecting elements."""
        if not arr:
            # Empty array: type array with no items specified
            return {'type': 'array'}

        # Limit samples if requested
        samples = arr if self.max_samples is None else arr[:self.max_samples]

        # Collect schemas for each element
        item_schemas = []
        for idx, item in enumerate(samples):
            item_path = f"{path}[{idx}]"
            item_schemas.append(self._infer_value(item, item_path))

        # Combine schemas: if all same, use that; else use anyOf/oneOf
        merged = self._merge_schemas(item_schemas)
        return {'type': 'array', 'items': merged}

    def _merge_schemas(self, schemas: List[Dict]) -> Dict:
        """Merge multiple schemas into one (union)."""
        if len(schemas) == 1:
            return schemas[0]

        # Simplify: if all have same type, combine their sub-structures
        types = [s.get('type') for s in schemas]
        if all(t == types[0] for t in types):
            # Same type, merge properties/items if applicable
            return self._merge_same_type(schemas, types[0])
        else:
            # Different types -> use anyOf
            return {'anyOf': schemas}

    def _merge_same_type(self, schemas: List[Dict], typ: str) -> Dict:
        """Merge schemas that all have the same type."""
        if typ == 'object':
            # Combine properties and required fields
            merged = {'type': 'object', 'properties': {}, 'required': []}
            # Collect all keys and schemas for merging
            all_keys = set()
            for s in schemas:
                all_keys.update(s.get('properties', {}).keys())
            for key in all_keys:
                # Gather schemas for this key from all objects
                key_schemas = []
                for s in schemas:
                    if key in s.get('properties', {}):
                        key_schemas.append(s['properties'][key])
                if key_schemas:
                    merged['properties'][key] = self._merge_schemas(key_schemas)
            # Required: keys that appear in all objects
            required_sets = [set(s.get('properties', {}).keys()) for s in schemas]
            common_keys = set.intersection(*required_sets) if required_sets else set()
            merged['required'] = list(common_keys)
            # Remove empty required
            if not merged['required']:
                del merged['required']
            return merged

        elif typ == 'array':
            # Merge items schemas
            items_schemas = [s.get('items', {'type': 'any'}) for s in schemas]
            merged_items = self._merge_schemas(items_schemas)
            return {'type': 'array', 'items': merged_items}

        else:
            # Primitive types: they are identical (same type), so just return one.
            return schemas[0]

# ----------------------------------------------------------------------
# Statistics collection (optional)
# ----------------------------------------------------------------------

class StructureStats:
    """Collect statistics about the data (e.g., count of types, field presence)."""
    def __init__(self):
        self.type_counts = Counter()
        self.field_presence = defaultdict(int)  # path -> count
        self.array_lengths = defaultdict(list)  # path -> list of lengths

    def collect(self, data: Any, path: str = '$'):
        self.type_counts[type(data).__name__] += 1
        if isinstance(data, dict):
            for k, v in data.items():
                subpath = f"{path}.{k}"
                self.field_presence[subpath] += 1
                self.collect(v, subpath)
        elif isinstance(data, list):
            self.array_lengths[path].append(len(data))
            for idx, item in enumerate(data):
                self.collect(item, f"{path}[{idx}]")

# ----------------------------------------------------------------------
# Output formatting
# ----------------------------------------------------------------------

def format_schema(schema: Dict, pretty: bool = False) -> str:
    """Convert schema dict to JSON string."""
    indent = 2 if pretty else None
    return json.dumps(schema, indent=indent, ensure_ascii=False)

def format_summary(schema: Dict, stats: Optional[StructureStats] = None) -> str:
    """Produce a human-readable structural summary."""
    lines = []
    def walk(schema, indent=0):
        prefix = "  " * indent
        typ = schema.get('type', 'unknown')
        if typ == 'object':
            lines.append(f"{prefix}Object:")
            for k, v in schema.get('properties', {}).items():
                required = k in schema.get('required', [])
                req_marker = " (required)" if required else ""
                lines.append(f"{prefix}  {k}{req_marker}:")
                walk(v, indent + 2)
        elif typ == 'array':
            items = schema.get('items')
            if items:
                lines.append(f"{prefix}Array of:")
                walk(items, indent + 1)
            else:
                lines.append(f"{prefix}Array (empty)")
        else:
            lines.append(f"{prefix}{typ}")
    walk(schema)
    if stats:
        lines.append("\nStatistics:")
        for path, count in stats.field_presence.items():
            lines.append(f"  {path}: present in {count} objects")
        for path, lengths in stats.array_lengths.items():
            if lengths:
                avg = sum(lengths)/len(lengths)
                lines.append(f"  {path}: lengths {min(lengths)}-{max(lengths)} (avg {avg:.1f}, {len(lengths)} entries)")
    return "\n".join(lines)

# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------

def summarize_json_structure(
    source: str,
    from_file: bool = True,
    output_format: Literal['schema', 'summary'] = 'schema',
    pretty: bool = False,
    max_samples: Optional[int] = None,
    return_type: Literal['str', 'dict'] = 'str'
) -> Union[str, Dict]:
    """
    Analyze the structure of JSON data and return a schema or summary.

    Parameters:
        source (str): Either a file path (if from_file=True) or a JSON string.
        from_file (bool): If True, source is a file path; else source is JSON content.
        output_format (str): 'schema' for JSON Schema, 'summary' for human-readable.
        pretty (bool): If True and output_format='schema', indent the JSON.
        max_samples (int, optional): Maximum number of elements to sample from arrays.
        return_type (str): 'str' to return a string, 'dict' to return the schema dict
                           (only valid for output_format='schema').

    Returns:
        Union[str, Dict]: The schema or summary as a string or dict.

    Raises:
        FileNotFoundError: If source is a file and does not exist.
        json.JSONDecodeError: If JSON cannot be parsed after repairs.
        ValueError: If return_type='dict' and output_format='summary'.
    """
    # Read input
    if from_file:
        with open(source, 'r', encoding='utf-8') as f:
            content = f.read()
    else:
        content = source

    # Parse
    data = parse_json_safe(content)

    # Collect stats (always, to use in summary)
    stats = StructureStats()
    stats.collect(data)

    # Infer schema
    inferrer = StructureInferrer(max_samples=max_samples)
    schema = inferrer.infer(data)

    # Return based on format
    if output_format == 'schema':
        if return_type == 'dict':
            return schema
        else:
            return format_schema(schema, pretty=pretty)
    elif output_format == 'summary':
        if return_type == 'dict':
            raise ValueError("return_type='dict' is not supported for output_format='summary'")
        return format_summary(schema, stats)
    else:
        raise ValueError(f"Invalid output_format: {output_format}")

# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Summarize JSON structure (infer schema and statistics)."
    )
    parser.add_argument('file', nargs='?', help='JSON file to analyze (omit for stdin)')
    parser.add_argument('--schema', action='store_true', default=True,
                        help='Output JSON Schema (default)')
    parser.add_argument('--summary', action='store_true',
                        help='Output human-readable summary')
    parser.add_argument('--pretty', action='store_true',
                        help='Pretty-print output')
    parser.add_argument('--max-samples', type=int, default=None,
                        help='Max array elements to sample for inference (default: all)')
    args = parser.parse_args()

    # Determine output format
    if args.summary:
        output_format = 'summary'
    else:
        output_format = 'schema'

    # Read input
    if args.file:
        source = args.file
        from_file = True
    else:
        # Read from stdin
        source = sys.stdin.read()
        from_file = False

    try:
        result = summarize_json_structure(
            source=source,
            from_file=from_file,
            output_format=output_format,
            pretty=args.pretty,
            max_samples=args.max_samples,
            return_type='str'
        )
        print(result)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        # Provide detailed error with line/col
        line = source.count('\n', 0, e.pos) + 1 if from_file else 1
        col = e.pos - source.rfind('\n', 0, e.pos) if from_file else e.pos
        print(f"JSON decode error at line {line}, column {col}: {e.msg}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()

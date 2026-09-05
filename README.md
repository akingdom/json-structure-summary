# JSON Structure Summary

**Infer and summarise the structure of any JSON file – even malformed ones – as a JSON Schema or a human‑readable tree.**

[![PyPI version](https://badge.fury.io/py/json-structure-summary.svg)](https://pypi.org/project/json-structure-summary/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## Why do developers need this?

Working with unknown JSON data is a common pain point:

- You receive a large JSON file and have **no idea what’s inside**.
- The file is **malformed** (trailing commas, C‑style comments) and breaks normal parsers.
- You need to **generate a JSON Schema** for validation or documentation.
- You want to **quickly understand the structure** without reading thousands of lines.
- You need **statistics** (field presence, array lengths) to assess data quality.

**json-structure-summary** solves these problems in one command. It:

- **Repairs common JSON errors** (comments, trailing commas, BOM) automatically.
- **Infers a JSON Schema** (draft‑07) that accurately describes the data, including union types, optional fields, and nested structures.
- **Provides a human‑readable summary** with field presence and array length statistics.
- **Works as a library** so you can integrate it into your own Python tools.

Whether you’re exploring a new API response, debugging a data pipeline, or writing documentation, this tool gives you instant insight into your JSON data.

---

## Features

- **Robust parsing** – strips `//` and `/* */` comments, removes trailing commas, handles byte‑order marks.
- **Schema inference** – outputs a standard JSON Schema (draft‑07) that you can use with validators like `jsonschema`.
- **Mixed‑type support** – arrays with different element types are represented using `anyOf`.
- **Optionality detection** – fields are marked `required` only if they appear in *every* object across the dataset.
- **Human‑readable summary** – prints a tree structure with type annotations and (optionally) statistics.
- **Statistics** – shows field presence counts and array length ranges (min, max, average).
- **Performance** – limit array sampling with `--max-samples` to handle huge files quickly.
- **Library friendly** – import `summarize_json_structure()` and use it programmatically.

---

## Installation

```bash
pip install json-structure-summary
```

Or install directly from source:

```bash
git clone https://github.com/akingdom/json-structure-summary.git
cd json-structure-summary
pip install -e .
```

---

## Usage

### Command‑line interface

```bash
# Basic usage – outputs JSON Schema
json-structure-summary data.json

# Human‑readable summary with statistics
json-structure-summary data.json --summary

# Pretty‑print the schema
json-structure-summary data.json --schema --pretty

# Limit array sampling to 100 elements for performance
json-structure-summary data.json --max-samples 100

# Read from stdin
cat data.json | json-structure-summary
```

### Options

| Option | Description |
|--------|-------------|
| `--schema` | Output a JSON Schema (default) |
| `--summary` | Output a human‑readable structural summary |
| `--pretty` | Pretty‑print the output (indent 2) |
| `--max-samples N` | Inspect at most N elements per array (default: all) |
| `--help` | Show help |

---

## Examples

### Input JSON (with trailing commas and comments)

```json
{
  "users": [  // list of users
    {"id": 1, "name": "Alice", "active": true,},
    {"id": 2, "name": "Bob", "active": false, "tags": ["admin"]}
  ]
}
```

### Output (schema, pretty‑printed)

```json
{
  "type": "object",
  "properties": {
    "users": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "id": { "type": "integer" },
          "name": { "type": "string" },
          "active": { "type": "boolean" },
          "tags": {
            "type": "array",
            "items": { "type": "string" }
          }
        },
        "required": ["id", "name", "active"]   // 'tags' is optional
      }
    }
  },
  "required": ["users"]
}
```

### Summary output

```
Object:
  users:
    Array of:
      Object:
        id:
          integer
        name:
          string
        active:
          boolean
        tags:
          Array of:
            string

Statistics:
  $.users: lengths 2-2 (avg 2.0, 1 entries)
  $.users[0].id: present in 1 objects
  $.users[0].name: present in 1 objects
  ...
```

---

## Using as a library

```python
from json_structure_summary import summarize_json_structure

# From a file, get schema as string
schema_str = summarize_json_structure('data.json', pretty=True)

# From a file, get schema as dict
schema_dict = summarize_json_structure('data.json', return_type='dict')

# From a JSON string, get summary
summary = summarize_json_structure(
    '{"x": 1, "y": "hello"}',
    from_file=False,
    output_format='summary'
)
print(summary)
```

**Function signature:**

```python
summarize_json_structure(
    source: str,
    from_file: bool = True,
    output_format: Literal['schema', 'summary'] = 'schema',
    pretty: bool = False,
    max_samples: Optional[int] = None,
    return_type: Literal['str', 'dict'] = 'str'
) -> Union[str, Dict]
```

---

## License

MIT License – see [LICENSE](LICENSE) for details.

---

## Contributing

Bug reports, feature requests, and pull requests are welcome on [GitHub](https://github.com/akingdom/json-structure-summary).

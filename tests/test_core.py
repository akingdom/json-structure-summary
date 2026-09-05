"""
Unit tests for json_structure_summary.core
"""

import json
import pytest
from json_structure_summary import summarize_json_structure, main
from json_structure_summary.core import (
    parse_json_safe,
    repair_json,
    remove_json_comments,
    remove_trailing_commas,
    StructureInferrer,
    StructureStats,
    format_schema,
    format_summary,
)
import sys
from io import StringIO


# ---------- Helpers ----------

def valid_json_str() -> str:
    return '{"users": [{"id": 1, "name": "Alice", "active": true}, {"id": 2, "name": "Bob", "active": false, "tags": ["admin"]}]}'

def malformed_json_str() -> str:
    return '''
{
  "users": [  // list of users
    {"id": 1, "name": "Alice", "active": true,},
    {"id": 2, "name": "Bob", "active": false, "tags": ["admin"]}
  ]
}
'''


# ---------- Repair Tests ----------

def test_remove_comments():
    text = '{"x": 1 /* comment */, "y": 2 // line\n}'
    cleaned = remove_json_comments(text)
    assert '/*' not in cleaned
    assert '//' not in cleaned
    assert 'comment' not in cleaned
    assert 'line' not in cleaned

def test_remove_trailing_commas():
    text = '{"a": 1, "b": 2,}'
    cleaned = remove_trailing_commas(text)
    assert cleaned == '{"a": 1, "b": 2}'
    text2 = '[1, 2, 3,]'
    cleaned2 = remove_trailing_commas(text2)
    assert cleaned2 == '[1, 2, 3]'

def test_repair_json():
    broken = '{"x": 1, /* comment */ "y": 2,}'
    fixed = repair_json(broken)
    assert fixed == '{"x": 1,  "y": 2}'

def test_parse_json_safe_valid():
    data = parse_json_safe(valid_json_str())
    assert isinstance(data, dict)
    assert 'users' in data

def test_parse_json_safe_malformed():
    data = parse_json_safe(malformed_json_str())
    assert isinstance(data, dict)
    assert 'users' in data
    assert len(data['users']) == 2

def test_parse_json_safe_raises_on_unrepairable():
    with pytest.raises(json.JSONDecodeError):
        parse_json_safe('{"x": }')  # definitely invalid


# ---------- Schema Inference ----------

def test_infer_simple_object():
    data = {"a": 1, "b": "hello", "c": None, "d": True}
    inferrer = StructureInferrer()
    schema = inferrer.infer(data)
    expected = {
        "type": "object",
        "properties": {
            "a": {"type": "integer"},
            "b": {"type": "string"},
            "c": {"type": "null"},
            "d": {"type": "boolean"},
        },
        "required": ["a", "b", "c", "d"],
    }
    assert schema == expected

def test_infer_array_of_primitives():
    data = [1, 2, 3]
    inferrer = StructureInferrer()
    schema = inferrer.infer(data)
    expected = {
        "type": "array",
        "items": {"type": "integer"},
    }
    assert schema == expected

def test_infer_mixed_array():
    data = [1, "two", 3.0, True]
    inferrer = StructureInferrer()
    schema = inferrer.infer(data)
    # Should produce anyOf with all types
    anyof = schema.get('items', {}).get('anyOf')
    assert anyof is not None
    types = [s['type'] for s in anyof]
    assert set(types) == {"integer", "string", "number", "boolean"}

def test_infer_nested():
    data = {"users": [{"id": 1, "name": "A"}, {"id": 2, "name": "B", "extra": True}]}
    inferrer = StructureInferrer()
    schema = inferrer.infer(data)
    # Check that 'extra' is not required
    users_schema = schema['properties']['users']['items']
    assert 'extra' not in users_schema.get('required', [])
    assert 'id' in users_schema['required']
    assert 'name' in users_schema['required']

def test_infer_empty_array():
    data = []
    inferrer = StructureInferrer()
    schema = inferrer.infer(data)
    assert schema == {"type": "array"}

def test_infer_array_with_empty_objects():
    data = [{}]
    inferrer = StructureInferrer()
    schema = inferrer.infer(data)
    assert schema == {"type": "array", "items": {"type": "object", "properties": {}, "required": []}}


# ---------- Statistics ----------

def test_stats_collection():
    data = {"x": [1, 2, 3], "y": {"z": "foo"}}
    stats = StructureStats()
    stats.collect(data)
    assert stats.type_counts['dict'] == 2  # root and y
    assert stats.type_counts['list'] == 1
    assert stats.type_counts['int'] == 3
    assert stats.type_counts['str'] == 1
    assert stats.field_presence['$.x'] == 1
    assert stats.field_presence['$.y.z'] == 1
    assert stats.array_lengths['$.x'] == [3]


# ---------- Formatting ----------

def test_format_schema_pretty():
    schema = {"type": "object"}
    output = format_schema(schema, pretty=True)
    assert "{" in output
    assert "\n" in output

def test_format_schema_not_pretty():
    schema = {"type": "object"}
    output = format_schema(schema, pretty=False)
    assert json.loads(output) == schema

def test_format_summary():
    schema = {"type": "object", "properties": {"a": {"type": "integer"}}, "required": ["a"]}
    stats = StructureStats()
    stats.field_presence["$.a"] = 5
    summary = format_summary(schema, stats)
    assert "Object:" in summary
    assert "a (required):" in summary
    assert "integer" in summary
    assert "Statistics:" in summary
    assert "$.a: present in 5 objects" in summary


# ---------- Public API ----------

def test_summarize_json_structure_file(tmp_path):
    # Write a JSON file
    f = tmp_path / "data.json"
    f.write_text(valid_json_str())
    result = summarize_json_structure(str(f), from_file=True, output_format='schema', return_type='str')
    assert '"type":"object"' in result or '"type": "object"' in result

def test_summarize_json_structure_string():
    result = summarize_json_structure(valid_json_str(), from_file=False, output_format='schema', return_type='str')
    assert "users" in result

def test_summarize_json_structure_dict_return():
    schema = summarize_json_structure(valid_json_str(), from_file=False, output_format='schema', return_type='dict')
    assert isinstance(schema, dict)
    assert schema['type'] == 'object'

def test_summarize_json_structure_summary():
    summary = summarize_json_structure(valid_json_str(), from_file=False, output_format='summary')
    assert "Object:" in summary
    assert "Statistics:" in summary

def test_summarize_json_structure_summary_raises_on_dict_return():
    with pytest.raises(ValueError, match="return_type='dict' is not supported"):
        summarize_json_structure(valid_json_str(), from_file=False, output_format='summary', return_type='dict')

def test_max_samples_limits():
    data = {"list": list(range(1000))}
    json_str = json.dumps(data)
    # Without max_samples, should inspect all
    inferrer = StructureInferrer(max_samples=None)
    schema_full = inferrer.infer(json.loads(json_str))
    # With max_samples=10, should only see first 10
    inferrer_limited = StructureInferrer(max_samples=10)
    schema_limited = inferrer_limited.infer(json.loads(json_str))
    # Both should be array of integer, but the limited one may not see all types if mixed
    # For homogeneous, they are same.
    assert schema_full == schema_limited  # still same type

def test_invalid_json_raises():
    with pytest.raises(json.JSONDecodeError):
        summarize_json_structure("{bad", from_file=False)


# ---------- CLI entry point ----------

def test_main_cli(monkeypatch, tmp_path):
    # Write a JSON file
    f = tmp_path / "data.json"
    f.write_text(valid_json_str())

    # Simulate CLI args
    monkeypatch.setattr(sys, 'argv', ['json-structure-summary', str(f), '--summary'])
    # Capture stdout
    import io
    captured = io.StringIO()
    monkeypatch.setattr(sys, 'stdout', captured)

    main()  # should run without errors

    output = captured.getvalue()
    assert "Object:" in output
    assert "Statistics:" in output

def test_main_cli_stdin(monkeypatch):
    # Simulate stdin input
    monkeypatch.setattr(sys, 'argv', ['json-structure-summary'])
    # Provide input via stdin
    import io
    monkeypatch.setattr(sys, 'stdin', io.StringIO(valid_json_str()))
    captured = io.StringIO()
    monkeypatch.setattr(sys, 'stdout', captured)

    main()
    output = captured.getvalue()
    assert '"type":"object"' in output or '"type": "object"' in output  # default schema output

def test_main_cli_invalid_file(monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['json-structure-summary', 'nonexistent.json'])
    with pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code == 1

def test_main_cli_bad_json(monkeypatch, tmp_path):
    f = tmp_path / "bad.json"
    f.write_text("{bad}")
    monkeypatch.setattr(sys, 'argv', ['json-structure-summary', str(f)])
    with pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code == 1

#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(dirname "$(readlink -f "$0" 2>/dev/null || perl -MCwd -e 'print Cwd::abs_path(shift)' "$0")")"
cd "${SCRIPT_DIR}"

# -----------------------------------------------------------------
# Extract the first optional-dependency group name (e.g., "test")
# -----------------------------------------------------------------
EXTRA_NAME=$(sed -n '/^\[project\.optional-dependencies\]/,/^\[/p' pyproject.toml \
    | grep -E '^[a-zA-Z0-9_-]+ *=' \
    | head -1 \
    | sed -E 's/ *=.*//' \
    | tr -d ' ')

# Fallback to "test" if extraction failed
if [ -z "$EXTRA_NAME" ]; then
    echo "WARNING: Could not parse optional-dependency group. Using default 'test'."
    EXTRA_NAME="test"
fi

echo "Using extra group: '${EXTRA_NAME}'"

# -----------------------------------------------------------------
# Rest of the script (same as Option A)
# -----------------------------------------------------------------
echo "=== 1. Cleaning Old Build Artifacts ==="
rm -rf build/ dist/ *.egg-info src/*.egg-info

echo "=== 2. Environment Verification & Tool Setup ==="
python3 -m pip install --upgrade --quiet build twine pytest

echo "Installing package locally in editable mode with '${EXTRA_NAME}' dependencies..."
python3 -m pip install -e ".[${EXTRA_NAME}]" --quiet

if ! python3 -c "import pytest_cov" 2>/dev/null; then
    echo "ERROR: pytest-cov not installed – did '${EXTRA_NAME}' extra include it?"
    exit 1
fi

MODULE_NAME=$(grep -m 1 "^name *=" pyproject.toml | sed -E 's/name *= *"([^"]*)".*/\1/' | tr '-' '_')

echo "=== 3. Executing Test Suite ==="
if [ -d "tests" ]; then
    python3 -m pytest tests/
else
    echo "No 'tests/' directory found. Running quick import smoke test..."
    python3 -c "import ${MODULE_NAME}; print('Module import successful.')"
fi

echo "=== 4. Packaging Wheel & Source Distribution ==="
python3 -m build

echo "=== 5. Checking Package Integrity with Twine ==="
python3 -m twine check dist/*

echo ""
echo "=="
echo " BUILD & VERIFICATION SUCCESSFUL"
echo "=="
echo "To publish to PyPI, run the following commands:"
echo ""
echo "  # Option A: TestPyPI (Recommended first step)"
echo "  python3 -m twine upload --repository testpypi dist/*"
echo ""
echo "  # Option B: Official PyPI Production Release"
echo "  python3 -m twine upload dist/*"
echo "========================================================"
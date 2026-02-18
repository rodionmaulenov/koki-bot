#!/bin/bash
# Run tests related to changed files
# Called from Stop hook after Claude finishes responding

cd "$CLAUDE_PROJECT_DIR" || exit 0

# Get changed .py files (staged + unstaged vs HEAD)
CHANGED=$(git diff --name-only HEAD -- '*.py' 2>/dev/null)
[ -z "$CHANGED" ] && exit 0

PARALLEL_DIRS=""
SEQUENTIAL_DIRS=""

for file in $CHANGED; do
    case "$file" in
        services/*|callbacks/*|keyboards/*|states/*|models/*|di/*|config.py|templates.py)
            PARALLEL_DIRS="$PARALLEL_DIRS tests/services/"
            ;;
        handlers/*)
            PARALLEL_DIRS="$PARALLEL_DIRS tests/handlers/"
            ;;
        workers/*)
            PARALLEL_DIRS="$PARALLEL_DIRS tests/workers/"
            ;;
        topic_access/*)
            PARALLEL_DIRS="$PARALLEL_DIRS tests/topic_access/"
            ;;
        repositories/*)
            SEQUENTIAL_DIRS="$SEQUENTIAL_DIRS tests/repositories/"
            ;;
        tests/scenarios/*|utils/*)
            SEQUENTIAL_DIRS="$SEQUENTIAL_DIRS tests/scenarios/"
            ;;
    esac
done

# Deduplicate directories
PARALLEL_DIRS=$(echo "$PARALLEL_DIRS" | tr ' ' '\n' | sort -u | tr '\n' ' ')
SEQUENTIAL_DIRS=$(echo "$SEQUENTIAL_DIRS" | tr ' ' '\n' | sort -u | tr '\n' ' ')

EXIT_CODE=0

# Run parallel tests
if [ -n "$PARALLEL_DIRS" ]; then
    echo "=== Parallel tests: $PARALLEL_DIRS ==="
    pytest -n auto --tb=short -q $PARALLEL_DIRS
    [ $? -ne 0 ] && EXIT_CODE=1
fi

# Run sequential tests
if [ -n "$SEQUENTIAL_DIRS" ]; then
    echo "=== Sequential tests: $SEQUENTIAL_DIRS ==="
    pytest --tb=short -q $SEQUENTIAL_DIRS
    [ $? -ne 0 ] && EXIT_CODE=1
fi

exit $EXIT_CODE

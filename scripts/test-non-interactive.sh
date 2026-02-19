#!/usr/bin/env bash
# Quick test of non-interactive mode

echo "Testing non-interactive mode..."
echo ""

# Test 1: Call start-services in non-interactive mode
echo "Test 1: Calling start-services via pipe (simulates non-interactive)"
echo "n" | timeout 10 ./scripts/services/start-services.sh 2>&1 | head -50

echo ""
echo "---"
echo ""

# Test 2: Check if INTERACTIVE_MODE detection works
echo "Test 2: Checking interactive mode detection"
if [ -t 0 ]; then
    echo "✓ stdin is a terminal (interactive)"
else
    echo "✓ stdin is NOT a terminal (non-interactive)"
fi

echo ""
echo "Test completed"

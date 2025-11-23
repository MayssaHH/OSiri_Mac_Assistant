#!/usr/bin/env python3
"""
Test script for the browser history tool.
"""
import sys
sys.path.insert(0, '.')

from src.web_agent.tools import get_browser_history

print("=== Testing Browser History Tool ===\n")

# Test 1: Last 5 URLs from today
print("Test 1: Last 5 URLs from today")
print("-" * 50)
result = get_browser_history(hours=24, count=5)
print(result)
print("\n")

# Test 2: Last 3 URLs from the last hour
print("Test 2: Last 3 URLs from the last hour")
print("-" * 50)
result = get_browser_history(hours=1, count=3)
print(result)
print("\n")

# Test 3: GitHub visits (if any)
print("Test 3: GitHub visits from today")
print("-" * 50)
result = get_browser_history(hours=24, count=10, domain="github.com")
print(result)


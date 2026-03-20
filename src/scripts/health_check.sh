#!/bin/bash
# Health Check Script
# This script monitors system health and logs results to a file.

LOG_FILE="/Users/peggy/.tinybot/agents/chat/server_health.log"
TIMESTAMP=$(date "+%Y-%m-%d %H:%M:%S")

# Resource Metrics
CPU_USAGE=$(top -l 1 | grep "CPU usage" | awk '{print $3}')
MEM_USED=$(vm_stat | grep "Pages active" | awk '{print $3}' | sed 's/\.//')
DISK_SPACE=$(df -h / | tail -1 | awk '{print $5}')

# Write to log
echo "[$TIMESTAMP] CPU: $CPU_USAGE | MEM (Pages Active): $MEM_USED | DISK: $DISK_SPACE" >> "$LOG_FILE"

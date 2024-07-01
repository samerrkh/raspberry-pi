#!/bin/bash

# Function to kill processes by name
kill_processes_by_name() {
    local process_name=$1
    echo "Killing processes: $process_name"
    pkill -f $process_name
}

# Kill Python processes
kill_processes_by_name "python"

# Kill VLC processes
kill_processes_by_name "vlc"

# Kill GStreamer processes
kill_processes_by_name "gst-launch-1.0"

# Verify processes are killed
echo "Verifying processes..."
ps aux | grep python
ps aux | grep vlc
ps aux | grep gst-launch-1.0

echo "All processes checked and killed."

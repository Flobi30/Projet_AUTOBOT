# Guardian Guide

')
    f.write('## Overview

')
    f.write('The `autobot_guardian.py` script performs system performance monitoring by logging CPU and memory usage every 5 seconds. It includes features for auto-restarting on errors and sending notifications via webhook.

')
    f.write('## Configuration

')
    f.write('- Replace `https://your-webhook-url` in the script with your actual webhook URL to receive notifications.

')
    f.write('## Usage

')
    f.write('- Run the script:
')
    f.write('  ```bash
')
    f.write('  python src/autobot_guardian.py
')
    f.write('  ```
')
    f.write('- The script will run indefinitely, monitoring system performance and sending updates.

')
    f.write('## Troubleshooting

')
    f.write('- Ensure `psutil` and `requests` libraries are installed:
')
    f.write('  ```bash
')
    f.write('  pip install psutil requests
')
    f.write('  ```
')
    f.write('- Verify the webhook URL is correct and accessible.
')
    f.write('- Check logs for errors if notifications are not received.

')
    f.write('## Notes

')
    f.write('- You can stop the script with Ctrl+C.
')
    f.write('- Customize the monitoring interval or add additional metrics as needed.
')

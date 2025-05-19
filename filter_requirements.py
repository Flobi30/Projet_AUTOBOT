"""
Script to filter out superagi from requirements.txt
"""

with open('requirements.txt', 'r') as f:
    lines = f.readlines()

with open('requirements_custom.txt', 'w') as f:
    for line in lines:
        if 'superagi' not in line:
            f.write(line)

print("Created requirements_custom.txt without superagi dependency")

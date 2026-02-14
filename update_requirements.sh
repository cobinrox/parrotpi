#!/bin/bash
# commands to run if you had to add extra pip install packages,
# just be sure to re-run this script which will udate the
# requirements.txt file
source venv/bin/activate
pip freeze > requirements.txt
echo "requirements.txt updated."
#!/bin/sh
set -eu
python manage.py run_weekly_scheduler --once

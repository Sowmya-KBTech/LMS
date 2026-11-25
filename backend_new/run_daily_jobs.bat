@echo off
REM STEP 8: REPLACED BY CELERY BEAT. Only a fallback while Beat is not live.
REM Never schedule this file AND run Beat: jobs would run twice.
REM NIGHTLY JOB RUNNER (Point 12, step 4): fee, attendance and assignment
REM reminders, then the email queue. Schedule daily at 12:15 AM in Task Scheduler.
REM %~dp0 = the folder this file is in (the backend folder), so no fixed path.
REM SAAS PHASE 1: runs once inside every active college (run_for_all_colleges).
cd /d "%~dp0"
"%~dp0venv\Scripts\python.exe" manage.py run_for_all_colleges run_daily_jobs >> "%~dp0daily_jobs_log.txt" 2>&1

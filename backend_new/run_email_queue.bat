@echo off
REM STEP 8: REPLACED BY CELERY BEAT. Only a fallback while Beat is not live.
REM Never schedule this file AND run Beat: jobs would run twice.
REM EMAIL QUEUE (Point 12, G4): sends pending notification emails in batches.
REM Schedule it in Windows Task Scheduler every 10 minutes.
REM %~dp0 = the folder this file is in (the backend folder), so no fixed path.
REM SAAS PHASE 1: runs once inside every active college (run_for_all_colleges).
cd /d "%~dp0"
"%~dp0venv\Scripts\python.exe" manage.py run_for_all_colleges send_notification_emails >> "%~dp0email_queue_log.txt" 2>&1

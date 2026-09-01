@echo off
rem הרצה ישירות מתיקיית המקור, בלי להתקין כלום.
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set PYTHONPATH=%~dp0;%PYTHONPATH%
python -m sbpy %*

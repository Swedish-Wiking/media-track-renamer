@echo off 
pushd %~dp0
python "track_renamer.py" %*
pause
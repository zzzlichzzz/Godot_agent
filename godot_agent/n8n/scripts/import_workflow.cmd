@echo off
rem Import the workflow snapshot from this repository into local n8n (npm).
rem The schema file contains only credential references (id + name), no keys.
rem Usage (from the n8n folder):  scripts\import_workflow.cmd [path\to\file.json]
setlocal
set "SCHEMA=%~1"
if "%SCHEMA%"=="" set "SCHEMA=%~dp0..\schemas\template_v2_core_4_channels.json"
echo Importing: "%SCHEMA%"
call "%APPDATA%\npm\n8n.cmd" import:workflow --input="%SCHEMA%"
endlocal

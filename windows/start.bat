@echo off
chcp 65001 >nul
title AlgoRE - Windows 11
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"
if errorlevel 1 pause

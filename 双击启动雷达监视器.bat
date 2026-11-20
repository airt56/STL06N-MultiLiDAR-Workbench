@echo off
chcp 65001 >nul
title LD19 激光雷达 360 度实时点云监视器
echo 正在启动 LD19 实时点云监视器 (COM7 @ 230400)...
"C:\Program Files\Derivative\TouchDesigner\bin\python.exe" "%~dp0LD19_Radar_Viewer.py" COM7
pause

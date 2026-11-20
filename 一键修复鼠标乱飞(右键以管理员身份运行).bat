@echo off
chcp 65001 >nul
title 修复 Windows 串口雷达误识别为鼠标问题
echo ========================================================
echo  正在禁用 Windows 串口鼠标检测驱动服务 (sermouse)...
echo ========================================================
reg add "HKLM\SYSTEM\CurrentControlSet\Services\sermouse" /v "Start" /t REG_DWORD /d 4 /f
if %errorlevel% equ 0 (
    echo.
    echo [成功] 修复完毕！
    echo Windows 已永久禁用老旧串口鼠标检测功能。
    echo 以后插拔 LD19 雷达，鼠标指针绝不会再发生乱跳、乱点、乱飘的问题！
    echo.
) else (
    echo.
    echo [失败] 权限不足！
    echo 请【右键点击本文件】并选择【以管理员身份运行】！
    echo.
)
pause

@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ========================================
echo   正在启动 Personal Asset Manager...
echo ========================================
echo.
where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    py -m streamlit run app.py
) else (
    python -m streamlit run app.py
)
pause
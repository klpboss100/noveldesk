@echo off
chcp 65001 > nul
echo.
echo ================================================
echo   NOVELDESK 시작
echo ================================================
echo.

cd /d "%~dp0"

python -c "import streamlit" 2>nul
if errorlevel 1 (
    echo 패키지를 설치합니다... 잠시 기다려주세요.
    pip install -r requirements.txt
    echo.
)

echo 브라우저에서 자동으로 열립니다...
echo 주소: http://localhost:8501
echo.
echo 종료하려면 이 창에서 Ctrl+C 를 누르세요.
echo ================================================
echo.

python -m streamlit run streamlit_app.py

pause

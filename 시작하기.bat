@echo off
chcp 65001 > nul
title NOVELDESK

echo.
echo ================================================
echo   NOVELDESK 시작하기
echo ================================================
echo.

cd /d "%~dp0"

echo [1] Python 확인 중...
python --version 2>nul
if errorlevel 1 (
    echo.
    echo [오류] Python이 설치되어 있지 않습니다.
    echo   https://python.org 에서 Python 3.11 이상을 설치해주세요.
    echo.
    pause
    exit
)

echo [2] Streamlit 확인 중...
python -c "import streamlit" 2>nul
if errorlevel 1 (
    echo   Streamlit 설치 중... 잠시 기다려주세요 (1~2분)
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [오류] 설치 실패. 인터넷 연결을 확인해주세요.
        pause
        exit
    )
)

echo [3] 서버 시작 중...
echo.
echo  브라우저가 자동으로 열립니다.
echo  주소: http://localhost:8501
echo.
echo  종료하려면 이 창에서 Ctrl+C 를 누르세요.
echo ================================================
echo.

python -m streamlit run streamlit_app.py --server.port 8501

echo.
echo 서버가 종료되었습니다.
pause

@echo off
chcp 65001 > nul
echo.
echo ================================================
echo   NOVELDESK 웹 서버 시작
echo ================================================
echo.

REM 현재 폴더를 이 bat 파일이 있는 web/ 폴더로 설정
cd /d "%~dp0"

REM Flask가 설치됐는지 확인
python -c "import flask" 2>nul
if errorlevel 1 (
    echo Flask가 설치되어 있지 않습니다.
    echo 지금 설치합니다... 잠시 기다려주세요.
    echo.
    pip install -r requirements.txt
    echo.
)

echo 서버를 시작합니다...
echo.
echo  브라우저에서 아래 주소를 열어주세요:
echo  http://127.0.0.1:5000
echo.
echo  종료하려면 이 창에서 Ctrl+C 를 누르세요.
echo ================================================
echo.

python app.py

pause

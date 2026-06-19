@echo off
:: 콘솔 창에서 한글이 깨지지 않도록 UTF-8 인코딩 설정
chcp 65001 > nul
echo =======================================
echo VoxCPM2 Realtime Mic Setup ^& Run
echo =======================================

:: 가상환경이 이미 존재하면 복잡한 설치/탐색 건너뛰고 바로 실행
IF EXIST "venv\Scripts\activate.bat" (
    goto :RUN_APP
)

echo [1/4] 적합한 파이썬 버전을 찾는 중입니다...
set PYTHON_CMD=

:: 1. 기본 설정된 python 명령어가 3.12 이하인지 확인
python -c "import sys; sys.exit(0 if sys.version_info <= (3, 12, 99) else 1)" >nul 2>nul
if %errorlevel% equ 0 (
    set PYTHON_CMD=python
    goto :CREATE_VENV
)

:: 2. py 런처를 이용해 3.12부터 3.9까지 역순으로 탐색
py -3.12 -c "exit()" >nul 2>nul
if %errorlevel% equ 0 ( set PYTHON_CMD=py -3.12 & goto :CREATE_VENV )

py -3.11 -c "exit()" >nul 2>nul
if %errorlevel% equ 0 ( set PYTHON_CMD=py -3.11 & goto :CREATE_VENV )

:: 3. py 런처가 고장났을 경우를 대비한 직접 경로 탐색 (3.12 및 3.11)
echo [안내] py 런처에서 찾지 못해 기본 설치 경로를 직접 탐색합니다...
set "PATH_LOCAL_312=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
set "PATH_PROG_312=C:\Program Files\Python312\python.exe"
set "PATH_LOCAL_311=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
set "PATH_PROG_311=C:\Program Files\Python311\python.exe"

if exist "%PATH_LOCAL_312%" ( set "PYTHON_CMD="%PATH_LOCAL_312%"" & goto :CREATE_VENV )
if exist "%PATH_PROG_312%" ( set "PYTHON_CMD="%PATH_PROG_312%"" & goto :CREATE_VENV )
if exist "%PATH_LOCAL_311%" ( set "PYTHON_CMD="%PATH_LOCAL_311%"" & goto :CREATE_VENV )
if exist "%PATH_PROG_311%" ( set "PYTHON_CMD="%PATH_PROG_311%"" & goto :CREATE_VENV )

:: 4. 모든 방법이 실패한 경우
echo.
echo [오류] 컴퓨터에서 Python 3.11 ~ 3.12 버전을 찾을 수 없습니다.
echo 현재 설치된 버전이 너무 높거나(3.13 이상), 파이썬이 표준 경로에 설치되지 않았습니다.
echo Python 3.12 공식 홈페이지 설치 파일을 다운로드하여 'Add to PATH' 체크 후 다시 설치해 주세요.
pause
exit /b

:CREATE_VENV
echo [탐색 완료] 선택된 파이썬 실행 파일: %PYTHON_CMD%
echo [2/4] 가상환경(venv)을 생성합니다. 시간이 조금 걸릴 수 있습니다...
%PYTHON_CMD% -m venv venv

:: 가상환경 활성화 및 pip 최신화
call venv\Scripts\activate
python -m pip install --upgrade pip > nul

:CHOOSE_ENVIRONMENT
echo.
echo =======================================
echo     하드웨어 환경 선택 ^(PyTorch 설치^)
echo =======================================
where nvidia-smi >nul 2>nul
if %errorlevel% equ 0 (
    echo [안내] 시스템에서 NVIDIA 그래픽 카드가 감지되었습니다!
    echo 1. CPU 버전 설치 ^(속도 매우 느림, 비추천^)
    echo 2. GPU ^(CUDA 12.1^) 버전 설치 [★ 시스템 추천 ★]
) else (
    echo [안내] NVIDIA 그래픽 카드가 감지되지 않았거나 드라이버가 없습니다.
    echo 1. CPU 버전 설치 [★ 시스템 추천 ★]
    echo 2. GPU ^(CUDA 12.1^) 버전 설치
)
echo =======================================

set /p USER_CHOICE="원하는 환경의 번호를 입력하고 엔터를 누르세요 (1 또는 2): "

if "%USER_CHOICE%"=="1" (
    echo [3/4] PyTorch CPU 버전을 설치합니다...
    pip install torch torchaudio
    goto :INSTALL_REMAINING
)
if "%USER_CHOICE%"=="2" (
    echo [3/4] PyTorch GPU ^(CUDA 12.1^) 버전을 설치합니다... 용량이 크니 잠시만 기다려주세요.
    pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121
    goto :INSTALL_REMAINING
)

echo 잘못된 입력입니다. 다시 선택해 주세요.
goto :CHOOSE_ENVIRONMENT

:INSTALL_REMAINING
echo 나머지 필수 패키지들을 설치하는 중입니다...
pip install -r requirements.txt
echo 모든 환경 설정 및 설치가 완료되었습니다!
goto :START_INTERFACE

:RUN_APP
call venv\Scripts\activate

:START_INTERFACE
echo [4/4] 웹 UI를 시작합니다! 브라우저 창이 열릴 때까지 기다려주세요.
python app.py
pause
@echo off
:: 콘솔 창에서 한글이 깨지지 않도록 UTF-8 인코딩 설정
chcp 65001 > nul
echo =======================================
echo VoxCPM2 Realtime Mic Setup ^& Run
echo =======================================

IF EXIST "venv\Scripts\activate.bat" (
    goto :CHECK_UPDATE
)

echo [1/4] 적합한 파이썬 버전을 찾는 중입니다...
set PYTHON_CMD=

python -c "import sys; sys.exit(0 if sys.version_info <= (3, 12, 99) else 1)" >nul 2>nul
if %errorlevel% equ 0 (
    set PYTHON_CMD=python
    goto :CREATE_VENV
)

py -3.12 -c "exit()" >nul 2>nul
if %errorlevel% equ 0 ( set PYTHON_CMD=py -3.12 & goto :CREATE_VENV )

py -3.11 -c "exit()" >nul 2>nul
if %errorlevel% equ 0 ( set PYTHON_CMD=py -3.11 & goto :CREATE_VENV )

echo [안내] py 런처에서 찾지 못해 기본 설치 경로를 직접 탐색합니다...
set "PATH_LOCAL_312=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
set "PATH_PROG_312=C:\Program Files\Python312\python.exe"
set "PATH_LOCAL_311=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
set "PATH_PROG_311=C:\Program Files\Python311\python.exe"

if exist "%PATH_LOCAL_312%" ( set "PYTHON_CMD=%PATH_LOCAL_312%" & goto :CREATE_VENV )
if exist "%PATH_PROG_312%" ( set "PYTHON_CMD=%PATH_PROG_312%" & goto :CREATE_VENV )
if exist "%PATH_LOCAL_311%" ( set "PYTHON_CMD=%PATH_LOCAL_311%" & goto :CREATE_VENV )
if exist "%PATH_PROG_311%" ( set "PYTHON_CMD=%PATH_PROG_311%" & goto :CREATE_VENV )

echo.
echo [안내] 자동 탐색에서 Python 3.11 ~ 3.12을 찾지 못했습니다.
echo 직접 파이썬 실행 파일 경로를 입력하거나 엔터로 종료할 수 있습니다.

:MANUAL_PY_PROMPT
set /p PY_MANUAL="파이썬 실행 파일 경로 입력 (예: C:\Python312\python.exe) 또는 빈칸 입력 후 엔터로 종료: "
if "%PY_MANUAL%"=="" (
    echo 종료합니다.
    exit /b
)
if not exist "%PY_MANUAL%" (
    echo [오류] 입력한 경로를 찾을 수 없습니다: %PY_MANUAL%
    goto :MANUAL_PY_PROMPT
)
"%PY_MANUAL%" -c "import sys; sys.exit(0 if sys.version_info <= (3, 12, 99) else 1)" >nul 2>nul
if %errorlevel% equ 0 (
    set "PYTHON_CMD=%PY_MANUAL%"
    goto :CREATE_VENV
) else (
    echo [오류] 알맞은 버전의 파이썬을 찾을 수 없습니다. 다시 입력해 주세요.
    goto :MANUAL_PY_PROMPT
)

:CREATE_VENV
echo [탐색 완료] 선택된 파이썬 실행 파일: %PYTHON_CMD%
echo [2/4] 가상환경(venv)을 생성합니다.
echo 시간이 조금 걸릴 수 있습니다...
%PYTHON_CMD% -m venv venv

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
    echo [3/4] PyTorch GPU ^(CUDA 12.1^) 버전을 설치합니다...
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

:CHECK_UPDATE
call venv\Scripts\activate
echo [시스템 점검] 신규 패키지 업데이트 내역을 확인합니다...
python -c "import faster_whisper" >nul 2>nul
if %errorlevel% neq 0 (
    echo [업데이트] faster-whisper 등 최적화 패키지가 누락되어 설치를 진행합니다...
    pip install -r requirements.txt
)

:START_INTERFACE
echo [4/4] 데스크톱 GUI 애플리케이션을 시작합니다!
python main.py
pause
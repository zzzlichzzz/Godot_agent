@echo off
chcp 65001 >nul
rem ============================================================
rem Сборка сервера агента (режим onedir — БЫСТРЫЙ старт, без распаковки при каждом запуске).
rem Результат: ПАПКА dist\godot_agent_server с godot_agent_server.exe внутри.
rem Переносите ВСЮ папку godot_agent_server целиком — панель найдёт exe сама.
rem ============================================================
title Сборка сервера Godot Agent
echo.
echo ============================================================
echo   Сборка сервера Godot Agent в exe-файл
echo ============================================================
echo.
cd /d "%~dp0"
echo Рабочая папка: %CD%
echo.

rem ------------------------------------------------------------
rem Ищем работающий Python по всем известным вариантам установки —
rem обычный "python"/"py" в PATH, либо новый Python Install Manager
rem (папка %LOCALAPPDATA%\Python\pythoncore-*), либо обычная подпапка
rem пользователя Programs\Python. Где бы он ни стоял, проверим напрямую.
rem ------------------------------------------------------------
set PYCMD=

python --version >nul 2>&1
if not errorlevel 1 set PYCMD=python

if "%PYCMD%"=="" (
    py --version >nul 2>&1
    if not errorlevel 1 set PYCMD=py
)

if "%PYCMD%"=="" (
    python3 --version >nul 2>&1
    if not errorlevel 1 set PYCMD=python3
)

rem Новый Python Install Manager (папки вида pythoncore-3.14-64)
if "%PYCMD%"=="" (
    for /d %%D in ("%LOCALAPPDATA%\Python\pythoncore-*") do (
        if exist "%%D\python.exe" set PYCMD="%%D\python.exe"
    )
)

rem Классическая пользовательская установка python.org
if "%PYCMD%"=="" (
    for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
        if exist "%%D\python.exe" set PYCMD="%%D\python.exe"
    )
)

rem Системные установки для всех пользователей
if "%PYCMD%"=="" (
    for /d %%D in ("C:\Program Files\Python3*") do (
        if exist "%%D\python.exe" set PYCMD="%%D\python.exe"
    )
)
if "%PYCMD%"=="" (
    for /d %%D in ("C:\Python3*") do (
        if exist "%%D\python.exe" set PYCMD="%%D\python.exe"
    )
)

if "%PYCMD%"=="" (
    echo [ERROR] Python не найден автоматически.
    echo Вы говорите, что Python у вас есть — возможно, он поставлен в нестандартное место.
    echo Откройте командную строку и выполните: where python
    echo затем напишите разработчику путь, который она выведет.
    goto END
)

for /f "tokens=*" %%v in ('%PYCMD% --version 2^>^&1') do echo Python: %%v (%PYCMD%)
echo.

echo [1/3] Установка PyInstaller...
%PYCMD% -m pip install pyinstaller numpy
if errorlevel 1 (
    echo.
    echo [ERROR] Не удалось установить PyInstaller.
    goto END
)
echo.
echo [2/3] Сборка exe (несколько минут, окно не закрывайте)...
rem ВАЖНО: список --paths должен совпадать с _PACKAGE_DIRS в _bootstrap.py.
rem Модули лежат по подпапкам, а импортируются плоско; PyInstaller видит такие
rem импорты только через --paths. Без --paths api --paths backends в сборку не
rem попадали api_keys/providers/openai_compat/api_backend/browser_backend, и
rem готовый exe падал на работе по ключу API, хотя локально всё работало.
rem
rem Модули работы по ключу перечислены и через --hidden-import, хотя --paths их
rem уже находит по цепочке импортов из main.py. Это не дубль: цепочку легко
rem порвать (сделать импорт ленивым или условным), и тогда модуль тихо выпадет
rem из сборки. Явное перечисление также попадает в перегенерированный .spec,
rem поэтому файл остаётся согласованным после каждой сборки.
%PYCMD% -m PyInstaller --onedir --noconfirm --paths parsers --paths browser --paths godot_tools --paths server --paths api --paths backends --collect-submodules selenium --hidden-import numpy --collect-submodules numpy --hidden-import minilich.ml_train --hidden-import minilich.ml_model --hidden-import minilich.ml_tokenizer --hidden-import parser_base --hidden-import ai_parser --hidden-import deepseek_parser --hidden-import qwen_parser --hidden-import kimi_parser --hidden-import arena_parser --hidden-import answer_judge --hidden-import api_keys --hidden-import providers --hidden-import openai_compat --hidden-import api_backend --hidden-import browser_backend --hidden-import api_history --hidden-import md_to_bbcode --hidden-import server_auth --name godot_agent_server main.py
if errorlevel 1 (
    echo.
    echo [ERROR] Ошибка сборки. Прочитайте вывод выше.
    goto END
)
echo.
rem Старый медленный одиночный exe (onefile) больше не нужен — удаляем его,
rem чтобы панель случайно не запускала его вместо быстрой папки.
if exist "dist\godot_agent_server.exe" del "dist\godot_agent_server.exe"
echo [3/3] Готово!
echo Файл: %CD%\dist\godot_agent_server\godot_agent_server.exe
echo Перенесите ВСЮ папку dist\godot_agent_server в папку аддона — панель найдёт exe сама. Старый одиночный exe можно удалить.

:END
echo.
echo Нажмите любую клавишу для закрытия...
pause >nul

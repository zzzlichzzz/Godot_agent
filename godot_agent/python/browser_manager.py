import os
import time
import subprocess
from selenium import webdriver

def find_chrome():
    """Ищет установленный Chrome в системе"""
    paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")
    ]
    for p in paths:
        if os.path.exists(p): return p
    return None

def setup_browser():
    """Запускает браузер и возвращает объект драйвера"""
    chrome_path = find_chrome()
    if not chrome_path:
        raise Exception("Google Chrome не найден на этом ПК!")

    profile_dir = os.path.expandvars(r"%LOCALAPPDATA%\Godot_AI_Profile")
    
    print("1. Запускаю выделенный браузер...")
    subprocess.Popen([
        chrome_path,
        '--remote-debugging-port=9222',
        f'--user-data-dir={profile_dir}',
        'https://aistudio.google.com/prompts/new_chat'
    ])
    
    time.sleep(3) # Ждем открытия окна
    
    print("2. Подключаю управление...")
    options = webdriver.ChromeOptions()
    options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
    driver = webdriver.Chrome(options=options)
    
    return driver
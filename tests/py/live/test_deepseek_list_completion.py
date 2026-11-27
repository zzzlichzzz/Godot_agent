"""Real layout, extracted text and CSS list labels; never visit a provider page."""
import os
from pathlib import Path

import pytest
from tests.py.browser.runtime_cases import references


@pytest.mark.needs_live
def test_wrapped_markdown_list_needs_complete_text_and_layout(tmp_path):
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    chrome = os.environ.get('GODOT_AGENT_CHROME_PATH')
    driver = os.environ.get('GODOT_AGENT_CHROMEDRIVER_PATH')
    if not all(p and Path(p).is_file() for p in (chrome, driver)):
        pytest.skip('Set local Chrome and ChromeDriver paths; no driver downloads')
    opts=webdriver.ChromeOptions();opts.binary_location=chrome
    for flag in ('--headless=new','--disable-background-networking','--no-first-run',
                 '--disable-sync','--disable-extensions','--proxy-server=127.0.0.1:1',f'--user-data-dir={tmp_path}/profile'):
        opts.add_argument(flag)
    with references() as native, webdriver.Chrome(service=Service(driver),options=opts) as browser:
        from python.substrate.llm.parsers.deepseek_completion import complete
        parser=native['deepseek_parser'];browser.get('about:blank')
        browser.execute_script('''document.body.innerHTML='<div class="ds-markdown" style="width:280px;font:16px/20px sans-serif"><ol><li></li><li></li></ol><p><strong>===DONE===</strong></p></div>';
            for(const li of document.querySelectorAll('li')) li.textContent='1. Literal prefix '+ 'wrap here '.repeat(45);''')
        first=browser.execute_script(parser.JS_EXTRACT)
        assert '2. 1. Literal prefix' in first['text'] and first['blockHeight']>400
        assert complete(browser,first)
        assert not complete(browser,dict(first,text=first['text'].replace('1. Literal prefix','Literal prefix',1)))
        browser.execute_script("document.querySelector('.ds-markdown').style.paddingBottom='600px'")
        assert not complete(browser,browser.execute_script(parser.JS_EXTRACT))

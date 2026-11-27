"""Exercise the editing operation on local HTML. No AI Studio connection or login."""
import os
from pathlib import Path

import pytest


@pytest.mark.needs_live
def test_studio_draft_preserves_unchanged_text_and_never_submits(tmp_path):
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from python.substrate.llm.parsers.studio_draft import _EDIT, studio_route
    chrome=os.environ.get('GODOT_AGENT_CHROME_PATH');driver=os.environ.get('GODOT_AGENT_CHROMEDRIVER_PATH')
    if not all(p and Path(p).is_file() for p in (chrome,driver)):pytest.skip('Local Chrome and ChromeDriver required')
    route='https://aistudio.google.com/prompts/new_chat'
    assert studio_route(route) and not any(studio_route(url) for url in [route.replace('https:', 'http:'),
        route.replace('.com/', '.com.example/'),route.replace('/prompts/', '/settings/')])
    opts=webdriver.ChromeOptions();opts.binary_location=chrome
    for flag in ('--headless=new','--disable-background-networking','--no-first-run','--disable-sync',
                 '--disable-extensions','--proxy-server=127.0.0.1:1',f'--user-data-dir={tmp_path}/profile'):opts.add_argument(flag)
    with webdriver.Chrome(service=Service(driver),options=opts) as browser:
        js=browser.execute_script;browser.get('about:blank');url=browser.current_url
        js('''document.body.innerHTML='<form><ms-prompt-box><textarea></textarea></ms-prompt-box><button>Send</button></form>';
        window.field=document.querySelector('textarea');window.events=[];window.submits=0;
        field.addEventListener('input',e=>events.push([e.data, field.value,field.selectionStart]));
        document.querySelector('form').onsubmit=e=>{e.preventDefault();submits++}''')
        tail=' — длинный хвост'*18;prefix='😀 Заголовок\n';js('field.value=arguments[0]',prefix+tail)
        for addition,delta in [('кошка','кошка'),('ложка','лож'),('ложка\n🐈','\n🐈'),('','')]:
            value=prefix+addition+tail
            assert js(_EDIT,url,value)
            event=js('return events.at(-1)');assert event[:2]==[delta or None,value]
            assert event[2]==len((prefix+addition).removesuffix('ка' if delta=='лож' else '').encode('utf-16-le'))//2
        assert js(_EDIT,url,value) and js('return events.length')==4
        assert not js(_EDIT,'about:other','wrong route')
        js("field.after(field.cloneNode());")
        assert not js(_EDIT,url,'ambiguous');js('field.nextSibling.remove()')
        js('field.readOnly=true');assert not js(_EDIT,url,'readonly');js('field.readOnly=false')
        js("field.addEventListener('beforeinput', e=>e.preventDefault(), {once:true})")
        assert not js(_EDIT,url,'cancelled')
        assert js('return [field.value,events.length,submits]')==[value,4,0]

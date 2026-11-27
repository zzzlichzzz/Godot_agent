"""An isolated copy of the reported declaration and untyped coin callback."""
import json


ACTION=json.loads('{"action":"rename_symbol","kind":"function","old_name":"add_coin","new_name":"gain_coin","declaration":"res://src/scripts/player.gd:94:6","allow_unverified":true,"mode":"probable"}')
PROPOSAL='Предлагаю переименование.\n```json\n'+json.dumps(ACTION,separators=(',',':'))+'\n```\n===DONE==='


def write_sources(project):
    src=project/'src/scripts';src.mkdir(parents=True)
    player=src/'player.gd';coin=src/'coin.gd'
    before={player:b'extends Node\n'+92*b'\n'+b'func add_coin():\n\tpass\n',
            coin:b'extends Area2D\r\nfunc hit(body):\r\n\tif body.has_method("add_coin"):\r\n\t\tbody.add_coin()\r\n'}
    for path,data in before.items():path.write_bytes(data)
    return before

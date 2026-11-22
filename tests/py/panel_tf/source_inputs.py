"""D90 input-only revision: exact old/new raw pins, unchanged business goldens."""
import hashlib

PATH='editor/core/resource_publication_observer.gd'
OLD_SHA='fa449727bf5b461b0cdff330bc4d60ced5a6a7765b665098486ea8bf05eb4706'
NEW_SHA='4e61db341215fc73142098265e243fb12a996f5a35348b3fcaa77faf9ed90f47'
OLD=b'extends "agent_resource_executor.gd"'
NEW=b'extends "res://addons/godot_agent/editor/native/agent_resource_executor.gd"'

def revised_fact(fact,before,current):
    if fact['path']!=PATH or fact['bytes']!=370 or fact['sha256']!=OLD_SHA:
        raise ValueError('Only the original D90 observer input may be revised')
    if len(before)!=370 or hashlib.sha256(before).hexdigest()!=OLD_SHA or before.count(OLD)!=1:
        raise ValueError('Original observer input drifted')
    if current!=before.replace(OLD,NEW,1) or len(current)!=409 or hashlib.sha256(current).hexdigest()!=NEW_SHA:
        raise ValueError('Observer change is not the authorized extends-only replacement')
    return dict(fact,bytes=409,sha256=NEW_SHA)

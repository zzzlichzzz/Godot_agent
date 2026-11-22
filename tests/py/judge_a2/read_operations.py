"""Direct native/canonical scene analysis and file-reference preparations."""
from .observations import call, HarnessInvocationError


def run(module, project, addon, case):
    function = case['function']
    if case['group'] == 'scene_deps':
        if function in ('to_snake', 'extract_handlers', 'parse_scene'):
            return call(getattr(module, function), case['text'])
        if function == 'analyze_scene_action':
            result = call(module.analyze_scene_action, case['text'],
                          case.get('path', 'res://scene.tscn'), str(project))
            if isinstance(result, BaseException):
                return result
            return {'analysis': result, 'again': call(module.analyze_scene_action,
                result[0], case.get('path', 'res://scene.tscn'), str(project))}
        if function == 'analyze_script_action':
            return call(module.analyze_script_action, case['text'],
                        case.get('path', 'res://scripts/player.gd'), str(project))
    elif case['group'] == 'file_refactor':
        options = dict(case.get('options', {}), addon_dir=str(addon))
        if function == 'find_file_references':
            return call(module.find_file_references, str(project), case['old'], **options)
        if function in ('prepare_file_rename', 'prepare_directory_relocation'):
            result = call(getattr(module, function), str(project), case['old'], case['new'], **options)
            return {'prepared': result, 'again': call(getattr(module, function), str(project),
                                                     case['old'], case['new'], **options)}
        if function == 'update_internal_relative_paths':
            return call(module.update_internal_relative_paths, case['text'],
                case['old'], case['new'], str(project), case.get('moved_files_map'))
    raise HarnessInvocationError('unknown read operation: '+function)

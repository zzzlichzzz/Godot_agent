"""Whitelisted observation calls; fixture data never becomes executable code."""
import errno
import os
from unittest.mock import patch

from tests.py.project.observations import attempt, snapshot

READ_CALLS = {
    'read_project_file', 'policy_read_project_file', 'describe_scene', 'policy_describe_scene',
    'build_project_tree', 'build_project_overview', 'search_project_text',
    'describe_architecture', 'has_architecture', '_parse_project_godot', 'snapshot_files',
}


def run_operation(modules, case, root, sandbox):
    tools, actions = modules['project_tools'], modules['project_settings_actions']
    trust = case.get('trust', 'valid')
    flags = {'allow_addons': case.get('allow_addons', False),
             'allow_self_edit': case.get('allow_self_edit', False),
             'addon_dir': str(root / 'Addons/RenamedWrapper/core') if trust == 'valid'
             else str(root / 'src') if trust == 'invalid' else None}
    kind = case['kind']
    if kind == 'path':
        path = case['path']
        return {'classification': tools.classify_project_path(path, str(root), flags['addon_dir']),
                'read': tools.can_read_project_path(path, str(root), **flags),
                'write': tools.can_write_project_path(path, str(root), **flags),
                'reference': tools.can_reference_project_path(path, str(root), **flags),
                'resolve': attempt(lambda: tools._resolve_safe_path(str(root), path)),
                'policy_read': attempt(lambda: tools.policy_read_project_file(str(root), path, **flags))}
    if kind == 'read':
        function = case['function']
        assert function in READ_CALLS
        kwargs = dict(case.get('kwargs', {}))
        if function in ('policy_read_project_file', 'policy_describe_scene', 'build_project_tree',
                        'build_project_overview', 'search_project_text', 'describe_architecture', 'snapshot_files'):
            kwargs.update(flags)
        return getattr(tools, function)(str(root), *case.get('args', []), **kwargs)
    if kind == 'settings':
        normalized, absolute = actions.normalize_action(str(root), case['action'], **flags)
        prepared = actions.prepare(str(root), case['action'], **flags)
        return {'normalized': normalized, 'project_file': absolute, 'prepared': prepared,
                'public': actions.public_prepared(prepared),
                'reverse_digest': actions.canonical_digest(dict(reversed(list(normalized.items()))))}
    if kind == 'casing':
        mode = case.get('mode', 'rollback')
        source = 'CaseDir/InnerDir/item.txt'
        destination = 'casedir/INNERDIR/item.txt'
        if mode == 'bad_depth':
            return tools.begin_case_only_dir_casing(str(root), source, 'Other/item.txt')
        if mode == 'apply_failure':
            rename, count = os.rename, [0]
            def fail_second(*args):
                count[0] += 1
                if count[0] == 2:
                    raise OSError(errno.EACCES, 'synthetic apply failure')
                return rename(*args)
            with patch.object(os, 'rename', fail_second):
                return tools.begin_case_only_dir_casing(str(root), source, destination)
        transaction = tools.begin_case_only_dir_casing(str(root), source, destination)
        middle = snapshot(sandbox)
        if mode == 'rollback_failure':
            def failed(*args):
                raise OSError(errno.EACCES, 'synthetic rollback failure')
            with patch.object(os, 'rename', failed):
                failure = attempt(transaction.rollback)
            transaction.rollback()
        elif mode == 'commit':
            failure = None
            transaction.commit()
            transaction.commit()
            transaction.rollback()
        else:
            failure = None
            transaction.rollback()
            transaction.rollback()
        return {'middle': middle, 'state': transaction.state, 'renames': transaction.renames,
                'rollback_succeeded': transaction.rollback_succeeded,
                'failed_renames': transaction.failed_renames, 'failure': failure}
    if kind == 'symlink_capability':
        link = root / 'symbolic_link'
        os.symlink(root / 'src', link, target_is_directory=True)
        try:
            return {'created': True, 'read': tools.can_read_project_path('res://symbolic_link/public.gd', str(root))}
        finally:
            link.unlink()
    raise AssertionError('unknown whitelisted operation')

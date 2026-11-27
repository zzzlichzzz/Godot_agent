"""Offline PyInstaller onefile build; all work/spec output is external."""
import argparse
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--work',required=True)
    parser.add_argument('--candidate',action='store_true',help='Keep the executable under WORK/dist for verification')
    args=parser.parse_args();work=Path(args.work).absolute()
    if ROOT==work or ROOT in work.parents:parser.error('Build work must be external')
    if work.exists():parser.error('Use a fresh external build directory')
    import PyInstaller  # Availability check only. Never installs/downloads dependencies.
    work.mkdir(parents=True)
    command=['--onefile','--noupx','--collect-submodules','selenium',
        '--name','godot_agent_server','--distpath',str(work/'dist' if args.candidate else ROOT/'python/dist'),
        '--workpath',str(work/'work'),'--specpath',str(work),'--paths',str(ROOT)]
    for path in sorted((ROOT/'python').rglob('*.py')):
        rel=path.relative_to(ROOT)
        if 'tests' in rel.parts or 'dist' in rel.parts or '__pycache__' in rel.parts:continue
        command+=['--add-data',str(path)+os.pathsep+str(rel.parent)]
        command+=['--hidden-import','.'.join(rel.with_suffix('').parts)]
    for name in ('core/project_file_io','core/structural_overlay','core/resource_publication_observer',
                 'native/agent_scene_executor','native/agent_resource_executor','native/agent_project_settings_executor'):
        path=Path('editor')/(name+'.gd');command+=['--add-data',str(ROOT/path)+os.pathsep+str(path.parent)]
    command+=['--add-data',str(ROOT/'contract/capabilities')+os.pathsep+'contract/capabilities',
              '--add-data',str(ROOT/'agent_api_cache')+os.pathsep+'agent_api_cache',
              str(ROOT/'python/channels/http/exe_entry.py')]
    from PyInstaller.__main__ import run
    run(command)  # Python API avoids Windows' command-line length limit; no shell.
    return 0

if __name__=='__main__':raise SystemExit(main())

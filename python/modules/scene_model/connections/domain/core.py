"""Raw fields plus literal display rows; no handler validation or project IO."""
from python.formats import tscn


def describe(raw):
    text=raw.decode('utf-8-sig',errors='replace').replace('\r\n','\n').replace('\r','\n')
    connections=tscn.fields(text)[2]
    rows=tscn.rows(text)
    if not rows['nodes']:
        raise ValueError('В файле не найдено ни одного узла [node].')
    display=rows['connections']
    lines=[]
    for link in display:
        frm=link['from'] if link['from'] not in ('','.') else '<root>'
        to=link['to'] if link['to'] not in ('','.') else '<root>'
        lines.append('- %s.%s -> %s.%s()'%(frm,link['signal'],to,link['method']))
    return {'connections':connections,'text':'\n'.join(lines)}

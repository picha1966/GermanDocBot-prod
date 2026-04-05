import urllib.request, json, sys

url = 'https://germandocbot.ngrok.app/api/form-schema?doc_type=buergergeld&lang=uk'
with urllib.request.urlopen(url, timeout=15) as r:
    s = json.load(r)

for sec in s['sections']:
    sys.stdout.buffer.write(('SECTION: ' + sec['id'] + '\n').encode('utf-8'))
    for f in sec.get('fields', []):
        lbl_uk = f.get('label_uk') or ''
        lbl_de = f.get('label_de') or ''
        vis    = f.get('visible_if')
        vis_str = ' [if ' + str(vis) + ']' if vis else ''
        line = '  {:40s} type={:8s} de={!r:30s} uk={!r}{}\n'.format(
            f['name'], f['type'], lbl_de, lbl_uk, vis_str)
        sys.stdout.buffer.write(line.encode('utf-8'))

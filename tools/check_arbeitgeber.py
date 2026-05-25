import subprocess, sys
result = subprocess.run(['git', 'show', 'HEAD:backend/document_config.py'], capture_output=True)
text = result.stdout.decode('utf-8')
lines = text.splitlines()

# Find arbeitgeber section in BUERGERGELD_SCHEMA
print("=== arbeitgeber in schema ===")
for i, l in enumerate(lines):
    if 'arbeitgeber' in l and 'title_key' in l:
        for j in range(i, min(i+15, len(lines))):
            sys.stdout.buffer.write((lines[j] + '\n').encode('utf-8'))
        break

# Check JOBCENTER_ACROFORM_MAPPING for employer fields
print("\n=== employer* in JOBCENTER_ACROFORM_MAPPING ===")
in_jc = False
for i, l in enumerate(lines):
    if 'JOBCENTER_ACROFORM_MAPPING' in l and 'Dict' in l:
        in_jc = True
    if in_jc and ('employer' in l):
        sys.stdout.buffer.write((str(i+1) + ' ' + l + '\n').encode('utf-8'))
    if in_jc and l.strip() == '}':
        in_jc = False

# Check what is in the arbeitgeber section fields in schema
print("\n=== arbeitgeber section full detail ===")
in_arb = False
brace_depth = 0
for i, l in enumerate(lines):
    if 'arbeitgeber' in l and 'title_key' in l:
        in_arb = True
    if in_arb:
        sys.stdout.buffer.write((lines[i] + '\n').encode('utf-8'))
        # detect end of this section dict
        if i > 0 and lines[i].strip() in (']},', ']},'):
            break

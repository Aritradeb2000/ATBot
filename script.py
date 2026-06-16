import json
with open(r'C:\Users\aritrad\.gemini\antigravity-ide\brain\0b1ba864-0f49-4973-ae45-77c67342e659\.system_generated\logs\transcript.jsonl', encoding='utf-8') as f:
    lines = f.readlines()
content = []
capturing = False
for line in reversed(lines):
    if 'view_file' in line and 'implementation_plan.md' in line and 'response' in line:
        d = json.loads(line)
        out = d.get('content', '')
        if out:
            # Extract from output
            lines_out = out.split('\n')
            for l in lines_out:
                if l.startswith('The following code has been modified') or l.startswith('File Path:'): continue
                if ':' in l:
                    try:
                        int(l.split(':')[0])
                        content.append(l.split(':', 1)[1].lstrip(' '))
                    except:
                        pass
            if content:
                content.reverse()
                with open(r'C:\Users\aritrad\.gemini\antigravity-ide\brain\0b1ba864-0f49-4973-ae45-77c67342e659\implementation_plan.md', 'w', encoding='utf-8') as f2:
                    f2.write('\n'.join(content))
                print('Restored from view_file')
                exit(0)


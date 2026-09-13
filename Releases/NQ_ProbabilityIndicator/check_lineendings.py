#!/usr/bin/env python3
"""Check and fix CRLF line endings"""

import os

folder = r'f:\Trading Software\MGEQuant\Releases\NQ_ProbabilityIndicator'

for filename in os.listdir(folder):
    if filename.endswith('.py') or filename.endswith('.cs'):
        filepath = os.path.join(folder, filename)
        with open(filepath, 'rb') as f:
            content = f.read()
        
        crlf = content.count(b'\r\n')
        lf = content.count(b'\n') - crlf
        cr = content.count(b'\r') - crlf
        
        print(f"{filename}: CRLF={crlf}, LF={lf}, CR={cr}")
        
        # Fix: convert all to CRLF for Windows
        if lf > 0 and crlf == 0:
            print(f"  -> Converting LF to CRLF for {filename}")
            content = content.replace(b'\n', b'\r\n')
            with open(filepath, 'wb') as f:
                f.write(content)
            print(f"  -> Fixed!")

print("\nDone!")

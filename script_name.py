import os
import re

# Comprehensive regex to match emojis and emoji presentation selectors:
# - Supplementary Multilingual Plane (U+10000 - U+10FFFF): 🚀, 🧠, 🛑, 🎯, 🟢, 🔴, 📁, 📈, 📉, 🤖, etc.
# - Miscellaneous Symbols & Dingbats (U+2600 - U+27BF): ⚠️, ⚡, ⚖️, ✅, ❌, etc.
# - Miscellaneous Technical (U+2300 - U+23FF): ⏰, ⏱️, ⏳, etc.
# - Stars & Circles (U+2B50, U+2B55): ⭐, ⭕, etc.
# - Variation selectors (U+FE0E - U+FE0F), Zero-width joiner (U+200D), Keycap (U+20E3)
# Also consumes trailing horizontal whitespace ([ \t]*) so no orphaned leading space remains in strings.
EMOJI_PATTERN = re.compile(
    r'['
    r'\U00010000-\U0010ffff'
    r'\u2600-\u27bf'
    r'\u2300-\u23ff'
    r'\u2b50\u2b55'
    r'\ufe0e\ufe0f'
    r'\u200d'
    r'\u20e3'
    r']+[ \t]*',
    flags=re.UNICODE
)

def remove_emojis_from_file(file_path):
    # Only target actual source code, text, or configuration files
    allowed_extensions = {'.py', '.json', '.md', '.txt', '.yaml', '.yml', '.ini', '.csv'}
    _, ext = os.path.splitext(file_path.lower())
    
    if ext not in allowed_extensions:
        return

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        clean_content = EMOJI_PATTERN.sub('', content)
        
        if content != clean_content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(clean_content)
            print(f"Cleaned: {file_path}")
            
    except Exception as e:
        print(f"Error processing {file_path}: {e}")

def clean_backend_folder(folder_name='backend'):
    # Support relative paths whether run from repo root or elsewhere
    if not os.path.exists(folder_name):
        candidate = os.path.join(os.path.dirname(os.path.abspath(__file__)), folder_name)
        if os.path.exists(candidate):
            folder_name = candidate
        else:
            print(f"Error: Folder '{folder_name}' not found.")
            return

    for root, dirs, files in os.walk(folder_name):
        # Proactively skip __pycache__ and hidden system directories
        dirs[:] = [d for d in dirs if d != '__pycache__' and not d.startswith('.')]
        
        for file in files:
            file_path = os.path.join(root, file)
            remove_emojis_from_file(file_path)

if __name__ == "__main__":
    clean_backend_folder()

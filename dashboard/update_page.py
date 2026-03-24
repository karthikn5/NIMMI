import os

filepath = r"c:\Users\karth\.gemini\antigravity\scratch\nimmi-ai\dashboard\src\app\dashboard\builder\[id]\page.tsx"
with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

target = '<option value="gemini-2.0-flash-001" className="bg-[#111]">Gemini 2.0 Flash (Latest / Free)</option>'
replacement = '<option value="gemini-3-flash-preview" className="bg-[#111]">Gemini 3 Flash Preview (Experimental)</option>\n                                                         <option value="gemini-2.0-flash-001" className="bg-[#111]">Gemini 2.0 Flash (Latest / Free)</option>'

if target in content:
    new_content = content.replace(target, replacement)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(new_content)
    print("Successfully updated page.tsx")
else:
    print("Target string not found in page.tsx")

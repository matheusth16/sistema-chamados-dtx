import re

print('Replacing nav block in base.html')

with open('app/templates/base.html', 'r', encoding='utf-8') as f:
    text = f.read()

# Make a backup
with open('app/templates/base.html.bak', 'w', encoding='utf-8') as f:
    f.write(text)

# Replace <nav> to </nav>
pattern = re.compile(r'<nav class="bg-\[#1a305d\].*?</nav>', re.DOTALL)

new_text = pattern.sub('{% include "components/navbar.html" %}', text)

# Update Javascript functions for animations in base.html
to_replace = {
    "dropdown.classList.remove('opacity-0', 'invisible');": "dropdown.classList.remove('opacity-0', 'invisible', 'scale-95', 'translate-y-2');",
    "dropdown.classList.add('opacity-100', 'visible');": "dropdown.classList.add('opacity-100', 'visible', 'scale-100', 'translate-y-0');",
    "dropdown.classList.add('opacity-0', 'invisible');": "dropdown.classList.add('opacity-0', 'invisible', 'scale-95', 'translate-y-2');",
    "dropdown.classList.remove('opacity-100', 'visible');": "dropdown.classList.remove('opacity-100', 'visible', 'scale-100', 'translate-y-0');",
    
    "menu.classList.remove('opacity-0', 'invisible');": "menu.classList.remove('opacity-0', 'invisible', 'scale-95', 'translate-y-2'); menu.parentElement.dataset.open = 'true';",
    "menu.classList.add('opacity-100', 'visible');": "menu.classList.add('opacity-100', 'visible', 'scale-100', 'translate-y-0');",
    "menu.classList.add('opacity-0', 'invisible');": "menu.classList.add('opacity-0', 'invisible', 'scale-95', 'translate-y-2'); menu.parentElement.dataset.open = 'false';",
    "menu.classList.remove('opacity-100', 'visible');": "menu.classList.remove('opacity-100', 'visible', 'scale-100', 'translate-y-0');"
}

for old, new_js in to_replace.items():
    new_text = new_text.replace(old, new_js)
    
with open('app/templates/base.html', 'w', encoding='utf-8') as f:
    f.write(new_text)

print('Success')

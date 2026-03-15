import subprocess
repo = r"C:/Users/COY/Downloads/PROYECTO/Proyecto-html/PRoyecto django/Proyecto-html"
paths = [
    r"PRoyecto django/Proyecto-html/SENNOVA/urls.py",
    r"PRoyecto django/Proyecto-html/Gesicom/templates/home.html",
    r"PRoyecto django/Proyecto-html/Gesicom/views.py",
]
for path in paths:
    print('\n--- DIFF', path)
    p = subprocess.run(['git','-C',repo,'diff','--',path], capture_output=True, text=True)
    print(p.stdout)

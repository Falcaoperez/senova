import subprocess, sys
repo = r"C:/Users/COY/Downloads/PROYECTO/Proyecto-html/PRoyecto django/Proyecto-html"
msg = "Fix: normalize app names, add register logs and success flow, add test/cleanup scripts, allow testserver in ALLOWED_HOSTS"
print('Running git add -A')
res = subprocess.run(['git','-C',repo,'add','-A'], capture_output=True, text=True)
print(res.stdout, res.stderr)
print('Running git commit')
res = subprocess.run(['git','-C',repo,'commit','-m',msg], capture_output=True, text=True)
print(res.stdout, res.stderr)
sys.exit(res.returncode)

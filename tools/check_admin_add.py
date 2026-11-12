import urllib.request, urllib.error

url = 'http://127.0.0.1:8000/admin/users/club/add/'
try:
    req = urllib.request.Request(url)
    resp = urllib.request.urlopen(req, timeout=10)
    print('STATUS', resp.getcode())
    body = resp.read(1024).decode('utf-8', errors='ignore')
    print(body[:800])
except urllib.error.HTTPError as e:
    print('HTTPERR', e.code)
    try:
        print(e.read(1024).decode('utf-8', errors='ignore')[:800])
    except:
        pass
except Exception as e:
    print('ERR', repr(e))

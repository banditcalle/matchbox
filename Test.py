import socket, requests

host = "avegagroup.crm4.dynamics.com"  # er instans utan https://
api  = f"https://{host}/api/data/v9.2/"

try:
    ip = socket.gethostbyname(host)
    print("✔ DNS fungerar:", host, "→", ip)
except Exception as e:
    print("✘ DNS misslyckades:", e)
    exit(1)

try:
    r = requests.get(api, timeout=5)
    print("✔ HTTP-statuskod:", r.status_code, 
          "(401 eller 403 betyder hosten är korrekt men ingen token skickades)")
except Exception as e:
    print("✘ HTTPS-anslutning misslyckades:", e)
    exit(1)

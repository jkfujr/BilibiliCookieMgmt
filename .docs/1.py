import urllib.request
import urllib.parse
import urllib.error
import json

BASE_URL = "http://10.0.0.101:18000"
TOKEN = "1145141919810"

def request(path, params=None, timeout=5):
    url = urllib.parse.urljoin(BASE_URL, path)
    if params:
        qs = urllib.parse.urlencode(params)
        url = url + ("&" if "?" in url else "?") + qs
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {TOKEN}",
        "User-Agent": "CookieAPI-Test/1.0"
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.getcode(), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        return None, str(e).encode()

def print_json(tag, status, data):
    try:
        obj = json.loads(data.decode())
        print(f"{tag} {status} {json.dumps(obj, ensure_ascii=False)}")
    except Exception:
        print(f"{tag} {status} {data[:200].decode(errors='ignore')}\n")

def main():
    s, d = request("/api/v1/health")
    print_json("HEALTH", s, d)

    s, d = request("/api/v1/cookies/")
    if s == 200:
        obj = json.loads(d.decode())
        total = len(obj) if isinstance(obj, list) else 0
        enabled_valid = 0
        if isinstance(obj, list):
            for item in obj:
                m = item.get("managed", {})
                if m.get("is_enabled") and m.get("status") == "valid":
                    enabled_valid += 1
        print(f"COOKIES 200 total={total} enabled_valid={enabled_valid}")
    else:
        print_json("COOKIES", s, d)

    s, d = request("/api/v1/cookies/random", {"format": "simple"})
    if s == 200:
        obj = json.loads(d.decode())
        duid = obj.get("DedeUserID")
        hs = obj.get("header_string")
        head = hs[:120] if isinstance(hs, str) else ""
        print(f"RANDOM 200 DedeUserID={duid} header_string={head}")
    else:
        print_json("RANDOM", s, d)

if __name__ == "__main__":
    main()


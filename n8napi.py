import uc_config as cfg
import json, os, subprocess, urllib.request, uuid
BASE = "http://localhost:5678/api/v1"
def _key():
    k = os.environ.get("N8N_API_KEY")
    if not k:
        k = subprocess.run(["powershell", "-NoProfile", "-Command",
            "[Environment]::GetEnvironmentVariable('N8N_API_KEY','User')"], capture_output=True, text=True).stdout.strip()
    return k
KEY = _key()
def api(method, path, body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
        headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            t = r.read().decode("utf-8")
            return json.loads(t) if t else {}
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{method} {path} -> {e.code}: {e.read().decode('utf-8')[:800]}")
def uid(): return str(uuid.uuid4())
NOTION = {"notionApi": cfg.n8n_cred("notionApi", "Notion account")}
GEMINI = {"googlePalmApi": cfg.n8n_cred("googlePalmApi", "Google Gemini(PaLM) Api account")}
APPKEY = {"httpHeaderAuth": cfg.n8n_cred("httpHeaderAuth", "Copilot web app key")}
DRIVE = {"googleDriveOAuth2Api": cfg.n8n_cred("googleDriveOAuth2Api", "Google Drive account")}
LMSTUDIO ={"openAiApi": cfg.n8n_cred("openAiApi", "LM Studio (local)")}

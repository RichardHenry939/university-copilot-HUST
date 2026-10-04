"""Move specific Notion pages to trash (recoverable) via a temporary n8n workflow using the existing Notion credential."""
import json, sys, time, urllib.request
from n8napi import *
ids = sys.argv[1:]
wf = {"name": "ZZ archive (temp, Claude)", "settings": {"executionOrder": "v1"},
 "nodes": [
  {"id": uid(), "name": "Hook", "type": "n8n-nodes-base.webhook", "typeVersion": 2, "position": [0,0], "webhookId": uid(),
   "parameters": {"path": "zz-archive-claude", "httpMethod": "POST", "responseMode": "lastNode", "options": {}}},
  {"id": uid(), "name": "Split", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [200,0],
   "parameters": {"jsCode": "return ($json.body.ids||[]).map(id=>({json:{id}}));"}},
  {"id": uid(), "name": "Archive", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": [400,0],
   "parameters": {"method": "PATCH", "url": "=https://api.notion.com/v1/pages/{{ $json.id }}", "authentication": "predefinedCredentialType",
     "nodeCredentialType": "notionApi", "sendBody": True, "contentType": "raw", "rawContentType": "application/json",
     "body": "{\"archived\": true}", "options": {}}, "credentials": NOTION},
  {"id": uid(), "name": "Out", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [600,0],
   "parameters": {"jsCode": "return [{json:{archived: $input.all().map(i=>({id:i.json.id, archived:i.json.archived}))}}];"}}],
 "connections": {"Hook": {"main": [[{"node": "Split", "type": "main", "index": 0}]]}, "Split": {"main": [[{"node": "Archive", "type": "main", "index": 0}]]},
                 "Archive": {"main": [[{"node": "Out", "type": "main", "index": 0}]]}}}
wid = api("POST", "/workflows", wf)["id"]
try:
    api("POST", f"/workflows/{wid}/activate"); time.sleep(1.5)
    req = urllib.request.Request("http://localhost:5678/webhook/zz-archive-claude", data=json.dumps({"ids": ids}).encode(), headers={"Content-Type": "application/json"})
    print(urllib.request.urlopen(req, timeout=60).read().decode())
finally:
    api("POST", f"/workflows/{wid}/deactivate"); api("DELETE", f"/workflows/{wid}")

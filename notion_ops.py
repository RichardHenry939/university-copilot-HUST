# -*- coding: utf-8 -*-
"""Gọi Notion API bằng credential Notion của n8n (workflow tạm, xoá ngay sau khi dùng). Claude 2026-10-03.
Dùng khi cần đọc/ghi Notion hàng loạt từ máy (Notion MCP của Claude có hạn mức truy vấn).

    from notion_ops import NotionOps
    with NotionOps() as n:
        rows = n.query_all(db_id, filter={...})
        n.run([{"method": "PATCH", "url": ".../pages/<id>", "body": {...}}])
"""
import json, time, urllib.request
from n8napi import api, uid, NOTION

class NotionOps:
    PATH = "zz-notion-ops-claude"

    def __enter__(self):
        wf = {"name": "ZZ notion ops (temp, Claude)", "settings": {"executionOrder": "v1"},
              "nodes": [
                {"id": uid(), "name": "Hook", "type": "n8n-nodes-base.webhook", "typeVersion": 2, "position": [0, 0], "webhookId": uid(),
                 "parameters": {"path": self.PATH, "httpMethod": "POST", "responseMode": "lastNode", "options": {}}},
                {"id": uid(), "name": "Split", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [200, 0],
                 "parameters": {"jsCode": "return ($json.body.ops||[]).map(o=>({json:{method:o.method,url:o.url,body:JSON.stringify(o.body||{})}}));"}},
                {"id": uid(), "name": "Notion", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": [400, 0],
                 "parameters": {"method": "={{ $json.method }}", "url": "={{ $json.url }}", "authentication": "predefinedCredentialType",
                                "nodeCredentialType": "notionApi", "sendBody": True, "contentType": "raw", "rawContentType": "application/json",
                                "body": "={{ $json.body }}",
                                "options": {"batching": {"batch": {"batchSize": 3, "batchInterval": 1200}},
                                            "response": {"response": {"neverError": True, "fullResponse": True}}}},
                 "credentials": NOTION},
                {"id": uid(), "name": "Out", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [600, 0],
                 "parameters": {"jsCode": "return [{json:{res:$input.all().map(i=>({code:i.json.statusCode, body:i.json.body}))}}];"}}],
              "connections": {"Hook": {"main": [[{"node": "Split", "type": "main", "index": 0}]]},
                              "Split": {"main": [[{"node": "Notion", "type": "main", "index": 0}]]},
                              "Notion": {"main": [[{"node": "Out", "type": "main", "index": 0}]]}}}
        self.wid = api("POST", "/workflows", wf)["id"]
        api("POST", f"/workflows/{self.wid}/activate"); time.sleep(1.5)
        return self

    def __exit__(self, *a):
        api("POST", f"/workflows/{self.wid}/deactivate"); api("DELETE", f"/workflows/{self.wid}")

    def run(self, ops):
        req = urllib.request.Request(f"http://localhost:5678/webhook/{self.PATH}", data=json.dumps({"ops": ops}).encode(),
                                     headers={"Content-Type": "application/json"})
        return json.loads(urllib.request.urlopen(req, timeout=900).read().decode())["res"]

    def query_all(self, db, filter=None, sorts=None):
        out, cursor = [], None
        while True:
            body = {"page_size": 100}
            if filter: body["filter"] = filter
            if sorts: body["sorts"] = sorts
            if cursor: body["start_cursor"] = cursor
            r = self.run([{"method": "POST", "url": f"https://api.notion.com/v1/databases/{db}/query", "body": body}])[0]
            if r["code"] != 200: raise RuntimeError(r["body"])
            out += r["body"]["results"]
            if not r["body"].get("has_more"): return out
            cursor = r["body"]["next_cursor"]

def prop(p, name):
    """Đọc giá trị đơn giản của một property Notion."""
    v = p["properties"].get(name)
    if not v: return None
    t = v["type"]
    if t in ("title", "rich_text"): return "".join(x.get("plain_text", "") for x in v[t])
    if t in ("select", "status"): return (v[t] or {}).get("name")
    if t == "number": return v["number"]
    if t == "checkbox": return v["checkbox"]
    if t == "relation": return [x["id"] for x in v["relation"]]
    if t == "date": return (v["date"] or {}).get("start")
    if t == "formula": return v["formula"].get(v["formula"]["type"])
    return None

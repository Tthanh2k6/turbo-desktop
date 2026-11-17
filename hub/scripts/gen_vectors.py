"""Writes android/app/src/test/resources/vectors.json: signatures made by the HUB's crypto code, which the Android
unit tests must verify (and the canonical strings they must reproduce byte for byte). Re-run when the wire format changes.
    hub\\.venv\\Scripts\\python hub\\scripts\\gen_vectors.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from turbo_hub import crypto  # noqa: E402

key = crypto.generate_key()
pub = crypto.pub_to_b64(key.public_key())
body = '{"text":"mở Máy tính"}'.encode()
req = crypto.canonical_request("post", "/tasks?x=1", body, "1800000000", "abc123nonce")
resp_body = b'{"ok":true}'
resp = crypto.canonical_response(200, "/tasks?x=1", resp_body, "1800000001", "abc123nonce")
payload = '{"seq":7,"type":"text","text":"xin chào"}'
evt = crypto.canonical_event(payload)
out = {
    "pub": pub, "deviceId": crypto.device_id_for(pub), "fingerprint": crypto.fingerprint(pub),
    "request": {"method": "post", "path": "/tasks?x=1", "body": body.decode(), "ts": "1800000000", "nonce": "abc123nonce",
                "canonical": req.decode(), "sig": crypto.sign(key, req), "bodySha256": crypto.sha256_hex(body)},
    "response": {"status": 200, "path": "/tasks?x=1", "body": resp_body.decode(), "ts": "1800000001", "nonce": "abc123nonce",
                 "canonical": resp.decode(), "sig": crypto.sign(key, resp)},
    "event": {"payload": payload, "canonical": evt.decode(), "sig": crypto.sign(key, evt)},
}
dest = Path(__file__).resolve().parents[2] / "android" / "app" / "src" / "test" / "resources" / "vectors.json"
dest.parent.mkdir(parents=True, exist_ok=True)
dest.write_text(json.dumps(out, indent=2, ensure_ascii=False), "utf-8")
print("wrote", dest)

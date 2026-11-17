import json
from pathlib import Path

import pytest

from turbo_hub import crypto

VEC = Path(__file__).resolve().parents[2] / "android" / "app" / "build" / "test-vectors" / "kotlin_vector.json"


@pytest.mark.skipif(not VEC.exists(), reason="run android :app:testDebugUnitTest first")
def test_hub_verifies_signature_made_by_android_jvm_code():
    v = json.loads(VEC.read_text("utf-8"))
    pub = crypto.pub_from_b64(v["pub"])
    assert crypto.verify(pub, v["canonical"].encode(), v["sig"])
    assert not crypto.verify(pub, v["canonical"].encode() + b"x", v["sig"])
    assert v["canonical"] == str(crypto.canonical_request("GET", "/status", b"", "1800000000", "n1"), "utf-8")

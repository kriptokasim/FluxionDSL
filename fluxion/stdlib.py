from __future__ import annotations
import time, json
from typing import Any, Dict, Optional
import requests

def _to_headers(h: Optional[Dict[str, Any]]):
    if not h: return {}
    # stringleştir
    return {str(k): str(v) for k, v in h.items()}

def http_get(url: str, headers: Optional[Dict[str, Any]] = None, timeout: float = 10.0) -> Dict[str, Any]:
    t0 = time.perf_counter()
    try:
        r = requests.get(url, headers=_to_headers(headers), timeout=timeout, allow_redirects=True)
        body = r.text if r.encoding else r.content[:4096].decode(errors="replace")
        return {
            "ok": r.ok,
            "status": r.status_code,
            "length": len(r.content),
            "elapsed_ms": int((time.perf_counter() - t0) * 1000),
            "headers": dict(r.headers),
            "text_preview": body[:512],
            "url": r.url,
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "elapsed_ms": int((time.perf_counter() - t0) * 1000), "url": url}

def http_head(url: str, headers: Optional[Dict[str, Any]] = None, timeout: float = 10.0) -> Dict[str, Any]:
    t0 = time.perf_counter()
    try:
        r = requests.head(url, headers=_to_headers(headers), timeout=timeout, allow_redirects=True)
        return {
            "ok": r.ok,
            "status": r.status_code,
            "elapsed_ms": int((time.perf_counter() - t0) * 1000),
            "headers": dict(r.headers),
            "url": r.url,
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "elapsed_ms": int((time.perf_counter() - t0) * 1000), "url": url}

def sleep(sec: float) -> int:
    time.sleep(max(0.0, float(sec)))
    return int(sec)

def join(a: Any, b: Any) -> str:
    # kolay string birleştirme (DSL içinde "http://" + host + "/x" vs.)
    return str(a) + str(b)

def oast_http_ping(base_host: str, token: str) -> Dict[str, Any]:
    """
    Basit HTTP ping OAST — DNS tetiklemek için base_host altında HTTP GET atar.
    Örn: http://<oast>/t/<token>?r=123
    """
    url = f"http://{base_host.strip('/')}/t/{token}"
    return http_get(url)

def jsonify(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False)  # DSL çıktısında debug için
    except Exception as e:
        return f"<json-error: {e}>"

# export edilecek tablo
FUNCS: Dict[str, Any] = {
    "http_get": http_get,
    "http_head": http_head,
    "sleep": sleep,
    "join": join,
    "oast_http_ping": oast_http_ping,
    "jsonify": jsonify,
}

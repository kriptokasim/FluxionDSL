# fluxion/runtime/runner_v2.py
from __future__ import annotations
from typing import Any, Dict, List, Optional

import json
import time
import socket
from urllib.parse import urlencode

import requests
from lark import Tree
from fluxion.core.parser import parse  # AST Lark Tree'lerini üreten parse

# ============================================================
# Yardımcı sinyaller / tipler
# ============================================================

class _ReturnSignal:
    def __init__(self, value: Any):
        self.value = value

Scope = Dict[str, Any]

# Bazı sabitler
BOOLS = {"true": True, "false": False, "null": None, "nil": None}

# ============================================================
# Stdlib (minimal)
# ============================================================

def _interpolate_string(raw: str, scope: Scope) -> str:
    """
    "X={{1}} {{x}}" gibi çift süslü parantez içi ifadeleri basitçe değerlendir.
    - Sadece basit sabitler (int/float), bools ve değişken isimleri desteklenir.
    """
    import re

    def repl(m):
        expr = m.group(1).strip()
        # bools
        if expr in BOOLS:
            v = BOOLS[expr]
            return "" if v is None else str(v)
        # scope var
        if expr in scope:
            v = scope[expr]
            return "" if v is None else str(v)
        # sayılar
        try:
            return str(int(expr))
        except Exception:
            pass
        try:
            return str(float(expr))
        except Exception:
            pass
        # bilinmiyorsa None gibi davran
        return "" if scope.get(expr) is None else str(scope.get(expr))

    # Çift/single tırnakları soyup çalış
    s = raw
    if isinstance(s, str) and len(s) >= 2 and ((s[0] == '"' and s[-1] == '"') or (s[0] == "'" and s[-1] == "'")):
        s = s[1:-1]
    return re.sub(r"\{\{([^}]+)\}\}", repl, s)


def _make_echo(scope: Scope):
    def _echo(**kwargs):
        # args'ı interpolate edip sakla
        args_cooked = {}
        for k, v in kwargs.items():
            if isinstance(v, str):
                args_cooked[k] = _interpolate_string(v, scope)
            else:
                args_cooked[k] = v
        scope["_last_command"] = {"name": "echo", "args": args_cooked}
        return None
    return _echo


def jsonify(*args, **kwargs):
    """
    JSON üretir. Hem kwargs (jsonify(a=1)) hem de tek positional payload (jsonify({"a":1}))
    desteği var. Birden çok positional verilirse ilk dict/list’i alır.
    """
    payload = None
    if kwargs:
        payload = kwargs
    elif args:
        for a in args:
            if isinstance(a, (dict, list)):
                payload = a
                break
    if payload is None and args:
        # Fallback: ilk arg'ı stringle
        payload = args[0]
    return json.dumps(payload, ensure_ascii=False)

def join(*args):
    return "".join(str(a) for a in args)

def _http_head_impl(url: str, timeout: float = 5.0, allow_redirects: bool = True, verify: bool = False):
    try:
        t0 = time.time()
        r = requests.head(url, timeout=timeout, allow_redirects=allow_redirects, verify=verify)
        elapsed_ms = int((time.time() - t0) * 1000)
        return {
            "ok": r.ok,
            "status": r.status_code,
            "elapsed_ms": elapsed_ms,
            "length": int(r.headers.get("Content-Length", 0)),
            "headers": dict(r.headers),
        }
    except Exception as e:
        return {"ok": False, "status": 0, "elapsed_ms": 0, "length": 0, "error": str(e), "headers": {}}
        
def _http_get_impl(url: str, timeout: float = 5.0, allow_redirects: bool = True, verify: bool = False, preview: int = 512):
    try:
        t0 = time.time()
        r = requests.get(url, timeout=timeout, allow_redirects=allow_redirects, verify=verify)
        elapsed_ms = int((time.time() - t0) * 1000)
        text_preview = r.text[:preview] if isinstance(r.text, str) else ""
        return {
            "ok": r.ok,
            "status": r.status_code,
            "elapsed_ms": elapsed_ms,
            "length": len(r.content or b""),
            "text_preview": text_preview,
            "headers": dict(r.headers),
        }
    except Exception as e:
        return {"ok": False, "status": 0, "elapsed_ms": 0, "length": 0, "text_preview": "", "error": str(e), "headers": {}}

def length(value):
    try:
        return len(value)
    except Exception:
        return 0

# Minimal http_* dummy’leri
def http_head(*args, **kwargs):
    """
    Hem call hem command tarzında çalışsın diye argümanları esnek alıyoruz.
    http_head("http://x")  ya da  http_head url="http://x"  şeklinde.
    """
    url = None
    if "url" in kwargs:
        url = kwargs["url"]
    elif args:
        url = args[0]
    if not url:
        return {"ok": False, "status": 0, "elapsed_ms": 0, "length": 0, "error": "missing url", "headers": {}}
    return _http_head_impl(str(url), timeout=float(kwargs.get("timeout", 5.0)))

def http_get(*args, **kwargs):
    url = None
    if "url" in kwargs:
        url = kwargs["url"]
    elif args:
        url = args[0]
    if not url:
        return {"ok": False, "status": 0, "elapsed_ms": 0, "length": 0, "text_preview": "", "error": "missing url", "headers": {}}
    return _http_get_impl(str(url), timeout=float(kwargs.get("timeout", 5.0)))

def oast_beacon(*args, **kwargs):
    """
    OAST’e DNS + HTTP sinyali yollar.
    Kullanım:
      oast_beacon sub="123", domain="abcd.oast.pro", path="/x", q={t: token}
    veya
      oast_beacon "123" "abcd.oast.pro" "/x"
    """
    positional = list(args)
    params: Dict[str, Any] = {}

    if positional and isinstance(positional[0], dict):
        params.update({str(k): v for k, v in positional[0].items()})
        positional = positional[1:]

    params.update({str(k): v for k, v in kwargs.items()})

    sub = params.get("sub") or (str(positional[0]) if len(positional) > 0 else None)
    domain = params.get("domain") or (str(positional[1]) if len(positional) > 1 else None)
    path = params.get("path") or (str(positional[2]) if len(positional) > 2 else "/")
    scheme = params.get("scheme", "http")
    q = params.get("q", None)
    timeout = float(params.get("timeout", 5.0))

    if not sub or not domain:
        return {"ok": False, "error": "missing sub or domain"}

    fqdn = f"{sub}.{domain}".strip(".")
    # DNS ping (hata verse de önemli değil; sadece sorgu tetiklesin)
    try:
        socket.getaddrinfo(fqdn, 80)
    except Exception:
        pass

    url = f"{scheme}://{fqdn}{path}"
    if isinstance(q, dict) and q:
        url = f"{url}?{urlencode({str(k): str(v) for k, v in q.items()})}"

    try:
        t0 = time.time()
        r = requests.get(url, timeout=timeout, allow_redirects=True, verify=False)
        elapsed_ms = int((time.time() - t0) * 1000)
        return {"ok": r.ok, "status": r.status_code, "elapsed_ms": elapsed_ms, "url": url}
    except Exception as e:
        return {"ok": False, "status": 0, "elapsed_ms": 0, "url": url, "error": str(e)}

STDLIB_FUNCS = {
    "jsonify": jsonify,
    "join": join,
    "len": len,            # küçük ama faydalı
    "http_head": http_head,
    "http_get": http_get,
    "oast_beacon": oast_beacon,
    # "echo" dinamik eklenecek (_make_echo)
}

# ============================================================
# Değer dönüştürücüler
# ============================================================

def _as_bool(v: Any) -> bool:
    return bool(v)

def _is_nullish(v: Any) -> bool:
    return v is None


def _resolve_attr(base: Any, name: str) -> Any:
    """Fetch attribute or mapping entry by name, returning None when missing."""
    if base is None:
        return None
    if isinstance(base, dict):
        return base.get(name)
    if isinstance(base, (list, tuple)) and name.isdigit():
        idx = int(name)
        if 0 <= idx < len(base):
            return base[idx]
        return None
    return getattr(base, name, None)

# ============================================================
# Evaluator
# ============================================================

def _eval_any(node: Any, scope: Scope) -> Any:
    """
    Node olabilir (typ attribute) veya Lark Tree olabilir.
    """
    # BuildAST'ten gelen Node tipi varsa:
    t = getattr(node, "typ", None)
    if t:
        if t == "num":
            return node.value
        if t == "str":
            # Interpolasyon destekleyelim (echo testinde bekleniyor)
            return _interpolate_string(node.value, scope)
        if t == "var":
            name = node.name
            if name in BOOLS:
                return BOOLS[name]
            return scope.get(name)
        if t == "list":
            return [_eval_any(x, scope) for x in node.items]
        if t == "map":
            return {k: _eval_any(v, scope) for k, v in node.items.items()}
        if t == "get":
            base = _eval_any(getattr(node, "obj", None), scope)
            return _resolve_attr(base, node.name)
        if t == "getprop":
            base = _eval_any(getattr(node, "base", None), scope)
            return _resolve_attr(base, node.name)
        if t == "call":
            # Built-in veya kullanıcı fonksiyonu
            fname = node.name
            # Arglar: BuildAST bazı yerlerde raw liste döndürür; burada normalize edip değerlendiririz
            raw_args = node.args or []
            args = []
            for a in raw_args:
                if isinstance(a, Tree):
                    args.extend([_eval_any(c, scope) for c in a.children])
                else:
                    args.append(_eval_any(a, scope))

            # user fn?
            fn = scope.get("__funcs__", {}).get(fname)
            if callable(fn):
                return fn(*args)
            # stdlib?
            fn = scope.get("__stdlib__", {}).get(fname)
            if callable(fn):
                return fn(*args)
            return None
        if t == "command":
            # Komutları _exec_stmt içinde ele alacağız
            return None
        if t == "func":
            # Fonksiyon tanımı _exec_stmt'te işlenecek
            return None
        if t == "assign":
            # Atama _exec_stmt'te
            return None
        if t == "return":
            # Return _exec_stmt'te
            return None
        # Fallback
        return None

    # Tree ise:
    if isinstance(node, Tree):
        return _eval_tree(node, scope)

    # Başka tipler (literal vs.)
    return node


def _eval_tree(t: Tree, scope: Scope) -> Any:
    typ = t.data

    # üst sarmalayıcılar
    if typ in ("program", "start", "stmts", "statements", "block"):
        last = None
        for ch in t.children:
            r = _eval_tree(ch, scope)
            if isinstance(r, _ReturnSignal): 
                return r
            if r is not None: 
                last = r
        return last

    if typ == "stmt":
        return _exec_stmt(t.children[0], scope) if t.children else None

    # expr ağaçları
    if typ in ("coalesce", "nullish_coalesce"):
        if not t.children:
            return None
        val = _eval_any(t.children[0], scope); i = 1
        while i < len(t.children):
            rhs = _eval_any(t.children[i + 1], scope)
            if not _is_nullish(val): 
                return val
            val = rhs; i += 2
        return val

    if typ in ("or_expr", "logical_or"):
        if not t.children:
            return None
        val = _eval_any(t.children[0], scope); i = 1
        while i < len(t.children):
            rhs = _eval_any(t.children[i + 1], scope)
            if _as_bool(val):
                return val
            val = rhs
            i += 2
        return val

    if typ in ("and_expr", "logical_and"):
        if not t.children:
            return None
        val = _eval_any(t.children[0], scope); i = 1
        while i < len(t.children):
            rhs = _eval_any(t.children[i + 1], scope)
            if not _as_bool(val):
                return val
            val = rhs
            i += 2
        return val

    if typ in ("compare", "comparison", "equality"):
        if not t.children:
            return None
        if len(t.children) == 1:
            return _eval_any(t.children[0], scope)
        left = _eval_any(t.children[0], scope); i = 1
        result = True
        while i < len(t.children):
            op = str(t.children[i]); right = _eval_any(t.children[i + 1], scope)
            if   op == "==": ok = (left == right)
            elif op == "!=": ok = (left != right)
            elif op == "<":  ok = (left <  right)
            elif op == "<=": ok = (left <= right)
            elif op == ">":  ok = (left >  right)
            elif op == ">=": ok = (left >= right)
            else: raise RuntimeError(f"Unknown compare op: {op}")
            if not ok:
                return False
            result = ok
            left = right; i += 2
        return result

    if typ in ("sum", "additive"):
        val = _eval_any(t.children[0], scope); i = 1
        while i + 1 < len(t.children):
            op = str(t.children[i]); rhs = _eval_any(t.children[i + 1], scope)
            if   op == "+": val = val + rhs
            elif op == "-": val = val - rhs
            i += 2
        return val

    if typ in ("term", "multiplicative"):
        val = _eval_any(t.children[0], scope); i = 1
        while i + 1 < len(t.children):
            op = str(t.children[i]); rhs = _eval_any(t.children[i + 1], scope)
            if   op == "*": val = val * rhs
            elif op == "/": val = val / rhs
            elif op == "%": val = val % rhs
            i += 2
        return val

    if typ == "ternary":
        if not t.children:
            return None
        cond_val = _eval_any(t.children[0], scope)
        if len(t.children) < 5:
            return cond_val
        true_expr = t.children[2]
        false_expr = t.children[4] if len(t.children) > 4 else None
        return _eval_any(true_expr, scope) if _as_bool(cond_val) else _eval_any(false_expr, scope)

    if typ == "unary":
        if not t.children:
            return None
        if len(t.children) == 1:
            return _eval_any(t.children[0], scope)
        op_token, operand_node = t.children[0], t.children[1]
        val = _eval_any(operand_node, scope)
        op = str(op_token)
        if op == "!":
            return not _as_bool(val)
        if op == "-":
            return -val
        if op == "+":
            return +val
        return val

    if typ == "factor" and len(t.children) == 2 and str(t.children[0]) == "-":
        return -_eval_any(t.children[1], scope)

    if typ in ("expr", "atom"):
        if len(t.children) == 1:
            return _eval_any(t.children[0], scope)
        # "( expr )" gibi: ortadakini döndür
        return _eval_any(t.children[-2], scope)

    if typ == "call":
        if not t.children:
            return None
        fname = str(t.children[0])
        arg_nodes = t.children[1:] if len(t.children) > 1 else []
        args = [_eval_any(a, scope) for a in arg_nodes]
        # Kullanıcı fonksiyonu önce
        fn = scope.get("__funcs__", {}).get(fname)
        if callable(fn):
            return fn(*args)
        # stdlib (scope’a eklenen)
        fn = scope.get("__stdlib__", {}).get(fname)
        if callable(fn):
            return fn(*args)
        return None

    if typ == "true_":
        return True
    if typ == "false_":
        return False
    if typ == "null_":
        return None

    # Bilinmiyorsa, çocuk varsa ilkini değerlendir
    if t.children:
        return _eval_any(t.children[0], scope)
    return None


def _exec_block(stmts: List[Any], scope: Scope) -> Optional[Any]:
    for s in stmts:
        r = _exec_stmt(s, scope)
        if isinstance(r, _ReturnSignal):
            return r
    return None


def _exec_stmt(stmt: Any, scope: Scope) -> Optional[Any]:
    # Lark Tree('stmt', ...) ise evaluator’a yönlendir
    if isinstance(stmt, Tree) and getattr(stmt, "data", None) == "stmt":
        return _eval_tree(stmt, scope)

    t = getattr(stmt, "typ", None)

    # -------- atama --------
    if t == "assign":
        name = stmt.name
        val = _eval_any(stmt.expr, scope)
        scope[name] = val
        return None

    # -------- return --------
    if t == "return":
        val = _eval_any(stmt.expr, scope)
        scope["__return__"] = val
        return _ReturnSignal(val)

    # -------- if --------
    if t == "if":
        cond = _eval_any(stmt.cond, scope)
        if _as_bool(cond):
            return _exec_block(stmt.then, scope)
        else:
            if getattr(stmt, "else_", None):
                return _exec_block(stmt.else_, scope)
        return None

    # -------- for --------
    if t == "for":
        it = _eval_any(stmt.iterable, scope)
        if it is None:
            return None
        for v in it:
            scope[stmt.var] = v
            r = _exec_block(stmt.block, scope)
            if isinstance(r, _ReturnSignal):
                return r
        return None

    # -------- func (kullanıcı fonksiyonu tanımı) --------
    if t == "func":
        fname = stmt.name
        params = stmt.params or []
        body = stmt.block or []

        def _fn_impl(*args):
            # Çocuk scope
            child: Scope = {}
            # stdlib ve user funcs chain:
            child["__funcs__"] = scope.get("__funcs__", {})
            child["__stdlib__"] = scope.get("__stdlib__", {})
            # paramları bağla
            for i, p in enumerate(params):
                child[p] = args[i] if i < len(args) else None
            # çalıştır
            r = _exec_block(body, child)
            if isinstance(r, _ReturnSignal):
                return r.value
            return child.get("__return__", None)

        # user funcs tablosuna yaz
        funcs = dict(scope.get("__funcs__", {}))
        funcs[fname] = _fn_impl
        scope["__funcs__"] = funcs
        return None

    # -------- call (bağımsız ifade olarak) --------
    if t == "call":
        return _eval_any(stmt, scope)

    # -------- command --------
    if t == "command":
        # Komutları kwargs olarak topluyordu: stmt.args -> {key: expr_node}
        args = {}
        for k, v in (stmt.args or {}).items():
            args[k] = _eval_any(v, scope)

        # Önce kullanıcı fonksiyonu ismiyle eşleşiyor mu?
        fn = scope.get("__funcs__", {}).get(stmt.name)
        if callable(fn):
            return fn(**args)

        # Sonra stdlib (scope’a yerleştirdiğimiz)
        fn = scope.get("__stdlib__", {}).get(stmt.name)
        if callable(fn):
            return fn(**args)

        return None

    # Tree olarak geldiyse (ör. 'stmt' dışı), evaluator’a
    if isinstance(stmt, Tree):
        return _eval_tree(stmt, scope)

    # başka türler (noop)
    return None


# ============================================================
# Runner
# ============================================================

class RunnerV2:
    def run_text(self, text: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        scope: Scope = {}

        # dışarıdan verilen değişkenler
        if variables:
            scope.update(variables)

        # stdlib'i scope'a koy (echo scope’a bağlı olduğundan burada kur)
        scope["__stdlib__"] = dict(STDLIB_FUNCS)
        scope["__stdlib__"]["echo"] = _make_echo(scope)

        # kullanıcı fonksiyonları için tablo
        scope["__funcs__"] = dict(scope.get("__funcs__", {}))

        # parse
        ast = parse(text)
        if not isinstance(ast, list):
            ast = [ast]

        ret_val: Any = None
        for stmt in ast:
            if isinstance(stmt, Tree):
                r = _eval_tree(stmt, scope)
            else:
                r = _exec_stmt(stmt, scope)
            if isinstance(r, _ReturnSignal):
                ret_val = r.value
                break

        if ret_val is None:
            ret_val = scope.get("__return__", None)

        # Vars: kullanıcıya sadece "görünür" olanlar
        vars_out = {k: v for k, v in scope.items() if not k.startswith("__")}
        return {"return": ret_val, "vars": vars_out}

    def run_file(self, path: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        return self.run_text(text, variables or {})

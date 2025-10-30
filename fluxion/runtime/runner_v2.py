# fluxion/runtime/runner_v2.py
from __future__ import annotations
from typing import Any, Dict, List, Optional
import json
from lark import Tree
from fluxion.core.parser import parse

# ---------- helpers ----------
class _ReturnSignal:
    def __init__(self, value: Any):
        self.value = value

Scope = Dict[str, Any]
BOOLS = {"true": True, "false": False, "null": None, "nil": None}

def _as_bool(v: Any) -> bool: return bool(v)
def _is_nullish(v: Any) -> bool: return v is None

# ---------- echo interpolation ----------
def _interpolate_string(raw: str, scope: Scope) -> str:
    import re
    s = raw
    if len(s) >= 2 and ((s[0] == '"' and s[-1] == '"') or (s[0] == "'" and s[-1] == "'")):
        s = s[1:-1]

    def repl(m):
        expr = m.group(1).strip()
        if expr in BOOLS:
            v = BOOLS[expr]; return "" if v is None else str(v)
        if expr in scope:
            v = scope[expr]; return "" if v is None else str(v)
        try:
            return str(int(expr))
        except Exception:
            pass
        try:
            return str(float(expr))
        except Exception:
            pass
        v = scope.get(expr)
        return "" if v is None else str(v)

    return re.sub(r"\{\{([^}]+)\}\}", repl, s)

def _make_echo(scope: Scope):
    def _echo(**kwargs):
        cooked = {k: (_interpolate_string(v, scope) if isinstance(v, str) else v)
                  for k, v in kwargs.items()}
        scope["_last_command"] = {"name": "echo", "args": cooked}
        return None
    return _echo

# ---------- stdlib ----------
def jsonify(obj: Any = None, **kwargs):
    if obj is not None and kwargs:
        return json.dumps({"_": obj, **kwargs}, ensure_ascii=False)
    if obj is not None:
        return json.dumps(obj, ensure_ascii=False)
    return json.dumps(kwargs, ensure_ascii=False)

def join(*args): return "".join(str(a) for a in args)

def http_head(_url: str) -> Dict[str, Any]:
    return {"ok": False, "status": 0, "elapsed_ms": 0, "length": 0, "headers": {}}

def http_get(_url: str) -> Dict[str, Any]:
    return {"ok": False, "status": 0, "elapsed_ms": 0, "length": 0, "text_preview": ""}

STDLIB_FUNCS = {
    "jsonify": jsonify,
    "join": join,
    "http_head": http_head,
    "http_get": http_get,
    # echo scope’a enjekte ediliyor
}

# ---------- invocation plumbing ----------
def _invoke_function(fname: str, args_pos: List[Any], args_kw: Dict[str, Any], scope: Scope) -> Any:
    fn = scope.get("__funcs__", {}).get(fname)
    if callable(fn):
        try:
            return fn(*args_pos, **args_kw) if args_kw else fn(*args_pos)
        except TypeError:
            return fn(*args_pos)

    fn = scope.get("__stdlib__", {}).get(fname)
    if callable(fn):
        try:
            return fn(*args_pos, **args_kw) if args_kw else fn(*args_pos)
        except TypeError:
            return fn(*args_pos)

    return None

def _collect_call_args(node_or_tree: Any, scope: Scope) -> (str, List[Any], Dict[str, Any]):
    """
    BuildAST Node(call/command) ya da Lark Tree(call) alır.
    Farklı üreticiler için hem positional hem keyword varyantlarını toparlar.
    """
    # BuildAST Node
    typ = getattr(node_or_tree, "typ", None)
    if typ in ("call", "command"):
        fname = getattr(node_or_tree, "name", "")
        pos: List[Any] = []
        kw: Dict[str, Any] = {}

        # 1) Yaygın: args (list | Tree | dict)
        if hasattr(node_or_tree, "args"):
            a = getattr(node_or_tree, "args")
            if isinstance(a, list):
                pos = [_eval_any(x, scope) for x in a]
            elif isinstance(a, Tree):
                pos = [_eval_any(x, scope) for x in (a.children or [])]
            elif isinstance(a, dict):
                for k, v in a.items():
                    kw[k] = _eval_any(v, scope)

        # 2) Tekli arg: arg
        if hasattr(node_or_tree, "arg"):
            pos.append(_eval_any(getattr(node_or_tree, "arg"), scope))

        # 3) Bazı build’ler: params / arguments
        if hasattr(node_or_tree, "params"):
            p = getattr(node_or_tree, "params")
            if isinstance(p, list):
                pos.extend(_eval_any(x, scope) for x in p)
        if hasattr(node_or_tree, "arguments"):
            p = getattr(node_or_tree, "arguments")
            if isinstance(p, list):
                pos.extend(_eval_any(x, scope) for x in p)

        # 4) kwargs (dict)
        if hasattr(node_or_tree, "kwargs") and isinstance(node_or_tree.kwargs, dict):
            for k, v in node_or_tree.kwargs.items():
                kw[k] = _eval_any(v, scope)

        return fname, pos, kw

    # Lark Tree(call)
    if isinstance(node_or_tree, Tree) and node_or_tree.data == "call":
        if not node_or_tree.children:
            return "", [], {}
        fname = str(node_or_tree.children[0])
        pos_nodes = node_or_tree.children[1:]
        pos = [_eval_any(a, scope) for a in pos_nodes]
        return fname, pos, {}

    return "", [], {}

# ---------- evaluator ----------
def _eval_any(node: Any, scope: Scope) -> Any:
    t = getattr(node, "typ", None)
    if t:
        if t == "num":  return node.value
        if t == "str":  return _interpolate_string(node.value, scope)
        if t == "var":
            name = node.name
            if name in BOOLS: return BOOLS[name]
            return scope.get(name)
        if t == "list":
            return [_eval_any(x, scope) for x in node.items]
        if t == "map":
            return {k: _eval_any(v, scope) for k, v in node.items.items()}
        if t in ("call", "command"):
            fname, pos, kw = _collect_call_args(node, scope)
            return _invoke_function(fname, pos, kw, scope) if fname else None
        return None

    if isinstance(node, Tree):
        return _eval_tree(node, scope)

    return node

def _eval_tree(t: Tree, scope: Scope) -> Any:
    typ = t.data

    # üst sarmalayıcılar
    if typ in ("program", "start", "stmts", "statements", "block"):
        last = None
        for ch in t.children:
            r = _eval_tree(ch, scope)
            if isinstance(r, _ReturnSignal): return r
            if r is not None: last = r
        return last

    if typ == "stmt":
        return _exec_stmt(t.children[0], scope) if t.children else None

    # expr ağaçları
    if typ == "coalesce":
        val = _eval_any(t.children[0], scope); i = 1
        while i < len(t.children):
            rhs = _eval_any(t.children[i + 1], scope)
            if not _is_nullish(val): return val
            val = rhs; i += 2
        return val

    if typ == "or_expr":
        val = _eval_any(t.children[0], scope); i = 1
        while i < len(t.children):
            rhs = _eval_any(t.children[i + 1], scope)
            if _as_bool(val): return True
            val = _as_bool(val) or _as_bool(rhs); i += 2
        return val

    if typ == "and_expr":
        val = _eval_any(t.children[0], scope); i = 1
        while i < len(t.children):
            rhs = _eval_any(t.children[i + 1], scope)
            if not _as_bool(val): return False
            val = _as_bool(val) and _as_bool(rhs); i += 2
        return val

    if typ == "compare":
        left = _eval_any(t.children[0], scope); i = 1
        while i < len(t.children):
            op = str(t.children[i]); right = _eval_any(t.children[i + 1], scope)
            if   op == "==": ok = (left == right)
            elif op == "!=": ok = (left != right)
            elif op == "<":  ok = (left <  right)
            elif op == "<=": ok = (left <= right)
            elif op == ">":  ok = (left >  right)
            elif op == ">=": ok = (left >= right)
            else: raise RuntimeError(f"Unknown compare op: {op}")
            if not ok: return False
            left = right; i += 2
        return True

    if typ == "sum":
        val = _eval_any(t.children[0], scope); i = 1
        while i + 1 < len(t.children):
            op = str(t.children[i]); rhs = _eval_any(t.children[i + 1], scope)
            if   op == "+": val = val + rhs
            elif op == "-": val = val - rhs
            i += 2
        return val

    if typ == "term":
        val = _eval_any(t.children[0], scope); i = 1
        while i + 1 < len(t.children):
            op = str(t.children[i]); rhs = _eval_any(t.children[i + 1], scope)
            if   op == "*": val = val * rhs
            elif op == "/": val = val / rhs
            elif op == "%": val = val % rhs
            i += 2
        return val

    if typ == "factor" and len(t.children) == 2 and str(t.children[0]) == "-":
        return -_eval_any(t.children[1], scope)

    if typ in ("expr", "atom"):
        if len(t.children) == 1:
            return _eval_any(t.children[0], scope)
        return _eval_any(t.children[-2], scope)

    if typ == "call":
        fname, pos, kw = _collect_call_args(t, scope)
        return _invoke_function(fname, pos, kw, scope) if fname else None

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
    if isinstance(stmt, Tree) and getattr(stmt, "data", None) == "stmt":
        return _eval_tree(stmt, scope)

    t = getattr(stmt, "typ", None)

    if t == "assign":
        scope[stmt.name] = _eval_any(stmt.expr, scope)
        return None

    if t == "return":
        val = _eval_any(stmt.expr, scope)
        scope["__return__"] = val
        return _ReturnSignal(val)

    if t == "if":
        cond = _eval_any(stmt.cond, scope)
        if _as_bool(cond):
            return _exec_block(stmt.then_block, scope)
        elif stmt.else_block:
            return _exec_block(stmt.else_block, scope)
        return None

    if t == "for":
        it = _eval_any(stmt.iterable, scope)
        if it is None: return None
        for v in it:
            scope[stmt.var] = v
            r = _exec_block(stmt.body, scope)
            if isinstance(r, _ReturnSignal):
                return r
        return None

    if t == "func":
        fname = stmt.name
        params = stmt.params or []
        body = stmt.block or []
        def _fn_impl(*args, **kwargs):
            child: Scope = {}
            child["__funcs__"]  = scope.get("__funcs__", {})
            child["__stdlib__"] = scope.get("__stdlib__", {})
            for i, p in enumerate(params):
                child[p] = args[i] if i < len(args) else kwargs.get(p)
            r = _exec_block(body, child)
            if isinstance(r, _ReturnSignal):
                return r.value
            return child.get("__return__", None)
        funcs = dict(scope.get("__funcs__", {}))
        funcs[fname] = _fn_impl
        scope["__funcs__"] = funcs
        return None

    if t in ("call", "command"):
        fname, pos, kw = _collect_call_args(stmt, scope)
        return _invoke_function(fname, pos, kw, scope) if fname else None

    if isinstance(stmt, Tree):
        return _eval_tree(stmt, scope)

    return None

# ---------- Runner ----------
class RunnerV2:
    def run_text(self, text: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        scope: Scope = {}
        if variables: scope.update(variables)

        scope["__stdlib__"] = dict(STDLIB_FUNCS)
        scope["__stdlib__"]["echo"] = _make_echo(scope)
        scope["__funcs__"] = dict(scope.get("__funcs__", {}))

        ast = parse(text)
        if not isinstance(ast, list):
            ast = [ast]

        ret_val: Any = None
        for stmt in ast:
            r = _eval_tree(stmt, scope) if isinstance(stmt, Tree) else _exec_stmt(stmt, scope)
            if isinstance(r, _ReturnSignal):
                ret_val = r.value
                break

        if ret_val is None:
            ret_val = scope.get("__return__", None)

        vars_out = {k: v for k, v in scope.items() if not k.startswith("__")}
        return {"return": ret_val, "vars": vars_out}

    def run_file(self, path: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        return self.run_text(text, variables or {})

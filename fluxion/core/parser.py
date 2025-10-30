from __future__ import annotations
from pathlib import Path
from typing import Any, Iterable, List, Tuple

from lark import Lark, Transformer, v_args, Tree, Token

# Grammar dosyasını yükle
_GRAMMAR = (Path(__file__).parents[1] / "grammar" / "fluxion.lark").read_text(encoding="utf-8")


# ----------------------------
# Basit AST düğümü
# ----------------------------
class Node:
    def __init__(self, typ, **kw):
        self.typ = typ
        self.__dict__.update(kw)
    def __repr__(self):
        return f"Node({self.typ}, {self.__dict__})"


# ----------------------------
# Yardımcılar (normalize)
# ----------------------------
_SEP = {"COMMA", "COLON", "EQUAL", "LBRACE", "RBRACE", "LSQB", "RSQB", "LPAR", "RPAR", "NL"}

def _is_sep(x: Any) -> bool:
    return isinstance(x, Token) and x.type in _SEP

def _flatten(xs: Iterable[Any]) -> List[Any]:
    out: List[Any] = []
    for x in xs:
        if isinstance(x, Tree):
            out.extend(_flatten(x.children))
        else:
            out.append(x)
    return out

def _only_ast(xs: Iterable[Any]) -> List[Any]:
    return [x for x in _flatten(xs) if not _is_sep(x)]

def _kv_pairs(items: Iterable[Any]) -> List[Tuple[str, Any]]:
    pairs: List[Tuple[str, Any]] = []
    for p in _only_ast(items):
        if isinstance(p, tuple) and len(p) == 2:
            k, v = p
            pairs.append((str(k), v))
    return pairs


@v_args(inline=True)
class BuildAST(Transformer):
    # roots
    def start(self, *stmts): return list(_only_ast(stmts))
    def expr_stmt(self, t):  return t  # Tree olarak kalsın; runner değerlendirip atar

    # literals
    def dqstring(self, tok): return Node("str", value=str(tok))
    def number(self, tok):
        s = str(tok)
        return Node("num", value=float(s) if any(c in s for c in ".eE") else int(s))
    def var(self, name):     return Node("var", name=str(name))

    # collections
    def list(self, *xs):
        items = []
        for x in xs:
            if isinstance(x, list):
                items.extend(x)
            else:
                items.append(x)
        items = [i for i in items if not (isinstance(i, Tree) and getattr(i, "data", None) == "list_ws")]
        return Node("list", items=items)

    def list_items(self, *xs):
        return list(xs)

    def pair(self, k, v):    return (str(k), v)

    def map(self, *items_or_pairs):
        pairs: List[Any] = []

        def collect(value: Any):
            if isinstance(value, Token):
                return
            if isinstance(value, Tree) and getattr(value, "data", None) == "list_ws":
                return
            if isinstance(value, list):
                for item in value:
                    collect(item)
                return
            if isinstance(value, Tree):
                for item in value.children:
                    collect(item)
                return
            if isinstance(value, Node) and getattr(value, "typ", "") == "map":
                for item in value.items.items():
                    collect(item)
                return
            if isinstance(value, dict):
                for item in value.items():
                    collect(item)
                return
            pairs.append(value)

        for x in items_or_pairs:
            collect(x)

        norm: List[Tuple[str, Any]] = []
        for p in pairs:
            if isinstance(p, tuple) and len(p) == 2:
                k, v = p
                norm.append((str(k), v))

        return Node("map", items=dict(norm))

    def map_items(self, *pairs):
        return list(pairs)

    # args
    def arg_list(self, *pairs):
        out = []
        for p in pairs:
            if isinstance(p, Tree):
                out.extend(p.children)
            else:
                out.append(p)
        return out

    def keyval(self, *args):
        # "k : v" veya "k = v"  -> ayırıcı tokenları at
        filtered = [a for a in args if not (isinstance(a, Token) and a.type in ('COLON', 'EQUAL'))]
        key = filtered[0]
        if isinstance(key, Token) and key.type == 'DQSTRING':
            key_name = key.value[1:-1]
        else:
            key_name = str(key)
        return (key_name, filtered[1])

    def arg_expr_list(self, *exprs):
        # virgülleri at ve ifadeleri topla
        out = []
        for e in exprs:
            if isinstance(e, Token) and e.type == 'COMMA':
                continue
            elif isinstance(e, Tree):
                out.extend(e.children)
            else:
                out.append(e)
        return out

    # statements
    def assign(self, name, expr): return Node("assign", name=str(name), expr=expr)
    def reassign(self, name, expr): return Node('assign', name=str(name), expr=expr)
    def return_(self, expr=None):
        return Node("return", expr=expr)
    def if_(self, cond, then_b, else_b=None): return Node("if", cond=cond, then=then_b or [], else_=else_b or [])
    def for_(self, name, iterable, block):    return Node("for", var=str(name), iterable=iterable, block=block or [])
    def func(self, name, params=None, block=None):
        return Node("func", name=str(name), params=[str(p) for p in (params or [])], block=block or [])
    def param_list(self, *names): return [str(n) for n in _only_ast(names)]
    def block(self, *stmts):      return list(_only_ast(stmts))

    def command(self, name, args=None):
        # args -> [(k,v), ...] | Tree | dict | None
        items = []
        if args is None:
            pass
        elif isinstance(args, dict):
            items = list(args.items())
        elif isinstance(args, list):
            items = _kv_pairs(args)
        elif isinstance(args, Tree):
            items = _kv_pairs(args.children)
        else:
            items = _kv_pairs([args])
        return Node("command", name=str(name), args=dict(items))

    # calls
    def call(self, name, *rest):
        if not rest:
            argv = []
        elif len(rest) == 1:
            a = rest[0]
            if isinstance(a, list):
                argv = a
            elif isinstance(a, Tree):
                argv = list(a.children)
            else:
                argv = [a]
        else:
            argv = list(rest)
        return Node("call", name=str(name), args=argv)

    # postfix get chain: Tree('get_chain', [atom, 'NAME', 'NAME', ...])
    def get_chain(self, *parts):
        base = parts[0]
        if isinstance(base, Token):
            base = Node("var", name=str(base))
        for p in parts[1:]:
            if isinstance(p, Token):
                base = Node("get", obj=base, name=str(p))
            else:
                base = Node("get", obj=base, name=str(p))
        return base

    def getprop(self, base, name):
        return Node('getprop', base=base, name=str(name))


def parse(text: str):
    # LALR kullanıyoruz; grammar bu haliyle çakışmasız derleniyor
    parser = Lark(_GRAMMAR, start="start", parser="lalr", maybe_placeholders=True)
    tree = parser.parse(text)
    ast = BuildAST().transform(tree)
    return ast

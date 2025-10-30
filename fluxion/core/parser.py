from __future__ import annotations
from pathlib import Path
from lark import Lark, Transformer, v_args, Tree, Token
from lark.exceptions import GrammarError
import re

_GRAMMAR = (Path(__file__).parents[1] / "grammar" / "fluxion.lark").read_text(encoding="utf-8")


class Node:
    def __init__(self, typ, **kw):
        self.typ = typ
        self.__dict__.update(kw)
    def __repr__(self):
        return f"Node({self.typ}, {self.__dict__})"


# -----------------------------
# Desugar helpers
# -----------------------------

_CMD_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_LEADING_CMD_RE = re.compile(r"^(\s*)([A-Za-z_][A-Za-z0-9_]*)\b(.*)$")

def _balanced_split_commas(s: str) -> list[str]:
    """Virgülleri yalnızca { } [ ] ( ) ve tırnaklar DENGELİ iken böl.
       Çift ve tek tırnak, kaçış, parantez/brace/braceket dengesi gözetilir."""
    out, buf = [], []
    st_paren = st_brack = st_brace = 0
    in_sq = in_dq = False
    esc = False
    for ch in s:
        if esc:
            buf.append(ch); esc = False; continue
        if ch == "\\":
            buf.append(ch); esc = True; continue
        if in_sq:
            buf.append(ch)
            if ch == "'": in_sq = False
            continue
        if in_dq:
            buf.append(ch)
            if ch == '"': in_dq = False
            continue

        if ch == "'": in_sq = True; buf.append(ch); continue
        if ch == '"': in_dq = True; buf.append(ch); continue

        if ch == '(': st_paren += 1
        elif ch == ')': st_paren -= 1
        elif ch == '[': st_brack += 1
        elif ch == ']': st_brack -= 1
        elif ch == '{': st_brace += 1
        elif ch == '}': st_brace -= 1

        if ch == ',' and st_paren == st_brack == st_brace == 0:
            out.append(''.join(buf).strip()); buf = []
        else:
            buf.append(ch)
    if buf:
        out.append(''.join(buf).strip())
    return out


def _looks_like_assign_list(s: str) -> bool:
    # En az bir "name = expr" parçası olmalı; sol taraf NAME olmalı
    parts = _balanced_split_commas(s)
    ok = False
    for p in parts:
        if '=' not in p:
            return False
        k, _eq, v = p.partition('=')
        if not _CMD_NAME_RE.match(k.strip()):
            return False
        if not v.strip():
            return False
        ok = True
    return ok


def _desugar_line(line: str) -> str:
    # fn → func
    m = re.match(r"^(\s*)fn\b", line)
    if m:
        return line[:m.end(1)] + "func" + line[m.end():]

    # Komut argümanlarını { k: v } şekline çevir
    m = _LEADING_CMD_RE.match(line)
    if not m:
        return line
    indent, head, rest = m.groups()

    # Bazı anahtar kelimeler komut değildir
    if head in ("let", "return", "if", "else", "for", "func"):
        return line

    # Eğer rest tamamen boşsa veya brace/paren ile başlıyorsa dokunma
    if not rest.strip():
        return line
    # Zaten '{' ile başlıyorsa komut map formundadır
    if rest.lstrip().startswith('{'):
        return line

    # "CMD k1=expr, k2=expr" kalıbını yakala
    # rest tipik olarak: "  k1=expr, k2=expr"
    if _looks_like_assign_list(rest.strip()):
        # { k1: expr, k2: expr }
        parts = _balanced_split_commas(rest.strip())
        pairs = []
        for p in parts:
            k, _eq, v = p.partition('=')
            pairs.append(f"{k.strip()}: {v.strip()}")
        return f"{indent}{head} {{ " + ", ".join(pairs) + " }"

    return line


def _desugar(text: str) -> str:
    lines = text.splitlines()
    return "\n".join(_desugar_line(ln) for ln in lines)


@v_args(inline=True)
class BuildAST(Transformer):
    # roots
    def start(self, *stmts): return list(stmts)
    def expr_stmt(self, t):  return t

    # literals
    def dqstring(self, tok): return Node("str", value=str(tok))
    def number(self, tok):
        s = str(tok)
        return Node("num", value=float(s) if any(c in s for c in ".eE") else int(s))
    def var(self, name):     return Node("var", name=str(name))

    # collections
    def list(self, *xs):     return Node("list", items=list(xs))
    def pair(self, k, v):    return (str(k), v)
    def map(self, *pairs):   return Node("map", items=dict(pairs))

    # args
    def arg_list(self, *pairs):
        out = []
        for p in pairs:
            if isinstance(p, Tree):
                out.extend(p.children)
            else:
                out.append(p)
        return out

    def keyval(self, k, v):  return (str(k), v)

    def arg_expr_list(self, *exprs):
        out = []
        for e in exprs:
            if isinstance(e, Tree):
                out.extend(e.children)
            else:
                out.append(e)
        return out

    # statements
    def assign(self, name, expr): return Node("assign", name=str(name), expr=expr)
    def return_(self, expr):     return Node("return", expr=expr)
    def if_(self, cond, then_b, else_b=None): return Node("if", cond=cond, then=then_b or [], else_=else_b or [])
    def for_(self, name, iterable, block):    return Node("for", var=str(name), iterable=iterable, block=block or [])
    def func(self, name, params=None, block=None):
        return Node("func", name=str(name), params=[str(p) for p in (params or [])], block=block or [])
    def param_list(self, *names): return list(names)
    def block(self, *stmts):      return list(stmts)

    def command(self, name, args=None):
        pairs = []
        if args is None:
            pairs = []
        elif isinstance(args, list):
            pairs = args
        elif isinstance(args, dict):
            pairs = list(args.items())
        elif isinstance(args, Node) and args.typ == "map":
            pairs = list(args.items.items())
        elif isinstance(args, Tree):
            tmp = []
            for ch in args.children:
                if isinstance(ch, Tree):
                    tmp.extend(ch.children)
                else:
                    tmp.append(ch)
            if len(tmp) == 1 and isinstance(tmp[0], Node) and getattr(tmp[0], "typ", "") == "map":
                pairs = list(tmp[0].items.items())
            else:
                pairs = tmp
        norm = []
        for p in pairs:
            if isinstance(p, tuple) and len(p) == 2:
                k, v = p
                norm.append((str(k), v))
        return Node("command", name=str(name), args=dict(norm))

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

    # get chain
    def get_chain(self, *parts):
        base = parts[0]
        for p in parts[1:]:
            if isinstance(p, Token):
                base = Node("get", obj=base, name=str(p))
            else:
                base = Node("get", obj=base, name=str(p))
        return base

    def reassign(self, name, expr):
        return Node('assign', name=str(name), expr=expr)

    def getprop(self, base, name):
        return Node('getprop', base=base, name=str(name))


def _build_parser():
    try:
        return Lark(
            _GRAMMAR,
            start="start",
            parser="lalr",
            maybe_placeholders=True,
        )
    except GrammarError:
        return Lark(
            _GRAMMAR,
            start="start",
            parser="earley",
            lexer="dynamic_complete",
            maybe_placeholders=True,
        )


_PARSER = None

def parse(text: str):
    """Public parse entry — önce sugar’ı sadeleştir, sonra parse et."""
    global _PARSER
    if _PARSER is None:
        _PARSER = _build_parser()
    text = _desugar(text)
    tree = _PARSER.parse(text)
    ast = BuildAST().transform(tree)
    return ast

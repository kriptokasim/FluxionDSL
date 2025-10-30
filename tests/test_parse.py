from fluxion.core.parser import parse

def test_parse_min():
    SRC = 'echo value="hi"'
    ast = parse(SRC)
    assert isinstance(ast, list) and len(ast) == 1

from fluxion.runtime.runner_v2 import RunnerV2

SRC = """
fn inc(a) { return a + 1 }
let x = 3
let y = inc(x)
return y
"""

def test_smoke():
    r = RunnerV2()
    out = r.run_text(SRC)
    assert out.get('return') == 4

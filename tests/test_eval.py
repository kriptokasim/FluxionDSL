from fluxion.runtime.runner_v2 import RunnerV2

def test_eval_interpolation():
    r = RunnerV2()
    res = r.run_text('echo value="X={{1}}"')
    assert 'vars' in res
    assert res['vars']['_last_command']['args']['value'] == "X=1"

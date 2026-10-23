"""Exhaustively check the emitted DP guard equations, independently of fit."""
import re

from simulators.cyclesim.hybrid.partition_probe import dp_guard_source


def test_emitted_dp_guard_all_stack_pointers():
    source = dp_guard_source()
    names = ("hiok", "hife", "hif6", "lozero", "lof0", "loabove", "fault.d")
    equations = []
    for name in names:
        expr = re.search(r"\b" + re.escape(name) + r"\s*=\s*([^;]+);", source)[1]
        expr = expr.replace(".io", "").replace("!", " not ").replace("&", " and ").replace("#", " or ")
        equations.append((name, compile(expr.strip(), "<generated guard CUPL>", "eval")))
    env = {"fault": False, "guardena": True}
    for rp in range(65536):
        env.update({f"RP_LO_{i}": bool(rp & (1 << i)) for i in range(8)})
        env.update({f"db{i}": bool(rp & (1 << (i + 8))) for i in range(8)})
        for name, code in equations[:-1]: env[name] = eval(code, {"__builtins__": {}}, env)
        for call in (False, True):
            env["iscall"] = call
            actual = bool(eval(equations[-1][1], {"__builtins__": {}}, env))
            invalid = rp % 2 != 0 or not 0xF600 <= rp <= 0xFEF0
            expected = invalid or (rp == 0xFEF0 if call else rp == 0xF600)
            assert actual == expected, (hex(rp), call)
    env["guardena"] = False
    assert not eval(equations[-1][1], {"__builtins__": {}}, env)
    env["fault"] = True
    assert eval(equations[-1][1], {"__builtins__": {}}, env)

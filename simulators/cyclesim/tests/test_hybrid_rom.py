"""Check serialized control-ROM execution against the sequential CPU."""
import pytest
from simulators.cyclesim.hybrid.rom_search import RomCpu, ControlStore
from simulators.cyclesim.hybrid.compare import paired, compare_instruction, run_pair
from simulators.cyclesim.fixtures.rom_builder import build_fib_recursive_rom


def lowered(blob, ram=None, **kwargs):
    h, ref = paired(blob, ram, **kwargs)
    h.__class__ = RomCpu
    return h, ref


@pytest.mark.parametrize("opcode", range(256))
@pytest.mark.parametrize("flags", [0, 3])
def test_rom_opcodes(opcode, flags):
    h, r = lowered(bytes([opcode, 0x34, 0x20]),
                   {0xF00: 2, 0xF01: 0xF6, 0xF600: 0x78, 0xF601: 0x56},
                   base=0x20FE, r0=0xA5, flags=flags)
    compare_instruction(h, r, wait_every=3)


@pytest.mark.parametrize("opcode", [6, 7])
@pytest.mark.parametrize("rp", [0, 0xF5FE, 0xF600, 0xF602, 0xF6FE, 0xF700, 0xFEEE, 0xFEF0, 0xFEF2, 0xFFFF, 0xF601])
def test_rom_stack(opcode, rp):
    h, r = lowered(bytes([opcode, 0, 0x30]), {0xF00: rp & 255, 0xF01: rp >> 8,
                   (rp - 2) & 65535: 0x34, (rp - 1) & 65535: 0x12}, base=0x2000)
    compare_instruction(h, r, wait_every=3)


def test_rom_recursive_program():
    b, ram, expected = build_fib_recursive_rom(5)
    h, r = lowered(b, ram)
    run_pair(h, r, cap=1000)
    assert h.r0 == expected


@pytest.mark.parametrize("base,blob", [(0xFFFF, [1, 1]), (0xFFFE, [5, 0, 0x20]), (0xFFFF, [10])])
def test_rom_pc_wrap(base, blob):
    h, r = lowered(bytes([blob[0]]), base=base)
    for i, b in enumerate(blob[1:], 1):
        h.mem.ram[(base + i) & 65535] = r.mem.sys.ram[(base + i) & 65535] = b
    compare_instruction(h, r)


@pytest.mark.parametrize("mode", [0, 1])
def test_rom_memory_map(mode):
    b = bytes([1, 0xA5, 3, 0x42, 15, 0, 0x80, 9, 0xFB, 8, 0xFB, 15, 0xFC, 0xFF, 10])
    h, r = lowered(b, map_mode=mode)
    run_pair(h, r, cap=20)


def test_external_register_alu_equations_exhaustive():
    """Verify all ADD/SUB input pairs against arithmetic, before fitter lowering."""
    import re
    from simulators.cyclesim.hybrid.local_search import external_bank_alu_source
    source = external_bank_alu_source("1502")
    equations = []
    for lhs, rhs in re.findall(r"(?m)^(y\d|c\d) = ([^;]+);", source):
        expr = rhs.replace("$", "^").replace("#", "|").replace("!", "~")
        equations.append((lhs, compile(expr, "<emitted ALU CUPL>", "eval")))
    env = {}
    for sub in (0, 1):
        env["sub"] = sub
        for a in range(256):
            env.update({f"a{i}": a >> i & 1 for i in range(8)})
            for b in range(256):
                env.update({f"b{i}": b >> i & 1 for i in range(8)})
                for lhs, code in equations:
                    env[lhs] = eval(code, {"__builtins__": {}}, env) & 1
                expected = a + (b ^ 255 if sub else b) + sub
                assert sum(env[f"y{i}"] << i for i in range(8)) == expected & 255
                assert env["c8"] == expected >> 8

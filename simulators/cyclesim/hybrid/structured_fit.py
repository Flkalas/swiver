"""Generate hardwired CUPL for the structured sequencer; no control ROM reads.

Python tables are compile-time truth-table inputs, lowered to Boolean equations.
This block emits command IDs to a separate output/flag/guard implementation.
"""
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
import json

from simulators.cyclesim.hybrid.structured_cu import (
    Stage, action, steps, command, commands, action_done, next_stage, instruction_class)
from simulators.cyclesim.hybrid.fit_blocks import header
from simulators.cyclesim.hybrid.rom_search import finish
from simulators.cyclesim.hybrid.partition_probe import fit


@lru_cache(None)
def command_set(order="original"):
    original = commands()
    if order == "original": return original
    if order == "fields":
        from simulators.cyclesim.hybrid.cpu import DP_REGS
        from simulators.cyclesim.hybrid.incdec import UnitTransfer
        result = [None] * 128
        misc = 0
        for t in original[1:]:
            if t.source == "DP" and t.destination.startswith("ADDR"):
                code = 16 + DP_REGS.index(t.select)
            elif t.source == "ALU" and (t.select == "R0" or isinstance(t, UnitTransfer)):
                code = 32 + DP_REGS.index(t.select) + 8*int(t.subtract)
            elif t.source == "RESULT":
                code = 48 + (8 if t.destination == "CU" else DP_REGS.index(t.select))
            elif t.source == "MEM":
                destinations = {"IR":0,"MBR":1,"TMP_LO":2,"TMP_HI":3}
                code = 64 + (destinations[t.destination] if t.destination in destinations else
                             4 if t.select == "R0" else 5 if t.select == "RP_LO" else
                             6 if t.guard == "call" else 7)
            elif t.source == "DP" and t.destination == "MEM":
                code = 80 + DP_REGS.index(t.select)
            elif t.source.startswith("TMP"):
                code = 96 + int(t.source == "TMP_HI") + 2*int(t.destination == "DP")
            else:
                code = 112 + misc
                misc += 1
            assert result[code] is None, (code,t,result[code])
            result[code] = t
        return tuple(result)
    def key(t):
        fields = (t.source, t.destination, t.select, type(t).__name__, t.subtract, t.flags, t.guard, t.constant)
        if order == "destination": return (fields[1], fields[0]) + fields[2:]
        if order == "operation": return (fields[3], fields[0], fields[2], fields[1]) + fields[4:]
        if order == "source": return fields
        raise ValueError(order)
    return (None,) + tuple(sorted(original[1:], key=key))


def enum_expr(prefix, values, width):
    values = frozenset(values)
    if not values: return "'b'0"
    if len(values) == 1 << width: return "'b'1"
    cubes = {(v, (1 << width)-1) for v in values}
    primes = set()
    while cubes:
        used, merged = set(), set()
        for value, mask in cubes:
            for bit in range(width):
                flag = 1 << bit
                other = (value ^ flag, mask)
                if mask & flag and other in cubes:
                    used.update(((value, mask), other))
                    merged.add((value & ~flag, mask & ~flag))
        primes.update(cubes-used)
        cubes = merged
    uncovered, selected = set(values), []
    while uncovered:
        best = max(sorted(primes), key=lambda c: (sum(v & c[1] == c[0] for v in uncovered), -c[1].bit_count()))
        selected.append(best)
        uncovered = {v for v in uncovered if v & best[1] != best[0]}
    return " # ".join("(" + " & ".join(("" if value >> bit & 1 else "!") + f"{prefix}{bit}"
                       for bit in range(width) if mask >> bit & 1) + ")" for value, mask in selected)


def cubes(rows, dimensions):
    """Merge exact Cartesian cubes; never introduce don't-care behavior."""
    current = {tuple(frozenset([v]) for v in row) for row in rows}
    while True:
        old = current
        for index in range(dimensions):
            groups = defaultdict(set)
            for row in current:
                key = row[:index] + row[index+1:]
                groups[key].update(row[index])
            current = {key[:index] + (frozenset(vals),) + key[index:] for key, vals in groups.items()}
        if current == old: return sorted(current, key=lambda r: tuple(tuple(sorted(x)) for x in r))


class Expressions:
    def __init__(self):
        self.definitions, self.named = [], {}

    def field(self, prefix, values, width):
        key = prefix, tuple(sorted(values)), width
        if key not in self.named:
            expr = enum_expr(prefix, values, width)
            if expr in ("'b'0", "'b'1"):
                self.named[key] = expr
            else:
                name = f"e{len(self.named)}"
                self.named[key] = name
                self.definitions.append(f"{name} = {expr};")
        return self.named[key]

    def table(self, rows, fields):
        terms = []
        for row in cubes(rows, len(fields)):
            bits = [self.field(prefix, vals, width) for vals, (prefix, width) in zip(row, fields)]
            terms.append("(" + " & ".join(x for x in bits if x != "'b'1") + ")")
        return " # ".join(terms) or "'b'0"


@lru_cache(None)
def sequencer_source(order="original", compact=True):
    expr = Expressions()
    command_bits = (len(command_set(order))-1).bit_length()
    cmd_rows = [[] for _ in range(command_bits)]
    done_rows, memory_rows = [], []
    for s in Stage:
        for k in range(16):
            for b in (0, 1):
                a = action(s, k, b)
                for t in steps(a):
                    transfer = command(a, t)
                    code = command_set(order).index(transfer)
                    row = (int(s), t, k, b)
                    for bit in range(command_bits):
                        if code >> bit & 1: cmd_rows[bit].append(row)
                    if transfer and (transfer.source == "MEM" or transfer.destination == "MEM"):
                        memory_rows.append(row)
                    for carry in (0, 1):
                        if action_done(a, t, carry): done_rows.append(row + (carry,))
    output = []
    fields = [("s", 5), ("t", 3), ("k", 4), ("b", 1)]
    for bit, rows in enumerate(cmd_rows):
        output.append(f"cmd{bit} = !fault & ({expr.table(rows, fields)});")
    output += [f"memop = {expr.table(memory_rows, fields)};",
               f"last = {expr.table(done_rows, fields + [('wc', 1)])};"]
    next_rows = [[] for _ in range(5)]
    for s in Stage:
        for k in range(16):
            for b in (0, 1):
                for z in (0, 1):
                    target = next_stage(s, k, b, z)
                    for bit in range(5):
                        if target >> bit & 1: next_rows[bit].append((int(s), k, b, z))
    for bit, rows in enumerate(next_rows):
        output.append(f"n{bit} = {expr.table(rows, [('s',5),('k',4),('b',1),('zf',1)])};")
    if compact:
        output = [line for line in output if not line.startswith(tuple(f"n{i} =" for i in range(5)) + ("memop =", "last ="))]
        def eqs(values): return enum_expr("s", values, 5)
        def eqk(values): return enum_expr("k", values, 4)
        output += [f"adjust = {eqs([2,4,15,18,21])};",
                   f"two = {eqs([0,3,7,9,10,11,13,16,19,22,24])};",
                   f"negative = ({eqs([15])}) # (({eqs([21])}) & !({eqk([6])}));",
                   f"last = (!adjust & !two) # (two & ({enum_expr('t',[1],3)})) # (adjust & (({enum_expr('t',[4],3)}) # (({enum_expr('t',[2],3)}) & (wc0 $ !negative))));",
                   f"memop = {eqs([1,5,8,12,14,17,20,23,25])};",
                   f"ispcinc = {eqs([2])};", f"isrphi = {eqs([14])};",
                   f"isrpwrite = {eqs([25])};", f"iscall = {eqk([6])};",
                   f"ishalt = {eqk([10])};", f"isshort = {eqk([0,7])};",
                   f"morebyte = !b0 & ({eqk([4,5,6,15])});",
                   f"normal = !({eqs([1,2,5,8,9,10,14,25,26])});",
                   "execsel = (ispcinc & isshort) # (operandread & !morebyte);",
                   "tothree = (ispcinc & !isshort) # (operandread & morebyte);"]
        exec_targets = {9: eqk([1,13]), 6: eqk([2,3,8,9]), 7: eqk([15]),
                        10: f"({eqk([5])}) # (({eqk([4])}) & zf0)", 11: eqk([6,7])}
        for bit in range(5):
            add = f"!s{bit}" if bit == 0 else f"s{bit} $ (" + " & ".join(f"s{i}" for i in range(bit)) + ")"
            execute = " # ".join(f"({cond})" for target,cond in exec_targets.items() if target >> bit & 1) or "'b'0"
            terms = [f"normal & ({add})", f"execsel & ({execute})"]
            for target, cond in [(26,"fetchread & ishalt"),(2,"fetchread & !ishalt"),
                                 (3,"tothree"),(16,"isrphi & iscall"),(15,"isrphi & !iscall"),
                                 (10,"isrpwrite"),(26,"stopped")]:
                if target >> bit & 1: terms.append(cond)
            output.append(f"n{bit} = " + " # ".join(f"({term})" for term in terms) + ";")
    lines = header("strucseq", "f1504plcc44")
    lines += ["PIN 43 = clk;", "PIN 1 = reset;", "PIN 2 = waitin;", "PIN 44 = zf0;",
              "PIN = [db0..7];", "PIN = wc0;", "PIN = fault;", f"PIN = [cmd0..{command_bits-1}];",
              "PIN = [p0..1];", "PIN = stopped;", "PINNODE = [s0..4];",
              "PINNODE = [t0..2];", "PINNODE = [k0..3];", "PINNODE = b0;"]
    lines += expr.definitions + output
    lines += [f"stopped = {enum_expr('s',[int(Stage.STOP)],5)};",
              f"fetchread = {enum_expr('s',[int(Stage.FETCH_READ)],5)};",
              f"operandread = {enum_expr('s',[int(Stage.OPERAND_READ)],5)};",
              "phase1 = p0 & !p1;", "phase3 = p0 & p1;",
              "active = !fault & !stopped;", "stall = phase1 & memop & waitin;",
              "capture = phase1 & !stall & active;", "irload = capture & fetchread;",
              "advance = phase3 & active;", "leave = advance & last;",
              f"nextfetch = {enum_expr('n',[0],5)};",
              f"unitstart = {enum_expr('n',[2,4,18,21],5)};",
              "p0.d = active & (!p0 # stall);", "p1.d = active & (p1 $ p0) & !stall;",
              "t0.d = (leave & unitstart) # (!leave & ((advance & !t0) # (!advance & t0)));",
              "t1.d = !leave & ((advance & (t1 $ t0)) # (!advance & t1));",
              "t2.d = !leave & ((advance & (t2 $ (t1 & t0))) # (!advance & t2));",
              "b0.d = (leave & !nextfetch & (operandread # b0)) # (!leave & b0);"]
    for bit in range(5): lines.append(f"s{bit}.d = (leave & n{bit}) # (!leave & s{bit});")
    for bit in range(4):
        values = [op for op in range(256) if instruction_class(op) >> bit & 1]
        lines.append(f"k{bit}.d = (irload & ({enum_expr('db',values,8)})) # (!irload & k{bit});")
    for reg in [f"s{i}" for i in range(5)] + [f"t{i}" for i in range(3)] + [f"k{i}" for i in range(4)] + ["b0", "p0", "p1"]:
        lines += [f"{reg}.ck = clk;", f"{reg}.ar = reset;"]
    return finish(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--order", choices=["original", "source", "destination", "operation", "fields"], default="fields")
    parser.add_argument("--nodes", nargs="*", default=[])
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    allowed = {"leave", "advance", "last", "execsel", "normal", "unitstart",
               "irload", "negative", "two", "adjust", *(f"n{i}" for i in range(5))}
    if set(args.nodes) - allowed:
        parser.error("unsupported intermediate node")
    source = sequencer_source(args.order)
    if args.nodes:
        source = source.replace("PINNODE = b0;", "PINNODE = b0;\n" +
            "\n".join(f"PINNODE = {n};" for n in dict.fromkeys(args.nodes)))
    result = fit("strucseq", source, root, root / "cpld/tools/wincupl-ii",
                 strategies=[("XOR_Synthesis", "ON")])
    print(json.dumps(dict(main_stages=len(Stage), step_bits=3, class_bits=4,
                         operand_bits=1, phase_bits=2, commands=len(commands()), result=result), indent=2))


if __name__ == "__main__": main()

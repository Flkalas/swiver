"""Explicit transfer FSM for fitting the experimental byte-bus CU.

This is a direct implementation, not a claim of minimum CPLD area. The same
graph drives the functional runner and the CUPL generator. No archived HDL.
Reset-vector boot and electrical latch-clock qualification remain out of scope.
"""
from functools import lru_cache

from simulators.cyclesim.hybrid.cpu import HybridCpu, Transfer, DP_REGS, LATCHES
from simulators.cyclesim.data.isa import insn_length
from simulators.cyclesim.hybrid.fit_blocks import header


class Graph:
    def __init__(self):
        self.nodes = []
        self.intern = {}
        self.halt = self.add(None, "HALT")
        jump = self.seq([Transfer("TMP_LO", "DP", "PC_LO"),
                         Transfer("TMP_HI", "DP", "PC_HI")], "FETCH")
        execute = {}
        for op in range(256):
            end = "FETCH"
            if op in (1, 13):
                end = self.alu("R0", "DP" if op == 1 else "CU", op == 13, True, end)
            elif op in (2, 3, 8, 9, 15):
                end = self.add(Transfer("MEM", "DP") if op in (2, 8)
                               else Transfer("DP", "MEM"), end)
                end = self.address("TMP", end)
                if op != 15:
                    end = self.add(Transfer("CU", "TMP_HI", constant=255 if op in (8, 9) else 0), end)
            elif op == 5: end = jump
            elif op == 4: end = ("zf", jump, "FETCH")
            elif op in (6, 7): end = self.stack(op == 6, jump)
            elif op == 10: end = self.halt
            for byte in reversed(range(insn_length(op) - 1)):
                target = "MBR" if op in (1, 13) else "TMP_LO" if byte == 0 else "TMP_HI"
                end = self.add(Transfer("MEM", target), end)
                end = self.adjust("PC", 1, end)
                end = self.address("PC", end)
            execute[op] = end if op == 10 else self.adjust("PC", 1, end)
        self.dispatch = execute
        self.fetch = self.address("PC", self.add(Transfer("MEM", "IR"), "DISPATCH"))
        self.bits = max(1, (len(self.nodes) - 1).bit_length())

    def add(self, transfer, successor):
        key = (transfer, successor)
        if key not in self.intern:
            self.intern[key] = len(self.nodes)
            self.nodes.append(key)
        return self.intern[key]

    def seq(self, transfers, successor):
        for t in reversed(transfers): successor = self.add(t, successor)
        return successor

    def address(self, prefix, end, literal=None):
        if literal is not None:
            ts = [Transfer("CU", "ADDR_LO", constant=literal & 255),
                  Transfer("CU", "ADDR_HI", constant=literal >> 8)]
        elif prefix == "TMP": ts = [Transfer("TMP_LO", "ADDR_LO"), Transfer("TMP_HI", "ADDR_HI")]
        else: ts = [Transfer("DP", "ADDR_LO", prefix + "_LO"), Transfer("DP", "ADDR_HI", prefix + "_HI")]
        return self.seq(ts, end)

    def alu(self, reg, dest, sub, flags, end):
        return self.seq([Transfer("ALU", "RESULT", reg, subtract=sub),
                         Transfer("RESULT", dest, reg, flags=flags)], end)

    def adjust(self, prefix, amount, end):
        high = self.add(Transfer("CU", "MBR", constant=1),
                        self.alu(prefix + "_HI", "DP", amount < 0, False, end))
        branch = ("wc", end, high) if amount < 0 else ("wc", high, end)
        low = self.alu(prefix + "_LO", "DP", amount < 0, False, branch)
        return self.add(Transfer("CU", "MBR", constant=abs(amount)), low)

    def stack(self, call, end):
        end = self.address(None, self.add(Transfer("DP", "MEM", "RP_HI"), end), literal=0xF01)
        end = self.address(None, self.add(Transfer("DP", "MEM", "RP_LO"), end), literal=0xF00)
        end = self.adjust("RP", 1 if call else -1, end)
        end = self.address("RP", self.add(Transfer("DP", "MEM", "PC_HI") if call else Transfer("MEM", "TMP_HI"), end))
        end = self.adjust("RP", 1, end)
        end = self.address("RP", self.add(Transfer("DP", "MEM", "PC_LO") if call else Transfer("MEM", "TMP_LO"), end))
        if not call: end = self.adjust("RP", -2, end)
        end = self.address(None, self.add(Transfer("MEM", "DP", "RP_HI", guard="call" if call else "ret"), end), literal=0xF01)
        return self.address(None, self.add(Transfer("MEM", "DP", "RP_LO", guard="low"), end), literal=0xF00)

    def resolve(self, target, cpu):
        while isinstance(target, tuple):
            flag, yes, no = target
            target = yes if (cpu.z if flag == "zf" else cpu.work_carry) else no
        if target == "FETCH": return self.fetch
        if target == "DISPATCH": return self.resolve(self.dispatch[cpu.ir], cpu)
        if target == "HALT": return self.halt
        return target


@lru_cache(maxsize=1)
def graph(): return Graph()


class FsmCpu(HybridCpu):
    def step_instruction(self, *, wait_every=0):
        if self.halted: return
        g = graph()
        state = g.fetch
        for _ in range(256):
            t, nxt = g.nodes[state]
            if t is None:
                self.halted = True
                self.retired += 1
                return
            self.transfer(t, waits=int(bool(wait_every and self.transfers % wait_every == 0)))
            if self.halted: return
            state = g.resolve(nxt, self)
            if state == g.fetch:
                self.retired += 1
                return
        raise AssertionError("CU FSM transfer cap")


def cu_source():
    """Registered controls, binary state/phase, no external microcode ROM.

    Phase 0 releases drivers/clocks, 1 sets up the new transfer, 2 captures,
    and 3 holds. State changes on 3->0; registered controls decode that state
    on 0->1. WAIT holds phase 1 for memory transfers and inhibits DP_WE.
    This direct encoding exposes all equations to the vendor fitter.
    """
    g = graph()
    lines = header("bytecu", "f1504plcc44")
    lines += ["PIN 43 = clk;", "PIN 1 = reset;", "PIN 2 = waitin;",
              "PIN = [db0..7];", "PIN = [sel0..2];", "PIN = dpwe;", "PIN = dpoe;",
              "PIN = [lc0..5];", "PIN = tloen;", "PIN = thien;", "PIN = resen;",
              "PIN = sub;", "PIN = subn;", "PIN = rd;", "PIN = wr;", "PIN = ac;",
              f"PINNODE = [s0..{g.bits-1}];", "PINNODE = [p0..1];",
              "PINNODE = [ir0..7];", "PINNODE = zf;", "PINNODE = cf;",
              "PINNODE = wc;", "PINNODE = odd;", "PINNODE = above;",
              "PINNODE = equal;", "PINNODE = zero;", "PINNODE = fault;", "PINNODE = busen;"]

    def eq(prefix, value, bits):
        return " & ".join(("" if value >> i & 1 else "!") + f"{prefix}{i}" for i in range(bits))

    def disj(terms): return " # ".join(f"({t})" for t in terms) or "'b'0"

    def group(pred): return disj(f"q{i}" for i, (t, _) in enumerate(g.nodes) if t and pred(t))

    for i in range(len(g.nodes)): lines.append(f"q{i} = {eq('s', i, g.bits)};")
    for i in range(4): lines.append(f"phase{i} = {eq('p', i, 2)};")
    lines += [f"memop = {group(lambda t: t.source == 'MEM' or t.destination == 'MEM')};",
              "stall = phase1 & memop & waitin;", "cap = phase1 & !stall;",
              "advance = phase3 & !fault;", "np0 = !p0 # stall;", "np1 = (p1 $ p0) & !stall;"]

    def routes(target, condition):
        if isinstance(target, tuple):
            flag, yes, no = target
            return routes(yes, f"{condition} & {flag}") + routes(no, f"{condition} & !{flag}")
        if target == "DISPATCH":
            grouped = {}
            for op, end in g.dispatch.items(): grouped.setdefault(end, []).append(eq("ir", op, 8))
            return [pair for end, conditions in grouped.items()
                    for pair in routes(end, f"{condition} & ({disj(conditions)})")]
        if target == "FETCH": target = g.fetch
        if target == "HALT": target = g.halt
        return [(target, condition)]

    edges = [pair for i, (_, nxt) in enumerate(g.nodes) for pair in routes(nxt, f"q{i}")]
    for bit in range(g.bits):
        expr = disj(cond for target, cond in edges if target >> bit & 1)
        # Reset initializes the state to fetch through per-bit async preset.
        lines.append(f"ns{bit} = (advance & ({expr})) # (!advance & !fault & s{bit});")
    for bit in range(g.bits): lines.append(f"s{bit}.d = ns{bit};")
    lines += ["p0.d = np0;", "p1.d = np1;"]
    # Decode current state after the state-change/release edge; this avoids
    # expanding the full next-state logic into every registered output.
    def ngroup(pred): return group(pred)

    capture_next = "(phase1 & !stall) # phase2"
    for bit in range(3): lines.append(f"sel{bit}.d = {ngroup(lambda t, b=bit: DP_REGS.index(t.select) >> b & 1)};")
    lines += [f"dpoe.d = !phase3 & ({ngroup(lambda t: t.source == 'DP')});",
              f"dpwe = cap & ({group(lambda t: t.destination == 'DP')});",
              f"tloen.d = phase3 # !({ngroup(lambda t: t.source == 'TMP_LO')});",
              f"thien.d = phase3 # !({ngroup(lambda t: t.source == 'TMP_HI')});",
              f"resen.d = phase3 # !({ngroup(lambda t: t.source == 'RESULT')});",
              f"sub.d = {ngroup(lambda t: t.subtract)};", f"subn.d = !({ngroup(lambda t: t.subtract)});",
              f"rd.d = !phase3 & ({ngroup(lambda t: t.source == 'MEM')});",
              f"wr.d = ({capture_next}) & ({ngroup(lambda t: t.destination == 'MEM')});"]
    for i, latch in enumerate(LATCHES):
        lines.append(f"lc{i}.d = ({capture_next}) & ({ngroup(lambda t, name=latch: t.destination == name)});")
    lines.append(f"busen.d = !phase3 & ({group(lambda t: t.source == 'CU')});")
    for bit in range(8):
        lines += [f"db{bit}.d = {ngroup(lambda t, b=bit: t.source == 'CU' and t.constant >> b & 1)};",
                  f"db{bit}.oe = busen;"]
    lines += [f"irload = cap & ({group(lambda t: t.destination == 'IR')});",
              f"wcload = cap & ({group(lambda t: t.source == 'ALU')});",
              f"flagload = cap & ({group(lambda t: t.flags)});",
              f"guardload = cap & ({group(lambda t: t.guard == 'low')});",
              f"callcheck = cap & ({group(lambda t: t.guard == 'call')});",
              f"retcheck = cap & ({group(lambda t: t.guard == 'ret')});",
              f"dbzero = {eq('db', 0, 8).replace('db', 'db')};",
              "dbfe = db7 & db6 & db5 & db4 & db3 & db2 & db1 & !db0;",
              "dbf6 = db7 & db6 & db5 & db4 & !db3 & db2 & db1 & !db0;",
              "validhi = db7 & db6 & db5 & db4 & (db3 # (db2 & db1)) & !(db3 & db2 & db1 & db0);",
              "badstack = odd # !validhi # (dbfe & above);",
              "fault.d = fault # ((callcheck # retcheck) & badstack) # (callcheck & dbfe & equal) # (retcheck & dbf6 & zero);",
              "wc.d = (wcload & ac) # (!wcload & wc);",
              "zf.d = (flagload & dbzero) # (!flagload & zf);",
              "cf.d = (flagload & wc) # (!flagload & cf);",
              "odd.d = (guardload & db0) # (!guardload & odd);",
              "above.d = (guardload & db7 & db6 & db5 & db4 & (db3 # db2 # db1 # db0)) # (!guardload & above);",
              "equal.d = (guardload & db7 & db6 & db5 & db4 & !db3 & !db2 & !db1 & !db0) # (!guardload & equal);",
              "zero.d = (guardload & dbzero) # (!guardload & zero);"]
    for bit in range(8): lines.append(f"ir{bit}.d = (irload & db{bit}.io) # (!irload & ir{bit});")
    # In CUPL a bidirectional registered pin reference denotes feedback. All
    # external DBUS predicates must explicitly select the physical input.
    import re
    lines = [re.sub(r'\bdb([0-7])(?![\w.])', r'db\1.io', line)
             if line.startswith(("dbzero =", "dbfe =", "dbf6 =", "validhi =", "odd.d", "above.d", "equal.d")) else line
             for line in lines]
    registers = ([f"s{i}" for i in range(g.bits)] + ["p0", "p1"] + [f"ir{i}" for i in range(8)]
                 + ["zf", "cf", "wc", "odd", "above", "equal", "zero", "fault", "busen"]
                 + [f"sel{i}" for i in range(3)] + ["dpoe", "tloen", "thien", "resen", "sub", "subn", "rd", "wr"]
                 + [f"lc{i}" for i in range(6)] + [f"db{i}" for i in range(8)])
    for reg in registers:
        lines.append(f"{reg}.ck = clk;")
        preset = reg in ("tloen", "thien", "resen", "subn") or (reg.startswith('s') and reg[1:].isdigit() and g.fetch >> int(reg[1:]) & 1)
        lines.append(f"{reg}.{'ap' if preset else 'ar'} = reset;")
    import textwrap
    return "\n".join(textwrap.fill(line, width=100, break_long_words=False,
                                   break_on_hyphens=False) for line in lines) + "\n"

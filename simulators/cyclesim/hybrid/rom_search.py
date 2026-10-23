"""A fully enumerated control-store partition for local fitting experiments.

The extra control ROM shares DBUS but has its own 11-bit address, so fetching
control words cannot destroy the CPU's latched memory address. Four ROM reads
precede each four-phase transfer. The 1502 is repurposed as a control expander;
memory decoding must therefore be counted externally, never silently omitted.
"""
from pathlib import Path
import json
import re
import textwrap

from simulators.cyclesim.hybrid.cpu import HybridCpu, DP_REGS, LATCHES
from simulators.cyclesim.hybrid.cu_fsm import graph, cu_source
from simulators.cyclesim.hybrid.fit_blocks import header
from simulators.cyclesim.hybrid.partition_probe import fit


def eq(prefix, value, bits, suffix=""):
    return " & ".join(("" if value >> i & 1 else "!") + f"{prefix}{i}{suffix}" for i in range(bits))


def ors(terms): return " # ".join(f"({t})" for t in terms) or "'b'0"


def finish(lines):
    return "\n".join(textwrap.fill(s, 100, break_long_words=False, break_on_hyphens=False) for s in lines) + "\n"


class ControlStore:
    def __init__(self):
        g = graph()
        # Preserve opcode bits for common dispatch heads; reserve zero for halt.
        preferred = {g.halt: 0}
        for op in (1, 2, 3, 4, 5, 6, 7, 8, 9, 13, 15, 16, 0):
            head = g.dispatch[op]
            if head not in preferred:
                code = op if op < 16 and op not in preferred.values() else next(i for i in range(16) if i not in preferred.values())
                preferred[head] = code
        self.address = dict(preferred)
        free = (i for i in range(512) if i not in preferred.values())
        for old in range(len(g.nodes)):
            if old not in self.address: self.address[old] = next(free)
        self.classes = [self.address[g.dispatch[op]] for op in range(256)]
        assert max(self.classes) < 16
        self.commands = list(dict.fromkeys(t for t, _ in g.nodes))
        assert self.commands[0] is None and len(self.commands) <= 64
        self.fetch = self.address[g.fetch]
        self.image = bytearray(2048)
        def addr(target):
            if target == "FETCH": target = g.fetch
            if target == "HALT": target = g.halt
            return self.address[target]
        for old, (t, nxt) in enumerate(g.nodes):
            mode = 0
            if nxt == "DISPATCH":
                mode, no, yes = 3, 0, 0
            elif isinstance(nxt, tuple):
                flag, true, false = nxt
                mode, no, yes = (1 if flag == "zf" else 2), addr(false), addr(true)
            else: no = yes = addr(nxt)
            base = self.address[old] * 4
            self.image[base:base+4] = bytes([self.commands.index(t) | mode << 6,
                                           no & 255, yes & 255, (no >> 8) | ((yes >> 8) << 1)])

    def group(self, pred, prefix="cw"):
        return ors(eq(prefix, i, 6) for i, t in enumerate(self.commands) if t is not None and pred(t))


class RomCpu(HybridCpu):
    def step_instruction(self, *, wait_every=0):
        if self.halted: return
        store = ControlStore()
        address = store.fetch
        for _ in range(256):
            cmd, no, yes, hi = store.image[address*4:address*4+4]
            t, mode = store.commands[cmd & 63], cmd >> 6
            self.ticks += 4
            if t is None:
                self.halted = True
                self.retired += 1
                return
            # Conditions are sampled while reading the control word; dispatch
            # uses the instruction captured by this transfer at its completion.
            take = self.z if mode == 1 else self.work_carry if mode == 2 else False
            self.transfer(t, waits=int(bool(wait_every and self.transfers % wait_every == 0)))
            if self.halted: return
            address = store.classes[self.ir] if mode == 3 else ((yes | ((hi >> 1 & 1) << 8)) if take else (no | ((hi & 1) << 8)))
            if address == store.fetch:
                self.retired += 1
                return
        raise AssertionError("control ROM transfer cap")


def sequencer_source(*, direct=False):
    s = ControlStore()
    lines = header("romseq", "f1504plcc44")
    lines += ["PIN 43 = clk;", "PIN 1 = reset;", "PIN 2 = waitin;", "PIN 44 = ac;",
              "PIN = [db0..7];", "PIN = [u0..8];", "PIN = [cmd0..5];",
              "PIN = [p0..1];", "PIN = rd;", "PIN = wr;", "PIN = romen;",
              "PINNODE = [cw0..5];", "PINNODE = [target0..8];", "PINNODE = [ic0..3];",
              "PINNODE = run;", "PINNODE = take;", "PINNODE = dispatch;", "PINNODE = stopped;",
              "PINNODE = zf;", "PINNODE = cf;", "PINNODE = wc;", "PINNODE = odd;",
              "PINNODE = above;", "PINNODE = equal;", "PINNODE = zero;", "PINNODE = fault;"]
    for i in range(4): lines.append(f"phase{i} = {eq('p',i,2)};")
    lines += [f"memop = {s.group(lambda t: t.source == 'MEM' or t.destination == 'MEM')};",
              "stall = run & phase1 & memop & waitin;",
              "cap = run & phase1 & !stall & !stopped & !fault;",
              "load0 = !run & phase0 & !stopped & !fault;",
              "loadlo = !run & ((phase1 & !take) # (phase2 & take)) & !stopped & !fault;",
              "loadhi = !run & phase3 & !stopped & !fault;",
              "done = run & phase3 & !stopped & !fault;",
              "p0.d = !p0 # stall;", "p1.d = (p1 $ p0) & !stall;",
              "run.d = !stopped & !fault & (run $ phase3);",
              "take.d = (load0 & ((db6.io & !db7.io & zf) # (!db6.io & db7.io & wc))) # (!load0 & take);",
              "dispatch.d = (load0 & db6.io & db7.io) # (!load0 & dispatch);",
              "stopped.d = stopped # (load0 & !db0.io & !db1.io & !db2.io & !db3.io & !db4.io & !db5.io);",
              "romen = !run & !stopped & !fault & !reset;"]
    for i in range(6):
        lines += [f"cw{i}.d = (load0 & db{i}.io) # (!load0 & cw{i});",
                  f"cmd{i} = run & !fault & !stopped & cw{i};"]
    for i in range(8): lines.append(f"target{i}.d = (loadlo & db{i}.io) # (!loadlo & target{i});")
    lines.append("target8.d = (loadhi & ((!take & db0.io) # (take & db1.io))) # (!loadhi & target8);")
    for i in range(9):
        dest = f"(dispatch & ic{i}) # (!dispatch & target{i})" if i < 4 else f"!dispatch & target{i}"
        lines.append(f"u{i}.d = (done & ({dest})) # (!done & u{i});")
    lines += [f"rd.d = run & !phase3 & ({s.group(lambda t: t.source == 'MEM')});",
              f"wr.d = run & ((phase1 & !stall) # phase2) & ({s.group(lambda t: t.destination == 'MEM')});"]
    for i in range(8):
        lines += [f"db{i} = {s.group(lambda t,b=i: t.source == 'CU' and t.constant >> b & 1)};",
                  f"db{i}.oe = run & !phase0 & !fault & !stopped & ({s.group(lambda t: t.source == 'CU')});"]
    # Reuse the reviewed state/guard expressions, substituting command decoding
    # for unrolled state decoding. Instruction class is captured separately.
    original = [" ".join(x.split()) for x in cu_source().split(';') if x.strip()]
    predicates = dict(irload=lambda t:t.destination == 'IR', wcload=lambda t:t.source == 'ALU',
                      flagload=lambda t:t.flags, guardload=lambda t:t.guard == 'low',
                      callcheck=lambda t:t.guard == 'call', retcheck=lambda t:t.guard == 'ret')
    for name, pred in predicates.items(): lines.append(f"{name} = cap & ({s.group(pred)});")
    prefixes = ("dbzero =", "dbfe =", "dbf6 =", "validhi =", "badstack =", "fault.d", "wc.d", "zf.d", "cf.d", "odd.d", "above.d", "equal.d", "zero.d")
    lines += [statement + ';' for statement in original if statement.startswith(prefixes)]
    for i in range(4):
        expr = ors(eq("db",op,8,".io") for op, cls in enumerate(s.classes) if cls >> i & 1)
        lines.append(f"ic{i}.d = (irload & ({expr})) # (!irload & ic{i});")
    registers = ([f"u{i}" for i in range(9)] + [f"target{i}" for i in range(9)] +
                 [f"cw{i}" for i in range(6)] + [f"ic{i}" for i in range(4)] +
                 ["p0", "p1", "run", "take", "dispatch", "stopped", "zf", "cf", "wc", "odd", "above", "equal", "zero", "fault", "rd", "wr"])
    for reg in registers:
        lines.append(f"{reg}.ck = clk;")
        preset = reg.startswith('u') and reg[1:].isdigit() and s.fetch >> int(reg[1:]) & 1
        lines.append(f"{reg}.{'ap' if preset else 'ar'} = reset;")
    if direct:
        lines = [line for line in lines if not line.startswith("PINNODE = [cw") and not re.match(r"cmd\d =", line)]
        lines = [re.sub(r"\bcw(\d)", r"cmd\1", line) for line in lines]
        lines = [line.replace("Name romseq;", "Name romdir;") for line in lines]
    return finish(lines)


def expander_source(*, direct=False):
    s = ControlStore()
    g = lambda pred: s.group(pred, "cmd")
    lines = header("romctrl", "f1502plcc44")
    lines += ["PIN 43 = clk;", "PIN 1 = reset;", "PIN 44 = waitin;",
              "PIN = [cmd0..5];", "PIN = [p0..1];", "PIN = [sel0..2];",
              "PIN = dpwe;", "PIN = dpoe;", "PIN = [lc0..5];", "PIN = tloen;",
              "PIN = thien;", "PIN = resen;", "PIN = sub;", "PIN = subn;"]
    for i in range(4): lines.append(f"phase{i} = {eq('p',i,2)};")
    lines += [f"memop = {g(lambda t:t.source == 'MEM' or t.destination == 'MEM')};",
              "stall = phase1 & memop & waitin;"]
    for bit in range(3): lines.append(f"sel{bit}.d = {g(lambda t,b=bit:DP_REGS.index(t.select) >> b & 1)};")
    lines += [f"dpwe = phase1 & !stall & ({g(lambda t:t.destination == 'DP')});",
              f"dpoe.d = !phase3 & ({g(lambda t:t.source == 'DP')});",
              f"tloen.d = phase3 # !({g(lambda t:t.source == 'TMP_LO')});",
              f"thien.d = phase3 # !({g(lambda t:t.source == 'TMP_HI')});",
              f"resen.d = phase3 # !({g(lambda t:t.source == 'RESULT')});",
              f"sub.d = {g(lambda t:t.subtract)};", f"subn.d = !({g(lambda t:t.subtract)});"]
    for i,name in enumerate(LATCHES): lines.append(f"lc{i}.d = ((phase1 & !stall) # phase2) & ({g(lambda t,n=name:t.destination == n)});")
    registers = [f"sel{i}" for i in range(3)] + [f"lc{i}" for i in range(6)] + ["dpoe", "tloen", "thien", "resen", "sub", "subn"]
    for reg in registers:
        lines += [f"{reg}.ck = clk;", f"{reg}.{'ap' if reg in ('tloen','thien','resen','subn') else 'ar'} = reset;"]
    if direct:
        lines.insert(10, "PIN = romen;")
        # Decode registered command pins only while the sequencer executes.
        lines = [line.replace("Name romctrl;", "Name ctrldir;") for line in lines]
        for i, line in enumerate(lines):
            if re.match(r"(?:sel[0-2]|lc[0-5]|dpoe|sub)\.d =", line) or line.startswith("dpwe ="):
                lhs, rhs = line.split(" = ", 1)
                lines[i] = lhs + " = !romen & (" + rhs[:-1] + ");"
            elif re.match(r"(?:tloen|thien|resen|subn)\.d =", line):
                lhs, rhs = line.split(" = ", 1)
                lines[i] = lhs + " = romen # (" + rhs[:-1] + ");"
    return finish(lines)


def guarded_partition_sources():
    """Move stack range checks into the register bank; encode ROM mode as 63."""
    from simulators.cyclesim.hybrid.partition_probe import dp_guard_source
    seq = [" ".join(x.split()) for x in sequencer_source().split(';') if x.strip()]
    removed = {"odd", "above", "equal", "zero", "fault"}
    out = []
    for line in seq:
        if line == "Name romseq": line = "Name romsplit"
        if line == "PIN = romen": line = "PIN = fault"
        if line in {f"PINNODE = {n}" for n in removed}: continue
        if re.match(r"(?:odd|above|equal|zero|fault)\.(?:d|ck|ar|ap)\s*=", line): continue
        if re.match(r"(?:guardload|badstack|dbfe|dbf6|validhi|callcheck|retcheck|romen)\s*=", line): continue
        m = re.match(r"cmd(\d) =", line)
        if m: line = f"cmd{m[1]} = !fault & !stopped & (!run # cw{m[1]})"
        out.append(line+';')
    seq = finish(out)
    ctrl = expander_source().replace("Name romctrl;", "Name ctrlsplt;")
    # Commands 0 and 63 cannot select a transfer. The ROM mode pin is driven
    # by the expander and is counted explicitly in the interconnect.
    ctrl += "PIN = romen;\nPIN = guardena;\nPIN = iscall;\n"
    ctrl += "romen = " + eq('cmd',63,6) + ";\n"
    st = ControlStore()
    ctrl += "guardena = phase1 & !stall & (" + st.group(lambda t:t.guard in ('call','ret'),'cmd') + ");\n"
    ctrl += "iscall = " + st.group(lambda t:t.guard == 'call','cmd') + ";\n"
    dp = dp_guard_source().replace("Name dpguard;", "Name dprom;")
    dp = dp.replace("PIN = alusub;\nPIN = subn;\nsubn = !alusub;\n", "")
    return seq, finish(ctrl.splitlines()), dp


def lean_sequencer_source():
    source = guarded_partition_sources()[0].replace('Name romsplit;', 'Name romlean;')
    # fault/stopped mask the command and force run low. Internal ROM registers
    # may keep sampling while stopped, but cannot enable a bus driver or write.
    statements = [" ".join(x.split()) for x in source.split(';') if x.strip()]
    for i, line in enumerate(statements):
        if line.startswith(('cap =', 'load0 =', 'loadlo =', 'loadhi =', 'done =')):
            statements[i] = line.replace(' & !stopped & !fault', '')
    return finish([line+';' for line in statements])


def looping_halt_source():
    """HALT loops over ROM state zero, issuing no CPU bus transfer."""
    source = lean_sequencer_source().replace('Name romlean;', 'Name romloop;')
    statements = [" ".join(x.split()) for x in source.split(';') if x.strip()]
    out = []
    for line in statements:
        if line == 'PINNODE = stopped' or line.startswith(('stopped.d', 'stopped.ck', 'stopped.ar')): continue
        line = line.replace('!stopped & ', '').replace(' & !stopped', '')
        out.append(line+';')
    return finish(out)


def shared_target_source():
    """IR dispatch overwrites the already loaded next target, sharing four FFs."""
    source = lean_sequencer_source().replace('Name romlean;', 'Name romshare;')
    statements = [" ".join(x.split()) for x in source.split(';') if x.strip()]
    ic = {int(re.match(r'ic(\d)', x)[1]): x.split(' = ',1)[1] for x in statements if re.match(r'ic\d\.d =',x)}
    out = []
    for line in statements:
        if line in ('PINNODE = [ic0..3]', 'PINNODE = dispatch'): continue
        if re.match(r'(?:ic\d|dispatch)\.(?:d|ck|ar|ap)',line): continue
        m = re.match(r'target([0-3])\.d =',line)
        if m:
            i = int(m[1])
            # irload and loadlo are exclusive execution/ROM phases.
            cls = ic[i].split(' # (!irload & ')[0]
            line = f'target{i}.d = {cls} # (loadlo & db{i}.io) # (!irload & !loadlo & target{i})'
        m = re.match(r'u(\d)\.d =',line)
        if m:
            i = int(m[1]); line = f'u{i}.d = (done & target{i}) # (!done & u{i})'
        out.append(line+';')
    return finish(out)


def main():
    root = Path(__file__).resolve().parents[3]
    installed = root / 'cpld/tools/wincupl-ii'
    results = {}
    for name, source, device in (("romseq",sequencer_source(),"1504"),("romctrl",expander_source(),"1502")):
        results[name] = fit(name,source,root,installed,device)
    out = root / 'simulators/cyclesim/build/hybrid-partition'
    (out / 'control.bin').write_bytes(ControlStore().image)
    (out / 'rom-search.json').write_text(json.dumps(results,indent=2)+'\n',encoding='utf-8')


if __name__ == '__main__': main()

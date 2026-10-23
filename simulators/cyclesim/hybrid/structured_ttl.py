"""Concrete all-74 mapping of the class/step CU and shared INC/DEC datapath.

Synchronous 574s have explicit 157 feedback; no imaginary register enables.
The internal byte bus is mux-selected; a 245 drives the external memory bus.
This is a reproducible mapping, not a minimum-chip or board-timing claim.
"""
import ast
from collections import Counter
from copy import deepcopy
from functools import lru_cache
import json
import hashlib
from pathlib import Path
import re

from simulators.cyclesim.ttl.netlist import Circuit
from simulators.cyclesim.ttl.optimize import optimize
from simulators.cyclesim.hybrid.cpu import HybridCpu, DP_REGS, LATCHES
from simulators.cyclesim.hybrid.incdec import UnitTransfer
from simulators.cyclesim.hybrid.external_partition import statements
from simulators.cyclesim.hybrid.structured_fit import sequencer_source, command_set, enum_expr, cubes
from simulators.cyclesim.hybrid.structured_cu import Stage, action, steps, command
from simulators.cyclesim.blocks.mem_decode import MemSystem


class Mapper:
    """Lower CUPL expressions to actual supported 74 gates, lazily by dependency."""
    def __init__(self, circuit, source):
        self.c = circuit
        self.expr, self.names, self.registers = {}, {}, {}
        for line in statements(source):
            m = re.fullmatch(r'(\w+(?:\.d)?)\s*=\s*(.*)', line)
            if m and m[1] not in ('PIN', 'PINNODE', 'PROPERTY'):
                rhs = m[2].replace("'b'0", '0').replace("'b'1", '1')
                rhs = rhs.replace('!', '~').replace('#', '|').replace('$', '^')
                self.expr[m[1]] = ast.parse(rhs, mode='eval').body
        for name in self.expr:
            if name.endswith('.d'):
                q = circuit.reg('seq_' + name[:-2], 1)
                self.names[name[:-2]] = q[0]
                self.registers[name[:-2]] = q

    def node(self, node):
        c = self.c
        if isinstance(node, ast.Constant): return int(node.value)
        if isinstance(node, ast.Name): return self.signal(node.id)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Invert):
            return c.inv(self.node(node.operand))
        if isinstance(node, ast.BinOp):
            a, b = self.node(node.left), self.node(node.right)
            if isinstance(node.op, ast.BitAnd): return c.and_(a, b)
            if isinstance(node.op, ast.BitOr): return c.or_(a, b)
            if isinstance(node.op, ast.BitXor):
                return c.mux(a, [b], [c.inv(b)])[0]
        raise ValueError(ast.dump(node))

    def signal(self, name):
        if name not in self.names:
            self.names[name] = self.node(self.expr[name])
        return self.names[name]

    def expression(self, text):
        text = text.replace("'b'0", '0').replace("'b'1", '1')
        return self.node(ast.parse(text.replace('!', '~').replace('#', '|').replace('$', '^'), mode='eval').body)


@lru_cache(None)
def build(order='fields', optimized=True, direct=True, decision_order='tsbk', mapping='sop'):
    c = Circuit()
    m = Mapper(c, sequencer_source(order))
    flags = c.reg('FLAGS', 3)  # Z, architectural C, working carry
    fault = c.reg('FAULT', 2)  # invalid, overflow, underflow encoded 1/2/3
    wait = c.bus('WAIT', 1)[0]
    reset = c.bus('RESET', 1)[0]
    mode = c.bus('MAP_MODE', 1)[0]
    memory = c.bus('MEMORY_INPUT', 8)
    m.names.update(wc0=flags[2], zf0=flags[0], fault=c.any(*fault), waitin=wait,
                   reset=reset, clk=c.clock_net)
    table = command_set(order)
    width = (len(table)-1).bit_length()
    cmd = [] if direct else [m.signal(f'cmd{i}') for i in range(width)]
    # Compile legal control tuples directly to output strobes. No command ROM,
    # encoded command bus, or software decoder is left in the resulting netlist.
    variables = [m.names[f'{prefix}{i}'] for prefix, count in [('s',5),('t',3),('k',4),('b',1)] for i in range(count)]
    indexes = {'s': list(range(5)), 't': list(range(5,8)), 'k': list(range(8,12)), 'b': [12]}
    bit_order = [i for key in decision_order for i in reversed(indexes[key])]
    rows = []
    for stage in Stage:
        for klass in range(16):
            for second in (0, 1):
                a = action(stage, klass, second)
                for step in steps(a):
                    rows.append((int(stage) | step << 5 | klass << 8 | second << 12, command(a, step)))

    @lru_cache(None)
    def decision(ones, zeros, bit=0):
        if not ones: return 0
        if not zeros: return 1
        assert bit < len(variables)
        index = bit_order[bit]
        mask = 1 << index
        lo = decision(frozenset(v for v in ones if not v & mask),
                      frozenset(v for v in zeros if not v & mask), bit+1)
        hi = decision(frozenset(v for v in ones if v & mask),
                      frozenset(v for v in zeros if v & mask), bit+1)
        return c.mux(variables[index], [lo], [hi])[0]

    def group(predicate):
        if direct:
            if mapping == 'sop':
                selected = [(v & 31, (v >> 5) & 7, (v >> 8) & 15, v >> 12)
                            for v,t in rows if t is not None and predicate(t)]
                terms = []
                for row in cubes(selected, 4):
                    terms.append(c.all(*(m.expression(enum_expr(prefix, vals, n))
                        for vals,(prefix,n) in zip(row, [('s',5),('t',3),('k',4),('b',1)]))))
                return c.and_(m.signal('active'), c.any(*terms))
            on = frozenset(v for v,t in rows if t is not None and predicate(t))
            off = frozenset(v for v,t in rows if t is None or not predicate(t))
            return c.and_(m.signal('active'), decision(on, off))
        ids = [i for i, t in enumerate(table) if t is not None and predicate(t)]
        return m.expression(enum_expr('cmd', ids, width))

    cap = m.signal('capture')
    c.group = 'datapath'
    regs = {name: c.reg(name, 8) for name in DP_REGS + LATCHES}
    c.group = 'bus'
    constant = [group(lambda t, i=i: t.source == 'CU' and t.constant >> i & 1) for i in range(8)]
    # Selection is concrete 157 wiring; no Python command dispatch at runtime.
    bus = constant
    for name in DP_REGS:
        en = group(lambda t, name=name: t.source in ('DP', 'ALU') and t.select == name)
        bus = c.mux(en, bus, regs[name])
    for name in ('TMP_LO', 'TMP_HI', 'RESULT'):
        bus = c.mux(group(lambda t, name=name: t.source == name), bus, regs[name])
    rd = group(lambda t: t.source == 'MEM')
    wr = c.and_(cap, group(lambda t: t.destination == 'MEM'))
    bus = c.mux(rd, bus, memory)
    c.probes['BYTE_BUS'] = bus
    c.probes['CPU_BUS_DRIVER'] = c.driver(bus, wr)
    m.names.update({f'db{i}': net for i, net in enumerate(bus)})
    c.group = 'alu_control'
    sub = group(lambda t: t.source == 'ALU' and t.subtract)
    unit = group(lambda t: isinstance(t, UnitTransfer))
    cin = c.mux(unit, [sub], [c.inv(sub)])[0]
    high = c.mux(unit, [c.inv(sub)], [sub])[0]
    c.group = 'alu'
    y, carry = c.import_arithmetic_alu(bus, regs['MBR'], cin, sub, high)
    c.group = 'datapath'
    for name, q in regs.items():
        enable = group(lambda t, name=name: (t.destination == 'DP' and t.select == name)
                       or t.destination == name)
        c.bind(q, y if name == 'RESULT' else bus, c.and_(cap, enable))
    c.group = 'flags_stack_checks'
    flagload = c.and_(cap, group(lambda t: t.flags))
    wcload = c.and_(cap, group(lambda t: t.source == 'ALU'))
    # bind the packed register as a whole, with explicit independent mux enables.
    fd = [c.mux(flagload, [flags[0]], [c.eq(bus, 0)])[0],
          c.mux(flagload, [flags[1]], [flags[2]])[0],
          c.mux(wcload, [flags[2]], [carry])[0]]
    c.bind(flags, fd, 1)
    rp = regs['RP_LO'] + bus
    invalid = c.any(rp[0], c.lt(rp, 0xF600), c.inv(c.lt(rp, 0xFEF1)))
    call = group(lambda t: t.guard == 'call')
    ret = group(lambda t: t.guard == 'ret')
    overflow = c.all(c.inv(invalid), call, c.eq(rp, 0xFEF0))
    underflow = c.all(c.inv(invalid), ret, c.eq(rp, 0xF600))
    bad = c.all(cap, c.or_(call, ret), c.any(invalid, overflow, underflow))
    c.bind(fault, [c.or_(invalid, underflow), c.or_(overflow, underflow)], bad)
    c.group = 'memory_decode'
    address = regs['ADDR_LO'] + regs['ADDR_HI']
    top = c.eq(address[8:], 255)
    vector = c.all(top, c.eq(address[2:8], 63))
    mailbox = c.all(top, c.inv(vector))
    rom = c.all(c.inv(mode), c.or_(c.eq(address[11:], 0), vector))
    ram = c.inv(c.or_(rom, mailbox))
    ram0, ram1 = c.and_(ram, c.inv(address[15])), c.and_(ram, address[15])
    c.group = 'control'
    for name, q in m.registers.items():
        c.bind(q, [c.and_(c.inv(reset), m.signal(name + '.d'))], 1)
    for key, val in dict(CAP=cap, RD=rd, WR=wr, ROM_SEL=rom, RAM0_SEL=ram0,
                         RAM1_SEL=ram1, MAILBOX_SEL=mailbox,
                         MEM_WE=c.all(wr, c.inv(rom)), STOP=m.signal('stopped')).items():
        c.probes[key] = [val]
    c.probes['PHASE'] = [m.names[f'p{i}'] for i in range(2)]
    c.probes['STAGE'] = [m.names[f's{i}'] for i in range(5)]
    c.probes['STEP'] = [m.names[f't{i}'] for i in range(3)]
    if cmd: c.probes['COMMAND'] = cmd
    c.finalize()
    return optimize(c) if optimized else c


class StructuredTtlCpu(HybridCpu):
    """Run gates and simultaneous D sampling; host supplies only memory and clock."""
    def __init__(self):
        self.mem = MemSystem()
        self.circuit = deepcopy(build())
        self.reset()

    def reset(self, pc=0):
        super().reset(pc)
        for _, q, _ in self.circuit.registers:
            self.circuit.set(q, 0)
        self._initialized = False

    def read(self, name): return self.circuit.read(self.circuit.probes[name])

    def _settle(self, wait=0):
        c = self.circuit
        c.set(c.probes['WAIT'], wait)
        c.set(c.probes['RESET'], 0)
        c.set(c.probes['MAP_MODE'], self.mem.map_mode)
        c.set(c.probes['MEMORY_INPUT'], 0)
        c.settle()
        a = self.read('ADDR_LO') | self.read('ADDR_HI') << 8
        if self.read('MAILBOX_SEL'): mem, key, writable = self.mem.mailbox, a & 255, True
        elif self.read('ROM_SEL'): mem, key, writable = self.mem.rom, a, False
        else:
            assert self.read('RAM0_SEL') or self.read('RAM1_SEL')
            mem, key, writable = self.mem.ram, a, True
        c.set(c.probes['MEMORY_INPUT'], mem.get(key, 0) & 255)
        c.settle()
        return mem, key, writable, a

    def step_instruction(self, *, wait_every=0):
        if self.halted: return
        c = self.circuit
        if not self._initialized:
            for name, value in self.dp.items(): c.set(c.probes[name], value)
            c.set(c.probes['FLAGS'], int(self.z) | int(self.c) << 1)
            self._initialized = True
        waited = False
        for _ in range(2048):
            self._settle()
            if self.read('STOP'):
                self.halted = True
                self.retired += 1
                return
            phase = self.read('PHASE')
            wait = bool(phase == 1 and wait_every and not waited and self.transfers % wait_every == 0)
            if wait: waited = True
            mem, key, writable, address = self._settle(int(wait))
            if self.read('CAP'):
                value = self.read('BYTE_BUS')
                if self.read('RD'): self.accesses.append(('read', address, value))
                if self.read('WR'):
                    assert bool(self.read('MEM_WE')) == writable
                    if writable: mem[key] = value
                    self.accesses.append(('write', address, value))
                self.transfers += 1
            c.clock()
            self.ticks += 1
            for name in self.dp: self.dp[name] = self.read(name)
            for name in self.latches: self.latches[name] = self.read(name)
            flags = self.read('FLAGS')
            self.z, self.c, self.work_carry = bool(flags & 1), bool(flags & 2), bool(flags & 4)
            fault = self.read('FAULT')
            if fault:
                self.fault = (None, 'invalid return stack pointer', 'return stack overflow', 'return stack underflow')[fault]
                self.halted = True
                return
            if phase == 3:
                waited = False
                if self.read('STAGE') == 0 and self.read('STEP') == 0:
                    self.retired += 1
                    return
        raise AssertionError('74 structured CU clock cap')


def main():
    out = Path('simulators/cyclesim/build/structured-ttl')
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for optimized in (False, True):
        c = build(optimized=optimized)
        rows.append(dict(optimized=optimized, packages=len(c.packages),
                         parts=dict(Counter(p.part for p in c.packages)), groups=c.inventory()))
    netlist = json.dumps(build().export(), indent=2)+'\n'
    (out/'netlist.json').write_text(netlist, encoding='utf-8')
    from simulators.cyclesim.hybrid.compare import paired, run_pair
    from simulators.cyclesim.fixtures.rom_builder import build_fib_recursive_rom
    cases = []
    for waits in (0, 5):
        blob, ram, expected = build_fib_recursive_rom(3)
        cpu, ref = paired(blob, ram, cpu_class=StructuredTtlCpu)
        run_pair(cpu, ref, cap=1000, wait_every=waits)
        assert cpu.r0 == expected
        if not waits: assert cpu.ticks == 6604
        cases.append(dict(program='fib_recursive_3', wait_every=waits, ticks=cpu.ticks,
                          instructions=cpu.retired, memory_accesses=len(cpu.accesses),
                          architectural_and_memory_access_match=True))
    root = Path(__file__).resolve().parents[3]
    paths = [Path(__file__), Path(__file__).with_name('structured_cu.py'),
             Path(__file__).with_name('structured_fit.py'),
             root/'simulators/cyclesim/ttl/netlist.py', root/'simulators/cyclesim/ttl/optimize.py']
    report = dict(scope='Concrete shared-adjust/class-step all-74 mapping, not minimum BOM or timing acceptance',
                  control_roms=0, cplds=0, variants=rows, cases=cases,
                  program_memory_chips_excluded=3, logic_plus_program_memory=len(build().packages)+3,
                  excludes=['oscillator', 'physical reset/boot circuit', 'fanout buffers',
                            'mailbox coprocessor', 'power/passives'],
                  bus_implementation='Internal mux-selected 8-bit bus; external memory bus uses 74HC245',
                  source_sha256={p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
                  netlist_sha256=hashlib.sha256(netlist.encode('utf-8')).hexdigest())
    (out/'inventory.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__': main()

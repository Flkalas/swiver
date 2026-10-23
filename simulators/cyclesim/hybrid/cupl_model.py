"""Boolean clock-edge simulation of generated CUPL, not post-fit timing."""
import re
from functools import lru_cache
from simulators.cyclesim.hybrid.cpu import HybridCpu, DP_REGS, LATCHES
from simulators.cyclesim.hybrid.rom_search import ControlStore
from simulators.cyclesim.hybrid.external_partition import (
    sequencer, auxiliary, auxiliary_table, latch_control, statements, decode_image)


class Values(dict):
    def __init__(self, model, inputs):
        super().__init__(model.state)
        self.model = model
        self.update(inputs)

    def __missing__(self, key):
        if key not in self.model.comb:
            raise KeyError('unbound CUPL signal ' + key)
        value = eval(self.model.comb[key], {'__builtins__': {}}, self) & 1
        self[key] = value
        return value


@lru_cache(None)
def compile_source(source):
    comb, ds, preset = {}, {}, set()
    for statement in statements(source):
        m = re.match(r'(\w+(?:\.(?:d|oe|ar|ap|ck))?)\s*=\s*(.*)$', statement)
        if not m:
            continue
        lhs, rhs = m.groups()
        if lhs in ('PIN', 'PINNODE', 'PROPERTY'):
            continue
        if lhs.endswith('.ap'):
            preset.add(lhs[:-3])
            continue
        if lhs.endswith(('.ar', '.ck')):
            continue
        rhs = rhs.replace("'b'0", '0').replace("'b'1", '1').replace('.io', '_io')
        rhs = rhs.replace('!', '~').replace('#', '|').replace('$', '^')
        code = compile(rhs, '<generated CUPL>', 'eval')
        if lhs.endswith('.d'):
            ds[lhs[:-2]] = code
        else:
            comb[lhs.replace('.oe', '_oe')] = code
    return comb, ds, preset


class Equations:
    def __init__(self, source):
        self.comb, self.ds, preset = compile_source(source)
        self.state = {name: int(name in preset) for name in self.ds}

    def values(self, inputs):
        return Values(self, inputs)

    def next(self, values):
        return {name: eval(code, {'__builtins__': {}}, values) & 1 for name, code in self.ds.items()}


def bits(prefix, value, n):
    return {f'{prefix}{i}': value >> i & 1 for i in range(n)}


def number(values, prefix, n):
    return sum(values[f'{prefix}{i}'] << i for i in range(n))


class PinCpu(HybridCpu):
    """Run three generated sources and external latches on each clock edge.

    Uses the existing 12-package 74 ALU. No Transfer is executed by this runner.
    A fixture supplies initial PC/registers; reset-vector boot remains separate.
    """
    table_decode = False

    def reset(self, pc=0):
        super().reset(pc)
        for name in ('seq', 'aux', 'ctrl', 'store', 'edge_count'):
            if hasattr(self, name):
                delattr(self, name)

    def _memory(self):
        if not self.table_decode:
            return super()._memory()
        a = self.address
        ce = decode_image()[(int(self.mem.map_mode) << 14) | (a >> 2)]
        selected = [i for i in range(4) if not (ce >> i & 1)]
        assert len(selected) == 1
        if selected[0] == 3:
            return self.mem.mailbox, a & 255, True, 'mailbox'
        if selected[0] == 2:
            return self.mem.rom, a, False, 'rom'
        return self.mem.ram, a, True, 'ram'

    def _ensure(self):
        if hasattr(self, 'seq'):
            return
        self.store = ControlStore()
        self.seq = Equations(sequencer())
        self.aux = Equations(auxiliary_table() if self.table_decode else auxiliary())
        self.ctrl = Equations(latch_control())
        self.aux.state.update(zf=int(self.z), cf=int(self.c))
        self.edge_count = 0

    def settle(self, wait=0):
        common = dict(clk=0, reset=0, waitin=wait)
        sv = self.seq.values(dict(common, zf=self.aux.state['zf'], wc=self.aux.state['wc'], fault=self.aux.state['fault']))
        cmd, phase = number(sv, 'cmd', 6), number(sv, 'p', 2)
        common.update(bits('cmd', cmd, 6))
        common.update(bits('p', phase, 2))
        if self.table_decode:
            common['romn'] = decode_image()[(int(self.mem.map_mode) << 14) | (self.address >> 2)] >> 2 & 1
        av, cv = self.aux.values(common), self.ctrl.values(common)
        drivers = []
        if not av['romen_n']:
            drivers.append(('control_rom', self.store.image[number(sv, 'u', 9)*4+phase]))
        for i, name in enumerate(DP_REGS):
            if not cv[f'den{i}']:
                drivers.append((name, self.dp[name]))
        for name, en in [('TMP_LO', 'tloen'), ('TMP_HI', 'thien'), ('RESULT', 'resen')]:
            if not av[en]:
                drivers.append((name, self.latches[name]))
        if av['rd']:
            mem, key, _, _ = self._memory()
            drivers.append(('memory', mem.get(key, 0) & 255))
        if av['db0_oe']:
            assert all(av[f'db{i}_oe'] for i in range(8))
            drivers.append(('constant', number(av, 'db', 8)))
        assert len(drivers) <= 1, (self.edge_count, cmd, phase, drivers)
        bus = drivers[0][1] if drivers else 0
        self.alu.set(self.a, bus)
        self.alu.set(self.b, self.latches['MBR'])
        self.alu.set(self.sub, av['sub'])
        self.alu.settle()
        y, carry = self.alu.read(self.y), self.alu.read([self.carry])
        db = {f'db{i}_io': bus >> i & 1 for i in range(8)}
        sv.update(db)
        av.update(db)
        av['ac'] = carry
        return sv, av, cv, bus, y, drivers

    def edge(self, wait=0):
        sv, av, cv, bus, y, drivers = self.settle(wait)
        before = self.address
        ns, na, nc = self.seq.next(sv), self.aux.next(av), self.ctrl.next(cv)
        self.seq.state, self.aux.state, self.ctrl.state = ns, na, nc
        _, av2, cv2, bus2, y2, drivers2 = self.settle(wait)
        captured = False
        for i, name in enumerate(DP_REGS):
            if not cv[f'dc{i}'] and cv2[f'dc{i}']:
                assert drivers and bus == bus2, ('DP hold', name, drivers, drivers2)
                self.dp[name] = bus
                captured = True
        for i, name in enumerate(LATCHES):
            if not cv[f'lc{i}'] and cv2[f'lc{i}']:
                if name == 'RESULT':
                    assert y == y2, ('ALU hold', y, y2)
                    self.latches[name] = y
                else:
                    assert drivers and bus == bus2, ('latch hold', name, drivers, drivers2)
                    self.latches[name] = bus
                captured = True
        if sv['irload']:
            self.ir = bus
            captured = True
        if av['rd'] and captured:
            self.accesses.append(('read', before, bus))
        if not av['wr'] and av2['wr']:
            assert drivers and bus == bus2
            mem, key, writable, _ = self._memory()
            if self.table_decode:
                assert bool(av2['wen_n']) == (not writable)
            if writable:
                mem[key] = bus
            self.accesses.append(('write', before, bus))
        self.z, self.c, self.work_carry = bool(na['zf']), bool(na['cf']), bool(na['wc'])
        self.edge_count += 1
        self.ticks += 1
        if captured:
            _, _, _, held, _, held_drivers = self.settle(wait)
            if drivers2:
                assert held == bus2, ('post-capture hold', drivers2, held_drivers)

    def step_instruction(self, *, wait_every=0):
        if self.halted:
            return
        self._ensure()
        executed, wait_done = False, False
        for _ in range(4096):
            sv, _, _, _, _, _ = self.settle()
            phase = number(sv, 'p', 2)
            if sv['run']:
                executed = True
            memory = bool(sv['memop'] and sv['run'] and phase == 1)
            if not memory:
                wait_done = False
            waiting = bool(memory and wait_every and not wait_done and self.transfers % wait_every == 0)
            if waiting:
                wait_done = True
            old_run = sv['run']
            self.edge(int(waiting))
            if old_run and phase == 3:
                self.transfers += 1
            if self.aux.state['fault']:
                rp = self.dp['RP_LO'] | self.dp['RP_HI'] << 8
                invalid = bool(rp & 1 or not 0xF600 <= rp <= 0xFEF0)
                self.fault = ('invalid return stack pointer' if invalid else
                              'return stack overflow' if self.ir == 6 else 'return stack underflow')
                self.halted = True
                return
            if self.seq.state['stopped']:
                self.halted = True
                self.retired += 1
                return
            if executed and not self.seq.state['run'] and number(self.seq.state, 'u', 9) == self.store.fetch:
                self.retired += 1
                return
        raise AssertionError('CUPL execution edge cap')


class TablePinCpu(PinCpu):
    table_decode = True

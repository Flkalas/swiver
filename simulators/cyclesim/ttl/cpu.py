"""All-74HC candidate CPU: fixed package wiring, no opcode executor callbacks.

The host supplies the clock, WAIT and asynchronous memory devices. Opcode and
phase decoding, next state, arithmetic, register enables, stack guards and
memory selection are evaluated through the exported 74HC network.
"""
from __future__ import annotations

from simulators.cyclesim.blocks.mem_decode import MemSystem
from simulators.cyclesim.data.sequential import BusAccess, SequentialState as S, StageActivity, SysTrace
from simulators.cyclesim.ttl.netlist import Circuit
from simulators.cyclesim.values import X, Z, resolve

PHASES = [S.FETCH_OPCODE, S.FETCH_OPERAND, S.FETCH_OPERAND, S.EXECUTE,
          S.MEM_READ, S.MEM_WRITE, S.STACK_RP_LO, S.STACK_RP_HI,
          S.STACK_DATA_LO, S.STACK_DATA_HI, S.STACK_WRITE_RP_LO, S.STACK_WRITE_RP_HI]
FAULTS = {0: None, 1: "invalid return stack pointer", 2: "return stack overflow",
          3: "return stack underflow"}


def build_cpu():
    c = Circuit()
    bus = c.bus("DBUS", 8)
    wait = c.bus("WAIT", 1)[0]
    map_mode = c.bus("MAP_MODE", 1)[0]
    phase = c.reg("phase", 4)
    stopped = c.reg("halted", 1)
    fault = c.reg("fault", 2)
    c.group = "registers"
    pc = c.reg("PC", 16)
    ir = c.reg("IR", 8)
    mbr = c.reg("MBR", 8)
    hi = c.reg("HI", 8)
    r0 = c.reg("R0", 8)
    flags = c.reg("FLAGS", 2)
    c.group = "stack"
    rp = c.reg("RP_TEMP", 16)
    popped = c.reg("RETURN_TEMP", 16)

    c.group = "control"
    st = [c.eq(phase, i) for i in range(12)]
    run = c.all(c.inv(wait), c.inv(stopped[0]))
    active = [c.and_(s, run) for s in st]
    f0, f1, f2, ex, mr, mw, rl, rh, dl, dh, wl, wh = active
    op = {code: c.eq(ir, code) for code in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 13, 15)}
    fetch_op = {code: c.eq(bus, code) for code in (7, 10, 12)}
    one_byte = c.any(bus[4], *fetch_op.values())
    wide = c.any(*(op[i] for i in (4, 5, 6, 15)))
    call, ret = op[6], op[7]
    stack = c.or_(call, ret)
    load = c.or_(op[2], op[8])
    store = c.any(op[3], op[9], op[15])
    finish_fetch = c.any(c.and_(f0, one_byte), c.all(f1, c.inv(wide)), f2)
    # At opcode fetch only RET/HALT/TRAP are one-byte; no stale IR dependency.
    to_stack = c.any(c.all(f0, fetch_op[7]), c.all(c.any(f1, f2), finish_fetch, stack))
    to_read = c.all(c.any(f1, f2), finish_fetch, load)
    to_write = c.all(c.any(f1, f2), finish_fetch, store)
    to_ex = c.all(finish_fetch, c.inv(c.any(to_stack, to_read, to_write)))
    fetch = c.any(f0, f1, f2)
    read = c.any(fetch, mr, rl, rh, c.all(c.any(dl, dh), ret))
    write = c.any(mw, wl, wh, c.all(c.any(dl, dh), call))
    alu_add, alu_cmp = c.and_(ex, op[1]), c.and_(ex, op[13])
    flg_we = c.or_(alu_add, alu_cmp)
    r0_we = c.or_(alu_add, mr)
    redirect = c.any(c.all(ex, c.any(op[5], c.and_(op[4], flags[0]))), wh)
    increment = c.any(f1, f2, c.all(f0, c.inv(fetch_op[10])))
    halt = c.and_(ex, op[10])

    c.group = "alu"
    y, carry = c.import_alu(r0, mbr, op[13])
    c.group = "alu_glue"
    zero = c.eq(y, 0)
    c.group = "registers"
    c.bind(ir, bus, f0)
    c.bind(mbr, bus, f1)
    c.bind(hi, bus, f2)
    c.bind(r0, c.mux(mr, y, bus), r0_we)
    c.bind(flags, [zero, carry], flg_we)

    c.group = "stack"
    c.bind(rp[:8], bus, rl)
    c.bind(rp[8:], bus, rh)
    c.bind(popped[:8], bus, c.and_(dl, ret))
    c.bind(popped[8:], bus, c.and_(dh, ret))
    delta = c.mux(ret, c.constant(2, 16), c.constant(0xFFFE, 16))
    next_rp, _ = c.add(rp, delta)
    stack_base = c.mux(ret, rp, next_rp)
    stack_addr, _ = c.add(stack_base, c.constant(0, 16), dh)
    candidate_rp = rp[:8] + bus
    invalid = c.any(candidate_rp[0], c.lt(candidate_rp, 0xF600), c.inv(c.lt(candidate_rp, 0xFEF1)))
    overflow = c.all(c.inv(invalid), call, c.eq(candidate_rp, 0xFEF0))
    underflow = c.all(c.inv(invalid), ret, c.eq(candidate_rp, 0xF600))
    stack_error = c.all(rh, c.any(invalid, overflow, underflow))
    error_code = [c.or_(invalid, underflow), c.or_(overflow, underflow)]

    c.group = "address"
    pc_plus, _ = c.add(pc, c.constant(1, 16))
    target = c.mux(ret, mbr + hi, popped)
    c.bind(pc, c.mux(redirect, pc_plus, target), c.or_(increment, redirect))
    io = c.or_(op[8], op[9])
    eff_hi = c.mux(op[15], c.constant(0, 8), hi)
    eff_hi = c.mux(io, eff_hi, c.constant(255, 8))
    address = c.mux(c.or_(mr, mw), pc, mbr + eff_hi)
    rp_access = c.any(rl, rh, wl, wh)
    address = c.mux(rp_access, address, [c.or_(rh, wh)] + c.constant(0x0F00, 16)[1:])
    address = c.mux(c.or_(dl, dh), address, stack_addr)
    c.probes["ADDRESS"] = address
    c.group = "bus"
    return_byte = c.mux(dh, pc[:8], pc[8:])
    rp_byte = c.mux(wh, next_rp[:8], next_rp[8:])
    wdata = c.mux(c.or_(dl, dh), r0, return_byte)
    wdata = c.mux(c.or_(wl, wh), wdata, rp_byte)
    driver = c.driver(wdata, write)
    c.probes["CPU_BUS_DRIVER"] = driver

    c.group = "memory_decode"
    top_page = c.eq(address[8:], 255)
    vector = c.all(top_page, c.eq(address[2:8], 63))
    mailbox = c.all(top_page, c.inv(vector))
    boot = c.eq(address[11:], 0)
    rom = c.all(c.inv(map_mode), c.or_(boot, vector))
    ram = c.inv(c.or_(mailbox, rom))

    c.group = "control"
    done = c.any(ex, mr, mw, wh)
    stop = c.or_(halt, stack_error)
    targets = {0: done, 1: c.all(f0, c.inv(one_byte)), 2: c.and_(f1, wide),
               3: to_ex, 4: to_read, 5: to_write, 6: to_stack,
               7: rl, 8: c.all(rh, c.inv(stack_error)), 9: dl, 10: dh, 11: wl}
    next_phase = [c.any(*(signal for state, signal in targets.items() if (state >> bit) & 1))
                  for bit in range(4)]
    c.bind(phase, next_phase, c.all(run, c.inv(stop)))
    c.bind(stopped, [1], stop)
    c.bind(fault, error_code, stack_error)
    trap = c.all(ex, c.inv(c.any(*op.values())))
    strobes = dict(FETCH=fetch, MEM_RD=read, MEM_WR=write, IR_LOAD=f0,
                   MBR_LOAD=f1, ABS16_HI_LOAD=f2, PC_INC=increment,
                   EXECUTE=c.any(ex, mr, mw), Y_OE=c.any(alu_add, mw),
                   REG_WE=r0_we, FLG_WE=flg_we, ALU_ADD=alu_add, ALU_CMP=alu_cmp,
                   PC_LOAD_EN=redirect, HALT=halt, TRAP=trap,
                   STACK=c.any(rl, rh, dl, dh, wl, wh), STACK_FAULT=stack_error,
                   STACK_PUSH=c.and_(wh, call), STACK_POP=c.and_(wh, ret))
    for name, bit in strobes.items(): c.probes[name] = [bit]
    c.probes.update(RETIRED=[done], ROM_SEL=[rom], RAM_SEL=[ram], MAILBOX_SEL=[mailbox])
    c.finalize()
    return c, strobes


class TtlCpu:
    def __init__(self):
        self.circuit, self.strobes = build_cpu()
        self.mem = MemSystem()
        self.trace: list[SysTrace] = []
        self._wait_next = False
        self.reset()

    def get(self, name): return self.circuit.read(self.circuit.probes[name])
    def set(self, name, value): self.circuit.set(self.circuit.probes[name], value)
    @property
    def pc(self): return self.get("PC")
    @property
    def r0(self): return self.get("R0")
    @property
    def halted(self): return bool(self.get("halted"))
    @property
    def fault(self): return FAULTS[self.get("fault")]
    @property
    def sys_ticks(self): return len(self.trace)
    @property
    def last_trace(self): return self.trace[-1] if self.trace else None
    @property
    def state(self): return PHASES[self.get("phase")]

    def reset(self, pc=0):
        for _, q, _ in self.circuit.registers: self.circuit.set(q, 0)
        self.set("PC", pc)
        self.set("WAIT", 0)
        self.set("MAP_MODE", self.mem.map_mode)
        self.set("DBUS", 0)
        self._wait_next = False
        self.trace.clear()

    def request_wait(self): self._wait_next = True

    def _memory_target(self, address):
        selects = [self.get(n) for n in ("ROM_SEL", "RAM_SEL", "MAILBOX_SEL")]
        if sum(selects) != 1: raise RuntimeError("memory selects are not one-hot")
        if selects[0]: return self.mem.rom, address, False
        if selects[1]: return self.mem.ram, address, True
        return self.mem.mailbox, address & 255, True

    def step(self):
        if self.halted: return
        c = self.circuit
        before, state, old_ir = self.pc, self.state, self.get("IR")
        waiting = self._wait_next
        self._wait_next = False
        self.set("WAIT", int(waiting))
        self.set("MAP_MODE", self.mem.map_mode)
        c.settle()
        rd, wr, address = self.get("MEM_RD"), self.get("MEM_WR"), self.get("ADDRESS")
        if rd and wr: raise RuntimeError("simultaneous memory read and write")
        store, offset, writable = self._memory_target(address)
        data = store.get(offset, 0) & 255
        # External memory is a second bus driver; 245 drives only on writes.
        for i, net in enumerate(c.probes["DBUS"]):
            device = (data >> i) & 1 if rd else Z
            cpu = c.values[c.probes["CPU_BUS_DRIVER"][i]]
            c.values[net] = resolve([device, cpu])
            if c.values[net] == X: raise RuntimeError("shared data bus contention/unknown")
        c.settle()
        if (rd, wr, address) != (self.get("MEM_RD"), self.get("MEM_WR"), self.get("ADDRESS")):
            raise RuntimeError("memory bus address/enable depends on read data")
        bus = None
        if rd or wr:
            value = self.get("DBUS")
            bus = BusAccess("read" if rd else "write", address, value)
            if wr and writable: store[offset] = value
        strobes = frozenset(name for name, bit in self.strobes.items() if c.values[bit] == 1)
        retired = bool(self.get("RETIRED"))
        c.clock()
        flags = self.get("FLAGS")
        stage = StageActivity() if waiting else (
            StageActivity(True, before) if state in (S.FETCH_OPCODE, S.FETCH_OPERAND)
            else StageActivity(execute_active=True, execute_opcode=old_ir))
        self.trace.append(SysTrace(self.sys_ticks, S.WAIT if waiting else state, stage,
                                   before, self.pc, self.get("IR"), self.get("MBR"),
                                   self.get("HI"), self.r0, bool(flags & 1), bool(flags & 2),
                                   bus, frozenset({"WAIT"}) if waiting else strobes,
                                   retired, waiting, self.fault))

"""Sequential CPU acceptance against actual memory calls, not trace labels alone."""

from __future__ import annotations

import pytest

from simulators.cyclesim.blocks.return_stack import RP_CELL, STACK_BASE, STACK_TOP
from simulators.cyclesim.data.isa import (
    OP_ADD, OP_BEQ, OP_CALL, OP_CMP, OP_HALT, OP_JMP, OP_LDA, OP_LDIO,
    OP_RET, OP_STA, OP_STA16, OP_STIO,
)
from simulators.cyclesim.data.sequential import SYS_COSTS, BusAccess, SequentialState as S, control_for
from simulators.cyclesim.program import ProgramRunner


def program(blob: bytes, *, base: int = 0) -> ProgramRunner:
    runner = ProgramRunner()
    # Load only RAM: instruction and data access must use the same map.
    runner.cpu.mem.load_bytes(base, blob, target="ram")
    runner.reset(pc=base, map_mode=1)
    return runner


def seed_word(runner: ProgramRunner, address: int, value: int) -> None:
    runner.load_ram(address, value & 0xFF)
    runner.load_ram(address + 1, value >> 8)


class MemoryRecorder:
    """Observe real calls at MemSystem, also catching bypasses of CPU helpers."""

    def __init__(self, runner: ProgramRunner, monkeypatch: pytest.MonkeyPatch) -> None:
        self.cpu = runner.cpu
        self.events: list[BusAccess] = []
        memory = self.cpu.mem.sys
        read, write = memory.read, memory.write

        def recorded_read(address: int) -> int:
            value = read(address)
            self.events.append(BusAccess("read", address & 0xFFFF, value))
            return value

        def recorded_write(address: int, value: int) -> None:
            self.events.append(BusAccess("write", address & 0xFFFF, value & 0xFF))
            write(address, value)

        monkeypatch.setattr(memory, "read", recorded_read)
        monkeypatch.setattr(memory, "write", recorded_write)

    def step(self) -> None:
        before = len(self.events)
        ticks = self.cpu.sys_ticks
        self.cpu.step()
        trace = self.cpu.last_trace
        assert trace is not None and self.cpu.sys_ticks == ticks + 1
        actual = self.events[before:]
        assert len(actual) <= 1, "more than one byte bus access in a SYS"
        assert actual == ([] if trace.bus_access is None else [trace.bus_access])
        assert not (trace.stage.fetch_active and trace.stage.execute_active)
        if trace.stage.fetch_active:
            assert actual and actual[0].kind == "read"
            assert trace.stage.fetch_address == actual[0].address
            assert not trace.retired


CASES = [
    (bytes([OP_ADD, 2]), 3, False, 2),
    (bytes([OP_CMP, 2]), 3, False, 2),
    (bytes([OP_LDA, 0x40]), 3, False, 2),
    (bytes([OP_STA, 0x40]), 3, False, 2),
    (bytes([OP_LDIO, 4]), 3, False, 2),
    (bytes([OP_STIO, 4]), 3, False, 2),
    (bytes([OP_STA16, 0, 0x20]), 4, False, 3),
    (bytes([OP_BEQ, 0x80, 0]), 4, False, 3),
    (bytes([OP_BEQ, 0x80, 0]), 4, True, 0x80),
    (bytes([OP_JMP, 0x80, 0]), 4, False, 0x80),
    (bytes([OP_CALL, 0x80, 0]), 9, False, 0x80),
    (bytes([OP_RET]), 7, False, 0x80),
    (bytes([OP_HALT]), 2, False, 0),
    (bytes([0x0C]), 2, False, 1),
    (bytes([0x18]), 2, False, 1),
]


@pytest.mark.parametrize("blob,cost,z,expected_pc", CASES)
def test_exact_instruction_cost_and_retirement(blob, cost, z, expected_pc, monkeypatch) -> None:
    runner = program(blob + bytes([OP_HALT]))
    runner.load_ram(0x80, OP_HALT)
    runner.load_ram(0x40, 0xA5)
    runner.cpu.mem.sys.mailbox[4] = 0xA5
    seed_word(runner, RP_CELL, STACK_BASE + (2 if blob[0] == OP_RET else 0))
    seed_word(runner, STACK_BASE, 0x80)
    runner.cpu.flg.z = z
    record = MemoryRecorder(runner, monkeypatch)
    for index in range(cost):
        record.step()
        assert runner.cpu.last_trace.retired == (index == cost - 1)
        if index < cost - 1:
            assert not runner.cpu.fetch_pending
            assert not runner.halted
    assert runner.pc == expected_pc
    assert control_for(blob[0]).typical_sys == cost
    assert SYS_COSTS[control_for(blob[0]).name] == cost
    if blob[0] == OP_HALT:
        assert runner.halted and not runner.cpu.fetch_pending
    else:
        assert runner.cpu.fetch_pending
        record.step()
        assert record.events[-1] == BusAccess("read", expected_pc, OP_HALT)
        assert runner.cpu.last_trace.state is S.FETCH_OPCODE


def test_operand_fetch_and_add_execution_are_separate(monkeypatch) -> None:
    runner = program(bytes([OP_ADD, 1, OP_HALT]))
    runner.cpu.gpr.regs[0] = 0xFF
    record = MemoryRecorder(runner, monkeypatch)
    record.step()
    record.step()
    assert runner.r0 == 0xFF and not runner.cpu.flg.z and not runner.cpu.flg.c
    assert record.events == [BusAccess("read", 0, OP_ADD), BusAccess("read", 1, 1)]
    record.step()
    assert runner.r0 == 0 and runner.cpu.flg.z and runner.cpu.flg.c
    assert runner.cpu.last_trace.bus_access is None
    assert runner.cpu.last_trace.reg_we and runner.cpu.last_trace.flg_we
    assert runner.cpu._trace_fetch == {}
    assert len(record.events) == 2  # The following HALT has not been prefetched.
    record.step()
    assert record.events[-1] == BusAccess("read", 2, OP_HALT)


STACK_CASES = [
    (OP_CALL, STACK_BASE), (OP_CALL, 0xF6FE), (OP_CALL, STACK_TOP - 1),
    (OP_RET, STACK_BASE + 2), (OP_RET, 0xF700), (OP_RET, STACK_TOP + 1),
]


@pytest.mark.parametrize("opcode,rp", STACK_CASES)
def test_stack_progression_one_actual_byte_per_sys(opcode, rp, monkeypatch) -> None:
    origin, target = 0x1234, 0x2345
    call = opcode == OP_CALL
    blob = bytes([opcode, target & 0xFF, target >> 8]) if call else bytes([opcode])
    runner = program(blob, base=origin)
    seed_word(runner, RP_CELL, rp)
    address = rp if call else rp - 2
    if not call:
        seed_word(runner, address, target)
    record = MemoryRecorder(runner, monkeypatch)
    for _ in blob:
        record.step()
    next_pc = origin + len(blob)
    next_rp = rp + 2 if call else rp - 2
    data = next_pc if call else target
    expected = [
        BusAccess("read", RP_CELL, rp & 0xFF),
        BusAccess("read", RP_CELL + 1, rp >> 8),
        BusAccess("write" if call else "read", address, data & 0xFF),
        BusAccess("write" if call else "read", address + 1, data >> 8),
        BusAccess("write", RP_CELL, next_rp & 0xFF),
        BusAccess("write", RP_CELL + 1, next_rp >> 8),
    ]
    expected_ram = dict(runner.cpu.mem.sys.ram)
    for index, event in enumerate(expected):
        record.step()
        assert record.events[-1] == event
        if event.kind == "write":
            expected_ram[event.address] = event.value
        assert runner.cpu.mem.sys.ram == expected_ram
        assert runner.cpu.last_trace.retired == (index == 5)
        assert runner.cpu.last_trace.pc_load_en == (index == 5)
        assert runner.pc == (target if index == 5 else next_pc)
        assert runner.cpu.fetch_pending == (index == 5)
    assert len(record.events) == len(blob) + 6
    assert runner.cpu.last_trace.state is S.STACK_WRITE_RP_HI


def execution_snapshot(runner: ProgramRunner) -> tuple:
    cpu = runner.cpu
    return (
        cpu.state, runner.pc, runner.ir, runner.mbr, cpu.abs16_hi.hi,
        runner.r0, cpu.flg.z, cpu.flg.c, cpu.current_op, cpu.halted, cpu.fault,
        cpu._operand_byte, cpu._operand_len, cpu._stack_rp, cpu._stack_next_rp,
        cpu._stack_addr, cpu._stack_return, cpu._stack_target,
        dict(cpu.mem.sys.ram), dict(cpu.mem.sys.rom), dict(cpu.mem.sys.mailbox),
    )


WAIT_CASES = [(opcode, index, cost) for opcode, cost in [(OP_CALL, 9), (OP_RET, 7), (OP_ADD, 3), (OP_LDA, 3), (OP_STA, 3), (OP_HALT, 2)] for index in range(cost)]


@pytest.mark.parametrize("opcode,wait_before,cost", WAIT_CASES)
def test_wait_freezes_each_pending_operation(opcode, wait_before, cost, monkeypatch) -> None:
    blob = bytes([opcode, 0x80, 0])
    runner = program(blob)
    seed_word(runner, RP_CELL, STACK_BASE + (2 if opcode == OP_RET else 0))
    seed_word(runner, STACK_BASE, 0x80)
    runner.load_ram(0x80, OP_HALT)
    record = MemoryRecorder(runner, monkeypatch)
    for _ in range(wait_before):
        record.step()
    before = execution_snapshot(runner)
    runner.cpu.request_wait()
    record.step()
    assert execution_snapshot(runner) == before
    trace = runner.cpu.last_trace
    assert trace.state is S.WAIT and trace.waiting and not trace.retired
    assert trace.bus_access is None and trace.strobes == frozenset({"WAIT"})
    assert not trace.stage.fetch_active and not trace.stage.execute_active
    for _ in range(cost - wait_before):
        record.step()
    assert runner.cpu.sys_ticks == cost + 1
    assert runner.cpu.last_trace.retired
    assert sum(trace.retired for trace in runner.cpu.traces) == 1


@pytest.mark.parametrize("opcode,rp,fault", [
    (OP_CALL, STACK_TOP + 1, "overflow"),
    (OP_CALL, STACK_BASE - 2, "invalid"),
    (OP_CALL, STACK_TOP, "invalid"),
    (OP_RET, STACK_BASE, "underflow"),
    (OP_RET, STACK_BASE - 2, "invalid"),
    (OP_RET, STACK_TOP + 3, "invalid"),
    (OP_RET, STACK_BASE + 1, "invalid"),
])
def test_stack_fault_is_bounded_without_writes_or_retirement(opcode, rp, fault, monkeypatch) -> None:
    runner = program(bytes([opcode, 0x80, 0, OP_HALT]))
    seed_word(runner, RP_CELL, rp)
    expected_ram = dict(runner.cpu.mem.sys.ram)
    record = MemoryRecorder(runner, monkeypatch)
    cost = (3 if opcode == OP_CALL else 1) + 2
    for _ in range(cost):
        record.step()
    assert runner.halted and fault in runner.cpu.fault
    assert runner.pc == cost - 2
    assert runner.cpu.last_trace.state is S.STACK_RP_HI
    assert all(not trace.retired for trace in runner.cpu.traces)
    assert all(event.kind == "read" for event in record.events)
    assert runner.cpu.mem.sys.ram == expected_ram
    assert runner.run_until_halt(max_steps=20) == 0
    runner.cpu.step()
    assert runner.cpu.sys_ticks == cost and len(record.events) == cost


def test_ram_store_changes_later_opcode_on_same_bus(monkeypatch) -> None:
    runner = program(bytes([
        OP_LDA, 0x40,
        OP_STA16, 0x08, 0x20,
        OP_JMP, 0x08, 0x20,
        0x0C,
    ]), base=0x2000)
    runner.load_ram(0x40, OP_HALT)
    record = MemoryRecorder(runner, monkeypatch)
    for _ in range(13):
        record.step()
    assert runner.halted and runner.pc == 0x2008
    assert [trace.ir for trace in runner.cpu.traces if trace.retired] == [OP_LDA, OP_STA16, OP_JMP, OP_HALT]
    write_index = record.events.index(BusAccess("write", 0x2008, OP_HALT))
    fetch_index = record.events.index(BusAccess("read", 0x2008, OP_HALT))
    assert write_index < fetch_index


def test_reset_vector_is_uncounted_setup_and_clears_wait(monkeypatch) -> None:
    runner = program(bytes([OP_HALT]))
    runner.cpu.mem.set_vector(0x1234)
    runner.cpu.request_wait()
    record = MemoryRecorder(runner, monkeypatch)
    runner.reset(from_vector=True, map_mode=0)
    assert record.events == [BusAccess("read", 0xFFFC, 0x34), BusAccess("read", 0xFFFD, 0x12)]
    assert runner.pc == 0x1234 and runner.cpu.sys_ticks == 0
    assert runner.cpu.traces == () and runner.cpu.state is S.FETCH_OPCODE
    runner.load_ram(0x1234, OP_HALT)
    record.step()
    assert runner.cpu.last_trace.state is S.FETCH_OPCODE
    assert not runner.halted and runner.pc == 0x1234
    record.step()
    assert runner.halted and runner.cpu.last_trace.retired


@pytest.mark.timeout(10)
def test_run_stays_step_bounded_and_counts_wait() -> None:
    runner = program(bytes([OP_JMP, 0, 0]))
    runner.cpu.request_wait()
    assert runner.run_until_halt(max_steps=9) == 9
    assert not runner.halted and runner.pc == 0
    assert runner.cpu.sys_ticks == 9
    assert sum(trace.retired for trace in runner.cpu.traces) == 2
    assert runner.cpu.traces[0].state is S.WAIT


@pytest.mark.parametrize("opcode", [0x0C, *range(0x10, 0x20), 0x00, 0x0B, 0x0E])
def test_trap_preserves_existing_opcode_lengths_and_registers(opcode, monkeypatch) -> None:
    length = 2 if opcode in (0x00, 0x0B, 0x0E) else 1
    blob = bytes([opcode, 0xA5, OP_HALT]) if length == 2 else bytes([opcode, OP_HALT])
    runner = program(blob)
    runner.cpu.gpr.regs[0] = 0x5A
    runner.cpu.flg.z = runner.cpu.flg.c = True
    record = MemoryRecorder(runner, monkeypatch)
    for _ in range(length + 1):
        record.step()
    assert runner.pc == length and not runner.halted
    assert runner.r0 == 0x5A and runner.cpu.flg.z and runner.cpu.flg.c
    assert runner.cpu.last_trace.retired and "TRAP" in runner.cpu.last_trace.strobes
    assert not runner.cpu.last_trace.reg_we and not runner.cpu.last_trace.flg_we
    assert [event.address for event in record.events] == list(range(length))


@pytest.mark.parametrize("opcode,base,operand,expected_pc,cost", [
    (OP_ADD, 0xFFFF, [1], 1, 3),
    (OP_JMP, 0xFFFE, [0, 0x20], 0x2000, 4),
    (OP_HALT, 0xFFFF, [], 0xFFFF, 2),
])
def test_pc_wraps_between_fetched_bytes(opcode, base, operand, expected_pc, cost, monkeypatch) -> None:
    runner = program(bytes([opcode]), base=base)
    for index, value in enumerate(operand, start=1):
        runner.load_ram((base + index) & 0xFFFF, value)
    record = MemoryRecorder(runner, monkeypatch)
    for _ in range(cost):
        record.step()
    assert runner.pc == expected_pc and runner.cpu.last_trace.retired
    assert [event.address for event in record.events] == [(base + index) & 0xFFFF for index in range(1 + len(operand))]

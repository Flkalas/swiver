"""Acceptance tests for the active P12 SYS-visible contract."""

from __future__ import annotations

from simulators.cyclesim.data.isa import OP_ADD, OP_BEQ, OP_HALT, OP_JMP, OP_LDA, OP_RET
from simulators.cyclesim.data.p12 import P12State, control_for
from simulators.cyclesim.program import ProgramRunner


def run_bytes(blob: bytes) -> ProgramRunner:
    runner = ProgramRunner()
    runner.load_rom_bytes(blob)
    runner.reset(pc=0)
    return runner


def test_reset_fill_and_sys_trace() -> None:
    runner = run_bytes(bytes([OP_ADD, 1, OP_HALT]))
    runner.cpu.step()
    assert runner.cpu.traces[0].state is P12State.FILL
    assert runner.cpu.traces[0].stage.if_active
    runner.cpu.step()
    assert runner.cpu.traces[1].state is P12State.IF_EX
    assert runner.cpu.traces[1].retired


def test_memory_stall_holds_if_and_loads_r0() -> None:
    runner = run_bytes(bytes([OP_LDA, 0x20, OP_HALT]))
    runner.load_ram(0x20, 0xA5)
    runner.run_until_halt()
    stalls = [t for t in runner.cpu.traces if t.state is P12State.MEM_STALL]
    assert len(stalls) == 1
    assert not stalls[0].stage.if_active
    assert runner.r0 == 0xA5


def test_taken_branch_has_visible_bubble() -> None:
    runner = run_bytes(bytes([OP_BEQ, 5, 0, OP_HALT, OP_HALT, OP_HALT]))
    runner.cpu.flg.z = True
    runner.run_until_halt()
    assert any(t.state is P12State.BRANCH_BUBBLE for t in runner.cpu.traces)
    assert runner.pc == 5


def test_reserved_0c_is_one_byte_trap() -> None:
    runner = run_bytes(bytes([0x0C, OP_HALT]))
    runner.run_until_halt()
    assert runner.halted and runner.pc == 1
    assert control_for(0x0C).name == "TRAP"


def test_explicit_degrade_hooks() -> None:
    runner = run_bytes(bytes([OP_HALT]))
    runner.cpu.request_stretch()
    runner.cpu.step()
    assert runner.cpu.last_trace and runner.cpu.last_trace.state is P12State.STRETCH
    runner.cpu.request_fallback_fe2()
    runner.cpu.step()
    assert runner.cpu.last_trace and runner.cpu.last_trace.state is P12State.FALLBACK_FE2

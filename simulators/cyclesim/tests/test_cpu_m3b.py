"""M3b fetch + execute — mini program and parity scenarios."""

from __future__ import annotations

from pathlib import Path

import pytest

from simulators.cyclesim.data.isa import (
    OP_BEQ,
    OP_JMP,
    OP_LDIO,
    OP_STA16,
    OP_STIO,
    insn_length,
)
from simulators.cyclesim.program import ProgramRunner
from simulators.cyclesim.values import H

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _run_fetch_opcode(runner: ProgramRunner) -> None:
    """Advance until first instruction opcode is latched in IR."""
    runner.reset(pc=0)
    runner.cpu.step()
    assert runner.cpu.last_trace is not None
    assert runner.cpu.last_trace.stage.fetch_active


def test_fetch_ir_mbr() -> None:
    runner = ProgramRunner()
    runner.load_rom_bytes(bytes([0x02, 0x42, 0x0A]), base=0)
    runner.reset(pc=0)
    runner.cpu.step()
    runner.cpu.step()
    assert runner.ir == 0x02
    assert runner.mbr == 0x42
    assert runner.pc == 2


def test_fetch_nets() -> None:
    runner = ProgramRunner()
    runner.load_rom_bytes(bytes([0x02, 0x42]), base=0)
    runner.reset(pc=0)
    runner.cpu.step()
    trace = runner.cpu._trace_fetch
    assert trace.get("net_fetch") == H
    assert trace.get("net_ir_load") is True
    assert trace.get("pc_inc_count") == 1
    runner.cpu.step()
    trace = runner.cpu._trace_fetch
    assert trace.get("net_mbr_load") is True
    assert trace.get("pc_inc_count") == 1
    assert runner.pc == 2
    assert insn_length(0x02) == 2


def test_mbr_before_mem_rd() -> None:
    runner = ProgramRunner()
    runner.load_rom_bytes(bytes([0x02, 0x42]), base=0)
    runner.load_ram(0x42, 0x99)
    runner.reset(pc=0)
    runner.cpu.step()
    runner.cpu.step()
    assert runner.mbr == 0x42
    runner.cpu.step()
    assert runner.gpr[0] == 0x99


def test_m3b_mini_program() -> None:
    runner = ProgramRunner()
    runner.load_rom_hex(FIXTURES / "m3b_mini.hex")
    runner.load_ram(0x42, 0x42)
    runner.reset(pc=0)
    steps = runner.run_until_halt(max_steps=500)
    assert runner.halted, f"did not halt in {steps} steps"
    assert runner.gpr[0] == 0x42


def test_add_writes_r0() -> None:
    runner = ProgramRunner()
    runner.load_rom_bytes(bytes([0x02, 0x10, 0x01, 0x05, 0x0A]), base=0)
    runner.load_ram(0x10, 0x10)
    runner.reset(pc=0)
    runner.run_until_halt(max_steps=200)
    assert runner.halted
    assert runner.gpr[0] == 0x15


def test_cmp_no_gpr_write() -> None:
    runner = ProgramRunner()
    runner.load_rom_bytes(bytes([0x02, 0x10, 0x0D, 0x10, 0x0A]), base=0)
    runner.load_ram(0x10, 0x10)
    runner.reset(pc=0)
    runner.run_until_halt(max_steps=200)
    assert runner.halted
    assert runner.gpr[0] == 0x10


def test_invalid_opcode_trap_nop() -> None:
    """0x10–0x1F: one-byte trap/NOP then fetch continues (not fetch-time HALT)."""
    runner = ProgramRunner()
    runner.load_rom_bytes(bytes([0x18, 0x0A]), base=0)
    runner.reset(pc=0)
    runner.run_until_halt(max_steps=50)
    assert runner.halted
    assert runner.pc == 1
    assert runner.gpr[0] == 0


def test_add_zero_after_cmp() -> None:
    runner = ProgramRunner()
    runner.load_rom_bytes(
        bytes([0x02, 0x10, 0x0D, 0xE9, 0x01, 0x00, 0x0A]),
        base=0,
    )
    runner.load_ram(0x10, 0x10)
    runner.reset(pc=0)
    runner.run_until_halt(max_steps=400)
    assert runner.halted
    assert runner.gpr[0] == 0x10


def test_beq_branch_taken() -> None:
    runner = ProgramRunner()
    # CMP $00 (Z=1) ; BEQ $0005 ; HALT at 5
    runner.load_rom_bytes(bytes([0x0D, 0x00, 0x04, 0x05, 0x00, 0x0A]), base=0)
    runner.reset(pc=0)
    runner.run_until_halt(max_steps=400)
    assert runner.halted
    assert runner.cpu.pc.pc == 5


def test_beq_not_taken() -> None:
    runner = ProgramRunner()
    runner.load_rom_bytes(bytes([0x02, 0x10, 0x0D, 0x00, 0x04, 0x08, 0x00, 0x0A]), base=0)
    runner.load_ram(0x10, 0x05)
    runner.reset(pc=0)
    runner.run_until_halt(max_steps=400)
    assert runner.halted


def test_jmp_unconditional() -> None:
    runner = ProgramRunner()
    runner.load_rom_bytes(bytes([0x05, 0x03, 0x00, 0x0A]), base=0)
    runner.reset(pc=0)
    runner.run_until_halt(max_steps=200)
    assert runner.halted
    assert runner.cpu.pc.pc == 3


def test_ldio_stio_mailbox() -> None:
    runner = ProgramRunner()
    runner.load_rom_bytes(bytes([0x08, 0x04, 0x09, 0x04, 0x0A]), base=0)
    runner.cpu.mem.sys.mailbox[0x04] = 0xAB
    runner.reset(pc=0)
    runner.run_until_halt(max_steps=400)
    assert runner.halted
    assert runner.gpr[0] == 0xAB
    assert runner.cpu.mem.sys.mailbox[0x04] == 0xAB


def test_mailbox_excludes_fffc() -> None:
    from simulators.cyclesim.blocks.mem_decode import mailbox_en

    assert not mailbox_en(0xFFFC)
    assert mailbox_en(0xFF00)
    assert mailbox_en(0xFFFB)


def test_reset_boot_vector() -> None:
    runner = ProgramRunner()
    runner.cpu.mem.set_vector(0x0000)
    runner.cpu.mem.load_bytes(0, bytes([0x0A]), target="rom")
    runner.reset(from_vector=True, map_mode=0)
    assert runner.pc == 0
    runner.run_until_halt(max_steps=100)
    assert runner.halted


def test_sta16_abs16_store() -> None:
    runner = ProgramRunner()
    runner.load_rom_bytes(bytes([0x0F, 0x00, 0x10, 0x0A]), base=0)
    runner.reset(pc=0)
    runner.cpu.gpr.regs[0] = 0x55
    runner.run_until_halt(max_steps=300)
    assert runner.halted
    assert runner.cpu.mem.read(0x1000) == 0x55


def test_map_mode_boot_vs_run() -> None:
    runner = ProgramRunner()
    runner.cpu.mem.sys.rom[0x100] = 0xAA
    runner.cpu.mem.sys.ram[0x100] = 0xBB
    runner.cpu.mem.map_mode = 0
    assert runner.cpu.mem.read(0x100) == 0xAA
    runner.cpu.mem.map_mode = 1
    assert runner.cpu.mem.read(0x100) == 0xBB


@pytest.mark.timeout(10)
def test_jmp_to_zero() -> None:
    """JMP $0000 must reload PC=0 (branch target may be zero)."""
    runner = ProgramRunner()
    runner.load_rom_bytes(bytes([0x05, 0x00, 0x00, 0x0A]), base=0)
    runner.reset(pc=0)
    for _ in range(12):
        runner.cpu.step()
    assert not runner.halted
    assert runner.pc == 0


@pytest.mark.timeout(120)
def test_fib_upto_250() -> None:
    from simulators.cyclesim.fixtures.rom_builder import (
        FIB_LIMIT,
        build_fib_to_limit_rom,
        fib_pair_before_target,
        fib_pairs_to_limit,
    )

    rom, ram_init, target, outer_pc = build_fib_to_limit_rom(FIB_LIMIT)
    assert target == 233  # largest Fibonacci term <= 250
    assert len(rom) < 80  # loop, not unrolled
    addr_fib_a, addr_fib_b = sorted(ram_init)
    exp_a, exp_b = fib_pair_before_target(FIB_LIMIT)
    assert exp_b == target
    pairs = fib_pairs_to_limit(FIB_LIMIT)

    runner = ProgramRunner()
    runner.load_rom_bytes(rom, base=0)
    for addr, val in ram_init.items():
        runner.load_ram(addr, val)
    runner.reset(pc=0)

    visit = 0
    steps = 0
    max_cpu_steps = 100_000
    while not runner.halted:
        if runner.pc == outer_pc and runner.cpu.fetch_pending:
            exp_a_step, exp_b_step = pairs[visit]
            assert runner.cpu.mem.read(addr_fib_a) == exp_a_step & 0xFF
            assert runner.cpu.mem.read(addr_fib_b) == exp_b_step & 0xFF
            visit += 1
        runner.cpu.step()
        steps += 1
        assert steps <= max_cpu_steps, f"fib exceeded {max_cpu_steps} CPU steps"

    assert visit == len(pairs)
    assert runner.cpu.mem.read(addr_fib_a) == exp_a & 0xFF
    assert runner.cpu.mem.read(addr_fib_b) == exp_b & 0xFF


@pytest.mark.timeout(10)
def test_call_ret_roundtrip() -> None:
    from simulators.cyclesim.blocks.return_stack import RP_CELL, STACK_BASE
    from simulators.cyclesim.fixtures.rom_builder import RomBuilder

    marker = 0x30
    rb = RomBuilder(0)
    rb.label("main")
    call_pos = rb.call("sub")
    return_pc = call_pos + 3
    rb.lda(marker)
    rb.halt()
    rb.label("sub")
    rb.ret()
    rom = rb.to_bytes()

    runner = ProgramRunner()
    runner.load_rom_bytes(rom, base=0)
    runner.load_ram(RP_CELL, STACK_BASE & 0xFF)
    runner.load_ram(RP_CELL + 1, (STACK_BASE >> 8) & 0xFF)
    runner.load_ram(marker, 0xAD)
    runner.reset(pc=0)

    steps = runner.run_until_halt(max_steps=500)
    assert steps > 0
    assert runner.halted
    assert runner.r0 == 0xAD
    assert runner.cpu.return_stack.read_rp() == STACK_BASE
    lo = runner.cpu.mem.read(STACK_BASE)
    hi = runner.cpu.mem.read(STACK_BASE + 1)
    assert lo | (hi << 8) == return_pc


@pytest.mark.timeout(10)
def test_ret_underflow_halts() -> None:
    from simulators.cyclesim.blocks.return_stack import RP_CELL, STACK_BASE
    from simulators.cyclesim.data.isa import OP_HALT, OP_RET

    runner = ProgramRunner()
    runner.load_rom_bytes(bytes([OP_RET, OP_HALT]), base=0)
    runner.load_ram(RP_CELL, STACK_BASE & 0xFF)
    runner.load_ram(RP_CELL + 1, (STACK_BASE >> 8) & 0xFF)
    runner.reset(pc=0)

    for _ in range(20):
        runner.cpu.step()
        if runner.halted:
            break

    assert runner.halted
    assert runner.pc == 1


@pytest.mark.timeout(60)
def test_fib_recursive() -> None:
    from simulators.cyclesim.fixtures.rom_builder import build_fib_recursive_rom

    n = 3
    rom, ram_init, expected = build_fib_recursive_rom(n)
    assert expected == 2

    n_arg = min(k for k in ram_init if k < 0x0F00)
    result_out = n_arg + 1

    runner = ProgramRunner()
    runner.load_rom_bytes(rom, base=0)
    for addr, val in ram_init.items():
        runner.load_ram(addr, val)
    runner.reset(pc=0)

    steps = 0
    max_cpu_steps = 2_000
    while not runner.halted:
        runner.cpu.step()
        steps += 1
        assert steps <= max_cpu_steps, f"fib recursive exceeded {max_cpu_steps} CPU steps"

    assert runner.r0 == expected & 0xFF
    assert runner.cpu.mem.read(result_out) == expected & 0xFF

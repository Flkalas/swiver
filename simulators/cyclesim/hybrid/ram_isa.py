"""Experimental paged-RAM ISA, deliberately separate from the v1.0 ISA.

Every instruction is two bytes: opcode and literal/offset. Bit 7 selects X
instead of the literal for the low address. Bit 6 is ignored. Bit 5 selects
AND/TEST instead of arithmetic in the ALU group (C=0); ignored otherwise.
Bit 4 selects STORE (other low opcode bits then ignored). Otherwise:
  0..3: LDI A, LDI X, LDI P, JMP
  4..7: LD A, LD X, LD P, JZ
  8..B: ADDI, SUBI, CMPI, JC
  C..F: ADD memory, SUB memory, CMP memory, HALT
P is the high address byte. X is the indirect low byte. Only the ALU group
updates Z/C; subtraction C means no borrow. HALT retains the post-fetch PC.
"""
from simulators.cyclesim.blocks.mem_decode import MemSystem

LDI, LXI, LPI, JMP = 0, 1, 2, 3
LDA, LDX, LDP, JZ = 4, 5, 6, 7
ADDI, SUBI, CMPI, JC = 8, 9, 10, 11
ADD, SUB, CMP, HALT, STA = 12, 13, 14, 15, 16
ANDI, TESTI, AND, TEST = 0x28, 0x2A, 0x2C, 0x2E
INDEXED = 0x80


class RamReference:
    """Independent instruction interpreter; never used to drive the circuit."""
    def __init__(self):
        self.mem = MemSystem()
        self.pc = self.a = self.x = self.p = 0
        self.z = self.c = self.halted = False
        self.retired = 0
        self.accesses = []

    def read(self, address):
        value = self.mem.read(address)
        self.accesses.append(('read', address, value))
        return value

    def step_instruction(self):
        if self.halted:
            return
        opcode = self.read(self.pc)
        self.pc = (self.pc + 1) & 65535
        literal = self.read(self.pc)
        self.pc = (self.pc + 1) & 65535
        address = self.p * 256 + (self.x if opcode & INDEXED else literal)
        op = opcode & 15
        if opcode & 16:
            self.mem.write(address, self.a)
            self.accesses.append(('write', address, self.a))
        elif op in (JMP, JZ, JC, HALT):
            if op == HALT:
                self.halted = True
            elif op == JMP or (op == JZ and self.z) or (op == JC and self.c):
                self.pc = address
        else:
            value = self.read(address) if op in (LDA, LDX, LDP, ADD, SUB, CMP) else literal
            if op in (LDI, LDA): self.a = value
            elif op in (LXI, LDX): self.x = value
            elif op in (LPI, LDP): self.p = value
            else:
                if opcode & 32:
                    result = self.a & value
                    self.z, self.c = result == 0, False
                else:
                    total = self.a + value if op in (ADDI, ADD) else self.a + 256 - value
                    result = total & 255
                    self.z, self.c = result == 0, total > 255
                if op not in (CMPI, CMP): self.a = result
        self.retired += 1


class Assembler:
    """Two-pass labels; symbolic low/high bytes keep far jumps explicit."""
    def __init__(self, base=0x800):
        self.base = base
        self.code = []
        self.labels = {}

    @property
    def pc(self): return self.base + len(self.code)

    def label(self, name):
        if name in self.labels: raise ValueError('duplicate label: '+name)
        self.labels[name] = self.pc

    def emit(self, opcode, operand=0):
        self.code.extend((opcode, operand))

    def jump(self, label, opcode=JMP):
        # LPI preserves flags, so this works for conditional branches too.
        self.emit(LPI, (label, 'hi'))
        self.emit(opcode, (label, 'lo'))

    def bytes(self):
        def resolve(value):
            if isinstance(value, tuple):
                address = self.labels[value[0]]
                return (address >> (8 if value[1] == 'hi' else 0)) & 255
            if not 0 <= value <= 255: raise ValueError(value)
            return value
        return bytes(resolve(v) for v in self.code)

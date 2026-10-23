"""Executable RAM-ISA examples and checked software call/return expansion.

CALL/RET preserve A, clobber P/X/Z/C, and use $0F02..$0F04 as scratch.
The original $0F00 pointer and $F600..$FEF0 aligned stack bounds are retained
by these macros, not enforced on arbitrary programs by the hardware.
"""
from simulators.cyclesim.hybrid.ram_isa import (
    Assembler, LDI, LXI, LPI, JMP, LDA, LDX, LDP, JZ, ADDI, SUBI,
    CMPI, JC, ADD, HALT, STA, INDEXED, TESTI,
)

RP, SAVED_A, TARGET_LO, TARGET_HI, ERROR = 0xF00,0xF02,0xF03,0xF04,0xF05


class Software(Assembler):
    def load(self,address,opcode=LDA):
        self.emit(LPI,address>>8)
        self.emit(opcode,address&255)

    def store(self,address):
        self.emit(LPI,address>>8)
        self.emit(STA,address&255)

    def adjust_pointer(self,cell,delta,tag):
        if delta not in (-1,1): raise ValueError(delta)
        self.load(cell)
        self.emit(ADDI if delta==1 else SUBI,1)
        self.store(cell)
        if delta==1:
            self.jump(tag+'_hi',JC)
            self.jump(tag+'_done')
            self.label(tag+'_hi')
        else:
            self.jump(tag+'_done',JC)  # no borrow
        self.load(cell+1)
        self.emit(ADDI if delta==1 else SUBI,1)
        self.store(cell+1)
        self.label(tag+'_done')

    def pointer(self,cell=RP):
        self.load(cell,LDX)
        if cell&255==255:
            self.emit(LPI,((cell+1)>>8)&255)
        self.emit(LDP,(cell+1)&255)  # address uses the old P before capture

    def guard(self,push,tag):
        self.load(RP)
        self.emit(TESTI,1)
        self.jump(tag+'_aligned',JZ)
        self.jump('invalid')
        self.label(tag+'_aligned')
        self.load(RP+1)
        self.emit(CMPI,0xF6)
        self.jump(tag+'_lower_ok',JC)
        self.jump('invalid')
        self.label(tag+'_lower_ok')
        self.emit(CMPI,0xFF)
        self.jump('invalid',JC)
        self.emit(CMPI,0xFE)
        self.jump(tag+'_top',JZ)
        if not push:
            self.emit(CMPI,0xF6)
            self.jump(tag+'_bottom',JZ)
        self.jump(tag+'_ok')
        self.label(tag+'_top')
        self.load(RP)
        self.emit(CMPI,0xF1)
        self.jump('invalid',JC)
        if push:
            self.emit(CMPI,0xF0)
            self.jump('overflow',JZ)
        self.jump(tag+'_ok')
        if not push:
            self.label(tag+'_bottom')
            self.load(RP)
            self.emit(CMPI,0)
            self.jump('underflow',JZ)
        self.label(tag+'_ok')

    def call(self,target,tag):
        self.store(SAVED_A)
        self.guard(True,tag)
        self.pointer()
        self.emit(LDI,(tag+'_return','lo'))
        self.emit(STA|INDEXED)
        self.adjust_pointer(RP,1,tag+'_inc0')
        self.pointer()
        self.emit(LDI,(tag+'_return','hi'))
        self.emit(STA|INDEXED)
        self.adjust_pointer(RP,1,tag+'_inc1')
        self.load(SAVED_A)
        self.jump(target)
        self.label(tag+'_return')

    def ret(self,tag):
        self.store(SAVED_A)
        self.guard(False,tag)
        self.adjust_pointer(RP,-1,tag+'_dec0')
        self.adjust_pointer(RP,-1,tag+'_dec1')
        self.pointer()
        self.emit(LDA|INDEXED)
        self.store(TARGET_LO)
        self.adjust_pointer(RP,1,tag+'_inc')
        self.pointer()
        self.emit(LDA|INDEXED)
        self.store(TARGET_HI)
        self.adjust_pointer(RP,-1,tag+'_dec2')
        self.load(SAVED_A)
        self.load(TARGET_LO,LDX)
        self.load(TARGET_HI,LDP)
        self.emit(JMP|INDEXED)

    def errors(self):
        for code,name in enumerate(('invalid','overflow','underflow'),1):
            self.label(name)
            self.emit(LDI,code)
            self.store(ERROR)
            self.emit(HALT)


def iterative_fibonacci(n=10):
    p=Software()
    for offset,value in enumerate((0,1,n)):
        p.emit(LDI,value);p.store(0x2000+offset)
    if n:
        p.label('loop')
        p.load(0x2000);p.emit(ADD,1);p.emit(STA,3)
        p.emit(LDA,1);p.emit(STA,0)
        p.emit(LDA,3);p.emit(STA,1)
        p.emit(LDA,2);p.emit(SUBI,1);p.emit(STA,2)
        p.jump('done',JZ);p.jump('loop')
    p.label('done');p.load(0x2000);p.emit(HALT)
    a,b=0,1
    for _ in range(n): a,b=b,(a+b)&255
    return p,{},a


def pointer_copy():
    """RAM-resident 16-bit pointer crosses $20FF->$2100, writes a second page."""
    p=Software();src=0x2200
    for i in range(4):
        p.pointer(src)
        p.emit(LDA|INDEXED)
        p.store(0x3000+i)
        p.adjust_pointer(src,1,'next'+str(i))
    p.emit(HALT)
    ram={src:0xFE,src+1:0x20}
    ram.update({0x20FE+i:0xA0+i for i in range(4)})
    return p,ram,2  # Final pointer is $2102; the last increment has no carry.


def recursive_fibonacci(n=3):
    p=Software()
    p.emit(LDI,n)
    p.call('fib','main')
    p.emit(HALT)
    p.label('fib')
    p.emit(CMPI,2)
    p.jump('recurse',JC)
    p.ret('base')
    p.label('recurse')
    # Per-depth scratch slots; this example is bounded to <128 nested frames.
    p.load(RP,LDX);p.emit(LPI,0x40);p.emit(STA|INDEXED)
    p.emit(SUBI,1);p.call('fib','left')
    p.load(RP,LDX);p.emit(LPI,0x41);p.emit(STA|INDEXED)
    p.emit(LPI,0x40);p.emit(LDA|INDEXED);p.emit(SUBI,2)
    p.call('fib','right')
    p.load(RP,LDX);p.emit(LPI,0x41);p.emit(ADD|INDEXED)
    p.ret('sum')
    p.errors()
    a,b=0,1
    for _ in range(n): a,b=b,(a+b)&255
    return p,{RP:0,RP+1:0xF6},a


def stack_boundary(push,rp):
    p=Software()
    p.emit(LDI,0x5A)
    if push:
        p.call('finish','check')
        p.emit(HALT)
        p.label('finish');p.emit(HALT)
    else:
        p.ret('check')
        p.label('finish');p.emit(HALT)
    p.errors()
    target=p.labels['finish']
    ram={RP:rp&255,RP+1:rp>>8}
    if not push:
        ram.update({(rp-2)&65535:target&255,(rp-1)&65535:target>>8})
    return p,ram

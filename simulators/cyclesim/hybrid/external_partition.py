"""74 ALU retained; external 574 bank; fitted control partition experiments."""
from pathlib import Path
import json
import re
from functools import lru_cache
from simulators.cyclesim.hybrid.rom_search import (
    ControlStore, shared_target_source, sequencer_source, eq, finish)
from simulators.cyclesim.hybrid.fit_blocks import header
from simulators.cyclesim.hybrid.partition_probe import fit
from simulators.cyclesim.hybrid.cpu import DP_REGS, LATCHES


def statements(source):
    return [' '.join(x.split()) for x in source.split(';') if x.strip()]


def sequencer():
    out=[]
    for line in statements(shared_target_source()):
        if line == 'Name romshare': line='Name extseq'
        if line == 'PIN 44 = ac': line='PIN 44 = zf'
        if line in ('PIN = rd','PIN = wr','PINNODE = zf','PINNODE = wc','PINNODE = cf'): continue
        if re.match(r'(?:rd|wr|zf|wc|cf)\.(?:d|ck|ar|ap)\s*=',line): continue
        if re.match(r'db\d(?:\.oe)?\s*=',line): continue
        if re.match(r'(?:dbzero|wcload|flagload)\s*=',line): continue
        out.append(line+';')
    out.insert(10,'PIN = wc;')
    return finish(out)


def auxiliary():
    s=ControlStore(); g=lambda pred:s.group(pred,'cmd')
    lines=header('extaux','f1504plcc44')
    lines += ['PIN 43 = clk;','PIN 1 = reset;','PIN 2 = waitin;','PIN 44 = ac;',
              'PIN = [db0..7];','PIN = [cmd0..5];','PIN = [p0..1];',
              'PIN = zf;','PIN = wc;','PIN = fault;','PIN = rd;','PIN = wr;',
              'PIN = romen_n;','PIN = tloen;','PIN = thien;','PIN = resen;',
              'PIN = sub;','PIN = subn;','PINNODE = cf;',
              'PINNODE = odd;','PINNODE = above;','PINNODE = equal;','PINNODE = zero;']
    for i in range(4): lines.append(f'phase{i} = {eq("p",i,2)};')
    lines += [f'memop = {g(lambda t:t.source=="MEM" or t.destination=="MEM")};',
              'stall = phase1 & memop & waitin;', 'cap = phase1 & !stall;',
              f'romen_n = reset # !({eq("cmd",63,6)});']
    for i in range(8):
        lines += [f'db{i} = {g(lambda t,b=i:t.source=="CU" and t.constant>>b&1)};',
                  f'db{i}.oe = !phase0 & ({g(lambda t:t.source=="CU")});']
    lines += [f'rd.d = !phase3 & ({g(lambda t:t.source=="MEM")});',
              f'wr.d = ((phase1 & !stall) # phase2) & ({g(lambda t:t.destination=="MEM")});',
              f'tloen.d = phase3 # !({g(lambda t:t.source=="TMP_LO")});',
              f'thien.d = phase3 # !({g(lambda t:t.source=="TMP_HI")});',
              f'resen.d = phase3 # !({g(lambda t:t.source=="RESULT")});',
              f'sub.d = {g(lambda t:t.subtract)};',f'subn.d = !({g(lambda t:t.subtract)});']
    predicates=dict(wcload=lambda t:t.source=='ALU',flagload=lambda t:t.flags,
                    guardload=lambda t:t.guard=='low',callcheck=lambda t:t.guard=='call',retcheck=lambda t:t.guard=='ret')
    for name,pred in predicates.items(): lines.append(f'{name} = cap & ({g(pred)});')
    prefixes=('dbzero =','dbfe =','dbf6 =','validhi =','badstack =','fault.d','wc.d','zf.d','cf.d','odd.d','above.d','equal.d','zero.d')
    lines += [line+';' for line in statements(sequencer_source()) if line.startswith(prefixes)]
    for name in ['zf','wc','cf','fault','odd','above','equal','zero','rd','wr','tloen','thien','resen','sub','subn']:
        lines += [f'{name}.ck = clk;',f'{name}.{"ap" if name in ("tloen","thien","resen","subn") else "ar"} = reset;']
    return finish(lines)


def latch_control():
    s=ControlStore();g=lambda pred:s.group(pred,'cmd')
    lines=header('extctrl','f1502plcc44')
    lines += ['PIN 43 = clk;','PIN 1 = reset;','PIN 44 = waitin;',
              'PIN = [cmd0..5];','PIN = [p0..1];','PIN = [dc0..4];','PIN = [den0..4];','PIN = [lc0..5];']
    for i in range(4): lines.append(f'phase{i} = {eq("p",i,2)};')
    lines += [f'memop = {g(lambda t:t.source=="MEM" or t.destination=="MEM")};','stall = phase1 & memop & waitin;']
    for i,reg in enumerate(DP_REGS):
        lines += [f'dc{i}.d = ((phase1 & !stall) # phase2) & ({g(lambda t,r=reg:t.destination=="DP" and t.select==r)});',
                  f'den{i}.d = phase3 # !({g(lambda t,r=reg:t.source in ("DP","ALU") and t.select==r)});']
    for i,reg in enumerate(LATCHES):
        lines.append(f'lc{i}.d = ((phase1 & !stall) # phase2) & ({g(lambda t,r=reg:t.destination==r)});')
    for reg in [f'dc{i}' for i in range(5)]+[f'den{i}' for i in range(5)]+[f'lc{i}' for i in range(6)]:
        lines += [f'{reg}.ck = clk;',f'{reg}.{"ap" if reg.startswith("den") else "ar"} = reset;']
    return finish(lines)


def auxiliary_table():
    """Use a decode ROM, with a CPLD write gate held inactive between writes."""
    source=auxiliary().replace('Name extaux;', 'Name tblaux;')
    source=source.replace('PIN = wr;', 'PINNODE = wr;\nPIN = wen_n;\nPIN = romn;')
    source += 'wen_n = !(wr & romn);\n'
    return source


@lru_cache(None)
def decode_image():
    """Address A2..A15, MAP; D0..3 are active-low RAM0/RAM1/ROM/mailbox CE."""
    result=bytearray(32768)
    for mode in (0,1):
        for a in range(0,65536,4):
            mb=0xFF00<=a<0xFFFC
            rom=not mode and (a<0x800 or a>=0xFFFC)
            ram=not(mb or rom)
            selected=(ram and a<0x8000,ram and a>=0x8000,rom,mb)
            result[(mode<<14)|(a>>2)] = sum(int(not x)<<i for i,x in enumerate(selected))
    return bytes(result)


def main():
    root=Path(__file__).resolve().parents[3];installed=root/'cpld/tools/wincupl-ii'
    results={}
    for name,src,dev in [('extseq',sequencer(),'1504'),('extaux',auxiliary(),'1504'),('extctrl',latch_control(),'1502'),('tblaux',auxiliary_table(),'1504')]:
        results[name]=fit(name,src,root,installed,dev)
    out=root/'simulators/cyclesim/build/hybrid-partition'
    (out/'external-search.json').write_text(json.dumps(results,indent=2)+'\n',encoding='utf-8')
    (out/'control.bin').write_bytes(ControlStore().image)
    (out/'decode.bin').write_bytes(decode_image())

if __name__=='__main__': main()

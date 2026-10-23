"""Two-1504 partitions with a real external IR/phase counter, optionally PC.

Same experimental RAM ISA and six-clock schedule. The ALU, accumulator,
writeback mux, data driver and zero comparator remain physical 74 packages.
Generated CUPL contains no hidden IR or phase counter copies.
"""
from simulators.cyclesim.hybrid.fit_blocks import header


def hold(lines, name, value, enable):
    lines += [f'{name}.ck = clk;', f'{name}.ar = !resetn;',
              f'{name}.d = ({enable} & ({value})) # (!({enable}) & {name});']


def cu_source(external_pc=False):
    lines = header('edupccu' if external_pc else 'educu', 'f1504plcc44')
    lines += ['PIN 43 = clk;', 'PIN 1 = resetn;', 'PIN 44 = wait;',
              'PIN 2 = carry;', 'PIN = [ir0..5];', 'PIN = [t0..2];',
              'PIN = zeron;', 'PIN = [cmd0..1];', 'PIN = immdrive;',
              'PIN = irloadn;', 'PIN = stepen;', 'PIN = steploadn;',
              'PIN = acloadn;', 'PIN = acdriven;', 'PIN = subcmd;',
              'PIN = subn;', 'PIN = rdn;', 'PIN = wrn;',
              'PINNODE = zflag;', 'PINNODE = cflag;', 'PINNODE = halted;']
    lines += ['flow = ir0 & ir1;', 'store = ir4;', 'ordinary = !(flow # store);',
              'frommem = ordinary & ir2;', 'alu = ordinary & ir3;',
              'execute = t2;', 'readreq = !execute # (execute & frommem);',
              'writereq = execute & store;', 'active = resetn & !halted;',
              'stall = t0 & wait & (readreq # writereq);',
              'tick = active & !stall;', 'cap = tick & t0;',
              'commit = cap & execute;', 'irload = cap & !execute & !t1;',
              'litload = cap & !execute & t1;',
              'xload = commit & !store & !ir3 & ir0 & !ir1;',
              'pload = commit & !store & !ir3 & !ir0 & ir1;',
              'cmd0 = litload # xload;', 'cmd1 = litload # pload;',
              'take = (!ir3 & (!ir2 # zflag)) # (ir3 & !ir2 & cflag);',
              'branch = commit & flow & !store & take;',
              'pcinc = cap & !execute;',
              'stop = flow & !store & ir2 & ir3;',
              'aenable = commit & ordinary & ((!ir3 & !ir0 & !ir1) # (ir3 & !ir1));',
              'flagload = commit & alu;',
              'irloadn = !irload;', 'stepen = tick;', 'steploadn = !commit;',
              'acloadn = !aenable;', 'acdriven = !(active & execute & store);',
              'immdrive = active & execute & ordinary & !frommem;',
              'subcmd = ir0 # ir1;', 'subn = !subcmd;',
              'rdn = !(active & readreq & t0);', 'wrn = !(cap & writereq);']
    hold(lines, 'halted', "'b'1", 'commit & stop')
    hold(lines, 'zflag', '!zeron', 'flagload')
    hold(lines, 'cflag', 'carry & !ir5', 'flagload')
    if external_pc:
        lines += ['PIN = pcenable;', 'PIN = pcloadn;', 'PIN = pcdriven;',
                  'PIN = addrdrive;', 'pcenable = pcinc;', 'pcloadn = !branch;',
                  'pcdriven = !(active & !execute & t0);',
                  'addrdrive = active & execute & t0;']
    else:
        lines += ['PIN = pcwrite;', 'pcwrite = pcinc # branch;']
    return '\n'.join(lines)+'\n'


def address_source(external_pc=False, nodes=()):
    lines = header('edupcaddr' if external_pc else 'eduaddr', 'f1504plcc44')
    lines += [f'PINNODE = {node};' for node in nodes]
    lines += ['PIN 43 = clk;', 'PIN 1 = resetn;',
              'PIN 44 = cmd0;', 'PIN 2 = cmd1;',
              'PIN = [db0..7];', 'PIN = [addr0..15];',
              'PIN = indexed;', 'PIN = immdrive;',
              'PINNODE = [x0..7];', 'PINNODE = [page0..7];',
              'xload = cmd0 & !cmd1;', 'pload = !cmd0 & cmd1;',
              'litload = cmd0 & cmd1;']
    if external_pc:
        lines += ['PIN = addrdrive;']
    else:
        lines += ['PIN = execute;', 'PIN = pcwrite;', 'PINNODE = [pc0..15];',
                  'branch = pcwrite & execute;', 'pcinc = pcwrite & !execute;']
    for bit in range(8):
        # Register feedback dbN means the literal Q, dbN.io means the physical pad.
        hold(lines, f'db{bit}', f'db{bit}.io', 'litload')
        lines += [f'db{bit}.oe = immdrive;']
        hold(lines, f'x{bit}', f'db{bit}.io', 'xload')
        hold(lines, f'page{bit}', f'db{bit}.io', 'pload')
        lines += [f'target{bit} = (indexed & x{bit}) # (!indexed & db{bit});',
                  f'target{bit+8} = page{bit};']
    for bit in range(16):
        if external_pc:
            lines += [f'addr{bit} = target{bit};', f'addr{bit}.oe = addrdrive;']
        else:
            lower = ' & '.join(f'pc{i}' for i in range(bit)) or "'b'1"
            # The low target is already driven on ADDRESS during branch capture.
            # Read the real pad instead of expanding that mux into every PC D term.
            target = f'addr{bit}.io' if bit < 8 else f'target{bit}'
            lines += [f'pc{bit}.ck = clk;', f'pc{bit}.ar = !resetn;',
                      f'pc{bit}.d = (branch & {target}) # (!branch & (pc{bit} $ (pcinc & ({lower}))));',
                      f'addr{bit} = (execute & target{bit}) # (!execute & pc{bit});']
    return '\n'.join(lines)+'\n'


def external_packages(external_pc=False):
    packages = []

    def add(ref, part, **pins):
        packages.append(dict(ref=ref, part=part, group='visible_state',
                             pins=dict(VCC='VCC', GND='GND', **pins)))

    def reg(ref, q, d, enable):
        add(ref, '74HC377', CLK='SYS', EN_N=enable,
            **{f'D{i}':f'{d}[{i}]' for i in range(8)},
            **{f'Q{i}':f'{q}[{i}]' for i in range(8)})

    def buffer(ref, q, d, enable, offset=0):
        add(ref, '74HC244', OE1_N=enable, OE2_N=enable,
            **{f'A{i}':f'{d}[{i+offset}]' for i in range(8)},
            **{f'Y{i}':f'{q}[{i+offset}]' for i in range(8)})

    reg('IR', 'IR', 'DB', 'IR_LOAD_N')
    reg('AC', 'A', 'WRITEBACK', 'AC_LOAD_N')
    for half in range(2):
        pins = dict(S='IR[3]', G_N='GND')
        for i in range(4):
            pins.update({f'{i+1}A':f'DB[{4*half+i}]',
                         f'{i+1}B':f'Y[{4*half+i}]',
                         f'{i+1}Y':f'WRITEBACK[{4*half+i}]'})
        add(f'WRITEBACK{half}', '74HC157', **pins)
    buffer('AC_DRIVER', 'DB', 'A', 'AC_DRIVE_N')
    add('ZERO', '74HC688', OE_N='GND', EQ_N='ZERO_N',
        **{f'P{i}':f'Y[{i}]' for i in range(8)},
        **{f'Q{i}':'GND' for i in range(8)})
    add('STEP', '74HC161', CLK='SYS', CLR_N='RESET_N',
        LOAD_N='STEP_LOAD_N', ENP='STEP_ENABLE', ENT='VCC', RCO=None,
        **{f'D{i}':'GND' for i in range(4)},
        **{f'Q{i}':f'STEP[{i}]' for i in range(4)})
    if external_pc:
        for nibble in range(4):
            add(f'PC{nibble}', '74HC161', CLK='SYS', CLR_N='RESET_N',
                LOAD_N='PC_LOAD_N', ENP='PC_ENABLE',
                ENT='VCC' if nibble==0 else f'PC_CARRY[{nibble-1}]',
                RCO=f'PC_CARRY[{nibble}]' if nibble<3 else None,
                **{f'D{i}':f'ADDRESS[{4*nibble+i}]' for i in range(4)},
                **{f'Q{i}':f'PC[{4*nibble+i}]' for i in range(4)})
        for half in range(2):
            buffer(f'PC_DRIVER{half}', 'ADDRESS', 'PC', 'PC_DRIVE_N', 8*half)
    return packages

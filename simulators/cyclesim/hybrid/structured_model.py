"""Execute generated structured sequencer equations on clock edges.

Output-command expansion and flags/guards are the existing transfer model here;
this validates the generated sequencer, not an assembled pin-level CPU.
"""
from simulators.cyclesim.hybrid.incdec import IncDecCpu
from simulators.cyclesim.hybrid.cupl_model import Equations, bits, number
from simulators.cyclesim.hybrid.structured_fit import sequencer_source, command_set


class StructuredEquationCpu(IncDecCpu):
    order = "fields"

    def reset(self, pc=0):
        super().reset(pc)
        self.seq = Equations(sequencer_source(self.order))
        self.control_trace = []

    def step_instruction(self, *, wait_every=0):
        if self.halted: return
        table = command_set(self.order)
        width = (len(table)-1).bit_length()
        waited = False
        for _ in range(2048):
            phase = number(self.seq.state, "p", 2)
            inputs = dict(clk=0, reset=0, waitin=0, wc0=int(self.work_carry),
                          zf0=int(self.z), fault=int(self.fault is not None))
            values = self.seq.values(inputs)
            if values["stopped"]:
                self.halted = True
                self.retired += 1
                return
            t = table[number(values, "cmd", width)]
            assert t is not None, (self.seq.state, number(values, "cmd", width))
            memory = t.source == "MEM" or t.destination == "MEM"
            wait = bool(phase == 1 and memory and wait_every and not waited
                        and self.transfers % wait_every == 0)
            if wait: waited = True
            inputs["waitin"] = int(wait)
            values = self.seq.values(inputs)
            bus, _ = self._drive(t)
            values.update(bits("db", bus, 8))
            nxt = self.seq.next(values)
            if values["capture"]:
                self.control_trace.append((number(values,"s",5), number(values,"t",3),
                                           number(values,"k",4), values["b0"]))
                ticks = self.ticks
                self.transfer(t)
                self.ticks = ticks
            self.seq.state = nxt
            self.ticks += 1
            if self.fault:
                return
            if phase == 3:
                waited = False
                if number(nxt,"s",5) == 0 and number(nxt,"t",3) == 0:
                    self.retired += 1
                    return
        raise AssertionError("structured CUPL edge cap")

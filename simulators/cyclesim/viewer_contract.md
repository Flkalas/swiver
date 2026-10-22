# ALU viewer API v1

This contract separates electrical connectivity, presentation, and observation.
`model_version` is `alu12-v1`. Simulation is zero delay; `iterations` counts
settling passes, never CPU clocks or nanoseconds. Pins use functional names,
with additional `package.pins` metadata mapping them to TI PDIP-16 contact numbers. The physical core contains exactly eight HC153, two HC283,
and two HC157 packages; control glue and comparison probes are outside it.

## Python boundary

`simulators.cyclesim.viewer_model.circuit_definition() -> dict`

`AluSession()` starts with A=B=0 and the ADD preset.
`session.snapshot() -> dict` returns a JSON-safe observation.
`session.update(payload: dict) -> dict` validates completely before mutation,
sets inputs, settles the actual netlist, increments `state_id`, and returns a
snapshot. `ValueError` means invalid input, with the old state preserved.
`session.reset() -> dict` restores initial inputs and increments `state_id`.
The HTTP layer serializes session operations with a lock.

## HTTP boundary

- `GET /api/circuit`: circuit definition.
- `GET /api/snapshot`: latest snapshot.
- `GET /api/revision`: process/asset revision; clients reload when it changes.
- `POST /api/input`: `{request_id, a, b, mode, operation, controls}`.
- `POST /api/reset`: `{request_id}`.
- Success returns the snapshot with the caller's integer `request_id` echoed.
- Errors return `{error: string}` with HTTP 400 (validation), 404, or 500.

Inputs `a,b` are integers 0..255 (booleans are invalid), `mode` is `preset` or
`direct`, `operation` is one of the preset IDs. Direct controls are integer
`cin` (0..1), `bctrl` (0..15), `lgc` (0..15), `y_mux_sel` (0..1).
No arithmetic is implemented in JavaScript. The client queues writes and
ignores obsolete responses by request ID and state ID, and visibly marks
observations stale when requests fail. Periodic GET detects disconnects.

## Circuit definition

```text
{
  model_version, title,
  components: [{id, part, pins: {pin_name: net_id}, source,
                package: {type, view, source, pins: {pin_name: {number,label,direction}}}}],
  nets: [{id, kind: "data"|"control"|"power", endpoints: [{component,pin}]}],
  buses: [{id, label, nets: [least_significant_net,...]}],
  presets: [{id, label, controls: {cin,bctrl,lgc,y_mux_sel},
             cpu_policy: {acc_write: boolean, flags_write: ["C","Z"]}}],
  boundary: [{id,label,description}]
}
```

Bus IDs: `a`, `b`, `b_add`, `logic`, `sum`, `y`. Component IDs and net IDs
retain the exported netlist spelling (`U_ALU_153_0`, `net_a0`, etc.).
Layout coordinates and collapsed/expanded selection live only in web assets.
The 153 address always equals A_bit + 2*B_bit; opcode select bits do not replace
operand selects. Enable/strobe pins are tied low and appear in the definition.

## Snapshot

```text
{
  model_version, state_id,
  inputs: {a,b,mode,operation,controls:{cin,bctrl,lgc,y_mux_sel}},
  signals: {net_id: "0"|"1"|"X"|"Z"},
  buses: {bus_id: {bits: "MSB...LSB", value: integer|null}},
  changed_nets: [net_id], active_nets: [net_id],
  components: {component_id: {pins:{pin_name:logic_string}, active:boolean, detail:string}},
  comparison: {expected:{stage:integer},actual:{stage:integer|null},
               match:boolean|null,first_mismatch:string|null},
  cpu_policy: {acc_write:boolean|null,flags_write:["C","Z"]},
  comparison_flags: {zero:boolean|null,carry_ge:integer|null},
  diagnostics: [{code,message,nets:[net_id]}],
  settled:boolean, iterations:integer
}
```

Comparison stages are `b_add`, `logic`, `sum`, `c_lo`, `c_hi`, `y` in that
order. Preset expectations use independent arithmetic/truth expressions;
direct mode uses independent table indexing. Unknown buses are null, never 0.
`net_c_hi` is the physical adder carry even during logic operations.
`comparison_flags` reports Y==0 and physical carry; carry means unsigned >=
only in SUB/CMP. CPU policy is descriptive and does not update CPU state.
Direct mode has null ACC policy and no implied flag writes.
NOP uses existing zero controls, so physical Y=A; CPU state holds.
CMP makes SUB Y and carry but inhibits ACC writes.

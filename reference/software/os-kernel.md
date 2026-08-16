# OS kernel (S6)

Host-side microkernel model used for early bring-up on logic VM (developer).

## Cooperative / polling model

Normative v1.0 hardware has **no IRQ**. **S6** uses **polling I/O** (Mailbox status polls) and **cooperative** tasking — no preemptive scheduler. See [swiver-whitepaper.md](../../swiver-whitepaper.md) §9.1.

## Responsibilities

- Boot flow and shell entry point
- Minimal bump allocator (`kmalloc`)
- Console output (`kprint`)
- Device discovery manager (`devmgr_scan`)
- GPIO/Serial peripheral ownership (polling)

## Implementation

- Kernel model: `kern/kernel.py`
- Scenario kind: `kind: kernel` in `hw/scenarios/vm/os_boot.yaml`
- Discovery spec: [device-discovery.md](../copro/device-discovery.md)

## Gate

- `tests/test_kernel_boot.py`
- `

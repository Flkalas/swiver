# Program loader (S7c)

`.PLR` is the Swiver executable format used by PL-DOS. It is intentionally minimal.

## Format

```
+0  magic[4]   \"PLR\\x00\"
+4  load_addr  u16 LE
+6  byte_size  u16 LE
+8  entry_off  u16 LE
+10 code[byte_size]
```

## Host reference implementation

- `kern/plr.py` — pack/unpack
- `kern/spawn.py` — `spawn()` loads into `SwiverMachine` RAM and runs until HALT

## Gate

- `tests/test_plr_exec.py`


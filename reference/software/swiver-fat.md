# PLFS on-disk layout (S7b)

PLFS is a minimal flat catalog filesystem used by PL-DOS v0.1.

## Sectors

- 512 bytes per sector
- Sector 0: reserved (future BPB / magic)
- Sector 1: directory sector (32 entries × 16 bytes)
- Sector 2+: data area (contiguous runs)

## Directory entry (16 bytes)

| Field | Size | Notes |
|-------|------|------|
| `name11` | 11 | 8.3 upper, padded with spaces |
| `start_sector` | 2 | u16 LE |
| `size_bytes` | 2 | u16 LE |
| `attr` | 1 | reserved |

Remaining bytes are reserved/padding.

## Host reference implementation

- `kern/plfs.py`
- Virtual FDD image helpers under host tooling (see PL-DOS roadmap)


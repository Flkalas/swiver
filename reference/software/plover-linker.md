# Swiver linker and object format (PLX) MVP

`PLX` is a link input format for `plover_ld`. The runtime executable remains `.PLR`.

## PLX container

For MVP, `PLX` is stored as JSON with this top-level structure:

- `magic`: `"PLX\0"`
- `version`: `1`
- `name`: module name
- `entry_symbol`: optional entry symbol (default `main`)
- `text`: byte array (list of `0..255`)
- `data`: byte array (list of `0..255`)
- `symbols`: symbol records
- `relocs`: relocation records

## Symbol record

Each symbol record:

- `name`: symbol name
- `section`: `text` | `data` | `abs` | `undef`
- `offset`: u16 offset in section (ignored for `undef`)
- `binding`: `global` | `local`
- `type`: `func` | `object`

## Relocation record

Each relocation record:

- `section`: `text` | `data`
- `offset`: relocation location offset in section
- `kind`: `abs16` | `rel8`
- `symbol`: referenced symbol name

`abs16`: write little-endian absolute address of symbol.  
`rel8`: write signed 8-bit relative displacement from `(patch_addr + 1)` to symbol.

## Link output

`plover_ld` links one or more `.plx` objects and emits:

- linked bytes (`text` + `data`)
- symbol map
- relocation stats
- Executable `.plr` format

## CLI

Emit linked images for breadboard using frozen fixtures in [fixtures](../fixtures/). No host toolchain lives in the Active tree.


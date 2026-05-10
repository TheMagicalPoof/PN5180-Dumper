# Serial Protocol

The current firmware uses a simple line-oriented protocol named `PND1`.

The protocol is intentionally human-readable because the diagnostic serial log is part of the workflow. A future `PND2` protocol may move to structured request IDs and NDJSON, but `PND1` is the implemented contract today.

## Startup

```text
READER_READY protocols=ISO15693,ISO14443A,FELICA device=XIAO-ESP32-S3
```

The firmware no longer performs cyclic reads by itself. The host must send commands.

## Dump Command

Request:

```text
PND1 DUMP
```

Typical response:

```text
TAG_DETECTED type=ISO14443A protocol=ISO14443A uid=C363AE0E uid_length=4 atqa=0400 sak=08 family=MIFARE_CLASSIC_1K
DUMP_BEGIN
META type=ISO14443A protocol=ISO14443A uid=C363AE0E uid_length=4 rc=0 block_size=16 num_blocks=64 ... memory_read=ok blocks_read=64 sectors=16 sectors_authenticated=16 key_dictionary_size=1
COMPACT_BEGIN
INFO mfclassic_block block=0
C3 63 AE 0E 00 08 04 00 62 63 64 65 66 67 68 69
COMPACT_END
DUMP_END
```

When no tag is present:

```text
INFO no_card
```

## Compact Block Status

Before each hex line, firmware may emit one block-status marker:

- `INFO mfclassic_block block=N`: block was read.
- `INFO mfclassic_block_missing block=N`: authenticated but read failed.
- `INFO mfclassic_block_key_missing block=N`: no known key worked.

The Python parser maps these to:

- `OK`
- `NN`
- `MS`

## MIFARE Classic Brute/Pick

Request:

```text
PND1 BRUTE <block> <A|B> <12-hex-key>
```

Response:

```text
PND1 BRUTE_RESULT block=15 key_type=A key=FFFFFFFFFFFF status=ok data=00112233445566778899AABBCCDDEEFF
PND1 BRUTE_RESULT block=15 key_type=A key=FFFFFFFFFFFF status=auth_failed
PND1 BRUTE_RESULT block=15 key_type=A key=FFFFFFFFFFFF status=read_failed
```

The Qt app queues dictionary attempts host-side and sends one command at a time.

## MIFARE Classic Write

Request:

```text
PND1 WRITE <block> <32-hex-data> [VERIFY] [ALLOW0]
```

Responses:

```text
PND1 WRITE_RESULT block=1 status=ok key_type=A key=FFFFFFFFFFFF
PND1 WRITE_RESULT block=3 status=skipped_protected
PND1 WRITE_RESULT block=0 status=magic_unlock_failed
PND1 WRITE_RESULT block=0 status=ok key_type=M key=FFFFFFFFFFFF
```

Safety behavior:

- Sector trailers are always skipped.
- Block 0 is skipped unless `ALLOW0` is present.
- `ALLOW0` is meant only for UID-changeable blanks.
- `key_type=M` means the Gen1A magic fallback wrote block 0.

Known block 0 failure statuses:

- `magic_unlock_failed`: Gen1A backdoor did not respond.
- `magic_write_failed`: backdoor opened but block write failed.
- `magic_verify_failed`: write appeared to run but verify did not match.

## Magic Probe

Request:

```text
PND1 MAGIC_PROBE
```

Response:

```text
PND1 MAGIC_RESULT gen1a=ok
PND1 MAGIC_RESULT gen1a=failed
```

This only probes the Gen1A `0x40/0x43` backdoor. CUID/FUID/UFUID blanks may still be UID-changeable even when this probe fails.

## Future PND2 Direction

The desired future protocol is request/response NDJSON with IDs:

```text
PND2 {"id":1,"cmd":"hello"}
PND2 {"id":1,"status":"ok","device":{"name":"PN5180 Dumper","fw":"0.3.0"}}
```

This is not implemented yet.

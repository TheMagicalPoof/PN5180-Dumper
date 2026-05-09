# Serial Protocol

This project currently supports a legacy streaming protocol and is being prepared for a command protocol.

## Legacy Streaming Protocol

The firmware emits records without host commands:

```text
READER_READY protocols=ISO15693,ISO14443A,FELICA device=XIAO-ESP32-S3
DUMP_BEGIN
META type=ISO15693 protocol=ISO15693 uid=E008... uid_length=8 rc=0 block_size=8 num_blocks=250 ...
COMPACT_BEGIN
00 00 00 00 00 00 00 00
COMPACT_END
DUMP_END
```

The host parser in `host/python/pn5180_dumper/capture.py` supports this for current captures.

## Planned Command Protocol V2

V2 should be line-oriented NDJSON with a short prefix so logs remain easy to inspect and resynchronize:

```text
PND2 {"id":1,"cmd":"hello"}
PND2 {"id":1,"status":"ok","device":{"name":"PN5180 Dumper","fw":"0.3.0"}}
```

Host request fields:

- `id` - host-generated integer request id.
- `cmd` - command name.
- `args` - optional command arguments.

Firmware response fields:

- `id` - matching request id, when response belongs to a request.
- `event` - async event name, for scans and progress.
- `status` - `ok` or `error` for command completion.
- `error` - structured error object when `status=error`.

## Planned Commands

- `hello` - firmware/protocol capabilities.
- `config.get` / `config.set` - RF and reader settings.
- `scan` - scan protocols and report visible tags.
- `identify` - activate one selected tag and return metadata.
- `read` - read blocks/pages/services.
- `write` - write blocks/pages/services.
- `dump` - read all discoverable memory using a strategy.
- `auth` - authenticate/unlock when supported.
- `auth.test_keys` - try a host-provided key dictionary against MIFARE Classic sectors.
- `raw.transceive` - expert low-level command.
- `cancel` - cancel long operation.

## Example Scan

```text
PND2 {"id":10,"cmd":"scan","args":{"protocols":["auto"],"timeout_ms":3000}}
PND2 {"id":10,"event":"tag","tag":{"protocol":"ISO15693","uid":"E008014860A33A8F"}}
PND2 {"id":10,"status":"ok","summary":{"count":1}}
```

## Example Read

```text
PND2 {"id":11,"cmd":"read","args":{"protocol":"ISO15693","uid":"E008014860A33A8F","block":0,"count":4}}
PND2 {"id":11,"event":"data","offset":0,"encoding":"hex","data":"000000000000000000010A0C070A0000"}
PND2 {"id":11,"status":"ok"}
```

## Example MIFARE Classic Key Test

```text
PND2 {"id":12,"cmd":"auth.test_keys","args":{"protocol":"ISO14443A","uid":"C363AE0E","key_type":["A","B"],"keys":["FFFFFFFFFFFF","A0A1A2A3A4A5"]}}
PND2 {"id":12,"event":"auth","sector":0,"key_type":"A","key":"FFFFFFFFFFFF","status":"ok"}
PND2 {"id":12,"event":"auth","sector":1,"status":"failed"}
PND2 {"id":12,"status":"ok","summary":{"sectors":16,"authenticated":1}}
```

## Safety Rules

- `write`, `lock`, `password`, and `raw.transceive` must never run implicitly.
- Host UIs should show the exact target protocol, UID, address range, and byte count before write operations.
- Dumps should include metadata, raw serial/protocol logs, and hashes.

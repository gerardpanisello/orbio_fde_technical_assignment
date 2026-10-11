# Carry-over notes for spec 003 (from 002 implementation)

- **Location extraction:** the engine splits location text only on `, / ( )`. Text like "Centro de Madrid" / "Madrid centro" won't match. The extractor must return city and zone as separate parts (e.g. `"Centro, Madrid"` or structured `{city_text, zone_text}`) plus `is_known_place`.
- **Start date:** extractor emits a structured expression (`asap` | `absolute` | `offset` | `next_weekday`), never computes dates.
- **Empty extraction:** `{}` must not parse as UNCLEAR (`Unclear.kind` has no default); map "nothing understood" explicitly.

Снимок настроек TTS — «голос ок» (2026-10-02).

Файлы:
  tts_config.json
  reading_profiles.json
  pronunciations.json  (если лежал рядом в корне — скопируй вручную при полном откате)

Откат в корень Cursor_TTS:
  powershell -NoProfile -File scripts\restore_tts_backup.ps1 -Stamp 2026-10-02_heard_ok

Или вручную скопировать json из этой папки поверх одноимённых в корне репо,
затем в панели TTS: Stop → Restart daemon (или просто сменить профиль туда-обратно).

Активный пресет в снимке: reading_profile=a (Tera ru_f1).
Эффективно из A: scale≈1.18, pause_ms≈480, chunk≈320.

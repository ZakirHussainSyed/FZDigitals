# Daily Quran and Hadith content

Add reviewed Quran verses and Hadith as entries in `daily_content.json`. Keep the
same text fields for both types: `id`, `type`, `topic`, `arabic`,
`translations`, and `review_status`.

Use type-specific citation objects:

```json
{
  "type": "quran",
  "citation": {
    "surah": "Al-Baqarah",
    "chapter": 2,
    "verse": 43
  }
}
```

```json
{
  "type": "hadith",
  "citation": {
    "book": "Sahih al-Bukhari",
    "number": "615"
  }
}
```

The displays show Quran citations as Surah, chapter, and verse, and Hadith
citations as book and Hadith number at the bottom of each card. Keep entries in
`draft` until their text and translations have been reviewed; only `approved`
entries are displayed. Increment the package `version` whenever its content
changes so offline devices refresh their cached copy.

# `person_names.txt`: where the list comes from

Used by `services/name_redaction.py` (patch 0064) to find people's first names in staff questions, so they can be
replaced before a question is stored or sent to an outside service. One lower-case name per line; 38,108 names.

- **Source:** US Social Security Administration, "Popular Baby Names", national data (`names.zip`, every name given to
  at least 5 babies in a year, 1880 to 2025), downloaded 2026-11-02 from https://www.ssa.gov/oact/babynames/limits.html.
  Work of the US federal government: public domain.
- **Kept:** names given to at least 100 babies in total.
- **Removed:** names that are ordinary English words (the macOS word list) unless given to at least 50,000 babies, so
  "maria" and "tom" stay but "key" and "any" go; month and day names (May, June, April and August stay, and are treated
  as names only beside a surname, a title or a role word); 42 capitalised words that occur in the BPL policies but are not
  people there (Media, Brooklyn, Manual, General...). John, Melanie and Don, which name people in the policies, stay.
- **Rebuild:** `python scripts/build_person_names.py packages/orchestrator/config/person_names.txt`, run from a folder
  holding the unzipped SSA files in `ssa/` (needs `/usr/share/dict/words`, i.e. macOS or Linux). Re-run the name tests.

Everyday-word names (Will, May, Grace, Mark, Hope...) are listed in `services/name_redaction.py` (`AMBIGUOUS`): they count
only beside a surname, a title or a role word. No list is complete: rare names (for example "Selvon") are missed, which
is why the question box also asks staff not to type names.

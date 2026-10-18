# PDF text reader (patch 0015)

Chunks, headings and page labels are built from the text the PDF reader returns. The current reader is `pypdf`. It
breaks words on some PDFs ("overal l", "T o p r o m o t e", "enha nce"); the extra spaces end up in stored chunks and
in the text the model reads. `pypdfium2` (PDFium, the engine Chrome uses) is available as an **opt-in** alternative.

**Nothing changes unless you set `PDF_READER=pdfium` and re-ingest.** The default is `pypdf`. Chunk strategy,
thresholds, top-k and OCR rules are untouched.

## Compare before you switch (read-only: no database, keys, Pinecone or OCR)

    askbpl-reader-compare "path/to/Policy.pdf" [more.pdf ...]
    askbpl-provenance-report --reader pdfium "path/to/Policy.pdf" ...      # chunks, pages, headings under pdfium
    askbpl-provenance-report --reader pypdf  "path/to/Policy.pdf" ...      # the same under pypdf

`askbpl-reader-compare` prints, per PDF and then in total:
- **split-word indicator** (approximate: isolated lower-case single letters other than "a"; read the samples);
- **characters only in one reader's output** (ligatures such as "fi" are normalised first, so what is left is real:
  text one reader could not read);
- **thin pages** (under 100 characters; a page below `OCR_MIN_CHARS_PER_PAGE` is sent to OCR when OCR is installed);
- **confident headings** each reader yields, and the ones only one of them finds;
- **unusual characters** (control, private-use, replacement) in each reader's text.

## What the comparison showed on the 28 supplied PDFs (sandbox, pypdf 6.19.0, pypdfium2 5.14.0)

| | pypdf | pdfium |
|---|---|---|
| Split-word indicator | 195 | 49 |
| Materials Selection (indexed) | 70 | 0 |
| Annual Leave (indexed) | 7 | 0 |
| Text only this reader produced | 18 characters | 0 |
| PDFs where confident headings differ | 3 | |
| PDFs where the thin-page count differs | 1 | |

Findings and costs, so nobody is surprised:
1. **PDFium writes U+FFFE where a line ends in a hyphen** ("Anti-" / "Harassment"). The patch maps it to the hyphen
   pypdf writes. Without that, "Anti-Harassment" would be stored with a non-character inside the word.
2. **PDFium can return nothing for text pypdf reads.** In *Use of Personal Vehicles* the title "Policy and Procedure"
   (18 characters) comes back as a non-breaking space. The comparison shows it as "only in pypdf". Run it on every
   PDF you intend to ingest and read the lines under "only in pypdf".
3. **Heading detection depends on line structure, which differs.** pypdf emits whitespace-only lines that PDFium does
   not. Across the 28 PDFs: one heading gained (*Media Relations*, "I. Policy Overview"), one lost (*Crisis
   Management*, "Related Policies/Documents", because the 0013b wrapped-sentence rule no longer sees a blank line
   above it), and one deck cleaner ("ONL Y" becomes "ONLY"). None of the three is among the seven indexed policies.
4. **Thin-page routing can change.** *Internal Communications* page 6 is 102 characters under pypdf and 99 under
   PDFium, so with OCR installed PDFium would send it to OCR. Not among the seven indexed policies.
5. **Chunk counts can shift** by one (Annual Leave 8 to 7 chunks in the sandbox) because removed stray spaces shorten text.
6. **A missing `pypdfium2` or an unknown reader name raises.** It never falls back to pypdf quietly, because that
   would store different text from the one you chose.

## Switching (only after reading the comparison on the PDFs you will ingest)

1. Set `PDF_READER=pdfium` in `.env`.
2. Re-ingest (`docs/PROVENANCE.md`). Old vectors for a document are deleted and replaced.
3. Run the live eval with `--repeat 3`. Change nothing else in the same run. Record the commit and results.

Rollback: set `PDF_READER=pypdf` (or remove the line) and re-ingest.

## Limits
- The comparison uses selectable text only. Scanned pages still go to OCR and are not compared.
- The sandbox could not download the real tokenizer vocabulary, so chunk counts there are approximate. Run
  `askbpl-provenance-report --reader pdfium` yourself on the seven indexed PDFs and read the chunk starts.
- Passing tests show pipeline behaviour, not that answers are correct.

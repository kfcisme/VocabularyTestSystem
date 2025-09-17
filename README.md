# VocabularyTestSystem

> Automatically generate English vocabulary test papers and answer sheets (with PDF export).

[![License](https://img.shields.io/badge/license-MIT-informational.svg)](#license)
[![Status](https://img.shields.io/badge/status-active-brightgreen.svg)]()
[![Python](https://img.shields.io/badge/Python-3.9%2B-blue.svg)]()

---

## ✨ Overview

**VocabularyTestSystem** takes your wordlist and automatically creates exam papers and answer sheets. You can specify the number of questions, control randomness with a seed, and export both the test and the answers as PDFs. The default question type is **four-choice multiple-choice cloze test**: the target word is blanked out in a sample sentence, and the system generates distractors from similar words.

This tool is designed for teachers, language learners, and test prep.

---

## ✅ Features

- **Upload wordlists**: Supports CSV/Excel  
- **Customizable question count**  
- **PDF export**: Separate test and answer sheets  
- **Reproducible randomness** with `--seed`  
- **Question type**: four-choice cloze multiple-choice questions  
- **Smart distractors**: selects words of similar part of speech or user-defined distractors  
- **Simple interface**: CLI support, optional web/GUI if enabled  

---

## 🗂️ Wordlist Format

Minimum recommended columns (CSV/Excel):

| column        | description                                | example                        |
|---------------|--------------------------------------------|--------------------------------|
| `word`        | target vocabulary word                     | `meticulous`                   |
| `pos`         | part of speech (optional but recommended)  | `adj.`                         |
| `meaning`     | meaning or definition                      | `very careful and precise`      |
| `example`     | sentence containing the word               | `She is a meticulous planner.` |
| `distractors` | optional, custom distractors (`;` separated) | `careless;casual;sloppy`      |
| `tag`         | optional, unit/lesson label                | `B2-Unit5`                     |

If no distractors are given, the system will automatically generate them.

---

## ⚙️ Installation

```bash
# 1) Create and activate a virtual environment
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

# 2) Install dependencies
pip install -r requirements.txt
```

---

## 🚀 Quick Start

### A) Command Line (CLI)

```bash
python main.py \
  --input data/wordlist.xlsx \        # wordlist (CSV/Excel)
  --sheet Words \                     # Excel sheet name (if applicable)
  --count 50 \                        # number of questions
  --seed 42 \                         # random seed (reproducible)
  --output out/test_paper.pdf \       # test PDF
  --answer out/test_answer.pdf \      # answer PDF
  --mode cloze                         # question type (cloze)
```

Common options:
- `--input`: wordlist path (.csv/.xlsx)  
- `--sheet`: sheet name (Excel only)  
- `--count`: number of questions  
- `--seed`: random seed  
- `--output`: test PDF file  
- `--answer`: answer PDF file  
- `--mode`: question type (`cloze`)  

### B) Web/GUI (optional)

```bash
streamlit run app.py
```

---

## 🧠 Question & Option Logic

- **Blanking strategy**: replaces the target word in `example` with a blank (e.g. `_____`)  
- **Options**: 1 correct + 3 distractors  
  - Priority: same part of speech → same tag → global pool  
  - If `distractors` column exists, it is used first  
- **Randomness**: controlled by `--seed`  
- **No duplicates**: avoids repeated questions or identical option sets in one test  

---

## 📄 PDF Samples

- `test_paper.pdf`: exam sheet (questions only)  
- `test_answer.pdf`: answer sheet (with correct answers, optionally with meanings)  

---

## 🔧 Configuration (Optional)

`config.yaml` example:

```yaml
seed: 42
mode: cloze
count: 50
distractors:
  source_priority: ["same_pos", "same_tag", "global"]
  same_pos_ratio: 0.7
  allow_duplicates: false
pdf:
  font: "NotoSerifCJK"
  show_meaning_on_answer_sheet: true
filters:
  include_tags: ["B2-Unit5"]
  exclude_words: []
```

---

## 🛣️ Roadmap

- [ ] More question types (synonym match, definition match)  
- [ ] Advanced distractor strategies (phonetic, morphological)  
- [ ] Adaptive difficulty (CAT)  
- [ ] Better GUI and cloud deployment  
- [ ] Additional export formats (DOCX, Excel answer sheets)  

---

## 🤝 Contributing

1. Fork this repo & create a feature branch (`feat/...` or `fix/...`)  
2. Add/update tests  
3. Submit a PR with description of changes  

---

## 📜 License

This project is licensed under the **MIT License**. See [`LICENSE`](./LICENSE) for details.

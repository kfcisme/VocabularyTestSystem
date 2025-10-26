import os
import json
import time
import random
import requests
import pandas as pd
from bs4 import BeautifulSoup
import nltk
from nltk.corpus import wordnet as wn
from fpdf import FPDF
from typing import List, Dict, Tuple

# Settings 
EXCEL_PATH = r"C:\\path_to_csv\\voc.csv" 
NUM_QUESTIONS = 10           
UNIT = "voc"
QUIZ_PDF = f"quiz_questions_{UNIT}.pdf"
ANSWER_PDF = f"quiz_answers_{UNIT}.pdf"

SENT_CACHE_JSON = f"sentence_cache_{UNIT}.json"

SIM_MIN = 0.15
SIM_MAX = 0.65
CANDIDATE_POOL_TOPK = 30
CHOICES_PER_QUESTION = 4

REQ_TIMEOUT = 5
REQ_RETRY = 2
REQ_SLEEP_BETWEEN = (0.6, 1.2)


def load_cache(path: str) -> dict:
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_cache(path: str, data: dict):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def guess_wn_pos(word: str):
    syns = wn.synsets(word)
    if not syns:
        return None
    pos_counts = {}
    for s in syns:
        pos = s.pos()
        if pos == "s":
            pos = "a"
        pos_counts[pos] = pos_counts.get(pos, 0) + 1
    if not pos_counts:
        return None
    return max(pos_counts, key=pos_counts.get)

def wn_similarity(w1: str, w2: str) -> float:
    syns1 = wn.synsets(w1)
    syns2 = wn.synsets(w2)
    if not syns1 or not syns2:
        return 0.0
    best = 0.0
    for s1 in syns1[:4]:
        for s2 in syns2[:4]:
            sim = s1.path_similarity(s2)
            if sim is not None and sim > best:
                best = sim
    return float(best)


def cambridge_examples(word: str) -> List[str]:
    url = f"https://dictionary.cambridge.org/dictionary/english/{word}"
    headers = {"User-Agent": "Mozilla/5.0", "Accept-Language": "en-US,en;q=0.8"}
    examples: List[str] = []
    for _ in range(REQ_RETRY + 1):
        try:
            r = requests.get(url, headers=headers, timeout=REQ_TIMEOUT)
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}")
            soup = BeautifulSoup(r.text, "html.parser")
            nodes = soup.select("div.examp.dexamp, span.eg, div.deg")
            for n in nodes:
                t = n.get_text(" ", strip=True)
                if t and len(t.split()) >= 5 and t[-1] in ".?!":
                    examples.append(t)
            if examples:
                break
        except Exception:
            time.sleep(random.uniform(*REQ_SLEEP_BETWEEN))
    return examples

import re

def clean_sentence(s: str) -> str:
    if not s:
        return ""
    for _ in range(3):
        s = re.sub(r"\([^()]*\)", " ", s)       
        s = re.sub(r"\[[^\[\]]*\]", " ", s)    
        s = re.sub(r"\{[^{}]*\}", " ", s)     
        s = re.sub(r"（[^（）]*）", " ", s)      
        s = re.sub(r"［[^［］]*］", " ", s)        
    s = re.sub(r"\bUS\b|\bUK\b", " ", s, flags=re.I)
    s = re.sub(r"\(=.+?\)", " ", s)            
    s = re.sub(r"[–—-]\s*[A-Za-z].*$", "", s)   
    s = s.replace(" 3-D", " 3D")              
    s = re.sub(r"\s+", " ", s).strip()
    return s

def is_good_sentence(word: str, s: str) -> bool:
    if not s:
        return False
    s_clean = clean_sentence(s)

    if not re.search(r"[.?!]$", s_clean):
        return False
    if len(s_clean.split()) < 6 or len(s_clean.split()) > 35:
        return False
    tokens = re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", s_clean)
    if not tokens:
        return False
    if tokens[0].lower() == word.lower():
        return False

    if not re.search(rf"\b{re.escape(word)}\b", s_clean, flags=re.I):
        return False

    if re.search(r"\b(means|meaning|be defined as|is called|i\.e\.|e\.g\.)\b", s_clean, flags=re.I):
        return False
    if "(=" in s or " = " in s:
        return False

    if re.search(r"\b\d+\b", s_clean) and len(re.findall(r"\b\d+\b", s_clean)) >= 2:
        return False

    return True

def wordnet_examples(word: str) -> List[str]:
    out: List[str] = []
    for s in wn.synsets(word):
        out.extend(s.examples())
    out = [e.strip() for e in out if e and len(e.split()) >= 5 and e[-1] in ".?!"]
    return list(dict.fromkeys(out))

def local_fallback_sentence(word: str) -> str:
    templates = [
        f"This question highlights how to use the word '{word}' in a sentence.",
        f"Please choose the best option that fits the blank with '{word}'.",
        f"In this sentence, the correct word is '{word}', but it has been removed.",
    ]
    return random.choice(templates)

def pick_sentence_for_word(word: str, cache: dict) -> str:
    key = word.lower()
    if key in cache and cache[key]:
        if is_good_sentence(word, cache[key]):
            return cache[key]

    chosen = None
    exs = cambridge_examples(word)
    cleaned = [clean_sentence(e) for e in exs]
    cand = [s for s in cleaned if is_good_sentence(word, s)]
    if cand:
        chosen = cand[0]

    if not chosen:
        wn_ex = wordnet_examples(word)
        wn_clean = [clean_sentence(e) for e in wn_ex]
        cand2 = [s for s in wn_clean if is_good_sentence(word, s)]
        if cand2:
            chosen = cand2[0]

    if not chosen:
        chosen = clean_sentence(local_fallback_sentence(word))

    cache[key] = chosen
    return chosen


def mask_word_in_sentence(sentence: str, word: str) -> str:
    import re
    s = sentence
    pattern = re.compile(rf"\b{re.escape(word)}\b", flags=re.IGNORECASE)
    s = pattern.sub("_____", s, count=1)
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\s+([,;:.?!])", r"\1", s)
    return s



def build_pos_buckets(vocab_list: List[str]) -> Dict[str, List[str]]:
    buckets: Dict[str, List[str]] = {"n": [], "v": [], "a": [], "r": []}
    for w in vocab_list:
        pos = guess_wn_pos(w)
        if pos in buckets:
            buckets[pos].append(w)
    return buckets

def choose_distractors(target: str, vocab_list: List[str], pos_buckets: Dict[str, List[str]]) -> List[str]:
    distractors: List[str] = []
    used = {target}

    tgt_pos = guess_wn_pos(target)
    candidates: List[str] = []
    if tgt_pos and pos_buckets.get(tgt_pos):
        candidates = [w for w in pos_buckets[tgt_pos] if w not in used]
    if len(candidates) < (CHOICES_PER_QUESTION - 1):
        pool = [w for w in vocab_list if w not in used]
        seen = set(candidates)
        for w in pool:
            if w not in seen:
                candidates.append(w)
                seen.add(w)

    scored = []
    for w in candidates:
        sim = wn_similarity(target, w)
        if SIM_MIN <= sim <= SIM_MAX:
            scored.append((sim, w))
    scored.sort(key=lambda x: x[0], reverse=True)

    pool = [w for _, w in scored[:CANDIDATE_POOL_TOPK]]

    if len(pool) < (CHOICES_PER_QUESTION - 1):
        loose: List[str] = []
        for w in candidates:
            if w in pool:
                continue
            sim = wn_similarity(target, w)
            if sim > 0.0 and w not in loose:
                loose.append(w)
        pool = list(dict.fromkeys(pool + loose))

    if len(pool) < (CHOICES_PER_QUESTION - 1):
        remain = [w for w in vocab_list if w not in used and w not in pool]
        random.shuffle(remain)
        pool += remain

    random.shuffle(pool)
    for w in pool:
        if len(distractors) >= (CHOICES_PER_QUESTION - 1):
            break
        if w not in used:
            distractors.append(w)
            used.add(w)
    return distractors


def generate_question(word: str, vocab_list: List[str], pos_buckets: Dict[str, List[str]], sent_cache: dict):
    sentence = pick_sentence_for_word(word, sent_cache)
    question = mask_word_in_sentence(sentence, word)  
    distractors = choose_distractors(word, vocab_list, pos_buckets)
    choices = [word] + distractors
    random.shuffle(choices)
    answer = "ABCD"[choices.index(word)]
    return {"word": word, "question": question, "choices": choices, "answer": answer}

def generate_quiz(vocab_list: List[str], num_questions: int):
    sent_cache = load_cache(SENT_CACHE_JSON)
    pos_buckets = build_pos_buckets(vocab_list)
    selected_words = random.sample(vocab_list, min(num_questions, len(vocab_list)))
    data = [generate_question(w, vocab_list, pos_buckets, sent_cache) for w in selected_words]
    save_cache(SENT_CACHE_JSON, sent_cache)
    return data


def _extract_en_from_cell(cell_text: str) -> str:
    import re
    s = str(cell_text).strip()
    if not s:
        return ""
    s = re.sub(r'^\s*\d+\s*[.)、-]\s*', '', s) 
    m = re.match(r'^([A-Za-z][A-Za-z\-]*)', s)
    if m:
        return m.group(1)
    if '@' in s:
        return s.split('@', 1)[0].strip()
    return s.split(' ', 1)[0].strip()

def load_vocab_and_zh_any(path: str):
    """
    回傳：
      vocab_list: List[str]  # 英文字清單（去重）
      zh_map: Dict[str, str] # 英文 -> 中文（若有中文欄）
    """
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        try:
            df = pd.read_csv(path, encoding="utf-8")
        except UnicodeDecodeError:
            df = pd.read_csv(path, encoding="big5")
    else:
        df = pd.read_excel(path)

    cols = [str(c).strip() for c in df.columns]

    def _find_col(cands):
        for i, c in enumerate(cols):
            for k in cands:
                if c.lower() == k.lower():
                    return i
        return None

    idx_word = _find_col(["單字", "word", "英文", "vocab"])
    idx_zh   = _find_col(["中文", "翻譯", "chinese", "meaning"])
    idx_out  = _find_col(["輸出", "output"])

    vocab_list, zh_map = [], {}

    if idx_word is not None:
        words = df.iloc[:, idx_word].astype(str).fillna("").str.strip().tolist()
        for w in words:
            en = _extract_en_from_cell(w)
            if en:
                vocab_list.append(en)
        if idx_zh is not None:
            zh_col = df.iloc[:, idx_zh].astype(str).fillna("").str.strip().tolist()
            for en, zh in zip(vocab_list, zh_col):
                if zh:
                    zh_map[en] = zh
        elif idx_out is not None:
            out_col = df.iloc[:, idx_out].astype(str).fillna("").str.strip().tolist()
            for en, outv in zip(vocab_list, out_col):
                if any('\u4e00' <= ch <= '\u9fff' for ch in outv):
                    zh_map[en] = outv
    else:
        col0 = df.iloc[:, 0].astype(str).fillna("").str.strip().tolist()
        for cell in col0:
            en = _extract_en_from_cell(cell)
            if en:
                vocab_list.append(en)
        if df.shape[1] >= 2:
            col1 = df.iloc[:, 1].astype(str).fillna("").str.strip().tolist()
            for en, zh in zip(vocab_list, col1):
                if any('\u4e00' <= ch <= '\u9fff' for ch in zh):
                    zh_map[en] = zh

    vocab_list = [w for w in dict.fromkeys(vocab_list) if w]  
    return vocab_list, zh_map


def export_to_pdf(data, quiz_pdf, answer_pdf):
    pdf_q = FPDF()
    pdf_q.set_auto_page_break(auto=True, margin=15)
    pdf_q.add_page()
    pdf_q.set_font("Arial", "B", 16)
    pdf_q.cell(0, 10, txt="English Vocabulary Quiz", ln=True, align="C")
    pdf_q.ln(2)
    pdf_q.set_font("Arial", size=12)

    for i, item in enumerate(data, 1):
        question_text = f"{i}) {item['question']}  "
        choices_text  = "   ".join([f"({chr(65+j)}) {opt}" for j, opt in enumerate(item['choices'])])
        pdf_q.multi_cell(0, 8, txt=question_text + choices_text)
    pdf_q.output(quiz_pdf)

    pdf_a = FPDF()
    pdf_a.set_auto_page_break(auto=True, margin=15)
    pdf_a.add_page()
    pdf_a.set_font("Arial", "B", 16)
    pdf_a.cell(0, 10, txt="Answer Sheet", ln=True, align="C")
    pdf_a.ln(2)
    pdf_a.set_font("Arial", size=12)
    for i, item in enumerate(data, 1):
        pdf_a.cell(0, 8, txt=f"{i}) {item['answer']}", ln=True)
    pdf_a.output(answer_pdf)


if __name__ == "__main__":
    vocab_list, zh_map = load_vocab_and_zh_any(EXCEL_PATH)
    if not vocab_list:
        raise SystemExit("No vocabulary loaded. Please check EXCEL_PATH and file format.")

    quiz_data = generate_quiz(vocab_list, NUM_QUESTIONS)
    export_to_pdf(quiz_data, QUIZ_PDF, ANSWER_PDF)

    print(f"PDF generated: {QUIZ_PDF}, {ANSWER_PDF}")

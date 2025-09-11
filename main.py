
import os
import json
import time
import random
import requests
import pandas as pd
from bs4 import BeautifulSoup
import nltk
from nltk.corpus import wordnet as wn

# setting
EXCEL_PATH = "C:\\Users\\hsu96\\Downloads\\AV18.xlsx"
NUM_QUESTIONS = 20
UNIT = "AV18"
QUIZ_PDF = "quiz_questions"+UNIT+".pdf"
ANSWER_PDF = "quiz_answers"+UNIT+".pdf"

# sample
SENT_CACHE_JSON = f"sentence_cache_{UNIT}.json"

# 可調整相似度
SIM_MIN = 0.15
SIM_MAX = 0.65
CANDIDATE_POOL_TOPK = 30
CHOICES_PER_QUESTION = 4

# 爬蟲requirement 設定
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
        if pos == 's':
            pos = 'a'
        pos_counts[pos] = pos_counts.get(pos, 0) + 1
    if not pos_counts:
        return None
    return max(pos_counts, key=pos_counts.get)

def wn_similarity(w1: str, w2: str) -> float:
    """WordNet path_similarity """
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

def cambridge_examples(word: str) -> list[str]:
    """get Cambridge """
    url = f"https://dictionary.cambridge.org/dictionary/english/{word}"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "en-US,en;q=0.8"
    }
    examples = []
    for attempt in range(REQ_RETRY):
        try:
            resp = requests.get(url, headers=headers, timeout=REQ_TIMEOUT)
            if resp.status_code != 200:
                raise RuntimeError(f"HTTP {resp.status_code}")
            soup = BeautifulSoup(resp.text, "html.parser")
            # selector）
            nodes = soup.select("div.examp.dexamp, span.eg, div.deg")
            for n in nodes:
                t = n.get_text(" ", strip=True)
                if t and len(t.split()) >= 5 and t.endswith(('.', '?', '!')):
                    examples.append(t)
            if examples:
                break
        except Exception:
            time.sleep(random.uniform(*REQ_SLEEP_BETWEEN))
    return examples

def wordnet_examples(word: str) -> list[str]:
    out = []
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
    if key in cache:
        return cache[key]

    # Cambridge
    exs = cambridge_examples(word)
    good = []
    for s in exs:
        low = s.lower()
        if word.lower() in low and not low.startswith(word.lower()):
            good.append(s)
    chosen = (good[0] if good else (exs[0] if exs else None))

    # WordNet
    if not chosen:
        wn_ex = wordnet_examples(word)
        if wn_ex:
            chosen = wn_ex[0]

    # Local template
    if not chosen:
        chosen = local_fallback_sentence(word)

    cache[key] = chosen
    return chosen

def mask_word_in_sentence(sentence: str, word: str) -> str:
    import re
    pattern = re.compile(rf"\b{re.escape(word)}\b", flags=re.IGNORECASE)
    return pattern.sub("_____", sentence, count=1)

def build_pos_buckets(vocab_list: list[str]) -> dict:
    buckets = {"n": [], "v": [], "a": [], "r": []}
    for w in vocab_list:
        pos = guess_wn_pos(w)
        if pos in buckets:
            buckets[pos].append(w)
    return buckets

def choose_distractors(target: str, vocab_list: list[str], pos_buckets: dict) -> list[str]:
    distractors = []
    used = {target}

    tgt_pos = guess_wn_pos(target)
    candidates = []
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
        loose = []
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

def generate_question(word: str, vocab_list: list[str], pos_buckets: dict, sent_cache: dict):
    sentence = pick_sentence_for_word(word, sent_cache)
    question = mask_word_in_sentence(sentence, word)

    distractors = choose_distractors(word, vocab_list, pos_buckets)
    choices = [word] + distractors
    random.shuffle(choices)
    answer = "ABCD"[choices.index(word)]

    return {
        "word": word,
        "question": question,
        "choices": choices,
        "answer": answer
    }

def generate_quiz(vocab_list: list[str], num_questions: int):
    sent_cache = load_cache(SENT_CACHE_JSON)
    pos_buckets = build_pos_buckets(vocab_list)

    selected_words = random.sample(vocab_list, min(num_questions, len(vocab_list)))
    data = []
    for w in selected_words:
        item = generate_question(w, vocab_list, pos_buckets, sent_cache)
        data.append(item)

    save_cache(SENT_CACHE_JSON, sent_cache)
    return data

from fpdf import FPDF

# output question and ans

def export_to_pdf(data, quiz_pdf, answer_pdf):
    pdf_q = FPDF()
    pdf_q.add_page()
    pdf_q.set_font("Arial", size=12)
    pdf_q.cell(200, 10, txt="English Vocabulary Quiz", ln=True, align="C")

    for i, item in enumerate(data, 1):
        pdf_q.ln()
        pdf_q.multi_cell(0, 10, txt=f"{i}. {item['question']}")
        for j, option in enumerate(item['choices']):
            pdf_q.cell(0, 10, txt=f"   {'ABCD'[j]}. {option}", ln=True)

    pdf_q.output(quiz_pdf)

    pdf_a = FPDF()
    pdf_a.add_page()
    pdf_a.set_font("Arial", size=12)
    pdf_a.cell(200, 10, txt="Answer Sheet", ln=True, align="C")
    pdf_a.ln()
    for i, item in enumerate(data, 1):
        pdf_a.cell(0, 10, txt=f"{i}. {item['answer']}", ln=True)

    pdf_a.output(answer_pdf)

if __name__ == "__main__":
    df = pd.read_excel(EXCEL_PATH)
    vocab_list = df.iloc[:, 0].dropna().astype(str).str.strip().tolist()
    vocab_list = [w for w in dict.fromkeys(vocab_list) if w]

    quiz_data = generate_quiz(vocab_list, NUM_QUESTIONS)
    export_to_pdf(quiz_data, QUIZ_PDF, ANSWER_PDF)
    print(f"PDF generated: {QUIZ_PDF}, {ANSWER_PDF}")

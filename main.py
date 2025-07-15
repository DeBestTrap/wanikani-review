from __future__ import annotations

import sys
import streamlit as st
from google import genai
from google.genai import types
from dotenv import load_dotenv
from typing import List, Tuple

from wanikani import get_vocab


def gen_chunks(prompt: str):
    global thought_box

    def finish_thinking():
        global thought_box
        if not thoughts_folded:
            thought_box.empty()
            thought_box = st.expander(expanded=False, label="Open for thoughts")
            thought_box.markdown(thoughts)  # live-update the side box

    params = {
        "model": model_name,
        "contents": prompt,
        "config": types.GenerateContentConfig(
            temperature=0.7,
            max_output_tokens=16384,
            thinking_config=types.ThinkingConfig(include_thoughts=True),
        ),
    }
    answer = ""
    thoughts = ""
    thoughts_folded = False

    # Each iteration yields a `GenerateContentResponse`
    for chunk in client.models.generate_content_stream(**params):
        for cand in chunk.candidates or []:
            if cand.content is None or cand.content.parts is None:
                continue
            for part in cand.content.parts:
                text = getattr(part, "text", "")
                if not text:
                    continue
                if part.thought:  # stream **thought summaries**
                    thoughts += str(text)
                    thought_box.markdown(thoughts)
                else:  # normal answer token → yield
                    finish_thinking()
                    thoughts_folded = True
                    answer += str(text)
                    yield text
    print(answer)


st.set_page_config(page_title="WaniKani Review", layout="wide")
st.set_page_config(layout="wide")

if "genai_client" not in st.session_state:
    load_dotenv()
    st.session_state.genai_client = genai.Client()
client = st.session_state.genai_client

prompt = "Here are sentences I wrote for words in Japanese, can you nitpick what I did wrong and provide an example sentence of the correct usage and grammar?"
model_name = "gemini-2.5-flash"

# Get the wanikani vocab from recent reviews
try:
    vocab = get_vocab(minutes=1440)
except Exception as e:
    print(e, file=sys.stderr)
    vocab = []

# Create the text that is presented to the user.
input_text = "\n\n\n".join(vocab)

# UI for links to vocab
vocab_links = []
for word in vocab:
    vocab_links.append(f"[{word}](https://wanikani.com/vocabulary/{word})")
vocab_box = st.expander(expanded=False, label="Vocab Links")
vocab_box.markdown("、　".join(vocab_links))

# UI for text input and the markdown preview of the input.
col1, col2 = st.columns(2)
with col1:
    input_text = st.text_area(
        "Write sentences for the words here.", value=input_text, height=700
    )
    go = st.button("Generate", type="primary", use_container_width=True)
with col2:
    st.markdown(input_text)

# Gemini output below the input
thought_box = st.empty()
if go and input_text.strip():
    input = f"{prompt}\n{input_text}"
    print(input)
    st.write_stream(gen_chunks(input))

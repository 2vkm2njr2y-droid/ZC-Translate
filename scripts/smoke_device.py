import json
import sys
import time

import openvino_genai as g

DEVICE = sys.argv[1] if len(sys.argv) > 1 else "CPU"
MODEL = sys.argv[2] if len(sys.argv) > 2 else r"models\hymt2-1.8b\ov-int4"
t0 = time.perf_counter()
pipe = g.LLMPipeline(MODEL, DEVICE)
load_ms = round((time.perf_counter() - t0) * 1000, 1)
tok = pipe.get_tokenizer()
msgs = [{"role": "user", "content": "将以下文本翻译为日语，注意只需要输出翻译后的结果，不要额外解释：\n\n今天天气真好。"}]
prompt = tok.apply_chat_template(msgs, add_generation_prompt=True)
cfg = g.GenerationConfig()
cfg.max_new_tokens = 64
cfg.do_sample = False
cfg.apply_chat_template = False
cfg.repetition_penalty = 1.05
chunks = []
t1 = time.perf_counter()
res = pipe.generate(prompt, cfg, lambda s: chunks.append(s) or False)
gen_ms = round((time.perf_counter() - t1) * 1000, 1)
text = "".join(chunks) or (res if isinstance(res, str) else "")
try:
    encoded = tok.encode(text)
    tokens = int(encoded.shape[-1])
except Exception:
    tokens = max(1, len(text) // 2)
out = {
    "device": DEVICE,
    "model": MODEL,
    "load_ms": load_ms,
    "gen_ms": gen_ms,
    "tokens": tokens,
    "tok_s": round(tokens / (gen_ms / 1000), 2) if gen_ms else 0,
    "text": text,
}
open(f"data/smoke-{DEVICE.lower()}.json", "w", encoding="utf-8").write(
    json.dumps(out, ensure_ascii=False, indent=2)
)
print(json.dumps(out, ensure_ascii=True, indent=2))

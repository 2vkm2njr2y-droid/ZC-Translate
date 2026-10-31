import json
import time

import openvino_genai as g

MODEL = r"models\hymt2-1.8b\ov-int4-npu"
pipe = g.LLMPipeline(MODEL, "NPU")
tok = pipe.get_tokenizer()
source = "会議の資料は昨日のうちに全員に送っておきました。"
prompts = {
    "zh_greedy": f"将以下文本翻译为中文，注意只需要输出翻译后的结果，不要额外解释：\n\n{source}",
    "zh_sampling": f"将以下文本翻译为中文，注意只需要输出翻译后的结果，不要额外解释：\n\n{source}",
    "en_greedy": f"Translate the following text into Chinese. Note that you should only output the translated result without any additional explanation:\n\n{source}",
    "zh_natural": f"将以下文本翻译为地道、自然的简体中文，注意只需要输出翻译后的结果，不要额外解释：\n\n{source}",
}
results = {}
for name, prompt in prompts.items():
    messages = [{"role": "user", "content": prompt}]
    templated = tok.apply_chat_template(messages, add_generation_prompt=True)
    cfg = g.GenerationConfig()
    cfg.max_new_tokens = 96
    cfg.repetition_penalty = 1.05
    cfg.apply_chat_template = False
    if name == "zh_sampling":
        cfg.do_sample = True
        cfg.temperature = 0.7
        cfg.top_p = 0.6
        cfg.top_k = 20
    else:
        cfg.do_sample = False
    chunks = []
    t0 = time.perf_counter()
    res = pipe.generate(templated, cfg, lambda s, chunks=chunks: chunks.append(s) or False)
    text = "".join(chunks) or (res if isinstance(res, str) else "")
    encoded = tok.encode(text)
    tensor = getattr(encoded, "input_ids", encoded)
    results[name] = {
        "text": text,
        "ms": round((time.perf_counter() - t0) * 1000, 1),
        "tokens": int(tensor.shape[-1]) if getattr(tensor, "shape", None) else 0,
    }
open("data/quality-probe-ja.json", "w", encoding="utf-8").write(
    json.dumps({"source": source, "results": results}, ensure_ascii=False, indent=2)
)
print(json.dumps({k: v["text"] for k, v in results.items()}, ensure_ascii=True, indent=2))

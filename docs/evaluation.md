# 准确率评测（首版）

- 数据集：`tests/fixtures/golden`，6 方向 × 8 句 = 48 句。
- 覆盖：日常、商务、新闻、技术、产品、UI 文案。
- 指标：chrF++（字符级，仅作回归参考）；最终以人工抽样复核为准。
- 详细抽样：[balanced](evaluation-balanced.md)、[quality](evaluation-quality.md)。

| 方向 | 1.8B / NPU | 7B / GPU | 提升 |
|---|---:|---:|---:|
| zh→ja | 53.22 | 58.75 | +5.53 |
| zh→en | 79.28 | 87.24 | +7.96 |
| ja→zh | 46.46 | 57.51 | +11.05 |
| ja→en | 66.15 | 81.86 | +15.71 |
| en→zh | 52.46 | 55.25 | +2.79 |
| en→ja | 49.67 | 66.06 | +16.39 |
| **平均** | **57.87** | **67.78** | **+9.91** |

## 结论

- 7B 在六个方向全面优于 1.8B，ja→en / en→ja / ja→zh 提升最明显。
- 1.8B 在 48 句抽样中主要问题：个别技术术语（如 cache directory → キャッシュディレクション）、少量漏译（来週/経費精算）和日语敬语/措辞不自然。
- 7B 抽样中未发现重大错译；个别措辞仍需润色（例如 en→ja 的「今午後」、経費報告書 vs 経費精算書）。
- 术语库对 1.8B 的术语问题非常有效：实测 `cache directory → キャッシュディレクトリ` 等术语可稳定命中，且译后校验无告警。
- 因此产品默认使用 1.8B + NPU（速度/功耗），需要更高准确率时切换到 7B + GPU。金标集后续应扩充到 150 句以上，并加入 COMET 等语义指标。

## 复现

```powershell
.\.venv-runtime\Scripts\python.exe scripts\evaluate.py --profile balanced --device NPU
.\.venv-runtime\Scripts\python.exe scripts\evaluate.py --profile quality --device GPU
```
